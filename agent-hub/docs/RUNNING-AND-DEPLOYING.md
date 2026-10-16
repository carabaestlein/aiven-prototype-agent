# Run and deploy the Agent Hub

The Hub lives in the user's existing `carabaestlein/aiven-prototype-agent` repository. It already includes the real first agent in its catalog and an approved LangGraph Scaffolder template.

## Run locally

Use Node.js 22 or 24. Yarn 4.13.0 is pinned and included under `agent-hub/.yarn/releases`.

```sh
cd agent-hub
node .yarn/releases/yarn-4.13.0.cjs install --immutable
node .yarn/releases/yarn-4.13.0.cjs start
```

Open [localhost:3000](http://localhost:3000). Local guest mode uses in-memory SQLite, so restart discards task history and manually registered entities. The checked-in first agent and template reload automatically. No cloud credentials are needed to browse the catalog.

For real Scaffolder draft pull requests, privately export a repository-scoped `GITHUB_TOKEN` with Contents and Pull requests write permission, then run `yarn start:github`. Without a token, use `yarn test:template` (`scripts/test-template.cjs`) or a fetch-only template-editor dry run with the publish step removed. A full normal Create run requires the token and opens a real draft PR. See [local configuration and verification](RUNNING.md) and the [new-agent workflow](NEW-AGENT.md).

## Deploy on Aiven Runtime

1. Prepare a dedicated database/user such as `backstage_agent_hub` on the existing `prototype-agent-pg` service. Backstage creates its plugin schemas there. Keep verified PostgreSQL TLS enabled and provide the project's CA certificate.
2. Create GitHub OAuth credentials for sign-in. Use the Hub's HTTPS origin as the homepage and append `/api/auth/github/handler/frame` for its callback. The stable-ID resolver initially admits only the seeded `carabaestlein` user. The separate `GITHUB_TOKEN` grants template repository writes.
3. Deploy the new `prototype-agent-hub` application from repository-root `Dockerfile.agent-hub`, root build context `.`, HTTP port `7007`. The public API body is `agent-hub/runtime.json`; it proposes a 4 GiB plan, which is not a validated sizing recommendation. Confirm the selected source branch exists remotely and review current project pricing before creating the service.
4. Supply `HUB_BASE_URL`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DATABASE`, `POSTGRES_CA_CERT`, `AUTH_GITHUB_CLIENT_ID`, `AUTH_GITHUB_CLIENT_SECRET` and `GITHUB_TOKEN` through Runtime configuration/secrets. Use the actual assigned HTTPS route. The JSON's empty environment list must be populated privately before deployment.
5. Verify GitHub sign-in, catalog loading, template rendering and persistence after a Hub restart. Runtime deployments and authenticated GitHub/OAuth flows are separate checks from local compilation.

Production loads `app-config.yaml` plus `app-config.production.yaml`; it does not load development guest authentication. Admitted users share catalog/template privileges in this minimal version. See [full Runtime instructions](RUNTIME.md) for the exact secret contract, credential boundaries, build command and acceptance checks.

## Create the next agent

Choose **Create → LangGraph agent on Aiven**, fill the public settings and open a draft PR under `agents/<name>` in the same repository. After review/merge, follow the generated README to add a separate agent database, configure private Gateway/Langfuse/application credentials and deploy. Register the merged catalog file and add the actual endpoint after verification. See [the complete workflow](NEW-AGENT.md) and [Langfuse project/key setup](LANGFUSE.md).

Existing service checks and exact links are recorded in [existing infrastructure](EXISTING-INFRASTRUCTURE.md) and [live evidence](live-infrastructure-check.json). Product observations are in [Aiven DX gaps](DX-GAPS.md). These files do not claim that the new Hub or a generated second agent has been deployed.
