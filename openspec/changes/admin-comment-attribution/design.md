*Extend the pseudo user-agent every connector writes; never replace it. Resolve the request half once, in the protocol layer.*

**Tracking:** HDX-12008

## Context

- `execute_query` sets `hdx_query_admin_comment` from a module-level constant, `User: <dist> version: <v> transport: <t>`; every user of a deployment writes the same string.
- The same prefix shape is written by the other Hydrolix connectors and the usage analytics on `hydro.logs` match on it; on a live cluster the column's top value is `User: kibana-gateway`.
- The `hydro.logs` transform is frozen; there are no new columns. It does carry a `user` column beside `hdx_query_admin_comment`, which the query head fills from the authenticated credential; today it is empty for service-account queries.
- Inline `SETTINGS` outrank transport-level settings on the Hydrolix query path (verified live, HDX-11717); `strip_conflicting_settings` removes an inline `hdx_query_admin_comment`, so the server's value stands for SQL sqlglot can parse.
- The HTTP transport runs stateless, so a `tools/call` request has no `initialize` client info of its own; a gateway in front of the server is the party that knows the client. One tool call issues several queries (a DESCRIBE per referenced table plus the statement).
- FastMCP's `get_http_headers` never raises and lowercases names; `Context.session_id` returns the `Mcp-Session-Id` header when an HTTP request carries one and otherwise generates a UUID cached on the session object.

## Goals / Non-Goals

- Goals: per-request attribution of the token subject and the agent, in the existing field, parseable by the existing `LIKE` and regex consumers, resolved once per request, never a query failure.
- Non-Goals: verifying identity (the gateway does); a new column; changing `execute_cmd` (catalog commands stay unattributed).

## Decisions

### Decision: keep-connector-format

- **Choice:** Keep `User: <dist> version: <v> transport: <t>` byte-for-byte and append further `key: value` tokens.
- **Why:** The maintainer asked for it in the 2026-09-16 review: the prefix and the colon separators are what the existing analytics are built around, and the same shape is shared with the other connectors.
- **Alternatives:** `key=value` tokens (the earlier draft) — breaks the existing queries for no functional gain.
- **Binding:** `HDX_ADMIN_COMMENT` MUST equal the legacy string and MUST be the prefix `render_admin_comment` appends to; the prefix is never dropped and never re-sanitized per query.

### Decision: sub-from-authenticating-credential

- **Choice:** Keep `sub`, keyed `sub`, and take it from `HydrolixCredential.subject` of the credential object that `execute_query` hands to the client for that query.
- **Why:** The maintainer's concern is conflicting records of who ran a query, not the field itself; deriving `sub` from the very credential that authenticates the query makes the two records identical by construction, in every deployment mode. It is the token's subject claim, the join key the gateway's audit log and the cluster's external identities use; `User:` already names the application; "principal" is ambiguous between subject and actor under RFC 8693 delegation, and an `act` token can be added beside `sub` later. Today `hydro.logs.user` is empty for service-account queries, so `sub` is also the only principal on those rows.
- **Alternatives:** `user` — collides with `User:` and, in the gateway's audit vocabulary, means the display name. `principal` — the ambiguity above. Drop the field — the principled reading of "the query head owns who", but it leaves service-account rows without a principal until core logs them. Duck-typing `service_account_id` or `username` — a new credential type would silently yield no `sub`.
- **Binding:** Every `HydrolixCredential` MUST implement `subject`; `execute_query` MUST resolve the credential once, pass that object to `create_hydrolix_client`, and take `sub` from it; `hydro.logs.user` is documented as authoritative when present.

### Decision: separators-excluded-from-values

- **Choice:** Values are reduced to `[A-Za-z0-9._/@-]`, other characters become `_`, 64 characters each; the whole string is capped at 512 bytes by dropping request tokens from the end, with `REQUEST_FIELDS` ordered `sub, agent, session, trace, model` so `model` goes first and the join keys last.
- **Why:** Colon and space are the separators; a value containing either would break a regex on `key: `. 64 characters fit a UUID, a `<client>/<version>` and a `traceparent`. Eight 64-character values render to 580 bytes, so the cap can bite; when it does, the descriptive `model` is the right token to lose.
- **Alternatives:** Quote values — the existing consumers do not unquote. No cap — the setting is a log column, not a blob.
- **Binding:** `sanitize_value` MUST enforce the alphabet and length; `render_admin_comment` MUST enforce the byte budget; a test MUST pin `RequestAttribution`'s fields to `AGENT_FIELDS` and `REQUEST_FIELDS` to `sub` followed by them.

