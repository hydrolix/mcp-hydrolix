*Resolved 5 decisions; 3 assumptions; 4 items deferred.*

**Tracking:** HDX-12410, HDX-12008

The operator is the console architect who owns the per-cluster gateway design. The questions below were put to him during the design review that produced plan revisions 3 to 6 and the phase 0 decision record (https://hydrolix.atlassian.net/wiki/x/CoAKNAE, section 8); the answers are quoted from that record.

## Questions Asked

- Should attribution land in new `hydro.logs` columns or in the existing query settings?
- What are the field names and the length budget for the admin comment?
- Should the SETTINGS stripper keep failing open on unparseable SQL?
- What is the scope of the hardening, and does in-executor token verification belong to it?
- How is a future write tool distinguished from the read-only set?

## Decisions

### Decision: no-schema-change

- **Question:** Should attribution land in new `hydro.logs` columns or in the existing query settings?
- **Answer:** The existing settings. The `hydro.logs` transform is frozen, so there are no new columns; HDX-12411 (canonical columns) was withdrawn.
- **Rationale:** No schema change anywhere; `hdx_query_admin_comment`, `hdx_query_comment` and `hdx_query_label` already land in `hydro.logs` and `hdx.active_queries`.
- **Affects:** `specs/query-admin-comment/spec.md → Requirement: Query Comment Composition`

### Decision: attribution-vocabulary

- **Question:** What are the field names and the length budget for the admin comment?
- **Answer:** Space-separated `key=value` tokens in fixed order: `app=<dist>/<version> transport=<t> user=<sub> agent=<client>/<version> model=<m> session=<id> trace=<traceparent>`. Values use `[A-Za-z0-9._:/@-]`, other bytes become `_`, 64 characters each, empty fields omitted, 512 bytes total with trailing fields dropped first. `hdx_query_comment` is the caller's purpose (256 characters); `hdx_query_label` is the constant `mcp`.
- **Rationale:** The admin comment is the first-party application-identification field (the Grafana precedent); a fixed order and a closed alphabet keep it parseable with a regex on `key=`.
- **Affects:** `specs/query-admin-comment/spec.md → Requirement: Query Comment Composition`, `specs/query-admin-comment/spec.md → Requirement: Query Purpose Comment`, `specs/query-admin-comment/spec.md → Requirement: Query Label`

### Decision: fail-closed-settings

- **Question:** Should the SETTINGS stripper keep failing open on unparseable SQL?
- **Answer:** No. Refuse any top-level SETTINGS clause on user SQL, and refuse a query whose SETTINGS cannot be parsed and inspected.
- **Rationale:** An inline setting that cannot be inspected could be lifting a guardrail; the cluster's `readonly` and limits are the server's to set.
- **Affects:** `specs/query-preflight/spec.md → Requirement: Settings Clause Refused`

### Decision: hardening-scope

- **Question:** What is the scope of the hardening, and does in-executor token verification belong to it?
- **Answer:** Exactly the plan's section 3d table: read-only allow-list and single-statement preflight, fail-closed SETTINGS handling, FORMAT strip, result-byte cap, caller-lowerable caps, reject `?token=`, remove the service-account fallback from the query path. Token verification stays out of mcp-hydrolix under this design (ToolHive verifies, a NetworkPolicy isolates the executor); HDX-11442, HDX-11444 and HDX-11167 are optional defense in depth.
- **Rationale:** The gateway is the authenticator; the executor must be safe to run with a per-user token and nothing else.
- **Affects:** `specs/request-credentials/spec.md → Requirement: Request Credential Required Mode`, `specs/result-limits/spec.md → Requirement: Caller Lowerable Cell Cap`

### Decision: write-tool-rule

- **Question:** How is a future write tool distinguished from the read-only set?
- **Answer:** Any future write tool carries `destructiveHint` and requires client confirmation; the gateway's per-tool authorization can gate it separately.
- **Rationale:** The gateway decides per tool; an unmarked write tool would be invisible to that decision.
- **Affects:** `specs/write-tool-policy/spec.md → Requirement: Read Only Tool Annotations`

## Deferred / Out of Scope

- ToolHive carrier for the agent fields (`headerForward` is static, so the gateway cannot forward `_meta` today) — verified under CFB-1625; this change accepts headers, `_meta` and `initialize` client info so any carrier works.
- hkt changes (version pin, in-cluster defaults, dropping the service-account env from the query path) — separate turbine PR after the release exists to pin.
- In-executor token verification (HDX-11442, HDX-11444, HDX-11167) — optional defense in depth under the gateway design.
- Live confirmation that the query head accepts `hdx_query_label` as a transport-level setting — phase 2 on qe-innovations-3; the label is unset until then, because the inline form is rejected under `readonly` (verified on ClickHouse).

## Assumptions

- A gateway that knows the client can set `X-Hdx-Agent` and `X-Hdx-Model` request headers — if false, the `agent` and `model` fields are absent under stateless HTTP and attribution joins on `trace` and `session` instead.
- `hdx_query_max_result_bytes` is accepted as an HTTP query parameter (the docs list it under the Query mechanism) — if false, every query fails at the query head and `HYDROLIX_QUERY_MAX_RESULT_BYTES` needs a bypass.
- External HTTP deployments that relied on `?token=` or on unbounded `max_cells=0` can set the new variables — if false, the upgrade breaks them until they do; the release notes name both.
