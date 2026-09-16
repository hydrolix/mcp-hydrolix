*Extend the pseudo user-agent every connector writes; never replace it.*

**Tracking:** HDX-12008

## Context

- `execute_query` sets `hdx_query_admin_comment` from a module-level constant, `User: <dist> version: <v> transport: <t>`; every user of a deployment writes the same string.
- The same prefix shape is written by the other Hydrolix connectors and the usage analytics on `hydro.logs` match on it; on a live cluster the column's top value is `User: kibana-gateway`.
- The `hydro.logs` transform is frozen; there are no new columns.
- Inline `SETTINGS` outrank transport-level settings on the Hydrolix query path (verified live, HDX-11717); `strip_conflicting_settings` removes an inline `hdx_query_admin_comment`, so the server's value stands for SQL sqlglot can parse.
- The HTTP transport runs stateless, so a `tools/call` request has no `initialize` client info of its own; a gateway in front of the server is the party that knows the client.

## Goals / Non-Goals

- Goals: per-request attribution of the token subject and the agent, in the existing field, parseable by the existing `LIKE` and regex consumers, never a query failure.
- Non-Goals: verifying identity (the gateway does); a new column; changing `execute_cmd` (catalog commands stay unattributed).

## Decisions

### Decision: keep-connector-format

- **Choice:** Keep `User: <dist> version: <v> transport: <t>` byte-for-byte and append further `key: value` tokens.
- **Why:** The maintainer asked for it in the 2026-09-16 review: the prefix and the colon separators are what the existing analytics are built around, and the same shape is shared with the other connectors.
- **Alternatives:** `key=value` tokens (the earlier draft) — breaks the existing queries for no functional gain.
- **Binding:** `HDX_ADMIN_COMMENT` MUST equal the legacy string; `build_admin_comment` MUST render the static tokens first and MUST never drop them.

### Decision: sub-key

- **Choice:** The identity field is keyed `sub`.
- **Why:** It is the token's subject claim, the join key the gateway's audit log and the cluster's external identities use; `User:` already names the application; "principal" is ambiguous between subject and actor under RFC 8693 delegation, and an `act` token can be added beside `sub` later without renaming anything.
- **Alternatives:** `user` — collides with `User:` and, in the gateway's audit vocabulary, means the display name. `principal` — the ambiguity above.
- **Binding:** `REQUEST_FIELDS` MUST start with `sub`; the value MUST be the credential's `sub` claim or basic-auth username.

### Decision: separators-excluded-from-values

- **Choice:** Values are reduced to `[A-Za-z0-9._/@-]`, other characters become `_`, 64 characters each; the whole string is capped at 512 bytes by dropping request tokens from the end.
- **Why:** Colon and space are the separators; a value containing either would break a regex on `key: `. 64 characters fit a UUID, a `<client>/<version>` and a `traceparent`.
- **Alternatives:** Quote values — the existing consumers do not unquote. No cap — the setting is a log column, not a blob.
- **Binding:** `sanitize_value` MUST enforce the alphabet and length; `build_admin_comment` MUST enforce the byte budget.

### Decision: attribution-best-effort

- **Choice:** `gather_request_attribution` never raises; sources in precedence order are gateway headers, request `_meta`, then `initialize` client info.
- **Why:** Attribution is observability; a missing header must not fail a query. Headers win because the gateway is the trusted party; `_meta` and client info are client-supplied.
- **Alternatives:** Require the header — breaks stdio. Trust `_meta` over headers — lets an agent overwrite what the gateway saw.
- **Binding:** `execute_query` MUST build the comment from `_APP_IDENTITY` plus the gathered fields on every call.

## Risks / Trade-offs

- [Stateless HTTP has no `initialize` client info] → `agent` comes from `X-Hdx-Agent` when a gateway sets it; otherwise `trace` and `session` join with the gateway's audit log.
- [Unparseable SQL with an inline `SETTINGS hdx_query_admin_comment`] → passes, per the deliberate fail-open stripper; the maintainer accepted that trade.
