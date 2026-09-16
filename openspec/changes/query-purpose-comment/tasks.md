*2 phases, 3 tasks.*

**Tracking:** HDX-12008

## 1. Implementation

- [x] 1.1 Add `sanitize_purpose` and `PURPOSE_MAX_CHARS` to `mcp_hydrolix/utils.py` [implements: query-admin-comment/query-purpose-comment] — verify: `pytest -q tests/test_query_purpose.py::TestSanitizePurpose` green
- [x] 1.2 Add `comment` to `execute_query` and `purpose` to `run_select_query`, forwarding one to the other [implements: query-admin-comment/query-purpose-comment, design/purpose-as-tool-argument] — verify: `pytest -q tests/test_query_purpose.py::TestQueryPurposeComment` green

## 2. Docs

- [x] 2.1 Document the `purpose` input in `README.md` and `hdx_query_comment` in `docs/CONFIG.md` [implements: meta/docs] — verify: `grep -n purpose README.md docs/CONFIG.md` non-empty
