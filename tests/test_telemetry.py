"""Exercise real Langfuse serialization and LangGraph context propagation offline."""
import json
import socket
import threading
from uuid import uuid4

import httpx
import pytest
from langfuse import Langfuse
from langgraph.graph import END, START, StateGraph
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from support import MemoryRuns, config
from telemetry import Telemetry
from workflow import build_graph


@pytest.fixture
def tracing(monkeypatch):
    """No global provider or actual exporter, and fail on accidental networking."""
    clients = []
    providers = []
    network_attempts = []

    def deny_network(*args, **kwargs):
        network_attempts.append(True)
        raise AssertionError('Telemetry tests must not open network connections')

    monkeypatch.setattr(socket.socket, 'connect', deny_network)

    def make(capture_content=False, exporter=None):
        exporter = exporter if exporter is not None else InMemorySpanExporter()
        provider = TracerProvider()
        client = Langfuse(
            # Resource managers are keyed by public key: isolate each test client.
            public_key='pk-lf-offline-' + str(uuid4()),
            secret_key='sk-lf-offline-test',
            base_url='https://telemetry.invalid',
            tracer_provider=provider,
            span_exporter=exporter,
            flush_at=512,
            flush_interval=3600,
            sample_rate=1.0,
        )
        clients.append(client)
        providers.append(provider)
        return Telemetry(client, capture_content), client, exporter

    yield make
    for client in clients:
        client.shutdown()
    for provider in providers:
        provider.shutdown()
    assert not network_attempts


def traced_runs(telemetry, mode='openai-compatible'):
    cfg = config()
    cfg.mode = mode
    cfg.model = 'requested-gateway-model'
    cfg.model_key = 'gateway-secret-do-not-record'
    runs = MemoryRuns(cfg)
    runs.telemetry = telemetry
    runs.graph = build_graph(runs.saver, cfg, telemetry)
    return runs


