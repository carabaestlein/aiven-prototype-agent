# Approved LangGraph template

`template.yaml` creates a draft PR under `agents/<name>` in the existing
`carabaestlein/aiven-prototype-agent` repository. The allowed repository is fixed
in the parameter schema. A server-side GitHub integration needs permission to
write contents and create pull requests; credentials never appear as template
parameters. The action uses `update: false`, so it does not overwrite an existing
PR branch. Choose a unique name and review the PR before merging.

The fetch step uses `.njk` rendering only. Phase 1 Python, static assets,
dependency pins and their tests are copied unchanged. The generated Dockerfile
uses repository-root context; both Compose manifests are adjusted accordingly.
The runtime JSON is a create-service body containing only public configuration.

The template does not provision cloud services, create Langfuse projects, add
secrets or claim a successful deployment. Generated instructions cover reusing
the existing PostgreSQL **service with an isolated database**, self-hosted
Langfuse and AI Gateway. It does not register an ephemeral PR branch in the
catalog; registration happens from the merged file using Backstage's built-in
registration flow.

## Local template testing

Use Backstage's **Create → Template editor** at `/create/edit`, load this
template directory and test with a unique sample name and nonsecret project ID.
`fetch:template` supports dry runs. The GitHub action's dry run still resolves
its integration: when GitHub is not configured, remove the publish step in the
editor's temporary copy and test only the fetch step. Do not click a normal
Create run unless you intend to open a real draft PR.

After rendering, run the generated tests from the rendered folder. They cover
revision/approval, authentication, failed-model recovery, TLS configuration and
Langfuse's real SDK serialization without network calls. PostgreSQL checks are
opt-in with a disposable test database. The generated application is not a
production multi-tenant agent platform; it preserves Phase 1's shared workspace
and single-process execution model.

Official action references:

- [Writing Backstage templates](https://backstage.io/docs/features/software-templates/writing-templates/)
- [GitHub pull-request action](https://github.com/backstage/backstage/blob/master/plugins/scaffolder-backend-module-github/src/actions/githubPullRequest.ts)
- [Fetch template action](https://github.com/backstage/backstage/blob/master/plugins/scaffolder-backend/src/scaffolder/actions/builtin/fetch/template.ts)
