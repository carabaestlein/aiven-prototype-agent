# Step 1 validation — 16 October 2026

## Verified

- **62 agent/deployment tests passed**, including two real PostgreSQL 16.2 integration tests; **11 Langfuse starter tests passed** separately. Offline tests cover trace parentage across LangGraph worker execution, session/model/usage attributes, default prompt exclusion, sanitized errors, and exporter failures without duplicate model calls.
- Seven fresh services in `cara-test`, `aws-eu-west-1`, were `RUNNING` at the 08:59 check: `prototype-agent`, `prototype-agent-pg`, `prototype-langfuse-web`, `prototype-langfuse-worker`, `prototype-langfuse-pg`, `prototype-langfuse-ch`, and `prototype-langfuse-valkey`. Older services were not reused. All three Runtime builds reported `SUCCESS`.
- [Agent](https://01a143ee-18f7-7972-aebe-7cd8498afb71-8080.eur-1.aiven.app) password login and [Langfuse](https://01a143e8-a09e-70b1-9170-21575e8e407f-8080.eur-1.aiven.app) administrator login/project API keys worked.
- A live `claude-sonnet-5` Gateway request produced a draft, PostgreSQL checkpoint, and retrievable Langfuse root/generation observations. Parent relationship, run session ID, release label, and **124 total tokens** were verified in the initial trace.
- The Runtime agent shut down at 09:00:43 and was healthy on a replacement host at 09:01:24 (`run-aceda9e5…` → `run-1ab53af8…`). Its existing checkpoint and draft hash survived. The saved run then reached revision 2 and was approved to completion.
- Draft and revision traces contain model generations. The completed approval trace contains none during a **90-second observation window**.
- Langfuse web and worker were restarted with new process identities. Earlier traces remained readable, and a new Gateway run produced a retrievable trace after both restarts. All seven services were confirmed running again; see [deployment-evidence.json](deployment-evidence.json). Times in this report are UTC.

## Source evidence

The public `release/step1` branch was frozen at `35cff71b56d8346be3acdb0364dc71a1c072b295`; GitHub checks before and after deployment confirmed that ref. Runtime was configured to build this branch. Runtime logs did **not** expose a resolved source SHA, so this establishes the intended source and successful builds, not an independent build-to-commit attestation. The agent's release label alone is not such an attestation.

## Limits

Checkpoint persistence and explicit continuation are verified. There is no autonomous recovery scheduler: interrupted work requires a continuation request. No abrupt crash during an in-flight model call was tested; checkpointing does not guarantee exactly-once model calls. Load, concurrent replicas, database outages, and backup/restore remain unvalidated. Container builds ran on Runtime; no local container engine is installed. The unit suite reports one upstream Starlette/AnyIO deprecation warning.

## Commands

Agent unit tests: `.venv/bin/python -m pytest -q` (PostgreSQL tests skip by default).
All agent tests: install optional `pgserver==0.1.4`, then `TEST_LOCAL_POSTGRES=1 .venv/bin/python -m pytest -q`.
Langfuse tests: from `infra/langfuse`, `python3 -m unittest discover -s tests -q`.
