## Context

mcp-hydrolix connects to other Hydrolix cluster services via two HTTP endpoints: a ClickHouse-HTTP query-head and a REST `/version` probe from the version service. Today, six env vars configure these endpoints: `HYDROLIX_HOST`, `HYDROLIX_PORT`, `HYDROLIX_SECURE`, `HYDROLIX_API_HOST`, `HYDROLIX_API_PORT` (plus the implicit scheme derivation from `HYDROLIX_SECURE`). These names conflate cluster identity with endpoint routing, and "API" is ambiguous in a system with multiple APIs.

Three deployment shapes exist:
- **In-cluster Remote ("Internal")** (o6r-managed): env vars point at distinct internal k8s services (`turbine-query:8088` for queries, `version:23925` for the REST probe). `HYDROLIX_URL` is already present in pod environments via the "general" ConfigMap but is not currently consumed by `HydrolixConfig`.
- **Out-of-cluster Remote ("External")** (testing, possible enterprise deployments): all vars typically converge on one canonical hostname (`*.trafficpeak.live` / `*.hydrolix.live`).
- **Local** (stdio transport): all vars typically converge on one canonical hostname

Upcoming OAuth work (HDX-11442) requires the cluster's canonical public URL at runtime, which is not derivable from an internal service hostname.

**Stakeholders**: external mcp-hydrolix users, SRE operators, the OAuth feature stream.

## Goals / Non-Goals

**Goals:**
- `HYDROLIX_URL` alone is a sufficient config for typical deployments (key design constraint).
- Clear separation between cluster identity (`HYDROLIX_URL`) and endpoint overrides (`HTTP_QUERY_*`, `VERSION_API_*`).
- All five legacy names remain honored with audience-appropriate deprecation messaging.
- Zero functional drift for existing `HYDROLIX_HOST`-only configurations.
- Zero functional drift for in-cluster deployments during the transition window (o6r still emitting old names).
- Internal-facing deprecation notices stay in server logs only (never reach the LLM/end-user).
- External-facing deprecation notices are visible once per session to the LLM/end-user.

**Non-Goals:**
- o6r migration (separate repo, separate PR, ships after this).
- Removal of deprecated aliases (future release, separate ticket).
- Changes to `HYDROLIX_VERIFY`, `HYDROLIX_TOKEN`, `HYDROLIX_USER`, `HYDROLIX_PASSWORD`, or any MCP bind/transport vars.
- Changes to `HYDROLIX_PROXY_PATH` (planned for removal from codebase).
- OAuth implementation itself.

## Decisions

### D1: Two-layer config model: Cluster identity

The config model separates concerns into three layers:

| Layer | Variables | Purpose |
|---|---|---|
| 1: Cluster identity | `HYDROLIX_URL` | Canonical public URL. Supplies defaults for all derived properties. |
| 2: override (HTTP query) | `HYDROLIX_HTTP_QUERY_HOST/PORT/SECURE` | Override the ClickHouse HTTP query endpoint. Used for internal deployments. |
| 3: override (Version-API) | `HYDROLIX_VERSION_API_HOST/PORT/SECURE` | Override the `/version` REST probe endpoint. Used for internal deployments. |

**Rationale**: Separating identity from routing makes the external path simple (`HYDROLIX_URL` alone) while preserving the internal split-endpoint flexibility. The `HTTP_QUERY_` prefix disambiguates from native-protocol ports. The `VERSION_API_` prefix clarifies that "API" means the `/version` probe specifically.

**Identity vs override**: Layer-1 (cluster identity) is the only layer that supplies a connection target. Layer-2 and Layer-3 are pure overrides and SHALL NEVER be sufficient on their own — setting `HYDROLIX_HTTP_QUERY_HOST` without a layer-1 value (URL, or the deprecated `HYDROLIX_HOST` for stdio) is a configuration error. The deprecated `HYDROLIX_HOST` alias is accepted as a layer-1 substitute only for stdio transport; http/sse transport requires `HYDROLIX_URL` specifically (OAuth metadata needs a canonical public URL).

**Alternative rejected**: A single `HYDROLIX_QUERY_URL` + `HYDROLIX_VERSION_URL` (full URL overrides). This would require URL parsing in two more places and doesn't match the existing granular host/port/secure pattern that o6r already emits.

### D2: Four-tier precedence chain

For each derived property:
```
explicit new var > deprecated alias > HYDROLIX_URL-derived > hard-coded default
```

**Rationale**: New vars win over aliases (migration target takes precedence). Aliases win over URL-derived (a user who has explicitly set `HYDROLIX_HOST` intends that value even if `HYDROLIX_URL` is also present). URL-derived wins over hard defaults (the URL is the new canonical source).

**Alternative rejected**: Making `HYDROLIX_URL` win over explicit aliases. This would not have sufficient expressivity for internal configurations, which rely on using different hostnames for the version and query services.

### D3: URL port ignored -- scheme-default ports only

`HYDROLIX_URL` with an explicit port (e.g. `https://cluster:9443`) ignores the port component and uses scheme-default (443/80). Clusters are always served on standard ports; non-standard ports are set via `HYDROLIX_HTTP_QUERY_PORT` or `HYDROLIX_VERSION_API_PORT`.

