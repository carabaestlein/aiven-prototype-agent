# Agent Hub validation — 16 October 2026

## Passed

- Official Backstage 1.55 application, Node 24.21.0, pinned Yarn 4.13.0 and a resolved dependency lockfile. TypeScript compilation and production frontend/backend bundle builds passed.
- Development and production configuration schema checks passed. Production schema validation used dummy values, not real OAuth or PostgreSQL credentials.
- Local Backstage started on localhost:3000/7007 with file-backed SQLite and guest sign-in. Catalog API returned the actual `prototype-agent` and `aiven-langgraph-agent` template; both `fetch:template` and `publish:github:pull-request` actions are registered.
- Browser checks: catalog lists Prototype Agent, detail page displays its three infrastructure dependencies and real links, New agent displays the approved template, and its two-step form loads the organization defaults.
- Aiven branding checked against the live homepage and its current stylesheet. Branded catalog search and clearing, agent detail routes, template selection, and both configuration steps through Review were exercised in the browser at the 736px app-pane width. No test pull request was submitted. Shared styling covers Material UI and Backstage UI; production bundles and the template-render test passed again after the redesign.
- Backstage's actual `fetch:template` action rendered the skeleton. Checks parse generated catalog YAML and Runtime JSON, exercise quoted/multiline descriptions, verify repository-root Dockerfile paths, exclude credentials, and compare the runtime files byte-for-byte with Phase 1.
- Copied agent tests: **26 offline tests plus 2 real temporary-PostgreSQL restart/recovery tests passed**. Langfuse helper: **13 offline tests passed**. Backstage app rendering test: **1 passed**.
- Cloud container build passed on Aiven Runtime. The separate `prototype-agent-hub` service in `cara-test` reports `RUNNING`, build `SUCCESS` and deployment `COMPLETED`; its selected branch is `feat/backstage-agent-hub`, with published deployment source commit `9eea2a2`. Assigned URL: [Agent Hub](https://01a14496-fd39-7b34-bb81-4fb2ff98e6b7-7007.eur-1.aiven.app). These control-plane results do not establish successful hosted sign-in.
- Created the isolated `backstage_agent_hub` database and `backstage_hub` login on existing `prototype-agent-pg`. A direct connection using that login passed PostgreSQL TLS verification and schema-creation privilege checks. The first agent's database and application remain separate. The installed Backstage DatabaseManager then connected to all four live Hub plugin schemas (`app`, `auth`, `catalog`, `scaffolder`) with TLS retained, using the preprovisioned-database configuration fix.
- Read-only live infrastructure checks: all seven Phase 1 services running; first agent readiness and authenticated session requests succeeded; Langfuse project API and stored observations succeeded. See `live-infrastructure-check.json`.
- Authenticated browser inspection verified the actual Aiven Console service links, including the required account path. The existing Langfuse Tracing page opened successfully and displayed stored runs.
- Scan of deliverable files found no matches for the known Phase 1 credential values. No credentials are included in template parameters, catalog entries or committed deployment configuration.

## Not yet verified

- Hosted startup acceptance is currently blocked: the homepage returned HTTP 404, and Backstage logs show database bootstrap trying to connect to a maintenance database named `postgres`, which does not exist on this Aiven service. The `ensureExists: false` / `ensureSchemaExists: true` fix passed a live DatabaseManager check, was published as `37cfbee`, and has been submitted for Runtime redeployment. That build is in progress; the earlier successful image build/control-plane state does not establish a working application.
- Hosted Hub GitHub OAuth sign-in is not configured or tested. OAuth credential setup is pending user approval and fresh GitHub verification; the assigned URL is not yet a verified signed-in Hub experience.
- The cloud container build passed; a local Docker build was not run because Docker is unavailable. Hosted application health, end-to-end PostgreSQL persistence and restart behavior still require separate acceptance checks. Direct database TLS connectivity has been verified.
- The template's GitHub publish action is registered, but hosted repository-write credentials are not configured and opening a new agent PR through the hosted Hub is untested. Credential setup is pending approval and fresh GitHub verification. Local publishing requires a repository-scoped `GITHUB_TOKEN` and `start:github`.
- No new agent was deployed by the template. Provisioning its database, project keys, Runtime secrets and service remains an explicit setup workflow, documented in the generated README. Agent catalog registration follows merge.

## Limits and repeatability

Run the commands in the Hub README to repeat compilation, bundling, real template rendering and helper tests. `yarn test --watchAll=false --runInBand` runs the app rendering test. The skeleton's Python tests have their own README instructions.

Upstream dependency peer/deprecation warnings remain for the legacy React/Material UI frontend. They did not prevent compilation or browser operation. `docs/DEPENDENCIES.md` records a pinned workaround for a published Yarn package that references an absent patch. Development SQLite uses files because the current CLI's in-memory database IPC timed out on this machine.

This portal is for trusted cataloged users. It supplies a catalog and a repeatable source-generation workflow, not fleet health metrics, automated cloud provisioning, multi-tenant authorization, a durable job scheduler or validated multi-replica agent execution.
