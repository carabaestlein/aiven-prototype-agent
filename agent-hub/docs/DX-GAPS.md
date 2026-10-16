# Aiven developer-experience findings

These are observations from the existing Phase 1 deployment and this Hub integration. The dated source of live resource status is [live-infrastructure-check.json](live-infrastructure-check.json); earlier deployment evidence and limitations remain in [DEPLOYMENT.md](../../DEPLOYMENT.md).

| Observed friction | Minimal workaround here | Product opportunity |
| --- | --- | --- |
| An agent deployment spans Runtime, Gateway, PostgreSQL, Langfuse web/worker, ClickHouse, Valkey and bucket storage. The platform has no single agent record. | Backstage Component with an owner, dependencies and actual service/trace links. | Agent-aware inventory and integration metadata exposed through an API. |
| Console service deep links require an account identifier in addition to project and service. The shorter project-only path redirected to home. | Copy the authenticated Console's actual service links, including the account segment. | Canonical Console URLs in service API responses and stable deep-link documentation. |
| A generic Runtime service URI was not the public HTTPS route. | Preserve the actual public HTTP endpoint in catalog metadata; do not infer it from service names. | Canonical application URL in deployment responses. |
| Langfuse project keys must be created and delivered separately from database credential integrations. | Parameterized configuration plus an operator workflow for project-key creation and private secret injection. | A first-class tracing integration that provisions scoped keys and keeps them out of generated code. |
| Full environment arrays are replaced on update and values are redacted on read. | Retain private configuration; update complete secret sets deliberately. The Hub does not rewrite existing service configuration. | Secret/config patch operations and revision-aware changes. |
| Runtime redeploy resolves the latest commit on a branch; Phase 1 logs did not expose an independently verified resolved source SHA. | Use a recorded release branch and application release metadata; inspect the completed build. | Immutable source selection and visible resolved commit/image identity. |
| Git pushes do not automatically deploy Runtime applications. | A developer creates a reviewed change, then explicitly deploys the intended commit through Runtime. | A native, configurable continuous deployment trigger with approval gates. |
| PostgreSQL checkpointing retains work but does not schedule interrupted work automatically. | Reuse the agent's explicit Continue operation and per-run locking. | Durable execution/recovery controls with observable job state. |
| A health endpoint can pass while model access or stored observations fail. | Keep end-to-end model, persistence and Langfuse verification separate from readiness. | Deployment acceptance checks with trace and release evidence. |
| Backstage must coordinate GitHub auth, repository writes, Runtime identity and Langfuse credentials. | Keep the minimal Hub trusted-user scoped; secrets stay server-side or in Runtime. | Clear, scoped platform credentials and an end-to-end deploy-readiness check. |

The Runtime push/redeploy behavior is also documented in [Deploy an application](https://aiven.io/docs/products/runtime/deploy-apps). The Langfuse SDK/server pins in the Phase 1 starter are intentional; do not assume the latest SDK works with the deployed server. See [Langfuse compatibility](https://langfuse.com/docs/compatibility).
