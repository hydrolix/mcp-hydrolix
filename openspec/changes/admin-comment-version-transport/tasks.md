*2 phases, 6 tasks (2 impl, 4 tests).*

**Tracking:** HDX-11481

## 1. Implementation

- [ ] 1.1 Add a module-level version resolver (`importlib.metadata.version("mcp-hydrolix")` with `PackageNotFoundError` → `unknown` + warning) and a module-level `HDX_ADMIN_COMMENT` constant assembled from name, resolved version, and `HYDROLIX_CONFIG.mcp_server_transport` [implements: query-admin-comment/query-comment-composition, query-admin-comment/version-resolution, query-admin-comment/transport-resolution, design/precompute-comment-at-startup, design/version-from-importlib-metadata, design/transport-from-config, explore/comment-format, explore/version-fallback] — verify: `ruff check mcp_hydrolix/mcp_server.py` clean
- [ ] 1.2 Replace the inline `f"User: {MCP_SERVER_NAME}"` at `mcp_hydrolix/mcp_server.py:235` with `HDX_ADMIN_COMMENT` [implements: query-admin-comment/query-comment-composition] — verify: `grep -n 'User: ' mcp_hydrolix/mcp_server.py` returns no matches

## 2. Tests

- [ ] 2.1 Add test for scenario `Renders Composed Comment` in `tests/test_query_settings.py` [implements: query-admin-comment/query-comment-composition, meta/tests] — verify: `pytest -q tests/test_query_settings.py::test_renders_composed_comment` green
- [ ] 2.2 Add test for scenario `Version Metadata Available` in `tests/test_query_settings.py` [implements: query-admin-comment/version-resolution, meta/tests] — verify: `pytest -q tests/test_query_settings.py::test_version_metadata_available` green
- [ ] 2.3 Add test for scenario `Version Metadata Unavailable` in `tests/test_query_settings.py` [implements: query-admin-comment/version-resolution, meta/tests] — verify: `pytest -q tests/test_query_settings.py::test_version_metadata_unavailable` green
- [ ] 2.4 Add test for scenario `Transport Reflects Config` in `tests/test_query_settings.py` [implements: query-admin-comment/transport-resolution, meta/tests] — verify: `pytest -q tests/test_query_settings.py::test_transport_reflects_config` green
