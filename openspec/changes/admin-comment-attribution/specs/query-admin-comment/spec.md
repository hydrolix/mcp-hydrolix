## MODIFIED Requirements

### Requirement: Query Comment Composition

The server MUST set `hdx_query_admin_comment` on every SQL query executed via `execute_query` to `User: <distribution> version: <version> transport: <transport>`, in that order, as space-separated `key: value` tokens (each key followed by a colon and a single space before the value), followed by the request tokens `sub`, `agent`, `session`, `trace` and `model` in that order, each present only when it has a value. Values MUST be reduced to `[A-Za-z0-9._/@-]` (other characters become `_`) and at most 64 characters. The whole string MUST be at most 512 bytes, trimmed by dropping request tokens from the end (`model` first) and never the three leading tokens. The fields of `RequestAttribution` MUST equal the request token vocabulary.

#### Scenario: Renders Composed Comment

- **GIVEN** server name `mcp-hydrolix`, version `0.3.2`, transport `stdio`, and a request with sub `9b2c0c5e-1f0a-4b4e-8a3e-2a1d2c3b4a5f`, agent `claude-code/2.1.0`, model `claude-opus-4-1`, session `sess-1` and a traceparent
- **WHEN** the server executes a query
- **THEN** the `hdx_query_admin_comment` setting equals `User: mcp-hydrolix version: 0.3.2 transport: stdio sub: 9b2c0c5e-1f0a-4b4e-8a3e-2a1d2c3b4a5f agent: claude-code/2.1.0 session: sess-1 trace: <traceparent> model: claude-opus-4-1`

#### Scenario: Static Prefix Unchanged

- **WHEN** no request field has a value
- **THEN** the setting equals `User: mcp-hydrolix version: 0.3.2 transport: stdio`

#### Scenario: Omits Empty Fields

- **WHEN** `sub` is None and `agent` is empty
- **THEN** neither `sub:` nor `agent:` appears in the setting

#### Scenario: Sanitizes Values

- **WHEN** the agent is `Claude Desktop/1.0 (beta)`, the model is 80 characters long and the session is `a:b`
- **THEN** the setting contains `agent: Claude_Desktop/1.0__beta_`, a 64-character model and `session: a_b`

#### Scenario: Budget Drops Model Before Join Keys

- **WHEN** the rendered string would exceed the budget
- **THEN** `model` is dropped before `trace` and `session`
- **AND** the three leading tokens are kept even when the budget is smaller than they are

#### Scenario: Fields Match Vocabulary

- **WHEN** `RequestAttribution` is inspected
- **THEN** its field names equal the request token vocabulary

### Requirement: Sub From The Authenticating Credential

Every `HydrolixCredential` MUST expose `subject`: a token's `sub` claim or the basic-auth username. `execute_query` MUST resolve the credential once, authenticate the query with that object, and take `sub` from its `subject`, so the comment and the query head can never disagree about who ran the query.

#### Scenario: Comment Built Per Request

- **WHEN** two requests with different bearer credentials execute queries
- **THEN** each query's setting carries that request's `sub`

#### Scenario: Client Authenticates With The Attributed Credential

- **WHEN** a query executes
- **THEN** the credential object handed to the client is the one whose `subject` the comment carries

#### Scenario: Sub From Basic Credential

- **WHEN** the query runs as basic-auth user `alice`
- **THEN** `sub` is `alice`

## ADDED Requirements

### Requirement: Agent Attribution Sources

The server MUST resolve `agent`, `model`, `session` and `trace` once per MCP request, in the protocol layer, in this precedence: the request headers `X-Hdx-Agent`, `X-Hdx-Model` and `traceparent`; then the `io.hydrolix/agent` and `io.hydrolix/model` keys of the request's MCP `_meta`, with the bare `agent` and `model` keys as a fallback; then the client name and version from the `initialize` handshake. `session` MUST be the server's session id on `stdio` and `sse` and MUST be absent on `streamable-http`. Resolution MUST never raise, and every query the request issues MUST read the same resolved values.

#### Scenario: Headers Take Precedence

- **WHEN** the request carries `X-Hdx-Agent: gateway-seen/1.0` and its `_meta` says `io.hydrolix/agent: meta/9`
- **THEN** `agent` is `gateway-seen/1.0`

#### Scenario: Prefixed Meta Keys Then Bare

- **WHEN** no attribution headers are present and `_meta` carries `io.hydrolix/agent`, `agent` and `model`
- **THEN** `agent` is the prefixed value and `model` is the bare value

#### Scenario: Client Info Fallback And Stdio Session

- **WHEN** no headers and no `_meta` fields are present on stdio and the `initialize` client info is `claude-code` `2.1.0`
- **THEN** `agent` is `claude-code/2.1.0` and `session` is the server's session id

#### Scenario: Stateless HTTP Has No Session

- **WHEN** the transport is `streamable-http`
- **THEN** `session` is absent

#### Scenario: Session Fields Failing Do Not Fail Attribution

- **WHEN** reading the session's transport or client info raises
- **THEN** the header-derived fields are still resolved and `session` is absent

#### Scenario: Resolved Once Per Request

- **WHEN** the middleware wraps a request
- **THEN** the resolved attribution is visible to the request's queries and is reset afterwards, including when the request fails
