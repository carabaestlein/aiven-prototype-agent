# Step 1: Aiven deployment

Target project: **cara-test**. Gateway: `https://ai.aiven.io/v1`. Requested model: **claude-sonnet-5**; verify availability with the project's key before deployment. Future HTML/CSS/JS generation and Nevia are out of scope.

## What we reuse

The agent already has FastAPI, authenticated UI/API, PostgreSQL run indexing and LangGraph checkpoints, human review interrupts, advisory locks, stale-checkpoint checks, explicit continuation, readiness and verified PostgreSQL TLS. It uses open-source LangGraph, not LangSmith Agent Server. Checkpoints survive restarts; they do **not** schedule unfinished work automatically.

Langfuse's starter already supplies pinned web/worker images, TLS setup, ClickHouse migrations, R2 configuration and initial account creation. Its prior live validation is upstream evidence; it does not prove this project's deployment works.

## Changes in this repository

- AI Gateway is the default endpoint; real mode remains explicit.
- Langfuse Python SDK **4.18.0** is pinned for server **4.38.0**. SDK v5 requires server >=4.59.0; upgrade both deliberately.
- Each graph invocation gets a `langgraph.run` span and returns `trace_id`. Actual model calls create child `gateway.chat` generations with model, usage and timing. Every invocation for the same saved run shares its Langfuse session ID. Read-only API calls do not create traces.
- Prompt/draft capture defaults off; `TRACE_CONTENT=true` enables it for synthetic testing. Provider errors record only exception type. Telemetry export failure does not retry the model call. Graceful shutdown drains tracing; a hard kill can still lose unexported spans.
- `scripts/verify_deployment.py` verifies stored observations, checkpoints and review after an externally performed restart.

## Deployment order

1. **Preflight.** Read project services and region; reuse only explicitly selected compatible services. Fetch service types/plans and prices. Choose distinct names such as `prototype-agent`, `prototype-agent-pg`, `prototype-langfuse-web`, `prototype-langfuse-worker`, `prototype-langfuse-pg`, `prototype-langfuse-ch`, `prototype-langfuse-valkey`. Inspect existing resources before creating any. Record region, plans, versions, repository SHA and service IDs.
2. **Storage.** Agent: dedicated PostgreSQL database, reference v16, 10-connection pool. Langfuse: separate PostgreSQL v17 database, ClickHouse **26.3** single shard with a pre-created Replicated `langfuse` database, and dedicated persistent Valkey with `noeviction`. Use the existing private R2 bucket with its real S3 endpoint, bucket-scoped S3 credentials, `S3_REGION=auto`, `S3_FORCE_PATH_STYLE=false`.
3. **Langfuse web.** Build `Dockerfile.langfuse-web` from repository root, one replica, HTTP 8080. Map PostgreSQL and Valkey credential integrations to `DATABASE_URL` and `VALKEY_URL`. Apply `infra/langfuse/.env.runtime.example` settings, preserving shared `SALT` and `ENCRYPTION_KEY`. Set `NEXTAUTH_URL` to the resulting web HTTPS origin. Wait for successful migrations, `/api/public/health`, and login.
4. **Langfuse worker.** Same repository commit, root `Dockerfile.langfuse-worker`, one replica, **no public ports**. Same databases, bucket, CA, secrets and web `NEXTAUTH_URL`. Start after web migrations. Keep `LANGFUSE_BACKGROUND_MIGRATION_V4_ENABLE_HISTORIC_BACKFILL=false` for this fresh installation. It is not an upgrade strategy for existing v3 data.
5. **Agent.** Build root `Dockerfile`, HTTP 8080, one replica/worker. Map its PostgreSQL URI to `DATABASE_URL`; set the project CA as `PG_CA_CERT_BASE64`. Apply `.env.runtime.example`, including Gateway key and self-hosted Langfuse project keys. Use three independently generated app secrets. Set `APP_RELEASE` to the deployed SHA. Keep `LOCAL_DEVELOPMENT` unset/false.
6. **Verify.** Run the acceptance sequence below; retain sanitized results and build SHA. Do not call the milestone complete until a real model draft, persisted checkpoint, successful resume after Runtime restart, and retrievable generation are confirmed.

