*3 phases, 5 tasks.*

**Tracking:** HDX-12008

## 1. Implementation

- [x] 1.1 Add `mcp_hydrolix/attribution.py`: `build_admin_comment`, `sanitize_value`, `RequestAttribution`, `gather_request_attribution` [implements: query-admin-comment/query-comment-composition, query-admin-comment/agent-attribution-sources, design/keep-connector-format, design/sub-key, design/separators-excluded-from-values, design/attribution-best-effort] — verify: `ruff check mcp_hydrolix/attribution.py` clean
- [x] 1.2 Build `HDX_ADMIN_COMMENT` from `_APP_IDENTITY` and the per-request comment in `execute_query` [implements: query-admin-comment/query-comment-composition] — verify: `grep -n _admin_comment_for_request mcp_hydrolix/mcp_server.py` non-empty and `pytest -q tests/test_query_settings.py` green

## 2. Tests

- [x] 2.1 Composition scenarios in `tests/test_query_admin_comment.py::TestQueryCommentComposition` [implements: query-admin-comment/query-comment-composition, meta/tests] — verify: `pytest -q tests/test_query_admin_comment.py::TestQueryCommentComposition` green
- [x] 2.2 Source scenarios in `tests/test_query_admin_comment.py::TestAgentAttributionSources` [implements: query-admin-comment/agent-attribution-sources, meta/tests] — verify: `pytest -q tests/test_query_admin_comment.py::TestAgentAttributionSources` green

## 3. Docs

- [x] 3.1 Document the format, the `sub` key and the sources in `docs/CONFIG.md` "Query attribution" [implements: meta/docs] — verify: `grep -n "X-Hdx-Agent" docs/CONFIG.md` non-empty
