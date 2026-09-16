## MODIFIED Requirements

### Requirement: Query Comment Composition

The server MUST set `hdx_query_admin_comment` on every SQL query executed via `execute_query` to `User: <distribution> version: <version> transport: <transport>`, in that order, as space-separated `key: value` tokens (each key followed by a colon and a single space before the value), followed by the request tokens `sub`, `agent`, `model`, `session` and `trace` in that order, each present only when it has a value. Values MUST be reduced to `[A-Za-z0-9._/@-]` (other characters become `_`) and at most 64 characters. The whole string MUST be at most 512 bytes, trimmed by dropping request tokens from the end and never the three leading tokens.

#### Scenario: Renders Composed Comment

- **GIVEN** server name `mcp-hydrolix`, version `0.3.2`, transport `stdio`, and a request with sub `9b2c0c5e-1f0a-4b4e-8a3e-2a1d2c3b4a5f`, agent `claude-code/2.1.0`, model `claude-opus-4-1`, session `sess-1` and a traceparent
- **WHEN** the server executes a query
- **THEN** the `hdx_query_admin_comment` setting equals `User: mcp-hydrolix version: 0.3.2 transport: stdio sub: 9b2c0c5e-1f0a-4b4e-8a3e-2a1d2c3b4a5f agent: claude-code/2.1.0 model: claude-opus-4-1 session: sess-1 trace: <traceparent>`

#### Scenario: Static Prefix Unchanged

- **WHEN** no request field has a value
- **THEN** the setting equals `User: mcp-hydrolix version: 0.3.2 transport: stdio`

#### Scenario: Omits Empty Fields

- **WHEN** `sub` is None and `agent` is empty
- **THEN** neither `sub:` nor `agent:` appears in the setting

#### Scenario: Sanitizes Values

- **WHEN** the agent is `Claude Desktop/1.0 (beta)`, the model is 80 characters long and the session is `a:b`
- **THEN** the setting contains `agent: Claude_Desktop/1.0__beta_`, a 64-character model and `session: a_b`

#### Scenario: Static Identity Survives Budget

- **WHEN** the rendered string would exceed the budget
- **THEN** request tokens are dropped from the end until it fits
- **AND** the three leading tokens are kept even when the budget is smaller than they are

#### Scenario: Comment Built Per Request

- **WHEN** two requests with different bearer credentials execute queries
- **THEN** each query's setting carries that request's `sub`

## ADDED Requirements

### Requirement: Agent Attribution Sources

The server MUST resolve `sub` from the credential the query runs as (the bearer token's `sub` claim, or the basic-auth username) and MUST resolve `agent`, `model`, `session` and `trace` in this precedence: the request headers `X-Hdx-Agent`, `X-Hdx-Model`, `traceparent` and `Mcp-Session-Id`; then the `agent` and `model` keys of the request's MCP `_meta`; then the client name and version from the `initialize` handshake, with the MCP session id as `session` on stdio. Resolution MUST never raise.

#### Scenario: Headers Take Precedence

- **WHEN** the request carries `X-Hdx-Agent: gateway-seen/1.0` and its `_meta` says `agent: meta/9`
- **THEN** `agent` is `gateway-seen/1.0`

#### Scenario: Meta Fallback

- **WHEN** no attribution headers are present and `_meta` carries `agent` and `model`
- **THEN** those values are used and `session` is absent

#### Scenario: Client Info Fallback

- **WHEN** no headers and no `_meta` fields are present on stdio and the `initialize` client info is `claude-code` `2.1.0`
- **THEN** `agent` is `claude-code/2.1.0` and `session` is the MCP session id

#### Scenario: Sub From Basic Credential

- **WHEN** the query runs as basic-auth user `alice`
- **THEN** `sub` is `alice`

#### Scenario: Attribution Never Raises

- **WHEN** reading headers and context both raise
- **THEN** `sub` is still resolved from the credential and the other fields are absent
