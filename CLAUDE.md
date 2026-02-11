# MCP Hydrolix Server

MCP server for Hydrolix (time-series database). Exposes query capabilities with special support for summary tables (pre-aggregated data).

## Development Commands

### Testing
```bash
docker compose up -d --wait --wait-timeout 300  # Start ClickHouse
uv run pytest                                    # All tests
uv run pytest -n auto                            # Parallel
docker compose down                              # Cleanup
```
Note: Tests use local ClickHouse, not Hydrolix.

### Run Server
```bash
# Required: HYDROLIX_HOST, HYDROLIX_USER, HYDROLIX_PASSWORD (or HYDROLIX_TOKEN)
uv run mcp-hydrolix

# HTTP mode (optional)
export HYDROLIX_MCP_SERVER_TRANSPORT=http
export HYDROLIX_MCP_BIND_PORT=8000
uv run mcp-hydrolix
```

## Architecture

**`main.py`**: Transport selection (stdio/HTTP/SSE)

**`mcp_server.py`**: MCP tools, connection pooling, summary table detection, query safety

**`mcp_env.py`**: All environment variables with defaults (see docstrings)

**`auth/`**: Authentication chain: (1) per-request Bearer token, (2) per-request query param, (3) environment credentials

### Summary Table Support

**Critical Feature**: Summary tables store pre-aggregated data in `AggregateFunction` or `SimpleAggregateFunction` columns. The codebase automatically detects these and enriches metadata.

**Column Types:**
- `aggregate`: Must wrap with -Merge functions (e.g., `countMerge(\`count(col)\`)`)
- `alias_aggregate`: Pre-wrapped shortcuts, use directly
- `dimension`: Regular columns for grouping

**Implementation**: See `enrich_column_metadata()` and related functions in mcp_server.py for the type parsing and merge function generation logic.

## Important Patterns

**Connection Management**: Never reuse clients across sessions - create new client per request.

**Query Safety**: All queries run with readonly=1, timeouts, and row/memory limits (see code for specifics).

**Configuration**: See `mcp_env.py` docstrings for all available environment variables and defaults.
