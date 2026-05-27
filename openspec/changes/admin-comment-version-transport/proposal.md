*Add MCP server version and active transport to `hdx_query_admin_comment`.*

**Tracking:** HDX-11481

## Why

Usage tracking needs to separate Hydrolix query traffic by MCP server version and transport (`stdio`/`http`/`sse`). Today the static `User: mcp-hydrolix` comment collapses both axes.

## What Changes

- Set `hdx_query_admin_comment` to `User=<name>; version=<version>; transport=<transport>` on every query.

## Capabilities

### New

- `query-admin-comment` — server name, version, and transport stamped on every Hydrolix query

### Modified

- *none*

## Impact

- `mcp_hydrolix/mcp_server.py` — `execute_query` settings dict.
