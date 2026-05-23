*Compute the admin-comment string once at module import from package metadata and runtime config, then attach it to every Hydrolix query.*

**Tracking:** HDX-11481

## Context

- `mcp_server.py:235` is today the only writer of `hdx_query_admin_comment`; value is the static `f"User: {MCP_SERVER_NAME}"`.
- `HYDROLIX_CONFIG: Final = get_config()` is already module-level (`mcp_server.py:64`); `HydrolixConfig.mcp_server_transport` reads `HYDROLIX_MCP_SERVER_TRANSPORT` once on access and defaults to `stdio`.
- The package distribution name is `mcp-hydrolix` (`pyproject.toml:2`), so `importlib.metadata.version("mcp-hydrolix")` is the canonical version source.
- Repo-wide grep confirms no internal consumer parses the literal `User: mcp-hydrolix` — the only call site is the one above.
- `execute_cmd` (`mcp_server.py:255`) reaches Hydrolix via `client.command(...)` without passing a settings dict, so it emits no admin comment today.

## Goals / Non-Goals

**Goals:**

- Emit `User=<name>; version=<version>; transport=<transport>` on every query path the proposal scopes (`execute_query`).
- Resolve version and transport once at startup; never recompute per query.
- Degrade gracefully when version metadata is unresolvable (per `explore/version-fallback`).

**Non-Goals:**

- Changing public MCP tool surface or response shapes.
- Plumbing per-request identity (authenticated principal) into the comment — deferred in `explore.md`.
- Making the comment format operator-configurable.

## Decisions

### Decision: precompute-comment-at-startup

- **Choice:** Build the full comment string once at module import in `mcp_server.py` and store it as a module-level constant (e.g. `HDX_ADMIN_COMMENT`). The `execute_query` settings dict references this constant directly.
- **Why:** All inputs (server name, version, configured transport) are immutable for the lifetime of the process. Per-query formatting wastes cycles and makes the resulting string harder to assert against in tests.
- **Alternatives:**
  - Compute per query — same output every time; pure waste.
  - `@lru_cache` on a builder function — over-engineered for a static value.
- **Binding:** The `execute_query` settings dict MUST set `"hdx_query_admin_comment"` to this single module-level constant; no per-call composition.

### Decision: version-from-importlib-metadata

- **Choice:** Resolve version via `importlib.metadata.version("mcp-hydrolix")` at module import, wrapped in `try/except PackageNotFoundError`. On failure, log a warning and substitute the literal string `unknown`.
- **Why:** Per `explore/version-fallback`, the comment is observability and must never block queries. `importlib.metadata` is stdlib (no new dependency) and tracks `pyproject.toml` automatically.
- **Alternatives:**
  - Hardcoded `__version__` constant — drifts from `pyproject.toml` silently.
  - Parse `pyproject.toml` at runtime — slower and not packaging-aware (won't see installed wheel metadata).
- **Binding:** Version MUST come from `importlib.metadata.version("mcp-hydrolix")`; the fallback path MUST log a warning and use the literal string `unknown` (no alternative sentinel like `""` or `None`).

### Decision: transport-from-config

- **Choice:** Read the transport value once from `HYDROLIX_CONFIG.mcp_server_transport` at module import.
- **Why:** Config is already module-level; transport is fixed by `HYDROLIX_MCP_SERVER_TRANSPORT` at startup and used by the launcher to pick the FastMCP transport. Reading once mirrors the launcher's source of truth.
- **Alternatives:**
  - Detect transport at runtime from the active FastMCP server object — couples the query path to server internals; brittle.
- **Binding:** The transport field's source MUST be `HYDROLIX_CONFIG.mcp_server_transport`. If a runtime-mutable transport is ever introduced, this decision is revisited.

## Risks / Trade-offs

- [Replacing `User: ` with `User=` breaks any external log parser] → Mitigation: call out in PR description; grep confirms no internal consumer; format chosen with operator per `explore/comment-format`.
- [`importlib.metadata.version` slows process startup] → Negligible; it's a dict lookup against already-loaded distribution metadata.
- [Transport reads stale if `HYDROLIX_MCP_SERVER_TRANSPORT` mutates post-startup] → Accepted; transport is immutable per process by design.

## Migration Plan

- Single deploy; no schema or data migration.
- Rollback = revert PR; comment string reverts to `User: mcp-hydrolix`.

## Open Questions

- Should `execute_cmd` (`mcp_server.py:255`) also set `hdx_query_admin_comment`? It currently passes no settings, so commands like `SHOW DATABASES` are unattributed under the new axes. The proposal scopes Impact to `execute_query` only; deferring the decision to apply-time, but the usage-tracking motivation argues for parity.