Upstream suggested starting sizes: agent Runtime 1 GiB; Langfuse web/worker 4 GiB each; agent/Langfuse PostgreSQL 4 GiB each; Valkey >=2 GiB; ClickHouse >=8 GiB. These are conservative demo starting points, not tested minimums. Resolve available project plans and costs before provisioning.

## Reproducible API approach

Use the [Aiven REST API](https://api.aiven.io/doc/) with a project-authorized token, never a token committed to Git. Discover current service types, plans and `user_config` schemas before constructing requests; provider identifiers must come from API responses. Create data services, databases, applications and credential integrations explicitly. API deployment does not execute Compose.

Keep a sanitized deployment record of resource names, source SHA, cloud, plans, versions, integration mappings and public endpoints. Store secrets privately and inject them as Runtime secrets. Aiven environment-variable updates replace the whole list: preserve existing entries. Do not recreate resources on retry after an ambiguous request; read their state first.

Use a release branch frozen at a recorded SHA; Runtime's normal redeploy builds the selected branch's latest commit. Verify the SHA in build logs. Roll back application code with a tested previous release and compatible database schema; never assume a code rollback reverses migrations. Runtime has no pre-deploy commands/one-off tasks, so keep single-instance startup schema setup for this milestone.

## Acceptance sequence

Export `APP_URL`, `APP_API_KEY`, `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` privately. Never put secret values in command arguments. From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -c constraints.txt
.venv/bin/python -m pytest -q
mkdir -p receipts
.venv/bin/python scripts/verify_deployment.py start --receipt receipts/runtime.json --expected-model claude-sonnet-5
```

Restart **only the agent application** via Aiven API power off/on, preserving its PostgreSQL service. Record the API lifecycle transition and wait for readiness. Then:

```sh
.venv/bin/python scripts/verify_deployment.py resume --receipt receipts/runtime.json --expected-model claude-sonnet-5 --restart-confirmed
```

The verifier compares the checkpoint and draft hash, revises, rejects unexpected mode/model configuration, and approves. It reads Langfuse `/api/public/v2/observations` with bounded worker-lag polling; an ingestion HTTP success is insufficient. Each model step must have a completed generation; approval must not generate again. A receipt makes trace-check retries resumable. The restart flag records operator confirmation, not independent proof.

Separately restart Langfuse web/worker and confirm original observations remain readable plus a new synthetic trace is processed. To test mid-step recovery, interrupt a synthetic agent execution, retrieve the saved run, and explicitly call Continue. A crash after an external model call but before its checkpoint may repeat that call; autonomous recovery and exactly-once model execution are not provided.

Optional local PostgreSQL test (test database only): install `pgserver==0.1.4`, then `TEST_LOCAL_POSTGRES=1 .venv/bin/python -m pytest -q tests/test_postgres.py`. Alternatively provide `TEST_DATABASE_URL` for a dedicated test database. Tests isolate their tables in random schemas.

## Friction and product opportunities

| Finding | Opportunity |
| --- | --- |
| Connector token expired; read-only/secret-redaction settings separately block deployment | Clear deploy-readiness check and scoped API access |
| Compose ignores managed-service versions; ClickHouse/R2 and web-before-worker ordering are manual | Version-aware multi-service deployment manifests |
| CA and cross-app Langfuse keys are manually supplied | Managed CA rotation and tracing integrations |
| Langfuse server/SDK/API compatibility is easy to miss | Template compatibility checks before build |
| Checkpointing does not resume work automatically | Durable job execution, cancellation and recovery controls |
| Environment updates replace the full list; release redeploy follows a branch | Safer secret/config patching and explicit release pinning |
| Health checks do not prove model access or stored traces | Built-in end-to-end deployment acceptance checks |

Sources: [Gateway API](https://aiven.io/docs/products/ai-gateway/rest-api), [Runtime Compose](https://aiven.io/docs/products/runtime/manifest-files/compose-files), [Runtime integrations](https://aiven.io/docs/products/runtime/connect-services-to-apps), [restart semantics](https://aiven.io/docs/products/runtime/power-off-apps), [Langfuse compatibility](https://langfuse.com/docs/compatibility), [Langfuse R2](https://langfuse.com/self-hosting/deployment/infrastructure/blobstorage).
