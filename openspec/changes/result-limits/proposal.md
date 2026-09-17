*Send a result byte cap with every query, and make the cell cap something a caller can only lower once a deployment sets it.*

**Tracking:** HDX-12410

## Why

The server bounds what reaches the client by cell count but nothing bounds what the query head materialises for it: there is no byte cap. And when an operator does set `HYDROLIX_MAX_RESULT_CELLS_LIMIT`, `max_cells=0` should not switch truncation back off. On a shared HTTP deployment that is one agent's decision about everyone's executor.

## What Changes

- Every query carries `hdx_query_max_result_bytes` (`HYDROLIX_QUERY_MAX_RESULT_BYTES`, default 64 MiB, floor 10000). The query head cancels a query whose result exceeds it, and the error the agent sees says what to do.
- `HYDROLIX_MAX_RESULT_CELLS_LIMIT` keeps its permissive default of 0. When an operator sets it, `max_cells=0` and any value above the cap are reduced to it. The cluster-managed deployment sets 200000.

## Capabilities

### New

- `result-limits` — the byte cap and the caller-lowerable cell cap.

### Modified

*none*

## Impact

- `mcp_hydrolix/mcp_env.py` — `query_max_result_bytes` and its validation (brand-aware message).
- `mcp_hydrolix/mcp_server.py` — one settings entry, the truncation message, the remedy appended to a cancelled query's error.
- `README.md`, `docs/CONFIG.md`.
- No default changes; nothing breaks on upgrade.
