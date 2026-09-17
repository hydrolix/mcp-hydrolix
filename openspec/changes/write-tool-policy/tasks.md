*2 phases, 2 tasks.*

**Tracking:** HDX-12410

## 1. Tests

- [x] 1.1 Add `tests/test_write_tool_policy.py` with the write-tool allow-list (empty) and the two scenarios [implements: write-tool-policy/read-only-tool-annotations, design/write-tool-policy-test, meta/tests] — verify: `pytest -q tests/test_write_tool_policy.py` green and `grep -n WRITE_TOOLS_REQUIRING_CONFIRMATION mcp_hydrolix` empty

## 2. Docs
- [x] 2.2 Document the rule in `docs/CONFIG.md` ("Tool policy") [implements: meta/docs] — verify: `grep -n "Tool policy" docs/CONFIG.md` non-empty
