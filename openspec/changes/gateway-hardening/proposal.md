*Harden mcp-hydrolix as the executor behind a per-cluster gateway: read-only preflight, fail-closed settings, caller-lowerable caps, per-request credentials, dual attribution.*

**Tracking:** HDX-12410, HDX-12008 (epic CFB-1616, plan https://hydrolix.atlassian.net/wiki/x/CoAKNAE section 3d)

## Why

Under the per-cluster gateway design ToolHive authenticates the caller and forwards a per-user token, so mcp-hydrolix stops verifying tokens and must hold the guards the console's `apps/mcp` enforces today. The executor is already reachable at `/mcp` on every cluster with a service-account fallback, so this gates exposing the gateway to non-staff users.

## What Changes

- `run_select_query` runs a read-only preflight before the cluster sees the statement: one statement, SELECT/WITH/SHOW/DESC/DESCRIBE/EXPLAIN only, no top-level SETTINGS, trailing FORMAT removed.
- **BREAKING** A query that mentions SETTINGS but cannot be parsed is refused instead of sent (the stripper fails closed).
- **BREAKING** `HYDROLIX_MAX_RESULT_CELLS_LIMIT` defaults to 200000; callers can only lower the budget. New `HYDROLIX_QUERY_MAX_RESULT_BYTES` (64 MiB) rides every query as `hdx_query_max_result_bytes`.
- **BREAKING** The `?token=` query parameter is refused unless `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM=true`.
- New `HYDROLIX_REQUIRE_REQUEST_CREDENTIAL`: with it on, a request without its own bearer token fails instead of running as the environment's service account; the readiness probe keeps its mounted credential.
- `hdx_query_admin_comment` is rebuilt per request as `key=value` tokens carrying the human principal and the agent identity; `hdx_query_comment` carries the caller's `purpose`; `hdx_query_label` is sent as a static transport setting when `HYDROLIX_QUERY_LABEL` is configured (unset by default).
- Every registered tool must be read-only; a future write tool must be listed, carry `destructiveHint`, and require client confirmation.

## Capabilities

### New

- `query-preflight` — statement-shape guard applied to user SQL before execution
- `result-limits` — result byte cap and caller-lowerable cell cap on every query
- `request-credentials` — per-request credential requirement and query-parameter token opt-in
- `write-tool-policy` — every registered tool read-only unless declared a confirmed write tool

### Modified

- `query-admin-comment` — per-request `key=value` composition; purpose comment and static label added

## Impact

- `mcp_hydrolix/preflight.py` (new), `mcp_hydrolix/attribution.py` (new)
- `mcp_hydrolix/mcp_server.py` — `execute_query` settings and attribution, `run_select_query` preflight and `purpose`, write-tool policy constant
- `mcp_hydrolix/mcp_env.py` — new variables, validation, `creds_with` required mode
- `mcp_hydrolix/auth/mcp_providers.py` — `?token=` backend behind a flag
- `mcp_hydrolix/utils.py` — `strip_conflicting_settings` raises on unparseable SQL
- hkt (`hkt/models/mcp_hydrolix.py`, `hkt/k8s/stages/aux/mcp_hydrolix.py`) pins the release, sets the in-cluster defaults, and drops the service-account env from the query path; separate turbine PR
- Release notes: three `Breaking:` entries above
