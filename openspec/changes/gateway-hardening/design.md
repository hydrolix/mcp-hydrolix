*Guard the statement before the cluster sees it, cap what comes back, never run as the service account, and say who asked.*

**Tracking:** HDX-12410, HDX-12008

## Context

- `execute_query` sends guardrails as transport-level settings; inline `SETTINGS` in the SQL outrank them on the Hydrolix HTTP path (HDX-11717), and the stripper fell back to sending the query when sqlglot could not parse it.
- `run_select_query` had no statement-shape guard; the cluster's `readonly=1` was the only read-only control.
- `HYDROLIX_MAX_RESULT_CELLS_LIMIT` defaulted to 0, so `max_cells=0` disabled truncation; there was no byte cap.
- `creds_with(None)` fell back to `HYDROLIX_TOKEN` / `HYDROLIX_USER`, so a request without a bearer ran as the deployment's service account; hkt mounts that account today.
- `?token=` was always accepted; the token then sits in every access log on the path.
- The HTTP transport runs `stateless_http=True`, so a `tools/call` request has no `initialize` client info of its own.
- The console guard this ports lives in `packages/cluster-client/src/utils/queryGuardrails.ts`.

## Goals / Non-Goals

- Goals: parity with the console's `apps/mcp` guards; fail closed wherever a guardrail cannot be verified; keep stdio single-user setups working unchanged; make attribution best-effort and never a query failure.
- Non-Goals: verifying inbound tokens in this server; replacing sqlglot; changing `execute_cmd` (catalog commands stay unattributed per the existing spec); hkt rendering (separate PR).

## Decisions

### Decision: port-console-scanner

- **Choice:** Port the console's character scanner (comments, strings, quoted identifiers, paren depth) rather than gate on sqlglot's parser.
- **Why:** Identical behaviour across the two MCP surfaces, and no dependence on the ClickHouse dialect's parser accepting every valid Hydrolix statement. Per explore/fail-closed-settings the scanner refuses a top-level SETTINGS clause; nested clauses go to the AST stripper, which now raises.
- **Alternatives:** sqlglot tokenizer — `SHOW`/`EXPLAIN` swallow the rest as one token, hiding a SETTINGS clause. Full parse, fail closed — refuses valid SQL the parser does not know.
- **Binding:** `run_select_query` MUST call `preflight()` before `_resolve_cell_limit` and MUST raise `ToolError(block_reason)` on a blocked result; no other caller rewrites user SQL.

### Decision: identifier-after-dot

- **Choice:** A keyword immediately preceded by `.` is an identifier, not a clause.
- **Why:** `SELECT name FROM system.settings` is a legitimate Hydrolix query; the console scanner blocks it. A deviation in the permissive direction is acceptable because the AST stripper still covers nested clauses and the cluster's `readonly` still holds.
- **Alternatives:** Keep parity and block — refuses a real query for no gain.
- **Binding:** `_tokenize` MUST record `after_dot` per word and the SETTINGS and FORMAT checks MUST skip such words.

### Decision: label-as-transport-setting-default-off

- **Choice:** Send `hdx_query_label` as a transport-level setting only when `HYDROLIX_QUERY_LABEL` is set; it is unset by default.
- **Why:** Verified against the integration stack (ClickHouse 26.8, `custom_settings_prefixes` including `hdx_`): an inline `SETTINGS hdx_query_label = 'mcp'` under the `readonly=1` the server always sends fails with `Code: 164 Cannot modify 'hdx_query_label' setting in readonly mode`, while the same custom setting as a URL parameter is accepted. The query options reference lists the label under SQL SETTINGS only, so whether the Hydrolix query head honours or rejects the parameter is unverified; off by default means an unverified mechanism cannot fail every query on upgrade. Per explore/attribution-vocabulary the value is the constant `mcp` once enabled.
- **Alternatives:** Inline SETTINGS clause — rejected under readonly (verified). `readonly=2` so the clause is allowed — widens what any inline clause may change. Default on — puts an unverified parameter on the path of every query.
- **Binding:** The label MUST come from `HydrolixConfig.query_label` (validated to `[A-Za-z0-9._-]{1,64}`), MUST be added to the settings dict in `execute_query` beside `hdx_query_admin_comment`, and MUST never be written into the SQL text.

### Decision: require-request-credential-flag

