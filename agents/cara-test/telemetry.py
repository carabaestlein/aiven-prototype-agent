"""Optional self-hosted Langfuse spans; telemetry never retries a workflow.

Explicit instrumentation covers each graph invocation and its HTTP model call.
Do not add a LangChain callback alone: this starter calls httpx directly.
"""
from contextlib import contextmanager, ExitStack
import logging

from langfuse import Langfuse, propagate_attributes

log = logging.getLogger(__name__)


class Observation:
    def __init__(self, span=None):
        self.span = span
        self.trace_id = span.trace_id if span is not None else None

    def update(self, **attributes):
        if self.span is not None:
            try:
                self.span.update(**attributes)
            except Exception:
                log.warning('Could not update telemetry observation')


class Telemetry:
    def __init__(self, client=None, capture_content=False):
        self.client = client
        self.capture_content = capture_content

    @classmethod
    def from_settings(cls, cfg):
        if not cfg.langfuse_base:
            return cls()
        # Explicit base_url prevents accidental export to the hosted service.
        client = Langfuse(public_key=cfg.langfuse_public_key, secret_key=cfg.langfuse_secret_key,
                         base_url=cfg.langfuse_base, timeout=5, flush_interval=1,
                         environment=cfg.environment, release=cfg.release or None,
                         sample_rate=1.0)
        return cls(client, cfg.trace_content)

    @contextmanager
    def observation(self, name, *, session_id=None, **attributes):
        if self.client is None:
            yield Observation()
            return
        stack = ExitStack()
        try:
            span = stack.enter_context(self.client.start_as_current_observation(name=name, **attributes))
            if session_id is not None:
                stack.enter_context(propagate_attributes(session_id=str(session_id)))
            observation = Observation(span)
        except Exception:
            stack.close()
            log.warning('Could not start telemetry observation')
            yield Observation()
            return
        try:
            yield observation
        except BaseException as exc:
            # No provider bodies, URLs, credentials or raw exception messages in spans.
            observation.update(level='ERROR', status_message=type(exc).__name__)
            raise
        finally:
            try:
                # Exit normally so the SDK cannot auto-record the raw exception.
                stack.close()
            except Exception:
                log.warning('Could not finish telemetry observation')

    def shutdown(self):
        if self.client is not None:
            try:
                self.client.shutdown()
            except Exception:
                log.warning('Telemetry shutdown did not complete')
