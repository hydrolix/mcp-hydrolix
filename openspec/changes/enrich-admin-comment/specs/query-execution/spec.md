# Delta for query-execution

## MODIFIED Requirements

### Requirement: `hdx_query_admin_comment` identifies version and transport
Previously, `execute_query` set `hdx_query_admin_comment` to
`"User: mcp-hydrolix"` for every query. The setting SHALL now be
`"User: mcp-hydrolix, <version> (<transport>)"`, where `<version>` is the
installed `mcp-hydrolix` package version and `<transport>` is one of
`stdio`, `http`, `sse`.

#### Scenario: Stdio deployment, version 0.3.2
- GIVEN `HYDROLIX_MCP_SERVER_TRANSPORT=stdio`
- AND the installed package version is `0.3.2`
- WHEN `execute_query` builds its settings
- THEN `hdx_query_admin_comment` SHALL equal `"User: mcp-hydrolix, 0.3.2 (stdio)"`

#### Scenario: HTTP deployment
- GIVEN `HYDROLIX_MCP_SERVER_TRANSPORT=http`
- WHEN `execute_query` builds its settings
- THEN `hdx_query_admin_comment` SHALL end with `" (http)"`
