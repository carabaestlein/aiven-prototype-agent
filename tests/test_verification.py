from argparse import Namespace
import json
from uuid import uuid4

import httpx
import pytest

from scripts import verify_deployment as verify


TRACE = 'a' * 32


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


def row(trace=TRACE, session='run', generation=False):
    return {'traceId': trace, 'sessionId': session, 'type': 'GENERATION' if generation else 'SPAN',
            'name': 'gateway.chat' if generation else 'langgraph.run', 'endTime': '2026-10-16T12:00:00Z',
            'model': 'resolved-router-model' if generation else None,
            'metadata': {'requested_model': 'configured-model'}, 'level': 'DEFAULT'}


def poll(client, generation=True, **kwargs):
    clock = Clock()
    verify.verify_trace(client, TRACE, 'run', '2026-10-16T11:59:00Z', generation,
                        'configured-model', timeout=4, interval=1,
                        monotonic=clock.monotonic, sleep=clock.sleep, **kwargs)
    return clock


def test_v2_trace_polling_waits_for_worker_and_reads_all_pages():
    requests = []

    def transport(request):
        requests.append(request)
        assert request.url.path == '/api/public/v2/observations'
        assert request.url.params['traceId'] == TRACE
        assert request.url.params['fromStartTime'] and request.url.params['toStartTime']
        assert request.url.params['fields'] == 'core,basic,model,metadata'
        if len(requests) == 1:
            return httpx.Response(200, json={'data': [], 'meta': {}})
        if 'cursor' not in request.url.params:
            return httpx.Response(200, json={'data': [row()], 'meta': {'cursor': 'page-two'}})
        return httpx.Response(200, json={'data': [row(generation=True)], 'meta': {'cursor': None}})

    with httpx.Client(base_url='https://langfuse.test', transport=httpx.MockTransport(transport)) as client:
        clock = poll(client)
    assert len(requests) == 3 and clock.now == 1


def test_approval_waits_for_late_generation_and_rejects_it():
    calls = []

    def transport(request):
        calls.append(request)
        data = [row()] if len(calls) < 3 else [row(), row(generation=True)]
        return httpx.Response(200, json={'data': data})

    with httpx.Client(base_url='https://langfuse.test', transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(verify.VerificationError, match='unexpectedly recorded'):
            poll(client, generation=False)
    assert len(calls) == 3


def test_approval_without_generation_is_observed_for_entire_window():
    with httpx.Client(base_url='https://langfuse.test', transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={'data': [row()]}))) as client:
        clock = poll(client, generation=False)
    assert clock.now == 4


def test_approval_final_partial_interval_does_not_begin_expiring_read():
    clock = Clock()
    budgets = []

    def transport(request):
        budget = request.extensions['timeout']['read']
        budgets.append(budget)
        # Successful requests take some time. The old loop made one extra
        # request with only 0.4 seconds left, timed out and erased its success.
        if budget < 0.5:
            clock.now += budget
            raise httpx.ReadTimeout('Synthetic end-of-window timeout', request=request)
        clock.now += 0.2
        return httpx.Response(200, json={'data': [row()]})

    with httpx.Client(base_url='https://langfuse.test', transport=httpx.MockTransport(transport)) as client:
        verify.verify_trace(client, TRACE, 'run', '2026-10-16T11:59:00Z', False,
                            'configured-model', timeout=4, interval=1,
                            monotonic=clock.monotonic, sleep=clock.sleep)
    assert len(budgets) == 3 and all(budget >= 1 for budget in budgets)
    assert clock.now == 4


