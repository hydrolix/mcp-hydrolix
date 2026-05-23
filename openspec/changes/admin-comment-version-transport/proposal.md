*Include the MCP server version and active transport in the `hdx_query_admin_comment` stamped on every Hydrolix query.*

**Tracking:** HDX-11481

## Why

As part of tracking MCP usage, we want to separate query traffic along two additional axes — server **version** and **transport** — that the static `User: mcp-hydrolix` we emit today collapses together. Without these axes the cluster-side query log can't attribute usage to specific builds or stdio/http/sse deployments, blocking rollout-health and adoption analysis.

## What Changes

- Extend the `hdx_query_admin_comment` value to carry the MCP server name, its version, and the active transport (`stdio` / `http` / `sse`).
- Resolve the version once at startup from package metadata, and the transport from the runtime config used to start the server.

## Capabilities

### New

- `query-admin-comment` — server name, version, and transport stamped on every Hydrolix query

### Modified

- *none*

## Impact

- `mcp_hydrolix/mcp_server.py` — `execute_query` settings dict (only call site of `hdx_query_admin_comment`).
- New runtime read of the resolved transport (already on `HydrolixConfig.mcp_server_transport`) and the package version (e.g. `importlib.metadata.version("mcp-hydrolix")`).
- No public MCP tool surface change; no schema or data migration. Only the Hydrolix-side query-log string changes.
