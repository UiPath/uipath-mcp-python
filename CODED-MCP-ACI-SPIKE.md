# Coded MCP on ACI — spike branch pointer

Branch **`spike/coded-mcp-aci-runtime`** is part of a **cross-repo spike/POC** that makes coded MCP
servers run as Azure Container Instances orchestrated by AgentHub (start faster / stay alive longer).

**This repo's slice:** the runtime **container mode** in `src/uipath_mcp/_cli/_runtime/`
(`_runtime.py`, `_factory.py`) — when `UIPATH_MCP_CONTAINER_RUNTIME=true`, the runtime declares
itself a `Coded` server, honors the AgentHub-assigned `UIPATH_RUNTIME_ID`, and stays long-lived
(not job-sandboxed) so the container can be reused/kept warm.

**Full handoff, docs, architecture, and how to resume on another machine** live in the
**`UiPath/AgentHubService`** repo on the **same branch**:
- `docs/coded-mcp-aci-HANDOFF.md` — **start here**
- `docs/coded-mcp-aci-poc-guide.md` — how it works + how to run

**Companion branches (same name `spike/coded-mcp-aci-runtime`):** `UiPath/AgentHubService`,
`UiPath/uipath-python`, `UiPath/uipath-mcp-python`.
