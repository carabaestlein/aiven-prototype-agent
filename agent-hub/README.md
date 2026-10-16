# Aiven Agent Hub

A minimal Backstage 1.55 portal in the same repository as the Phase 1 LangGraph agent.

The separate [hosted Agent Hub](https://01a14496-fd39-7b34-bb81-4fb2ff98e6b7-7007.eur-1.aiven.app) is running on Aiven Runtime. GitHub sign-in, the first agent's catalog/detail pages, and the new-agent form through Review are verified. Catalog data persisted across redeployment. Creating a pull request through the hosted template remains untested. See [Runtime setup and acceptance](docs/RUNTIME.md).

- **Agent catalog:** the real `prototype-agent` in `cara-test`, with verified links to the agent, Aiven Console and its existing self-hosted Langfuse project.
- **New agent:** an approved Scaffolder template copies the tested Phase 1 code into `agents/<name>` and opens a draft pull request in `carabaestlein/aiven-prototype-agent`.
- **Shared services:** agents reuse AI Gateway and Langfuse infrastructure, with their own PostgreSQL databases and Langfuse project keys.
- **Hub hosting:** a repository-root `Dockerfile.agent-hub`, Runtime configuration, GitHub sign-in and PostgreSQL persistence.
- **Aiven interface:** locally hosted official logo/fonts, a shared dark theme, searchable agent catalog, service shortcuts and a branded Scaffolder flow. Brand assets and their provenance are recorded in [SOURCES.md](packages/app/public/brand/SOURCES.md).

## Run locally

Use Node 24 and the bundled Yarn binary:

```sh
cd agent-hub
node .yarn/releases/yarn-4.13.0.cjs install --immutable
node .yarn/releases/yarn-4.13.0.cjs start
```

Open <http://localhost:3000>. Local guest access and persistent SQLite need no service credentials; local database files are excluded from Git. To open actual template pull requests, privately provide `GITHUB_TOKEN` and use `start:github` instead of `start`. The token needs Contents and Pull requests write permission on this repository. The template contains no credential fields.

The repository token lets the template create a pull request. GitHub OAuth separately signs users into the hosted Hub. Deploying the Hub or a generated agent is a separate Aiven Runtime operation; the template does not use the repository token to deploy services.

## Use it

1. Open **Agents → Prototype Agent** for the existing agent and its service/observability links.
2. Open **Create an agent → Use template** and provide a name, team and Langfuse project ID. Organization settings have Phase 1 defaults.
3. Review and merge the generated pull request, then follow its README to create an isolated database, supply secrets and deploy the agent separately on Runtime.
4. Register the merged agent catalog file, then add the verified endpoint after deployment.

The template creates source code and configuration; it does not provision billable services or claim an agent is deployed. Catalog links use each external service's own authentication. The catalog does not fabricate health, cost or success-rate metrics.

## Verify

```sh
node .yarn/releases/yarn-4.13.0.cjs tsc
node .yarn/releases/yarn-4.13.0.cjs build:backend
node .yarn/releases/yarn-4.13.0.cjs test:template
node scripts/test-github-identity.cjs
node --test scripts/runtime-env.test.cjs
python3 -m unittest discover -s tests -p 'test_langfuse*.py'
```

`test:template` uses Backstage's actual rendering action, parses the resulting catalog/Runtime configuration, verifies same-repository output and checks that the Phase 1 runtime code is preserved. The identity test exercises the installed GitHub resolver against the checked-in catalog, including denial of unrelated identities. The copied Python agent tests also cover real temporary-PostgreSQL restart/recovery.

## Setup and findings

- [Running and deploying](docs/RUNNING-AND-DEPLOYING.md)
- [New-agent workflow](docs/NEW-AGENT.md)
- [Langfuse project keys and connection verification](docs/LANGFUSE.md)
- [Existing infrastructure and live evidence](docs/EXISTING-INFRASTRUCTURE.md)
- [Validation and remaining limits](docs/VALIDATION.md)
- [Aiven DX gaps](docs/DX-GAPS.md)
- [Dependency workaround](docs/DEPENDENCIES.md)

Production sign-in initially allows the repository owner's immutable GitHub user ID. All admitted users share catalog and scaffolder privileges in this minimal portal. Add an appropriate permission policy before extending it to teams requiring different access. The hub receives no model, agent or Langfuse secrets merely to show links.