def test_approval_fails_if_reads_remain_unavailable_after_initial_success():
    clock = Clock()
    calls = []

    def transport(request):
        calls.append(request)
        clock.now += 0.2
        if len(calls) == 1:
            return httpx.Response(200, json={'data': [row()]})
        return httpx.Response(503)

    with httpx.Client(base_url='https://langfuse.test', transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(verify.VerificationError, match='timed out'):
            verify.verify_trace(client, TRACE, 'run', '2026-10-16T11:59:00Z', False,
                                'configured-model', timeout=4, interval=1,
                                monotonic=clock.monotonic, sleep=clock.sleep)
    assert len(calls) == 3 and clock.now == 4


@pytest.mark.parametrize('bad_row,diagnostic', [
    (row(session='another-run'), 'session'),
    (dict(row(), level='ERROR'), 'error observation'),
    (dict(row(), traceId='b' * 32), 'another trace'),
    (dict(row(generation=True), metadata={'requested_model': 'wrong'}), 'different model'),
])
def test_trace_mismatch_or_error_never_passes(bad_row, diagnostic):
    with httpx.Client(base_url='https://langfuse.test', transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={'data': [row(), bad_row]}))) as client:
        with pytest.raises(verify.VerificationError, match=diagnostic):
            poll(client)


def test_trace_timeout_is_bounded_and_failure_body_is_not_exposed():
    with httpx.Client(base_url='https://langfuse.test', transport=httpx.MockTransport(
            lambda _: httpx.Response(503, text='secret-key-value'))) as client:
        with pytest.raises(verify.VerificationError, match='timed out') as error:
            poll(client)
    assert 'secret-key-value' not in str(error.value)
    with httpx.Client(base_url='https://app.test', transport=httpx.MockTransport(
            lambda _: httpx.Response(401, text='secret-key-value'))) as client:
        with pytest.raises(verify.VerificationError, match='401') as error:
            verify.request_json(client, 'GET', '/api/session')
    assert 'secret-key-value' not in str(error.value)


