*Cap what comes back, in bytes at the query head and in cells at the client.*

**Tracking:** HDX-12410

## Context

- `execute_query` sends its limits as transport-level settings. Verified live on a Hydrolix query head (qe-innovations-3, v6.4.0-rc.1): `hdx_query_max_result_bytes` sent that way is enforced (code 396, TOO_MANY_ROWS_OR_BYTES) and an unknown `hdx_query_*` parameter is ignored, so an older query head cannot fail on the new setting.
- Also verified there: an inline `SETTINGS` clause outranks the transport-level value (HDX-11717). `strip_conflicting_settings` removes inline collisions for SQL sqlglot can parse; for SQL it cannot parse, an inline override passes, which is the deliberate fail-open behaviour.
- `_resolve_cell_limit` already caps a caller's `max_cells` when `HYDROLIX_MAX_RESULT_CELLS_LIMIT` is positive; only the default and the `max_cells=0` case change.

## Goals / Non-Goals

- Goals: a byte bound the query head enforces; a cell cap a caller cannot lift by default; the old behaviour one variable away.
- Non-Goals: choosing thresholds by argument (the maintainer prefers adjusting them on feedback); memory limits (the query head's startup configuration owns those).

## Decisions

### Decision: cap-defaults

- **Choice:** `HYDROLIX_MAX_RESULT_CELLS_LIMIT` defaults to 200000; `HYDROLIX_QUERY_MAX_RESULT_BYTES` defaults to 64 MiB with a 10000 floor.
- **Why:** The cell cap already bounds what reaches the client; the byte cap protects the executor's memory on a wide result and rarely triggers. 200000 cells is a generous ceiling for most agents. The Config API enforces the 10000 floor.
- **Alternatives:** Keep 0 — `max_cells=0` disables truncation for any caller. Match the console's 4 MiB — below what 200000 cells of wide rows need. Debate the number up front — the maintainer would rather change it on complaint; the release notes name the variable so that is a configuration change.
- **Binding:** Both values MUST be read from `HydrolixConfig` properties and validated at construction; `hdx_query_max_result_bytes` MUST be in the base settings dict of every `execute_query` call.

### Decision: cancel-not-truncate

- **Choice:** The byte cap is the query head's own limit, so a query over it fails rather than being trimmed; the tool docstring says so and tells the agent what to do.
- **Why:** The bytes are counted where the result is built; trimming after the fact would not protect anything.
- **Alternatives:** Stream and cut — not how the driver reads results.
- **Binding:** The tool docstring MUST describe the cancel and the remedy.

## Risks / Trade-offs

- [A caller relying on `max_cells=0`] → the release notes name `HYDROLIX_MAX_RESULT_CELLS_LIMIT=0` as the way back.
- [Unparseable SQL with an inline `SETTINGS hdx_query_max_result_bytes`] → passes, per the fail-open stripper the maintainer chose to keep.
