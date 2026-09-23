*Cap what comes back in bytes at the query head; let the deployment decide the cell cap.*

**Tracking:** HDX-12410

## Context

- `execute_query` sends its limits as transport-level settings. Verified live on a Hydrolix query head (qe-innovations-3, v6.4.0-rc.1): `hdx_query_max_result_bytes` sent that way is enforced (code 396, TOO_MANY_ROWS_OR_BYTES) and an unknown `hdx_query_*` parameter is ignored, so an older query head cannot fail on the new setting.
- Also verified there: an inline `SETTINGS` clause outranks the transport-level value (HDX-11717). `strip_conflicting_settings` removes inline collisions for SQL sqlglot can parse; for SQL it cannot parse, an inline override passes, which is the deliberate fail-open behaviour.
- `_resolve_cell_limit` already caps a caller's `max_cells` when `HYDROLIX_MAX_RESULT_CELLS_LIMIT` is positive, including `max_cells=0`; the default stays 0.

## Goals / Non-Goals

- Goals: a byte bound the query head enforces, with a remedy in the error; a cell cap a caller cannot lift where a deployment sets one; no behaviour change by default.
- Non-Goals: choosing thresholds upstream (the maintainer prefers a permissive default and cluster-managed settings); memory limits (the query head's startup configuration owns those).

## Decisions

### Decision: cap-defaults

- **Choice:** `HYDROLIX_MAX_RESULT_CELLS_LIMIT` keeps its default of 0 and the cluster-managed deployment sets 200000; `HYDROLIX_QUERY_MAX_RESULT_BYTES` defaults to 64 MiB with a 10000 floor.
- **Why:** The maintainer's principle is to fail loudly rather than return a partial result an agent may not notice, and the agents expected here (Claude Code, Codex) already page large tool output to files. The cap belongs where its clients are known, the deployment, not upstream. The first cut shipped 200000 upstream; this is the "disagreed but aligned" outcome of its review. The byte cap fails loudly, so it stays as a default. The Config API enforces the 10000 floor.
- **Alternatives:** 200000 upstream — a partial result by default, and a breaking change for `max_cells=0` callers. Match the console's 4 MiB — below what wide results need.
- **Binding:** Both values MUST be read from `HydrolixConfig` properties and validated at construction; the default cell cap MUST stay 0; the server MUST NOT warn about an operator's choice of `0`, since opting in must not produce a warning; `hdx_query_max_result_bytes` MUST be in the base settings dict of every `execute_query` call.

### Decision: cancel-not-truncate

- **Choice:** The byte cap is the query head's own limit, so a query over it fails rather than being trimmed. The remedy lives in the error the agent receives, not in the tool description.
- **Why:** The bytes are counted where the result is built; trimming after the fact would not protect anything. The limits are not tool arguments, so the tool description has nothing for the agent to set; the conditional error is where the guidance is actionable.
- **Alternatives:** Stream and cut — not how the driver reads results. Describe the cap in the tool docstring — spends every call's context on a case that rarely happens (review feedback on the first cut).
- **Binding:** `execute_query` MUST append the remedy when the cluster reports TOO_MANY_ROWS_OR_BYTES; the tool docstring MUST NOT describe the byte cap.

### Decision: brand-aware-messages

- **Choice:** The `HYDROLIX_QUERY_MAX_RESULT_BYTES` validation error names the variable through the baked env prefix, as `_connection_target_hint` does.
- **Why:** A TrafficPeak wheel must not tell its operator to set a `HYDROLIX_*` variable.
- **Binding:** New validation messages MUST use `__env_prefix__`.

## Risks / Trade-offs

- [A caller passes `max_cells=0` on a shared deployment that set no cap] → the deployment sets the cap; upstream stays permissive by the maintainer's decision.
- [Unparseable SQL with an inline `SETTINGS hdx_query_max_result_bytes`] → passes, per the fail-open stripper the maintainer chose to keep.
