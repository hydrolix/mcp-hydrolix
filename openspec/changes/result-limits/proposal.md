*Send a result byte cap with every query and make the cell cap something a caller can only lower.*

**Tracking:** HDX-12410

## Why

The server bounds what reaches the client by cell count but nothing bounds what the query head materialises for it: there is no byte cap, and `HYDROLIX_MAX_RESULT_CELLS_LIMIT` defaults to 0, so any caller can pass `max_cells=0` and switch truncation off. On a shared HTTP deployment that is one agent's decision about everyone's executor.

## What Changes

- Every query carries `hdx_query_max_result_bytes` (`HYDROLIX_QUERY_MAX_RESULT_BYTES`, default 64 MiB, floor 10000). The query head cancels a query whose result exceeds it.
- **BREAKING** `HYDROLIX_MAX_RESULT_CELLS_LIMIT` defaults to 200000 instead of 0; `max_cells=0` and any value above the cap are reduced to it. `0` restores the old behaviour, and the server warns when it sees `0` on http or sse.

## Capabilities

### New

- `result-limits` — the byte cap and the caller-lowerable cell cap.

### Modified

*none*

## Impact

- `mcp_hydrolix/mcp_env.py` — `query_max_result_bytes`, the new default and validation, one startup warning.
- `mcp_hydrolix/mcp_server.py` — one settings entry, the truncation message, the tool docstring.
- `README.md`, `docs/CONFIG.md`.
- Release notes carry the `Breaking:` entry for the default change.
