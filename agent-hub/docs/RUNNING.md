# Run the Agent Hub

From this repository, use Node.js 22 or 24 and Yarn 4.13.0 (the package manager is pinned in `agent-hub/package.json`). On a fresh Node installation, enable Corepack or install the pinned Yarn version with your normal package manager. Native dependencies need Python and a C/C++ build toolchain.

```sh
cd agent-hub
corepack enable
yarn install --immutable
yarn start
```

Open [localhost:3000](http://localhost:3000). The backend listens on `127.0.0.1:7007`. Local development uses guest sign-in and a separate SQLite file for each plugin in `packages/backend/.backstage-dev-db/`, excluded from Git. Catalog additions and task history survive backend restarts. The first agent and template load from their checked-in files. File-backed SQLite also avoids the CLI's in-memory database IPC bridge, which timed out during a fresh combined frontend/backend start in this environment.

In **Catalog**, select the **agent** type and open **Prototype Agent**. Its details show the owner, dependencies and links to the existing agent, Runtime service and Langfuse project/traces/sessions. Those external tools keep their own authentication. No Gateway or Langfuse keys are required to browse this catalog.

Open **Create** to view the approved LangGraph template. With no GitHub token, run `yarn test:template` (`scripts/test-template.cjs`) to render and inspect representative output, or use a fetch-only template-editor dry run with the publish step removed. A full normal Create run requires the GitHub integration and opens a real draft PR. To actually open draft pull requests, privately export a GitHub token scoped to this repository with Contents and Pull requests write permission, then run:

```sh
yarn start:github
```

The token is read by the backend integration. Do not paste credentials into template parameters, generated files or source-controlled configuration. See [New-agent workflow](NEW-AGENT.md).

## Verification

From `agent-hub`:

```sh
yarn tsc
yarn build:backend
yarn test:template
```

The template check renders representative parameters and validates the generated application/configuration. The Phase 1 Python tests and the Langfuse setup helper tests are described in their own directories. A successful build or local render does not prove that a new cloud deployment works.

## Configurations

| Files | Purpose |
| --- | --- |
| `app-config.yaml` + `app-config.development.yaml` | Local catalog/template demo, guest authentication, persistent local SQLite |
| Add `app-config.github.yaml` | Enable authenticated repository writes for local Scaffolder runs |
| `app-config.yaml` + `app-config.production.yaml` | Deployed Hub, GitHub sign-in, verified PostgreSQL TLS and persistent plugin schemas |

Never expose the guest development server as the deployed Hub. The production container starts only the base and production files. Its GitHub sign-in resolver requires a cataloged numeric GitHub user ID; initially only the repository owner is seeded. All admitted users share catalog and template access because granular permissions are disabled in this minimal version. Add reviewed `User` entities to admit colleagues; a public or multi-team deployment needs a permission policy appropriate to that audience.

See [Runtime deployment](RUNTIME.md), [Langfuse setup](LANGFUSE.md) and [existing infrastructure](EXISTING-INFRASTRUCTURE.md).
