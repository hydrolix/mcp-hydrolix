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

**`mcp_server.py`**: MCP tools, connection pooling, summary table detection, query safety, pagination

**`mcp_env.py`**: All environment variables with defaults (see docstrings)

**`pagination.py`**: Cursor-based pagination utilities (encoding, validation, hashing)

**`auth/`**: Authentication chain: (1) per-request Bearer token, (2) per-request query param, (3) environment credentials

### Summary Table Support

**Critical Feature**: Summary tables store pre-aggregated data in `AggregateFunction` or `SimpleAggregateFunction` columns. The codebase automatically detects these and enriches metadata.

**Column Types:**
- `aggregate`: Must wrap with -Merge functions (e.g., `countMerge(\`count(col)\`)`)
- `alias_aggregate`: Pre-wrapped shortcuts, use directly
- `dimension`: Regular columns for grouping

**Implementation**: See `enrich_column_metadata()` and related functions in mcp_server.py for the type parsing and merge function generation logic.

### Pagination Support

**Critical Feature**: `list_tables` and `run_select_query` tools support cursor-based pagination to handle large result sets efficiently.

**How It Works:**
- Results are returned in pages (default: 50 tables or 10,000 rows per page)
- Each response includes a `nextCursor` field (opaque token) if more data exists
- Clients loop by passing the cursor to subsequent calls until `nextCursor` is None

**Tool Behavior:**
- `list_tables(database, paginate=True)` → Returns `PaginatedTableList` with `tables`, `nextCursor`, `pageSize`, `totalRetrieved`
- `run_select_query(query, paginate=True)` → Returns `PaginatedQueryResult` with `rows`, `columns`, `nextCursor`, `hasMore`
- Set `paginate=False` for legacy behavior (returns all data in single response)

**Configuration:**
- `HYDROLIX_LIST_TABLES_PAGE_SIZE=50` (default)
- `HYDROLIX_QUERY_RESULT_PAGE_SIZE=10000` (default)
- `HYDROLIX_ENABLE_PAGINATION=true` (default)

**Implementation Details:**
- Cursors are base64-encoded JSON with offset and validation data
- Cursors are tied to specific query parameters/queries (validated on each use)
- Uses SQL `LIMIT`/`OFFSET` for efficient database pagination
- Solves N+1 query problem in `list_tables` by only fetching column metadata for current page

**Security:** Cursor validation prevents parameter tampering and query switching attacks.

**For LLMs/Clients:** Tool docstrings include complete pagination workflow examples showing how to:
1. Check for `nextCursor` in response
2. Loop until `nextCursor` is None
3. Pass cursor to subsequent calls
4. Handle both paginated and non-paginated modes

## Important Patterns

**Connection Management**: Never reuse clients across sessions - create new client per request.

**Query Safety**: All queries run with readonly=1, timeouts, and row/memory limits (see code for specifics).

**Pagination**: Always check for `nextCursor` in tool responses. Loop with cursor parameter until None to fetch all data.

**Configuration**: See `mcp_env.py` docstrings for all available environment variables and defaults.
