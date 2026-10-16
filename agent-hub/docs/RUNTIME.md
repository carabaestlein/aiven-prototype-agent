# Deploy Backstage on Aiven Runtime

The deployable Hub is included in this repository as `Dockerfile.agent-hub`. Use the **repository root** as the build context. The container serves the frontend and backend together on HTTP port **7007** using the base and production Backstage configuration. It must be deployed as a new Runtime application; the first agent and Langfuse services remain independent.

The supplied instructions and manifests are deployable setup, not a receipt of a successful Hub deployment. Refer to the task's final verification record for what was actually run.

## 1. Prepare persistent storage and sign-in

Create a separate PostgreSQL database such as `backstage_agent_hub`, with a dedicated owner/login, on the existing `prototype-agent-pg` service if its capacity and access requirements permit. This reuses the Aiven service, not the agent's database. Backstage uses one schema per plugin in this database (`pluginDivisionMode: schema`); its login must be able to create and migrate those schemas. Keep verified TLS enabled and obtain the project's CA certificate from Aiven. See the [Backstage PostgreSQL guide](https://backstage.io/docs/tutorials/switching-sqlite-postgres/).

Create a GitHub OAuth app for Hub sign-in. Set its homepage to the Hub's public HTTPS origin and its callback to `<HUB_BASE_URL>/api/auth/github/handler/frame`. Retain its client ID and secret privately. The resolver matches the stable `github.com/user-id` annotation in `catalog/entities.yaml`; initially it admits `carabaestlein` (`34475835`) only. See [Backstage GitHub authentication](https://backstage.io/docs/auth/github/provider/).

Create a separate GitHub integration token restricted to `carabaestlein/aiven-prototype-agent`, with Contents and Pull requests write permission, for the Scaffolder draft-PR action. OAuth sign-in credentials and repository-write credentials have different purposes.

## 2. Build and deploy the Hub application

Optionally verify the container locally from the repository root:

```sh
docker build -f Dockerfile.agent-hub -t aiven-agent-hub .
```

In project `cara-test`, open **Runtime → Deploy application**. Choose the user's `carabaestlein/aiven-prototype-agent` repository and a reviewed branch containing the Hub. Select `Dockerfile.agent-hub` with root build context `.`. The supplied `agent-hub/runtime.json` names the new service `prototype-agent-hub`, uses HTTP port `7007`, and proposes `startup-200-4096` (4 GiB). Treat that as a starting point; Backstage sizing has not been measured. Use one instance initially. Check available plan prices before provisioning; the existing agent's 1 GiB plan is not evidence of a sufficient Backstage plan.

For API-based deployment, use `agent-hub/runtime.json` as the public create-service body. Its `feat/backstage-agent-hub` source branch must exist remotely and contain the reviewed changes; update it to your chosen release branch before deployment. Its environment array is intentionally empty: assemble all required runtime configuration and secrets privately before submitting it. The equivalent application source fields are: `repository_url`, the reviewed `branch`, `build_path: .`, `containerfile_path: Dockerfile.agent-hub`, and a single `HTTP` port `7007`. Use the current [Aiven deployment API documentation](https://aiven.io/docs/products/runtime/deploy-apps) to resolve connected GitHub repository IDs and project permissions. Runtime supports direct repository URLs in its API; use the connection appropriate to the repository's visibility and access policy.

Configure the following values in Runtime. Values marked secret belong in Runtime secret variables, not Docker build arguments or committed configuration.

| Variable | Value |
| --- | --- |
| `HUB_BASE_URL` | Runtime's actual public HTTPS origin, with no trailing slash |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Existing PostgreSQL service host and TLS port |
| `POSTGRES_DATABASE` | Dedicated Hub database, e.g. `backstage_agent_hub` |
| `POSTGRES_USER` | Dedicated Hub database login |
| `POSTGRES_PASSWORD` | **Secret:** that user's password |
| `POSTGRES_CA_CERT` | Aiven CA certificate in PEM form, preserving its line breaks |
| `AUTH_GITHUB_CLIENT_ID` | GitHub sign-in OAuth client ID |
| `AUTH_GITHUB_CLIENT_SECRET` | **Secret:** GitHub sign-in OAuth client secret |
| `GITHUB_TOKEN` | **Secret:** repository-scoped integration token |

Once Runtime assigns the public route, ensure `HUB_BASE_URL`, OAuth homepage and callback use exactly that origin and redeploy if necessary. Do not derive the HTTPS route from Aiven's generic `service_uri`. Do not add agent, Gateway or Langfuse keys to the Hub just to display links.

The existing Aiven database credential integration may supply the database's default URI; this Hub expects separate connection fields for its isolated database/user. Verify any integration mapping instead of connecting it to `defaultdb` by accident.

## 3. Accept the deployment

Wait for the intended build to finish and the deployment to complete. Open the Hub's HTTPS URL, sign in as the cataloged GitHub user, and confirm that the first agent and approved template appear. Check that an uncataloged GitHub user cannot sign in. Follow the agent and Langfuse links and use their own credentials. Start with the local template-render check or a fetch-only editor dry run; a full normal Create run requires the GitHub integration and opens a real draft PR.

Confirm persistent task/catalog data after a Hub application restart, keeping the PostgreSQL service running. A basic HTTP response does not verify OAuth, database persistence or GitHub write permissions. These checks must succeed before treating a deployed Hub as usable.

Runtime deploys the latest commit on the selected branch when explicitly redeployed; a Git push alone does not deploy it. Record the reviewed source commit and retain a stable release branch. Environment-variable API updates replace complete lists; preserve every existing secret when changing a value. See [Aiven deploy/redeploy behavior](https://aiven.io/docs/products/runtime/deploy-apps).

This minimal Hub admits trusted cataloged users and shares template privileges among them. Add a Backstage permission policy before extending it to teams that should have different access. Keep the dependency lockfile reviewed and rebuild deliberately when upgrading Backstage.
