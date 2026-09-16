*Record the caller's stated purpose with every user query as `hdx_query_comment`.*

**Tracking:** HDX-12008

## Why

Operators reading `hydro.logs` can see which server ran a query but not why an agent ran it. `hdx_query_comment` already lands in `hydro.logs` and `hdx.active_queries` and is the field meant for exactly this; today the server never sets it.

## What Changes

- `run_select_query` gains an optional `purpose` argument.
- `execute_query` sends `hdx_query_comment` when a purpose is given: whitespace collapsed, capped at 256 characters, omitted when empty.

## Capabilities

### New

*none*

### Modified

- `query-admin-comment` — adds the Query Purpose Comment requirement.

## Impact

- `mcp_hydrolix/utils.py` — `sanitize_purpose`, `PURPOSE_MAX_CHARS`.
- `mcp_hydrolix/mcp_server.py` — `execute_query(comment=)`, `run_select_query(purpose=)`.
- `README.md`, `docs/CONFIG.md` — the new input and the setting it maps to.
- No new dependencies; no change to any existing query setting.
