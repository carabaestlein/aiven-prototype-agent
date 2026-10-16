# Connect an agent to the existing Langfuse stack

Reuse the Phase 1 deployment in Aiven project `cara-test`: [Langfuse web](https://01a143e8-a09e-70b1-9170-21575e8e407f-8080.eur-1.aiven.app), project `prototype-project`, web/worker version **4.38.0**, Python SDK **4.18.0**. These details come from the repository's deployment evidence and configuration. Registration in Backstage does not re-verify or redeploy those services.

The existing agent already instruments graph invocations and model calls, including session IDs, model usage and release/environment metadata. A new generated agent uses the same instrumentation. Backstage links to Langfuse; it does not need Langfuse secret keys. Keep `TRACE_CONTENT=false` unless the team deliberately wants prompts and generated content stored in traces.

## 1. Choose the Langfuse project and obtain project keys

For the first agent, keep its existing project and Runtime secrets. For a new agent, either reuse an existing project that the team may access or create a project in the existing Langfuse UI. Use a dedicated project/key pair when access or retention needs to differ. Create project keys under **Project Settings → API Keys**, record the project ID, and store the key pair in the team's secret store. The secret key is shown only at creation. [Langfuse API-key documentation](https://langfuse.com/docs/administration/rbac).

Project and key creation remain a short operator step in this open-source implementation. The official organization-scoped provisioning APIs require **self-hosted Enterprise Edition**. We do not depend on those APIs, undocumented browser endpoints, direct database writes, or changing the bootstrap settings of the running shared stack. [Organization API availability](https://langfuse.com/docs/administration/scim-and-org-api).

## 2. Verify the credentials without sending traces

Run from the repository root with Python 3.10 or later. Load these values into your shell environment through your secret manager or hidden input; avoid literal credentials in shell history, command arguments, chat, or Backstage template parameters:

| Environment variable | Value |
| --- | --- |
| `LANGFUSE_BASE_URL` | The existing Langfuse web origin above, without `/api` |
| `LANGFUSE_PUBLIC_KEY` | Project public key |
| `LANGFUSE_SECRET_KEY` | Project secret key |
| `LANGFUSE_PROJECT_ID` | Expected project ID; optional for discovery, recommended for deployment |

```sh
python3 agent-hub/scripts/langfuse_setup.py
```

The helper makes a single authenticated `GET /api/public/projects`, verifies the project ID and prints no keys. This is the documented project-key verification endpoint. It requires HTTPS, except for loopback development, verifies certificates, refuses redirects and fails safely without echoing response bodies. A successful check establishes API access, **not** end-to-end trace ingestion. [Langfuse Public API](https://langfuse.com/docs/api-and-data-platform/features/public-api).

If a local shell environment file is useful, create one explicitly after loading the same environment values:

```sh
agent_hub_private_dir=$(mktemp -d "${TMPDIR:-/tmp}/agent-hub-secrets.XXXXXX")
python3 agent-hub/scripts/langfuse_setup.py \
  --write-env "$agent_hub_private_dir/new-agent.env"
```

The helper verifies the credentials first, then creates a new owner-readable/writable file (`0600`). It refuses an existing destination, symlinks at the destination, and paths inside any detected Git checkout. The file uses shell quoting and includes the discovered project ID. Use it only from a trusted local shell, with tracing disabled:

```sh
set +x
set -a
. "$agent_hub_private_dir/new-agent.env"
set +a
```

Do not copy the populated file into the repository or a container image. Delete the temporary file after storing the values in your approved secret store.

## 3. Supply the agent's Runtime configuration

Set `LANGFUSE_BASE_URL` and `LANGFUSE_PROJECT_ID` to the chosen public configuration; store `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` as secrets on **the new agent's** Aiven Runtime service. Supply its AI Gateway `MODEL_API_KEY` and PostgreSQL connection/certificate independently using the generated agent's deployment instructions. Do not give Backstage the AI Gateway or Langfuse project secrets. None of this requires new Langfuse, ClickHouse, Valkey or R2 services.

The helper does not install environment values into Aiven Runtime, deploy the agent, or rotate an existing key. During rotation, deploy and verify the new key pair before deleting the old key in Langfuse.

## 4. Confirm the complete path

After deployment, run one synthetic request through the new agent and follow its Langfuse link. Confirm that the graph invocation and model generation appear in the intended project with matching session, environment and model information. An accepted HTTP request or healthy Langfuse web page alone does not establish that the worker stored the observation.

For the original Phase 1 agent, the repository's [deployment validation](../../VALIDATION.md) and `scripts/verify_deployment.py` describe its existing generation/revision/restart test. That workflow makes model calls and writes traces; run it deliberately with the appropriate agent API key. For a no-model ingestion check, the [existing synthetic OTLP example](../../infra/langfuse/README.md#send-a-synthetic-trace) uses `LANGFUSE_HOST` (set it to `LANGFUSE_BASE_URL`) and the same project keys. It writes a synthetic trace.

## Offline helper tests

```sh
python3 -m unittest discover -s agent-hub/tests -p 'test_langfuse*' -v
```

The tests mock HTTP and cover project mismatch, authentication/transport errors, redirects, invalid inputs, secret-safe output, protected file permissions, overwrite refusal and Git checkout/symlink rejection. They do not contact the deployed stack.
