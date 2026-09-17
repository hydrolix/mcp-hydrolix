*3 phases, 5 tasks.*

**Tracking:** HDX-12410

## 1. Implementation

- [x] 1.1 Add `query_max_result_bytes` with its floor validation and a brand-aware message; leave the `max_result_cells_limit` default at 0 and emit no warning about it [implements: result-limits/result-byte-cap, result-limits/caller-lowerable-cell-cap, design/cap-defaults, design/brand-aware-messages] — verify: `pytest -q tests/test_result_limits.py -k "byte_cap or default_cell_cap"` green
- [x] 1.2 Send `hdx_query_max_result_bytes` in the base settings of `execute_query`; append the remedy to a TOO_MANY_ROWS_OR_BYTES error; keep the byte cap out of the tool docstring [implements: result-limits/result-byte-cap, result-limits/cancelled-result-carries-a-remedy, design/cancel-not-truncate] — verify: `grep -n hdx_query_max_result_bytes mcp_hydrolix/mcp_server.py` non-empty and `grep -n "byte cap" mcp_hydrolix/mcp_server.py` shows no docstring hit

## 2. Tests

- [x] 2.1 `tests/test_result_limits.py` covers every scenario above [implements: meta/tests] — verify: `pytest -q tests/test_result_limits.py` green

## 3. Docs and rollout

- [x] 3.1 Document both variables in `docs/CONFIG.md` and the caller-lowerable `max_cells` in `README.md` [implements: meta/docs] — verify: `grep -n HYDROLIX_QUERY_MAX_RESULT_BYTES docs/CONFIG.md` non-empty
- [ ] 3.2 Cluster-managed deployments set `HYDROLIX_MAX_RESULT_CELLS_LIMIT=200000` (hkt, separate turbine PR) [implements: design/cap-defaults] — verify: the mcp-hydrolix Deployment on a managed cluster carries the variable