def test_redirects_do_not_receive_credentials():
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(307, headers={'Location': 'https://elsewhere.test'})

    with httpx.Client(base_url='https://app.test', headers={'Authorization': 'Bearer secret'},
                      follow_redirects=False, transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(verify.VerificationError, match='redirect'):
            verify.request_json(client, 'GET', '/health/ready')
    assert len(requests) == 1


class Deployment:
    def __init__(self):
        self.run_id = str(uuid4())
        self.current = None
        self.actions = []
        self.traces = {}

    def app(self, request):
        path = request.url.path
        if path == '/health/ready':
            return httpx.Response(200, json={'status': 'ready'})
        if path == '/api/session':
            return httpx.Response(200, json={'mode': 'openai-compatible', 'model': 'configured-model'})
        if request.method == 'GET':
            return httpx.Response(200, json={k: v for k, v in self.current.items() if k != 'trace_id'})
        body = json.loads(request.content)
        action = body.get('action', 'create')
        self.actions.append(action)
        number = len(self.actions)
        target_trace = str(number) * 32
        if action != 'create':
            assert body['checkpoint'] == self.current['checkpoint']
        self.current = {'id': self.run_id, 'status': 'completed' if action == 'approve' else 'awaiting_review',
                        'revision': 1 if action == 'create' else 2, 'mode': 'openai-compatible',
                        'checkpoint': f'checkpoint-{number}', 'draft': 'Draft one' if action == 'create' else 'Draft two',
                        'trace_id': target_trace}
        self.traces[target_trace] = [row(target_trace, self.run_id)]
        if action != 'approve':
            self.traces[target_trace].append(row(target_trace, self.run_id, generation=True))
        return httpx.Response(200, json=self.current)

    def langfuse(self, request):
        return httpx.Response(200, json={'data': self.traces[request.url.params['traceId']]})


def arguments(**kwargs):
    return Namespace(allow_mock=False, expected_model='configured-model', trace_timeout=4,
                     poll_interval=1, restart_confirmed=kwargs.get('restart_confirmed', True))


def fast_traces(monkeypatch):
    original = verify.verify_trace

    def verify_now(*args, **kwargs):
        clock = Clock()
        return original(*args, **kwargs, monotonic=clock.monotonic, sleep=clock.sleep)

    monkeypatch.setattr(verify, 'verify_trace', verify_now)
    return verify_now


def test_start_resume_proves_preserved_checkpoint_and_separate_traces(tmp_path, monkeypatch):
    fast_traces(monkeypatch)
    deployment = Deployment()
    receipt_path = tmp_path / 'receipt.json'
    with httpx.Client(base_url='https://app.test', transport=httpx.MockTransport(deployment.app)) as app:
        with httpx.Client(base_url='https://langfuse.test', transport=httpx.MockTransport(deployment.langfuse)) as langfuse:
            verify.start(app, langfuse, 'https://app.test', receipt_path, arguments())
            saved = json.loads(receipt_path.read_text())
            assert saved['checkpoint'] == 'checkpoint-1'
            assert saved['draft_sha256'] == verify.draft_hash('Draft one')
            assert 'Draft one' not in receipt_path.read_text()
            assert receipt_path.stat().st_mode & 0o777 == 0o600
            verify.resume(app, langfuse, 'https://app.test', receipt_path, arguments())
    saved = json.loads(receipt_path.read_text())
    assert saved['stage'] == 'complete' and saved['operator_confirmed_restart'] is True
    assert saved['checkpoint'] == 'checkpoint-3'
    assert len({saved['trace_id'], saved['revision_trace_id'], saved['approval_trace_id']}) == 3
    assert deployment.actions == ['create', 'revise', 'approve']


def test_resume_requires_restart_confirmation_and_refuses_changed_checkpoint(tmp_path, monkeypatch):
    fast_traces(monkeypatch)
    deployment = Deployment()
    receipt_path = tmp_path / 'receipt.json'
    with httpx.Client(base_url='https://app.test', transport=httpx.MockTransport(deployment.app)) as app:
        with httpx.Client(base_url='https://langfuse.test', transport=httpx.MockTransport(deployment.langfuse)) as langfuse:
            verify.start(app, langfuse, 'https://app.test', receipt_path, arguments())
            with pytest.raises(verify.VerificationError, match='Restart the app'):
                verify.resume(app, langfuse, 'https://app.test', receipt_path, arguments(restart_confirmed=False))
            deployment.current['checkpoint'] = 'unexpected-new-checkpoint'
            with pytest.raises(verify.VerificationError, match='checkpoint changed'):
                verify.resume(app, langfuse, 'https://app.test', receipt_path, arguments())
    assert deployment.actions == ['create']


def test_retry_after_revision_trace_lag_does_not_repeat_model_mutation(tmp_path, monkeypatch):
    verify_now = fast_traces(monkeypatch)
    deployment = Deployment()
    receipt_path = tmp_path / 'receipt.json'
    with httpx.Client(base_url='https://app.test', transport=httpx.MockTransport(deployment.app)) as app:
        with httpx.Client(base_url='https://langfuse.test', transport=httpx.MockTransport(deployment.langfuse)) as langfuse:
            verify.start(app, langfuse, 'https://app.test', receipt_path, arguments())

            def delayed(client, target_trace, *args, **kwargs):
                if target_trace == '2' * 32:
                    raise verify.VerificationError('Trace verification timed out')
                return verify_now(client, target_trace, *args, **kwargs)

            monkeypatch.setattr(verify, 'verify_trace', delayed)
            with pytest.raises(verify.VerificationError, match='timed out'):
                verify.resume(app, langfuse, 'https://app.test', receipt_path, arguments())
            assert json.loads(receipt_path.read_text())['stage'] == 'revised'
            monkeypatch.setattr(verify, 'verify_trace', verify_now)
            verify.resume(app, langfuse, 'https://app.test', receipt_path, arguments())
    assert deployment.actions == ['create', 'revise', 'approve']


@pytest.mark.parametrize('url', ['http://remote.example', 'https://user:password@example.com',
                                'https://example.com?key=secret', 'https://example.com/#secret'])
def test_connection_urls_do_not_allow_credentials_or_remote_cleartext(url):
    with pytest.raises(verify.VerificationError):
        verify.base_url(url, 'APP_URL')


def test_mock_mode_needs_explicit_opt_in():
    def transport(request):
        return httpx.Response(200, json={'status': 'ready'} if request.url.path == '/health/ready' else {'mode': 'mock', 'model': None})

    with httpx.Client(base_url='https://app.test', transport=httpx.MockTransport(transport)) as app:
        with pytest.raises(verify.VerificationError, match='mock mode'):
            verify.check_session(app)
        assert verify.check_session(app, allow_mock=True)['mode'] == 'mock'
