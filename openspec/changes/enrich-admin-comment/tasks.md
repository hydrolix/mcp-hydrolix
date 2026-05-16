# Tasks

## 1. Implement
- [ ] 1.1 In `mcp_hydrolix/mcp_server.py`, resolve the package version at module scope via `importlib.metadata.version("mcp-hydrolix")`.
- [ ] 1.2 Replace the literal at line 235 with `f"User: mcp-hydrolix, {_VERSION} ({HYDROLIX_CONFIG.mcp_server_transport})"`.

## 2. Test
- [ ] 2.1 Extend `tests/test_query_settings.py` to assert `hdx_query_admin_comment` matches the pattern `^User: mcp-hydrolix, [^ ]+ \((stdio|http|sse)\)$`, parameterised over transport via monkeypatched `HYDROLIX_MCP_SERVER_TRANSPORT`.

## 3. Verify
- [ ] 3.1 `uv run pytest` and `uv run ruff check` clean.
