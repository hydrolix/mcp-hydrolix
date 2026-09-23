*3 phases, 5 tasks.*

**Tracking:** HDX-12008

## 1. Implementation

- [x] 1.1 Add `mcp_hydrolix/attribution.py` as a pure module: `build_admin_comment`, `render_admin_comment`, `sanitize_value`, `RequestAttribution`, `resolve_request_attribution` [implements: query-admin-comment/query-comment-composition, query-admin-comment/agent-attribution-sources, design/keep-connector-format, design/separators-excluded-from-values, design/meta-key-namespace] — verify: `grep -n fastmcp mcp_hydrolix/attribution.py` empty
- [x] 1.2 Add `mcp_hydrolix/middlewares/request_attribution.py`: `RequestAttributionMiddleware`, `attribution_for`, `current_attribution` over a context variable; register the middleware in `mcp_server.py` [implements: query-admin-comment/agent-attribution-sources, design/resolve-once-per-request, design/session-per-transport] — verify: `grep -n RequestAttributionMiddleware mcp_hydrolix/mcp_server.py` non-empty
- [x] 1.3 Add `HydrolixCredential.subject`; in `execute_query` resolve the credential once, pass it to `create_hydrolix_client`, and render the comment from `HDX_ADMIN_COMMENT`, `current_attribution()` and `credential.subject` [implements: query-admin-comment/sub-from-the-authenticating-credential, design/sub-from-authenticating-credential] — verify: `pytest -q tests/test_query_settings.py tests/test_query_admin_comment.py::TestCommentBuiltPerRequest` green
- [x] 1.4 Keep `sub` out of `RequestAttribution`: the type holds `AGENT_FIELDS` only and `render_admin_comment(prefix, sub, request)` takes the subject at render time [implements: query-admin-comment/query-comment-composition, design/type-holds-only-the-agent-half] — verify: `pytest -q tests/test_query_admin_comment.py::TestQueryCommentComposition::test_fields_match_vocabulary` green

## 2. Tests

- [x] 2.1 Composition and credential scenarios in `tests/test_query_admin_comment.py` [implements: query-admin-comment/query-comment-composition, query-admin-comment/sub-from-the-authenticating-credential, meta/tests] — verify: `pytest -q tests/test_query_admin_comment.py` green
- [x] 2.2 Source and once-per-request scenarios in `tests/test_request_attribution.py` [implements: query-admin-comment/agent-attribution-sources, meta/tests] — verify: `pytest -q tests/test_request_attribution.py` green

## 3. Docs

- [x] 3.1 Document the format, the `sub` key and the sources in `docs/CONFIG.md` "Query attribution" [implements: meta/docs] — verify: `grep -n "X-Hdx-Agent" docs/CONFIG.md` non-empty
