# Proposal: Include version and transport in `hdx_query_admin_comment`

> Jira: [HDX-11481](https://hydrolix.atlassian.net/browse/HDX-11481)
> Branch: `il/hdx-11481-admin-comment`

## Intent

`mcp_server.py:235` tags every query with the static string
`"User: mcp-hydrolix"`. The data team needs to split MCP usage by
deployment mode (local stdio vs. hosted http/sse) and by server version,
and can't with a constant.

## Scope

Change the value of `hdx_query_admin_comment` from
`"User: mcp-hydrolix"` to `"User: mcp-hydrolix, <version> (<transport>)"`,
e.g. `"User: mcp-hydrolix, 0.3.2 (stdio)"`.

## Approach

- Read version once via `importlib.metadata.version("mcp-hydrolix")` at
  module load.
- Read transport per call via the existing
  `HydrolixConfig.mcp_server_transport`.
- Keep the existing `User: mcp-hydrolix` prefix so historical parsers /
  greps continue to match; append the new fields after a comma.
