*2 phases, 3 tasks.*

**Tracking:** HDX-12410

## 1. Implementation

- [x] 1.1 Add `WRITE_TOOLS_REQUIRING_CONFIRMATION` to `mcp_hydrolix/mcp_server.py` [implements: write-tool-policy/read-only-tool-annotations, design/write-tool-policy-test] — verify: `grep -n WRITE_TOOLS_REQUIRING_CONFIRMATION mcp_hydrolix/mcp_server.py` non-empty

## 2. Tests and docs

- [x] 2.1 Add `tests/test_write_tool_policy.py` with the two scenarios [implements: write-tool-policy/read-only-tool-annotations, meta/tests] — verify: `pytest -q tests/test_write_tool_policy.py` green
- [x] 2.2 Document the rule in `docs/CONFIG.md` ("Tool policy") [implements: meta/docs] — verify: `grep -n "Tool policy" docs/CONFIG.md` non-empty
