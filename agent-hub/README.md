# Aiven Agent Hub

A minimal Backstage 1.55 portal in the same repository as the Phase 1 LangGraph agent.

- **Agent catalog:** the real `prototype-agent` in `cara-test`, with verified links to the agent, Aiven Console and its existing self-hosted Langfuse project.
- **New agent:** an approved Scaffolder template copies the tested Phase 1 code into `agents/<name>` and opens a draft pull request in `carabaestlein/aiven-prototype-agent`.
- **Shared services:** agents reuse AI Gateway and Langfuse infrastructure, with their own PostgreSQL databases and Langfuse project keys.
- **Hub hosting:** a repository-root `Dockerfile.agent-hub`, Runtime configuration, GitHub sign-in and PostgreSQL persistence.

## Run locally

Use Node 24 and the bundled Yarn binary:

```sh
cd agent-hub
node .yarn/releases/yarn-4.13.0.cjs install --immutable
node .yarn/releases/yarn-4.13.0.cjs start
```

Open <http://localhost:3000>. Local guest access and persistent SQLite need no service credentials; local database files are excluded from Git. To open actual template pull requests, privately provide `GITHUB_TOKEN` and use `start:github` instead of `start`. The token needs Contents and Pull requests write permission on this repository. The template contains no credential fields.

## Use it

1. Open **Agents → Prototype Agent** for the existing agent and its service/observability links.
2. Open **New agent → LangGraph agent on Aiven** and provide a name, team and Langfuse project ID. Organization settings have Phase 1 defaults.
3. Review and merge the generated pull request. Its README explains isolated database creation, secrets and Runtime deployment.
4. Register the merged agent catalog file, then add the verified endpoint after deployment.

The template creates source code and configuration; it does not provision billable services or claim an agent is deployed. Catalog links use each external service's own authentication. The catalog does not fabricate health, cost or success-rate metrics.

## Verify

```sh
node .yarn/releases/yarn-4.13.0.cjs tsc
node .yarn/releases/yarn-4.13.0.cjs build:backend
node .yarn/releases/yarn-4.13.0.cjs test:template
python3 -m unittest discover -s tests -p 'test_langfuse*.py'
```

`test:template` uses Backstage's actual rendering action, parses the resulting catalog/Runtime configuration, verifies same-repository output and checks that the Phase 1 runtime code is preserved. The copied Python agent tests also cover real temporary-PostgreSQL restart/recovery.

## Setup and findings

- [Running and deploying](docs/RUNNING-AND-DEPLOYING.md)
- [New-agent workflow](docs/NEW-AGENT.md)
- [Langfuse project keys and connection verification](docs/LANGFUSE.md)
- [Existing infrastructure and live evidence](docs/EXISTING-INFRASTRUCTURE.md)
- [Validation and remaining limits](docs/VALIDATION.md)
- [Aiven DX gaps](docs/DX-GAPS.md)
- [Dependency workaround](docs/DEPENDENCIES.md)

Production sign-in initially allows the repository owner's immutable GitHub user ID. All admitted users share catalog and scaffolder privileges in this minimal portal. Add an appropriate permission policy before extending it to teams requiring different access. The hub receives no model, agent or Langfuse secrets merely to show links.
