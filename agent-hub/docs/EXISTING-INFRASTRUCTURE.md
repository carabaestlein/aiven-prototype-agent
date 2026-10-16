# Existing infrastructure

This Hub belongs to **[carabaestlein/aiven-prototype-agent](https://github.com/carabaestlein/aiven-prototype-agent)**, the user's writable Phase 1 repository. The public [LangGraph](https://github.com/Aiven-Labs/aiven-runtime-langgraph) and [Langfuse](https://github.com/Aiven-Labs/aiven-runtime-langfuse) repositories are upstream references. They are not the publishing destination.

The catalog registers the already deployed first agent. It does not create a replacement or change the existing applications. See [live-infrastructure-check.json](live-infrastructure-check.json) for the read-only check performed on 2026-10-16 and the original [deployment evidence](../../deployment-evidence.json) for Phase 1 acceptance checks.

| Role | Actual resource |
| --- | --- |
| Aiven project / region | `cara-test` / `aws-eu-west-1` |
| First agent | `prototype-agent`, source branch `release/langfuse-connection` |
| Agent PostgreSQL | `prototype-agent-pg` |
| Langfuse web / worker | `prototype-langfuse-web` / `prototype-langfuse-worker` |
| Langfuse storage | `prototype-langfuse-pg`, `prototype-langfuse-ch`, `prototype-langfuse-valkey`, existing private Cloudflare R2 bucket |
| Langfuse project ID | `prototype-project` (display name: `Provisioned Project`) |
| Model endpoint | `https://ai.aiven.io/v1`; Phase 1 used `claude-sonnet-5` |

**[Open the first agent](https://01a143ee-18f7-7972-aebe-7cd8498afb71-8080.eur-1.aiven.app)** · **[Open its Langfuse project](https://01a143e8-a09e-70b1-9170-21575e8e407f-8080.eur-1.aiven.app/project/prototype-project)**

## What was verified

All seven Phase 1 Aiven services were `RUNNING`; all three applications reported successful builds and completed deployments. The agent readiness endpoint and authenticated session API returned HTTP 200. Langfuse health, authenticated project lookup and v4 observations lookup returned HTTP 200; a stored observation was readable. The agent's own configuration returned the catalog's Langfuse project and sessions URLs. Content capture was disabled.

These checks did not create model calls, restart services or provision resources. They are a dated record, not a live health monitor. The catalog does not claim live success rates, costs or latency. It provides ownership, dependencies and links to the systems that hold that information.

The Aiven Console service URLs were taken from the authenticated Console's service links. They include account ID `a524d1eab5eb`; omitting that account segment redirected to the Console home instead of the service. Langfuse UI links require a separate Langfuse user login. The authenticated project API was verified; the trace-list URL is built from that verified project ID. The agent deliberately disables Swagger and OpenAPI endpoints, so its catalog links point to its real UI, readiness endpoint and source API documentation.

## Reuse boundaries

The Hub does not need the agent password, agent API key, Gateway key or Langfuse secret key just to display the catalog. Backstage holds its own catalog, sign-in and task data in a separate PostgreSQL database when deployed. An operator may create that database and a dedicated user on the existing `prototype-agent-pg` service, subject to capacity and access requirements. Never point Backstage at the agent's existing database or Langfuse's database.

A newly scaffolded agent reuses the LangGraph implementation and connects to the existing Gateway and self-hosted Langfuse deployment. Give it its own PostgreSQL database/user and preferably its own Langfuse project. Reusing a shared Langfuse project is possible for a small trusted demo, but its project keys expose that entire project's data and the traces/sessions list then includes other agents.

The `aiven-platform` group is a logical catalog owner, not a claim about actual Aiven or GitHub organization membership. The seeded `carabaestlein` Backstage user matches GitHub's stable numeric user ID `34475835`. Production authentication initially allows only explicitly cataloged GitHub identities; it is a trusted-user MVP, not team-level authorization.
