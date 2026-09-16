*Per-request `key=value` admin comment naming the principal and the agent; purpose comment and static label added.*

## MODIFIED Requirements

### Requirement: Query Comment Composition

The server MUST set `hdx_query_admin_comment` on every SQL query executed via `execute_query`, built per request from `app=<dist>/<version>`, `transport=<transport>`, `user=<sub of the bearer credential>`, `agent=<client>/<version>`, `model=<model>`, `session=<mcp session id>` and `trace=<traceparent>`, in that order, as space-separated `key=value` tokens. Values MUST be reduced to `[A-Za-z0-9._:/@-]` (other bytes become `_`) and 64 characters; a field with no value MUST be omitted; the string MUST not exceed 512 bytes, dropping trailing fields first.
<!-- settle: explore/no-schema-change -->
<!-- settle: explore/attribution-vocabulary -->

#### Scenario: Renders Composed Comment

- **GIVEN** app `mcp-hydrolix/0.3.2`, transport `stdio`, a user sub, agent `claude-code/2.1.0`, model `claude-opus-4-1`, session `sess-1` and a traceparent
- **WHEN** the comment is built
- **THEN** it equals `app=mcp-hydrolix/0.3.2 transport=stdio user=<sub> agent=claude-code/2.1.0 model=claude-opus-4-1 session=sess-1 trace=<traceparent>`

#### Scenario: Omits Empty Fields

- **GIVEN** no user and an empty agent
- **WHEN** the comment is built
- **THEN** it contains neither `user=` nor `agent=`

#### Scenario: Sanitizes Values

- **GIVEN** an agent containing spaces and parentheses and a model of 80 characters
- **WHEN** the comment is built
- **THEN** the disallowed characters are `_` and the model is cut to 64 characters

#### Scenario: Caps Comment At Budget

- **GIVEN** seven fields of 64 characters and a budget smaller than their total
- **WHEN** the comment is built
- **THEN** it fits the budget and the trailing fields are the ones dropped

#### Scenario: Comment Built Per Request

- **GIVEN** a request carrying a bearer credential with a `sub`
- **WHEN** `execute_query` runs
- **THEN** the `hdx_query_admin_comment` sent starts with `app=mcp-hydrolix/` and contains `user=<that sub>`

## ADDED Requirements

### Requirement: Query Purpose Comment

`run_select_query` MUST accept an optional `purpose` and `execute_query` MUST send it as `hdx_query_comment`, whitespace-collapsed and cut to 256 characters; without a purpose the key MUST be absent.
<!-- settle: explore/attribution-vocabulary -->

#### Scenario: Purpose Sets Query Comment

- **WHEN** `execute_query` runs with a purpose containing extra whitespace
- **THEN** the settings sent contain `hdx_query_comment` equal to the collapsed text

#### Scenario: Purpose Truncated To Budget

- **WHEN** a purpose of 1000 characters is sanitized
- **THEN** the result is 256 characters long

#### Scenario: No Purpose No Comment

- **WHEN** `execute_query` runs without a purpose
- **THEN** the settings sent contain no `hdx_query_comment`

### Requirement: Query Label

When `HYDROLIX_QUERY_LABEL` is set, `execute_query` MUST send it as the transport-level `hdx_query_label` setting on every query and MUST NOT write it into the SQL text; by default no label is sent; startup MUST reject a label outside `[A-Za-z0-9._-]{1,64}`.
<!-- settle: explore/attribution-vocabulary -->

#### Scenario: Label Sent As Transport Setting When Configured

- **GIVEN** `HYDROLIX_QUERY_LABEL=mcp`
- **WHEN** `execute_query` runs
- **THEN** the settings sent contain `hdx_query_label` equal to `mcp`
- **AND** the SQL text is unchanged

#### Scenario: Label Absent By Default

- **GIVEN** `HYDROLIX_QUERY_LABEL` unset
- **WHEN** `execute_query` runs
- **THEN** the settings sent contain no `hdx_query_label`

#### Scenario: Label Rejects Unsafe Value

- **GIVEN** `HYDROLIX_QUERY_LABEL` containing a quote or a space
- **WHEN** the configuration is constructed
- **THEN** it raises `ValueError` naming the variable

### Requirement: Agent Attribution Sources

The agent fields MUST be resolved best-effort in this precedence: request headers `X-Hdx-Agent`, `X-Hdx-Model`, `traceparent` and `Mcp-Session-Id`; then the request's MCP `_meta` keys `agent` and `model`; then the session's `initialize` client info for `agent` and, on stdio, the session id. `user` MUST be the `sub` of a bearer credential or the username of a basic-auth credential. Resolution MUST never raise.

#### Scenario: Headers Take Precedence

- **GIVEN** headers, `_meta` and client info all present
- **WHEN** attribution is gathered
- **THEN** agent, model, trace and session come from the headers and user from the credential

#### Scenario: Meta Fallback

- **GIVEN** no headers and `_meta` carrying agent and model
- **WHEN** attribution is gathered
- **THEN** agent and model come from `_meta` and session is absent

#### Scenario: Client Info Fallback

- **GIVEN** no headers, no `_meta`, client info `claude-code` `2.1.0`, and the stdio transport
- **WHEN** attribution is gathered
- **THEN** agent is `claude-code/2.1.0` and session is the context session id

#### Scenario: User From Basic Credential

- **GIVEN** a username and password credential
- **WHEN** attribution is gathered
- **THEN** user is the username

#### Scenario: Attribution Never Raises

- **GIVEN** the header and context helpers raise
- **WHEN** attribution is gathered
- **THEN** the result carries the user and no agent fields, and no exception escapes
