*Remove a trailing FORMAT clause, a trailing semicolon and comments from user SQL before the driver adds its own FORMAT clause.*

**Tracking:** HDX-12410

## Why

clickhouse-connect appends `FORMAT Native` to every query it sends. When an agent ends its statement with `FORMAT JSON` (a common habit), the cluster receives two FORMAT clauses and refuses the statement with code 62. The maintainer reports this as the most common failure in day-to-day use of the server. A trailing semicolon followed by a comment fails the same way, as a multi-statement.

## What Changes

- New module `mcp_hydrolix/statement.py`: a comment-, literal- and quote-aware scanner that follows ClickHouse's lexer, and `normalize_statement`, which drops comments, one trailing semicolon and one trailing top-level `FORMAT <name>`.
- `run_select_query` normalises the statement before the LIMIT rewrite; nothing else about the statement changes, and inner semicolons are left alone.

## Capabilities

### New

- `query-text-handling` — what the server removes from user SQL before execution, and what it never touches.

### Modified

*none*

## Impact

- `mcp_hydrolix/statement.py` (new), `mcp_hydrolix/mcp_server.py` (one call at the top of `run_select_query`).
- `README.md`, `docs/CONFIG.md`.
- No new dependencies. No change to `execute_query` or to the SETTINGS stripper.