- **Choice:** `HYDROLIX_REQUIRE_REQUEST_CREDENTIAL` (default false) makes `creds_with(None)` raise `MissingRequestCredentialError`; hkt sets it true in-cluster; startup refuses it on stdio.
- **Why:** stdio has no per-request credential, so the environment credential is the user's own there; external HTTP deployments documented the environment fallback. Per explore/hardening-scope the in-cluster path must never run as the service account, so the platform flips the default.
- **Alternatives:** Remove the fallback outright — breaks stdio. Default on for http/sse — breaks documented external deployments on upgrade.
- **Binding:** `creds_with` is the only place the fallback decision is made; the readiness probe MUST pass its mounted credential explicitly rather than relying on the fallback.

### Decision: token-query-param-opt-in

- **Choice:** `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM` (default false) adds `GetParamAuthBackend` to the chain; enabling it logs a warning.
- **Why:** A token in the URL is written to every access log on the path. Clients that cannot set headers keep an explicit escape hatch instead of a silent break.
- **Alternatives:** Delete the backend — no path for header-less clients. Keep on by default — the status quo the plan rejects.
- **Binding:** `HydrolixCredentialChain.backends()` MUST be the single source of the backend list.

### Decision: cap-defaults

- **Choice:** `HYDROLIX_MAX_RESULT_CELLS_LIMIT` defaults to 200000; `HYDROLIX_QUERY_MAX_RESULT_BYTES` defaults to 64 MiB with a 10000 floor.
- **Why:** The console rejects over 1000 rows or 4 MiB; this server's cell truncation already bounds what reaches the client, so the byte cap protects the executor's memory on a wide result and rarely triggers. The Config API enforces the 10000 floor.
- **Alternatives:** Keep 0 — `max_cells=0` disables truncation for any caller. Match the console's 4 MiB — below what 200000 cells of wide rows need.
- **Binding:** Both values MUST be read from `HydrolixConfig` properties and validated at construction; `hdx_query_max_result_bytes` MUST be in the base settings dict of every `execute_query` call.

### Decision: attribution-best-effort

- **Choice:** `gather_request_attribution` never raises; sources in precedence order are gateway headers, request `_meta`, then `initialize` client info; `user` is the bearer's `sub`.
- **Why:** Attribution is observability; a missing header must not fail a query. Headers win because the gateway is the trusted party; `_meta` and client info are client-supplied.
- **Alternatives:** Require the header — breaks stdio. Trust `_meta` over headers — lets an agent overwrite what the gateway saw.
- **Binding:** `execute_query` MUST build the admin comment from `_APP_IDENTITY` plus the gathered fields on every call; no module-level constant may be sent as the comment.

### Decision: write-tool-policy-test

- **Choice:** `WRITE_TOOLS_REQUIRING_CONFIRMATION` (empty) plus a test that every other registered tool has `readOnlyHint=True` and `destructiveHint=False`.
- **Why:** Per explore/write-tool-rule a write tool must be declared; a test is the only place the rule bites at build time.
- **Alternatives:** Documentation only — nothing enforces it.
- **Binding:** A new write tool MUST be added to the set and MUST declare `destructiveHint=True`, or the suite fails.

## Risks / Trade-offs

- [Query head ignores or rejects `hdx_query_label` as a URL parameter] → off by default; phase 2 on qe enables it and checks the metric before hkt sets it fleet-wide.
- [Nested SETTINGS in SQL sqlglot cannot parse now fails] → the error names the SETTINGS clause as the cause; the top-level case is refused earlier with a clearer message.
- [Stateless HTTP has no `initialize` client info] → `agent` comes from `X-Hdx-Agent` when a gateway sets it; `trace` and `session` join with the gateway's audit log otherwise.
- [External HTTP deployments relying on `?token=` or `max_cells=0`] → release notes carry `Breaking:` entries naming the new variables.
- [Attribution adds a JWT decode per query] → the credential is already decoded for the connection; `service_account_id` is read, not re-parsed.

## Migration Plan

- Release the server; then hkt pins the version, sets `HYDROLIX_REQUIRE_REQUEST_CREDENTIAL=true`, `HYDROLIX_MAX_RESULT_CELLS_LIMIT` and `HYDROLIX_QUERY_MAX_RESULT_BYTES`, and drops `HYDROLIX_TOKEN` / `HYDROLIX_USER` / `HYDROLIX_PASSWORD` from the mcp-hydrolix stage while keeping the `service-tokens` mount for `/health`.
- Rollback: pin the previous tag in hkt; no data or schema changes exist.

## Open Questions

- Whether ToolHive can inject the client identity it saw at `initialize` into an upstream header; if not, `agent` stays empty on the gateway path and the join is by trace id (CFB-1625).
