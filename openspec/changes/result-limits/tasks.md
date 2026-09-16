*3 phases, 5 tasks.*

**Tracking:** HDX-12410

## 1. Implementation

- [x] 1.1 Add `query_max_result_bytes` with its floor validation, change the `max_result_cells_limit` default to 200000, and warn at construction when it is 0 on http or sse [implements: result-limits/result-byte-cap, result-limits/caller-lowerable-cell-cap, design/cap-defaults] — verify: `pytest -q tests/test_result_limits.py -k "byte_cap or default_cell_cap or zero_limit_warns"` green
- [x] 1.2 Send `hdx_query_max_result_bytes` in the base settings of `execute_query`; reword the truncation message and the tool docstring [implements: result-limits/result-byte-cap, design/cancel-not-truncate] — verify: `grep -n hdx_query_max_result_bytes mcp_hydrolix/mcp_server.py` non-empty

## 2. Tests

- [x] 2.1 `tests/test_result_limits.py` covers every scenario above [implements: meta/tests] — verify: `pytest -q tests/test_result_limits.py` green

## 3. Docs and release

- [x] 3.1 Document both variables in `docs/CONFIG.md` and the caller-lowerable `max_cells` in `README.md` [implements: meta/docs] — verify: `grep -n HYDROLIX_QUERY_MAX_RESULT_BYTES docs/CONFIG.md` non-empty
- [ ] 3.2 Release notes carry `Breaking: HYDROLIX_MAX_RESULT_CELLS_LIMIT now defaults to 200000; set 0 for the previous behaviour` [implements: meta/rollout] — verify: the annotated tag message lists it
