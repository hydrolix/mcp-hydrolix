## Why

mcp-hydrolix needs its cluster's canonical public URL at runtime for upcoming OAuth features: token issuer validation (HDX-11167, HDX-11443) compares `iss` claims against the cluster identity, and OAuth resource-server metadata (`/.well-known/oauth-protected-resource`) advertises it. Today the only "host" configs can point at an internal k8s service name like `turbine-query`, which is insufficient for either feature. Before auth work can ship cleanly, the connection config needs a first-class "cluster public URL" input, and the surrounding naming ambiguities (`HYDROLIX_HOST` serving dual roles, `HYDROLIX_API_HOST` being misleadingly named) should be resolved while the touchpoints are open.

## What Changes

- Introduce `HYDROLIX_URL` as the primary cluster identity input (e.g. `https://mycluster.hydrolix.live`). For external deployments, this single variable is sufficient to derive all connection parameters.
- Introduce `HYDROLIX_HTTP_QUERY_HOST`, `HYDROLIX_HTTP_QUERY_PORT`, `HYDROLIX_HTTP_QUERY_SECURE` as dedicated override channels for the ClickHouse HTTP query endpoint (splitting the dual role of the old `HYDROLIX_HOST/PORT/SECURE` trio).
- Rename `HYDROLIX_API_HOST` / `HYDROLIX_API_PORT` to `HYDROLIX_VERSION_API_HOST` / `HYDROLIX_VERSION_API_PORT` to reflect their actual purpose (the `/version` REST probe, not a generic API).
- Add `HYDROLIX_VERSION_API_SECURE` property (no prior equivalent existed) that inherits from the resolved HTTP query SECURE value by default.
- Universally deprecate five legacy env vars: `HYDROLIX_HOST`, `HYDROLIX_PORT`, `HYDROLIX_SECURE`, `HYDROLIX_API_HOST`, `HYDROLIX_API_PORT`. They remain honored during a transition period.
- Implement audience-aware deprecation messaging:
  - **External** (no `HYDROLIX_NAME`): WARNING log at startup + LLM-visible advisory via FastMCP `instructions` pointing to `HYDROLIX_URL` as the sufficient replacement.
  - **Internal** (`HYDROLIX_NAME` set): ERROR log from the `/version` probe, gated on cluster version >= 6.1 (the first release whose hkt emits the new names). Never reaches the LLM/end-user.
- **BREAKING** (future): The five deprecated aliases will be removed in a future release after hkt migration and bake time.
- **BREAKING (scoped):** Require `HYDROLIX_URL` specifically when `HYDROLIX_MCP_SERVER_TRANSPORT` is `http` or `sse` (OAuth metadata needs the canonical URL). The break only affects **external** remote deployments, since o6r-managed (internal) remote deployments already inject `HYDROLIX_URL` via the "general" ConfigMap. This is acceptable on the explicit assumption that **no extant external remote deployments exist today** — if any do, those operators will hit a startup `ValueError` naming `HYDROLIX_URL` and `HYDROLIX_MCP_SERVER_TRANSPORT` and must set `HYDROLIX_URL`. Stdio transport is unaffected.
- Update `_check_parameterized_query_support` to use the renamed `version_api_host`, `version_api_port`, and new `version_api_secure` properties.

## Capabilities

### New Capabilities

- `connection-config`: How the server resolves where and how to talk to the cluster. Covers `HYDROLIX_URL` parsing and validation, connection target validation, transport-specific URL requirements, the four-tier precedence chain (explicit new var > deprecated alias > URL-derived > hard default) for all six derived properties (host, port, secure, version_api_host, version_api_port, version_api_secure), version probe URL construction, and the transitional deprecated-alias detection / audience-aware messaging behavior. The transitional requirements (alias detection, audience classification, external startup advisory + LLM `instructions` wiring, version-gated internal log) will be REMOVED in a future change once the five deprecated aliases are dropped.

### Modified Capabilities

(none -- no existing specs to modify)

## Impact

- **mcp_hydrolix/mcp_env.py**: Major changes -- URL parsing, precedence chain for all properties, deprecation detection/classification helpers, new `deprecation_notice` and `deprecation_audience` properties, updated `_validate_required_vars`.
- **mcp_hydrolix/mcp_server.py**: Wire `instructions=` on `FastMCP` constructor, add version-gated internal deprecation log helper in the `/version` probe path, rename `api_host`/`api_port` references to `version_api_host`/`version_api_port`, switch probe scheme source to `version_api_secure`.
- **tests/test_parameterized_queries.py**: Update mock attribute names from `api_host`/`api_port`/`secure` to `version_api_host`/`version_api_port`/`version_api_secure` in the probe path tests.
- **tests/**: Three new test modules for URL+precedence, deprecation classification+messaging, and version-gated internal logging.
- **README.md**: Document new variables, deprecation, and audience-specific migration guidance.
- **No new dependencies**: All additions use stdlib (`urllib.parse`, `logging`).
- **Downstream**: hkt migration (separate repo, separate PR) will switch env var names after this ships. Not part of this change.
