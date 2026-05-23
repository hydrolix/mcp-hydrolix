*The MCP server stamps a structured admin comment carrying its name, version, and active transport on every query it sends to Hydrolix.*

**Tracking:** HDX-11481

## ADDED Requirements

### Requirement: Query Comment Composition
<!-- settle: explore/comment-format -->

The server MUST set the `hdx_query_admin_comment` ClickHouse setting on every query it issues to Hydrolix. The value MUST be composed of three `key=value` pairs separated by `; ` (semicolon followed by a single space), in this exact order: `User=<server-name>; version=<server-version>; transport=<active-transport>`. The server MUST NOT include any additional fields or alternative separators.

#### Scenario: Default Stdio Deployment Issues A Query

- **GIVEN** the server is running with `HYDROLIX_MCP_SERVER_TRANSPORT` unset (defaulting to `stdio`)
- **AND** the installed distribution metadata reports version `0.3.2`
- **WHEN** the server executes a Hydrolix query
- **THEN** the request's `hdx_query_admin_comment` setting equals `User=mcp-hydrolix; version=0.3.2; transport=stdio`

#### Scenario: Http Transport Deployment Issues A Query

- **GIVEN** the server is started with `HYDROLIX_MCP_SERVER_TRANSPORT=http`
- **AND** the installed distribution metadata reports version `0.4.0`
- **WHEN** the server executes a Hydrolix query
- **THEN** the request's `hdx_query_admin_comment` setting equals `User=mcp-hydrolix; version=0.4.0; transport=http`

### Requirement: Version Resolution
<!-- settle: explore/version-fallback -->

The server MUST resolve the `version` field by calling `importlib.metadata.version("mcp-hydrolix")` at startup. If the lookup raises `PackageNotFoundError` (or any other resolution error), the server MUST emit the literal string `unknown` for the `version` field, MUST log a warning identifying the resolution failure, and MUST NOT block query execution.

#### Scenario: Version Metadata Available

- **GIVEN** the `mcp-hydrolix` distribution is installed with a discoverable version
- **WHEN** the server resolves its admin comment at startup
- **THEN** the `version` field of the comment equals the value returned by `importlib.metadata.version("mcp-hydrolix")`

#### Scenario: Version Metadata Unavailable

- **GIVEN** `importlib.metadata.version("mcp-hydrolix")` raises `PackageNotFoundError`
- **WHEN** the server resolves its admin comment at startup
- **THEN** the `version` field of the comment is the literal string `unknown`
- **AND** the server logs a warning naming the resolution failure
- **AND** subsequent queries proceed normally with the comment attached

### Requirement: Transport Resolution

The server MUST resolve the `transport` field once at startup from `HydrolixConfig.mcp_server_transport`, which reads `HYDROLIX_MCP_SERVER_TRANSPORT` (defaulting to `stdio`). Permitted values are exactly the members of the `HydrolixTransport` enum: `stdio`, `http`, `sse`.

#### Scenario: Transport Reflects Launcher Configuration

- **GIVEN** the server is started with `HYDROLIX_MCP_SERVER_TRANSPORT=sse`
- **WHEN** the server resolves its admin comment at startup
- **THEN** the `transport` field of the comment equals `sse`

#### Scenario: Transport Defaults When Unset

- **GIVEN** `HYDROLIX_MCP_SERVER_TRANSPORT` is not set in the environment
- **WHEN** the server resolves its admin comment at startup
- **THEN** the `transport` field of the comment equals `stdio`