### Decision: type-holds-only-the-agent-half

- **Choice:** `RequestAttribution` carries `agent`, `session`, `trace` and `model`, each independently optional; `sub` is not a field. `render_admin_comment(prefix, sub, request)` takes the subject from the credential at render time.
- **Why:** Review of #148 asked which combinations of the fields are valid. Every field the type keeps is genuinely independent: each has its own source and can be absent on its own, and `session` follows the transport. `sub` was the one field that was always empty at construction and filled in later, so a middleware-produced value carrying a subject was representable but never valid; removing the field removes the state.
- **Alternatives:** Keep `sub` with `with_sub`: the invalid state above. Encode the transport in the type so `session` is non-optional on stdio and SSE: a sum type for one field, more machinery than two log columns justify.
- **Binding:** `RequestAttribution` MUST NOT have a `sub` field; a test MUST pin its fields to `AGENT_FIELDS`.

### Decision: resolve-once-per-request

- **Choice:** `attribution.py` is pure (vocabulary, sanitizer, renderer, a resolver over extracted inputs). `RequestAttributionMiddleware.on_request` reads the headers, the request's `_meta`, the `initialize` client info and the session id once, stores a `RequestAttribution` in a context variable, and resets it after the request; `execute_query` renders it together with the credential's subject.
- **Why:** The middleware is the one place where "this is the request's `_meta`" is unambiguous; a tool call issues several queries and should not walk headers and session state for each; and the pure module is testable without faking three layers of MCP internals. `get_http_headers` never raises, so no guard is needed around it; only the session attribute chains are guarded.
- **Alternatives:** Resolve inside `execute_query` from ambient FastMCP state (the first cut) — transport policy in the application layer, N+1 resolutions per tool call, tests that fake framework internals.
- **Binding:** `execute_query` MUST NOT touch headers, `_meta` or the session; it MUST build the comment from `HDX_ADMIN_COMMENT`, `current_attribution()` and the credential's `subject`. Headers win over `_meta`, which wins over client info.

### Decision: session-per-transport

- **Choice:** `session` is `ctx.session_id` on `stdio` and `sse` only, and absent on `streamable-http`.
- **Why:** On stdio and SSE the session object lives for the client connection, so the id groups one agent run, even though FastMCP generates it server-side and the client never sees it. On the stateless streamable-HTTP app FastMCP would mint a fresh UUID per request unless the client sends `Mcp-Session-Id`, which is pure log cardinality; there `trace` is the join key. Reading `Mcp-Session-Id` directly is left to FastMCP (review feedback).
- **Alternatives:** Gate on the configured transport string — silently dropped SSE and used the config's vocabulary for a runtime fact. Read the header ourselves — a protocol detail FastMCP already owns.
- **Binding:** The gate MUST use `ctx.transport`; the docs MUST say what `session` means per transport.

### Decision: meta-key-namespace

- **Choice:** Read `io.hydrolix/agent` and `io.hydrolix/model` from the request's `_meta`, falling back to the bare `agent` and `model` keys.
- **Why:** MCP recommends reverse-DNS prefixes for application keys, and `agent`/`model` are the two names most likely to be claimed by a future spec or client.
- **Alternatives:** Bare keys only — a collision silently changes meaning.
- **Binding:** Prefixed keys MUST win over bare ones.

## Risks / Trade-offs

- [Stateless HTTP has no `initialize` client info] → `agent` comes from `X-Hdx-Agent` when a gateway sets it; otherwise `trace` joins with the gateway's audit log.
- [A client sets `X-Hdx-Agent` or `_meta` itself] → recorded as attested by the client; sanitization bounds the blast radius to log pollution. The docs say so.
- [Core starts filling `hydro.logs.user` for service accounts] → two records of the same identity, possibly a UUID beside a name; the docs name `user` as authoritative.
- [Unparseable SQL with an inline `SETTINGS hdx_query_admin_comment`] → passes, per the deliberate fail-open stripper; the maintainer accepted that trade.
