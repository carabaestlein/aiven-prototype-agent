# Step 1 validation — 16 October 2026

## Completed in this session

- Inspected both upstream repositories at the commits recorded in UPSTREAM.md.
- Python 3.12.14: **34 tests passed**, including two actual PostgreSQL 16.2 integration tests. **11 Langfuse starter tests passed** separately from infra/langfuse.
- Native Langfuse SDK/OTel serialization verified without network: model spans remain children of their run span across LangGraph worker execution; session IDs, actual/requested model and usage are recorded; prompts default off; exporter failures do not repeat model calls.
- PostgreSQL checkpoints verified after closing/reopening connection pools and rebuilding saver/graph/service, including stale-review rejection and recovery after a failed mocked model request. This is not an abrupt process-kill test.
- Live Aiven API authentication works for cara-test. Gateway models API confirms claude-sonnet-5 is available. No inference made yet.
- Found existing powered-off Langfuse web/worker, PostgreSQL 17, ClickHouse 26.3 and persistent noeviction Valkey 8.1; agent PostgreSQL 16 also exists. Existing Langfuse settings include R2 configuration and project keys.

## Pending live acceptance

- Activate/redeploy selected Runtime services and confirm build SHA/readiness.
- Real AI Gateway draft and Langfuse generation ingestion/retrieval.
- Restart Runtime agent, compare checkpoint/draft, revise and approve.
- Restart Langfuse web/worker, read old trace and process new trace.

No new services or live app restarts have been performed yet. Docker/container build validation awaits Runtime; no local container engine is installed. The unit suite reports one upstream Starlette/AnyIO deprecation warning.

## Commands

Agent unit tests: `.venv/bin/python -m pytest -q` (PostgreSQL tests skip by default).
All agent tests: install optional `pgserver==0.1.4`, then `TEST_LOCAL_POSTGRES=1 .venv/bin/python -m pytest -q`.
Langfuse tests: from `infra/langfuse`, `python3 -m unittest discover -s tests -q`.