def fake_gateway(monkeypatch, content='Private generated answer'):
    calls = []

    def post(client, url, **kwargs):
        calls.append((threading.get_ident(), url, kwargs))
        return httpx.Response(
            200,
            request=httpx.Request('POST', url),
            json={
                'model': 'resolved-gateway-model',
                'choices': [{'message': {'content': content}}],
                'usage': {'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10},
            },
        )

    monkeypatch.setattr(httpx.Client, 'post', post)
    return calls


def finished(client, exporter):
    client.flush()
    return exporter.get_finished_spans()


def test_graph_threadpool_preserves_root_parent_session_and_response_trace_id(tracing, monkeypatch):
    telemetry, client, exporter = tracing()
    runs = traced_runs(telemetry)
    calls = fake_gateway(monkeypatch)
    original_compile = StateGraph.compile

    def compile_parallel(builder, *args, **kwargs):
        # A second runnable node forces LangGraph's own executor path; the
        # ordinary one-node graph can run inline and would miss this regression.
        builder.add_node('parallel_probe', lambda state: {})
        builder.add_edge(START, 'parallel_probe')
        builder.add_edge('parallel_probe', END)
        return original_compile(builder, *args, **kwargs)

    monkeypatch.setattr(StateGraph, 'compile', compile_parallel)
    runs.graph = build_graph(runs.saver, runs.cfg, telemetry)
    invoking_thread = threading.get_ident()
    result = runs.create('Private user request')
    spans = {span.name: span for span in finished(client, exporter)}
    assert result['status'] == 'awaiting_review'
    assert len(calls) == 1
    assert calls[0][0] != invoking_thread
    assert set(spans) == {'langgraph.run', 'gateway.chat'}
    root, generation = spans['langgraph.run'], spans['gateway.chat']
    assert root.parent is None
    assert generation.parent.span_id == root.context.span_id
    assert generation.context.trace_id == root.context.trace_id
    assert result['trace_id'] == format(root.context.trace_id, '032x')
    assert root.attributes['session.id'] == result['id']
    assert generation.attributes['session.id'] == result['id']
    assert generation.attributes['langfuse.observation.type'] == 'generation'
    assert generation.attributes['langfuse.observation.model.name'] == 'resolved-gateway-model'
    assert json.loads(generation.attributes['langfuse.observation.usage_details']) == {'input': 7, 'output': 3}


@pytest.mark.parametrize('capture_content', [False, True])
def test_prompt_and_response_capture_requires_opt_in(tracing, monkeypatch, capture_content):
    telemetry, client, exporter = tracing(capture_content)
    runs = traced_runs(telemetry)
    calls = fake_gateway(monkeypatch)
    result = runs.create('Private user request')
    spans = {span.name: span for span in finished(client, exporter)}
    root, generation = spans['langgraph.run'], spans['gateway.chat']
    serialized = str([dict(span.attributes) for span in spans.values()])
    assert len(calls) == 1
    assert 'gateway-secret-do-not-record' not in serialized
    assert ('Private user request' in serialized) is capture_content
    assert ('Private generated answer' in serialized) is capture_content
    if capture_content:
        assert json.loads(root.attributes['langfuse.observation.input'])['request'] == 'Private user request'
        assert json.loads(root.attributes['langfuse.observation.output'])['draft'] == result['draft']
        assert json.loads(generation.attributes['langfuse.observation.input'])[1]['content'] == 'Private user request'
        assert generation.attributes['langfuse.observation.output'] == 'Private generated answer'
    else:
        assert 'draft' not in json.loads(root.attributes['langfuse.observation.output'])
        assert 'langfuse.observation.input' not in root.attributes
        assert 'langfuse.observation.input' not in generation.attributes
        assert 'langfuse.observation.output' not in generation.attributes
    assert json.loads(root.attributes['langfuse.observation.output'])['status'] == result['status']


def test_provider_exception_is_sanitized_in_spans_logs_and_response(tracing, monkeypatch, caplog):
    telemetry, client, exporter = tracing()
    runs = traced_runs(telemetry)
    calls = []
    secret = 'secret-provider-body-and-credential'

    def fail(*args, **kwargs):
        calls.append(True)
        raise RuntimeError('https://user:' + secret + '@provider.invalid/private-prompt')

    monkeypatch.setattr(httpx.Client, 'post', fail)
    result = runs.create('A request')
    spans = finished(client, exporter)
    assert len(calls) == 1
    assert result['status'] == 'needs_continue'
    assert 'error' in result
    assert secret not in str(result) + caplog.text
    assert {span.name for span in spans} == {'langgraph.run', 'gateway.chat'}
    for span in spans:
        assert span.attributes['langfuse.observation.level'] == 'ERROR'
        assert span.attributes['langfuse.observation.status_message'] == 'RuntimeError'
        assert secret not in str(dict(span.attributes)) + str(span.events)
        assert not span.events  # SDK must not attach raw exception/stack events.


def test_mock_mode_produces_run_span_without_a_generation(tracing, monkeypatch):
    telemetry, client, exporter = tracing()
    runs = traced_runs(telemetry, mode='mock')
    calls = fake_gateway(monkeypatch)
    result = runs.create('Mock request')
    spans = finished(client, exporter)
    assert not calls
    assert result['status'] == 'awaiting_review'
    assert [span.name for span in spans] == ['langgraph.run']
    assert spans[0].attributes['session.id'] == result['id']
    assert result['trace_id'] == format(spans[0].context.trace_id, '032x')


class FailingExporter(SpanExporter):
    def __init__(self, raises):
        self.raises = raises
        self.attempts = 0

    def export(self, spans):
        self.attempts += 1
        if self.raises:
            raise RuntimeError('Offline telemetry export failure')
        return SpanExportResult.FAILURE

    def shutdown(self):
        pass


@pytest.mark.parametrize('raises', [False, True])
def test_sdk_exporter_failure_does_not_retry_model_or_change_checkpoint(tracing, monkeypatch, raises):
    exporter = FailingExporter(raises)
    telemetry, client, _ = tracing(exporter=exporter)
    runs = traced_runs(telemetry)
    calls = fake_gateway(monkeypatch)
    result = runs.create('A request')
    client.flush()
    assert exporter.attempts >= 1
    assert len(calls) == 1
    assert result['status'] == 'awaiting_review'
    assert result['revision'] == 1
    assert 'error' not in result
    assert runs.view(result['id'])['checkpoint'] == result['checkpoint']
    approved = runs.execute(result['id'], 'approve', checkpoint=result['checkpoint'])
    client.flush()
    assert len(calls) == 1
    assert approved['status'] == 'completed'
