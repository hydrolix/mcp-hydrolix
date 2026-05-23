*2 phases, 9 tasks (3 implementation, 6 tests); ends with full test-suite green.*

**Tracking:** HDX-11481

## 1. Implementation

- [ ] 1.1 Add `_resolve_server_version()` helper at module scope in `mcp_hydrolix/mcp_server.py` that returns `importlib.metadata.version("mcp-hydrolix")` or, on `PackageNotFoundError`, logs a warning and returns the literal string `unknown` [implements: query-admin-comment/version-resolution, design/version-from-importlib-metadata, explore/version-fallback] — verify: `ruff check mcp_hydrolix/mcp_server.py` clean
- [ ] 1.2 Add module-level constant `HDX_ADMIN_COMMENT` assembled once at import as `f"User={MCP_SERVER_NAME}; version={_resolve_server_version()}; transport={HYDROLIX_CONFIG.mcp_server_transport}"` [implements: query-admin-comment/query-comment-composition, query-admin-comment/transport-resolution, design/precompute-comment-at-startup, design/transport-from-config, explore/comment-format] — verify: `ruff check mcp_hydrolix/mcp_server.py` clean
- [ ] 1.3 Replace the inline `f"User: {MCP_SERVER_NAME}"` value at `mcp_hydrolix/mcp_server.py:235` with the new `HDX_ADMIN_COMMENT` constant [implements: query-admin-comment/query-comment-composition, design/precompute-comment-at-startup] — verify: `grep -n 'User: ' mcp_hydrolix/mcp_server.py` returns no matches

## 2. Tests

- [ ] 2.1 Add test for scenario `Default Stdio Deployment Issues A Query` in `tests/test_query_settings.py` (asserts the rendered admin-comment value at the call to `client.query`) [implements: query-admin-comment/query-comment-composition, meta/tests] — verify: `pytest -q tests/test_query_settings.py::test_default_stdio_deployment_issues_a_query` green
- [ ] 2.2 Add test for scenario `Http Transport Deployment Issues A Query` in `tests/test_query_settings.py` (patches `HYDROLIX_CONFIG.mcp_server_transport` to `http` and asserts the comment) [implements: query-admin-comment/query-comment-composition, meta/tests] — verify: `pytest -q tests/test_query_settings.py::test_http_transport_deployment_issues_a_query` green
- [ ] 2.3 Add test for scenario `Version Metadata Available` in `tests/test_query_settings.py` (patches `importlib.metadata.version` to return a fixed string and asserts the version field) [implements: query-admin-comment/version-resolution, meta/tests] — verify: `pytest -q tests/test_query_settings.py::test_version_metadata_available` green
- [ ] 2.4 Add test for scenario `Version Metadata Unavailable` in `tests/test_query_settings.py` (patches `importlib.metadata.version` to raise `PackageNotFoundError`, asserts `version=unknown` and that a warning is logged) [implements: query-admin-comment/version-resolution, meta/tests] — verify: `pytest -q tests/test_query_settings.py::test_version_metadata_unavailable` green
- [ ] 2.5 Add test for scenario `Transport Reflects Launcher Configuration` in `tests/test_query_settings.py` (sets `HYDROLIX_MCP_SERVER_TRANSPORT=sse`, reloads/patches config, asserts `transport=sse`) [implements: query-admin-comment/transport-resolution, meta/tests] — verify: `pytest -q tests/test_query_settings.py::test_transport_reflects_launcher_configuration` green
- [ ] 2.6 Add test for scenario `Transport Defaults When Unset` in `tests/test_query_settings.py` (unsets `HYDROLIX_MCP_SERVER_TRANSPORT`, asserts `transport=stdio`) [implements: query-admin-comment/transport-resolution, meta/tests] — verify: `pytest -q tests/test_query_settings.py::test_transport_defaults_when_unset` green
