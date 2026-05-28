*Compute the admin-comment once at module import from package metadata and runtime config.*

**Tracking:** HDX-11481

## Context

- Only writer of `hdx_query_admin_comment` today: `mcp_server.py:235`.
- `HYDROLIX_CONFIG.mcp_server_transport` is module-level and defaults to `stdio`.
- Package distribution name is `mcp-hydrolix` (`pyproject.toml:2`).
- No repo consumer parses the literal `User: mcp-hydrolix` (verified by grep).

## Decisions

### Decision: precompute-comment-at-startup

- **Choice:** Assemble the comment once at module import; store as a module-level constant.
- **Why:** Inputs are immutable per process; per-query formatting is waste.
- **Alternatives:** Per-query format — wasteful. `@lru_cache` — over-engineered.
- **Binding:** `execute_query` settings dict MUST reference the single module-level constant.

### Decision: version-from-importlib-metadata

- **Choice:** `importlib.metadata.version("mcp-hydrolix")` at import; on `PackageNotFoundError`, log a warning and substitute the literal string `unknown`.
- **Why:** Per `explore/version-fallback`, comment must not block queries. Stdlib; tracks `pyproject.toml`.
- **Alternatives:** Hardcoded constant — drifts silently. Parse `pyproject.toml` at runtime — slower, not packaging-aware.
- **Binding:** Version field MUST use this source and the exact fallback sentinel `unknown`.

### Decision: transport-from-config

- **Choice:** Read once from `HYDROLIX_CONFIG.mcp_server_transport`.
- **Why:** Already module-level; mirrors the launcher's source of truth.
- **Alternatives:** Probe the FastMCP server at runtime — couples to internals.
- **Binding:** Transport field MUST source from `HYDROLIX_CONFIG.mcp_server_transport`.

### Decision: scope-limited-to-execute-query

- **Choice:** Apply `hdx_query_admin_comment` only in `execute_query`; leave `execute_cmd` (`mcp_server.py:255`) unchanged.
- **Why:** Usage attribution is only needed for SQL query traffic. `execute_cmd` runs catalog operations (e.g. `SHOW DATABASES` at `mcp_server.py:401`), which are not the queries we want to attribute.
- **Alternatives:** Cover `execute_cmd` for symmetry — rejected; dilutes the per-user signal with catalog noise.
- **Binding:** `execute_cmd` MUST NOT set `hdx_query_admin_comment`. Future attribution of catalog traffic, if needed, requires a separate change.
