*Server name, version, and transport stamped on every Hydrolix query via `hdx_query_admin_comment`.*


## ADDED Requirements

### Requirement: Query Comment Composition
<!-- settle: explore/comment-format -->

The server MUST set `hdx_query_admin_comment` on every SQL query executed via `execute_query` to `User: mcp-hydrolix version: <version> transport: <transport>`, in that order, as space-separated `key: value` tokens (each key followed by a colon and a single space before the value).

#### Scenario: Renders Composed Comment

- **GIVEN** server name `mcp-hydrolix`, version `0.3.2`, transport `stdio`
- **WHEN** the server executes a query
- **THEN** the `hdx_query_admin_comment` setting equals `User: mcp-hydrolix version: 0.3.2 transport: stdio`

### Requirement: Catalog Command Exclusion

The server MUST NOT set `hdx_query_admin_comment` on requests issued via `execute_cmd`. Catalog/admin commands are out of scope for usage attribution; covering them would dilute the per-user signal with catalog noise.

#### Scenario: execute_cmd Omits Admin Comment

- **WHEN** the server invokes `execute_cmd` (e.g. for `SHOW DATABASES`)
- **THEN** the request settings MUST NOT contain a `hdx_query_admin_comment` key

### Requirement: Version Resolution
<!-- settle: explore/version-fallback -->

The server MUST resolve the `version` field via `importlib.metadata.version("mcp-hydrolix")`. On `PackageNotFoundError`, the server MUST emit `version=unknown` and log a warning.

#### Scenario: Version Metadata Available

- **WHEN** the server resolves its admin comment at startup
- **THEN** the `version` field equals the value returned by `importlib.metadata.version("mcp-hydrolix")`

#### Scenario: Version Metadata Unavailable

- **GIVEN** `importlib.metadata.version("mcp-hydrolix")` raises `PackageNotFoundError`
- **WHEN** the server resolves its admin comment at startup
- **THEN** the `version` field equals `unknown`
- **AND** a warning is logged

### Requirement: Transport Resolution

The server MUST source the `transport` field from `HydrolixConfig.mcp_server_transport`. Permitted values: `stdio`, `http`, `sse`.

#### Scenario: Transport Reflects Config

- **GIVEN** `HydrolixConfig.mcp_server_transport` returns `sse`
- **WHEN** the server resolves its admin comment at startup
- **THEN** the `transport` field equals `sse`
