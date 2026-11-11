# Starter provenance

The runtime Python modules, static assets, dependency pins and tests are copied
from this repository's working Phase 1 LangGraph agent at commit
`54371a66c0bed60124d3cfe2c4a0cca054b00902`.

Source: https://github.com/carabaestlein/aiven-prototype-agent

Upstream reference: https://github.com/Aiven-Labs/aiven-runtime-langgraph

The MIT license is preserved in `LICENSE`; font licenses and source notes are
preserved under `static/brand/`. The Scaffolder only renders the deployment,
catalog and documentation files ending in `.njk`. Python and binary assets are
copied byte for byte. The root-context Dockerfile and local Compose build paths
are adapted for the `agents/<name>` layout in the same repository.