**Rationale**: Prevents a likely misconfiguration where users copy a browser URL with a non-standard port and get unexpected query endpoint behavior. The URL is for identity, not routing.

### D4: Audience detection via HYDROLIX_NAME

`HYDROLIX_NAME` is an o6r-injected env var present in every pod via the "general" ConfigMap. Its presence is used as a proxy for "this is an o6r-managed deployment".

**Rationale**: Simple, low false-positive risk (customers are extremely unlikely to set `HYDROLIX_NAME`), low false-negative risk (in-cluster pods always inherit the ConfigMap).

**Alternative rejected**: Using `HYDROLIX_URL` presence as the signal. A partially-migrated external user who has set `HYDROLIX_URL` but still has `HYDROLIX_HOST` would be misclassified as internal and miss the LLM advisory.

**Alternative rejected**: Dot-in-hostname heuristic (`turbine-query` has no dots, `mycluster.hydrolix.live` does). Brittle -- custom internal DNS names can have dots.

### D5: Version gate for internal deprecation log

The internal deprecation log only fires when the connected cluster reports version >= 6.1 (the first Hydrolix release whose bundled o6r emits the new names).

**Rationale**: Operators on older clusters/o6r can't act on the notice -- logging it is noise. The gate ensures the log only appears where migration is actionable.

**Implementation**: Piggybacks on the existing `_parse_hydrolix_version` -> `(major, minor)` tuple in the `/version` probe. The check is `parsed_version >= (6, 1)`.

### D6: External deprecation via FastMCP instructions

The external deprecation message is wired into `FastMCP(instructions=...)` at construction time.

**Rationale**: The MCP protocol delivers `InitializeResult.instructions` once per client session. This is the correct channel for per-session operator advisories without adding custom middleware. When no deprecation is detected, `instructions` is `None` (matching current behavior). This prompts external MCP operators to update their configurations

### D7: version_api_secure inherits from resolved secure

`HYDROLIX_VERSION_API_SECURE` defaults to the resolved `secure` property (the HTTP query SECURE value after the full precedence chain). This means the common case (query and version-API use the same TLS setting) requires no explicit configuration, and o6r does not need to emit `HYDROLIX_VERSION_API_SECURE` at all.

**Rationale**: In-cluster, `HYDROLIX_HTTP_QUERY_SECURE=false` (or its alias `HYDROLIX_SECURE=false`) implies the version probe is also plain HTTP. Explicit override is only needed for unusual setups where the two endpoints use different TLS modes.

## Risks / Trade-offs

- **BREAKING for external remote deployments (scoped break, explicit assumption)** -> Requiring `HYDROLIX_URL` when `HYDROLIX_MCP_SERVER_TRANSPORT` is `http` or `sse` is a hard breaking change for any deployment that today runs the http/sse transport without `HYDROLIX_URL` set. Scope analysis:
  - **Internal remote (o6r-managed):** unaffected. o6r injects `HYDROLIX_URL` into every pod via the "general" ConfigMap; the variable is already present, just not consumed by `HydrolixConfig` today.
  - **Stdio (local / IDE clients):** unaffected. The transport requirement only fires for `http`/`sse`.
  - **External remote:** breaks for any operator running http/sse without `HYDROLIX_URL`. They hit a startup `ValueError` naming `HYDROLIX_URL` and `HYDROLIX_MCP_SERVER_TRANSPORT` and must set `HYDROLIX_URL` to recover.

  **Explicit assumption (load-bearing):** we are not aware of any extant external remote deployments today. The break is acceptable on that basis. If this assumption is wrong, the cost to affected operators is one config edit (set `HYDROLIX_URL`), surfaced by a clear, actionable startup error — not a silent regression. We are NOT relying on a runtime warning or grace period to soften the break, because OAuth metadata generation cannot proceed without a canonical URL.

- **Audience-detection heuristic is not 100% accurate** -> Misclassification is non-fatal in either direction. A misclassified-as-internal external user just sees the log without LLM nudging (can still find guidance in README). The single `_classify_deprecation()` helper is the touch-point to refine if reports accumulate.

- **Internal deprecation log never fires if `/version` probe fails repeatedly** -> Acceptable degradation. The deprecation is informational, not critical. Probe failure produces its own pre-existing WARNING log. Operators can find guidance in README and release notes.

- **Operator sets both old and new names during hand-migration** -> Precedence rule makes `HTTP_QUERY_*` win. Internal deprecation log fires for the old alias, which is the correct signal to finish removing it.

- **URL with userinfo** (`https://user:pass@host`) -> `urlparse.hostname` strips userinfo. Documented as silently ignored. Credentials stay in their dedicated env vars. Again, URL is identity, not routing.

- **Test env bleed from `.env` files** -> `autouse=True` fixture clears every `HYDROLIX_*` env var before each test in new test modules.

## Migration Plan

1. Ship mcp-hydrolix with this change (Phases 1-5 of the implementation plan).
2. External users see the deprecation advisory and can migrate at their pace. Existing configs continue to work unchanged.
3. After this release is deployed, switch o6r to emit the new names (Phase 6, separate repo/PR).
4. After o6r migration and bake time, remove the five deprecated aliases in a future release (separate ticket).

Rollback: Revert the mcp-hydrolix release. All old env var names continue to work because aliases are additive.

## Open Questions

(none -- resolved during planning)
