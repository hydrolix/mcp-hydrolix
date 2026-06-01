*Register an unauthenticated RFC 9728 metadata route at the path-scoped location `/.well-known/oauth-protected-resource/mcp` and add a resource-URL precedence resolver to `OAuthConfig`.*

## Context

- OAuth activation, `OAuthConfig` shape, and the partial-config error path are defined by `oauth-config-and-preflight`. This change adds one field to that config and registers one new route.
- New routes are registered on the ASGI app returned by `create_app()` in `webapp.py` (FastAPI/Starlette under FastMCP).
- When `oauth-jwt-verifier` or `oauth-auth-chain-and-activation` has landed, requests rejected at the auth layer return HTTP 401 with a `WWW-Authenticate: Bearer realm=…` header. This change appends a `resource_metadata=<url>` parameter to that header when present. The RFC 9728 metadata endpoint itself functions independently of any 401-emitting path — it can be exercised standalone.
- RFC 9728 §3 forbids protecting the metadata endpoint with the credentials it describes.
- `HYDROLIX_URL` is owned by `hydrolix-url-config-collapse`; this change consumes it.

## Goals / Non-Goals

**Goals:**
- One new route, registered only when OAuth is active.
- `OAuthConfig.resource_url` resolved at `create_app()` time.
- No operator override env var for `resource_url` — single source of truth is `HYDROLIX_URL` (with bind-URL fallback). See "no-resource-url-override" decision.
- No new external dependencies.

**Non-Goals:**
- RFC 9728 metadata when OAuth is inactive (returns 404).
- Authorization server metadata endpoint (RFC 8414) — belongs to the IdP.
- Caching or signing the document.

## Decisions

### Decision: path-scoped-well-known-per-rfc-9728

**Choice:** Serve the metadata endpoint at the RFC 9728 §3 canonical path-scoped location — `/.well-known/oauth-protected-resource` + the path component of `OAuthConfig.resource_url` (i.e. `/.well-known/oauth-protected-resource/mcp` for the default chain) — registered as a plain Starlette/FastAPI route on the ASGI app inside `create_app()` before any auth middleware is applied, guarded by the same `oauth_active` flag used for the JWT verifier middleware.

**Why:** Three forces pick the path; one operational constraint picks the registration site.

1. **RFC 9728 §3** inserts the well-known suffix between authority and resource path. For a path-scoped resource like `https://cluster.example.com/mcp`, the canonical metadata URL is `https://cluster.example.com/.well-known/oauth-protected-resource/mcp`. Serving at the bare origin root would only be RFC-canonical if the resource identifier had no path component.
2. **Traefik shares ingress across services** in the Hydrolix cluster. A rule allowing unauthenticated `GET /.well-known/oauth-protected-resource` at the origin root would apply to every backend behind the same router, not just MCP. The path-scoped form lets the Traefik rule target exactly the suffix this service owns.
3. **Clients that have already seen a 401** find the metadata via the `WWW-Authenticate: resource_metadata=<url>` parameter regardless of path; the location only matters to clients doing pure RFC 9728 discovery without a prior 401, and for them the canonical path is the correct one.
4. **Registration mechanics:** the route must be unauthenticated, so it cannot go through the auth middleware stack. Registering it directly on the ASGI app object before mounting FastMCP tools (and before any auth middleware) is the simplest placement that bypasses auth while remaining inside the same ASGI process. The path is computed at `create_app()` time from `OAuthConfig.resource_url.path`, not registered as a wildcard — exactly one absolute path is served.

**Alternatives:**
- Origin root `/.well-known/oauth-protected-resource`: violates RFC 9728 §3 for path-scoped resources; Traefik allowlist would over-share.
- Under MCP mount `/mcp/.well-known/oauth-protected-resource`: operationally appealing (same Traefik router as MCP) but non-standard — strict RFC 9728 clients without a prior 401 would 404.
- Mount as a sub-application at the ASGI root: more complexity, no benefit.
- Add via FastMCP `custom_routes`: FastMCP's custom route surface is not yet stable and may apply auth middleware.

**Binding:** The metadata endpoint SHALL be at `/.well-known/oauth-protected-resource{resource_url.path}`. The handler MUST be registered before any auth middleware is applied to the app so unauthenticated GET requests reach it directly. The registered path MUST be derived from `OAuthConfig.resource_url.path`, not hard-coded — this keeps the implementation honest about the path-scoped contract and ready for a future operator-override env var without code surgery. The worker SHALL NOT register a handler for the origin root `/.well-known/oauth-protected-resource` (no suffix); tests SHALL assert the worker itself returns 404 at that path. The worker does not constrain cluster-level behavior at the root path — that location is left unclaimed so a future broader-scoped service in the cluster may claim it via ingress routing.

### Decision: resource-url-bind-url-fallback

**Choice:** When `HYDROLIX_URL` is absent, `OAuthConfig.resource_url` is populated from the server's bind address (host + port from the uvicorn/Hypercorn config) **with `/mcp` appended** at `create_app()` time, not from a fallback string constant.

**Why:** A hardcoded fallback like `http://localhost:8000` would be correct only for development; production workers may bind to non-default ports or addresses. Reading the actual bind config is the only way to produce a correct default. The `/mcp` suffix is appended because the FastMCP application is mounted at that path (`webapp.py:19`) — the resource identifier must include the path component the resource actually lives at.

**Alternatives:**
- Leave `resource_url` as `None` and skip the `resource` field: violates RFC 9728 §4.1 (field REQUIRED).
- Use `127.0.0.1` as default: incorrect for remote-transport deployments.
- Omit the `/mcp` suffix: the metadata's `resource` field would no longer identify the actual resource location, and the well-known path would land at origin root instead of the RFC-canonical scoped location.

**Binding:** `create_app()` MUST pass the resolved bind base URL **plus the FastMCP mount path** into `OAuthConfig` (or into a `resource_url` resolver) so the route handler can read it from config, not re-derive it at request time. The mount path SHALL be sourced from the same constant used in `webapp.py` (currently `"/mcp"`), not duplicated as a literal — if the mount path ever changes, the resource URL follows.

### Decision: no-resource-url-override

**Choice:** Do not introduce a `HYDROLIX_OAUTH_RESOURCE_URL` env var. `OAuthConfig.resource_url` is resolved only from `HYDROLIX_URL` (with bind-URL fallback), always with `/mcp` appended.

**Why:** `resource_url` participates in nothing structural — it is only advertised in the RFC 9728 JSON `resource` field, used to derive the well-known path per RFC 9728 §3, and used to build the `WWW-Authenticate: resource_metadata=` pointer. It does NOT gate token verification (that's `audience`), does NOT affect issuer matching, and does NOT affect activation. Across the supported deployment models (cluster, external/remote, stdio, local dev), every realistic resource identifier is `<HYDROLIX_URL>/mcp` — operators who need to advertise a different URL can simply set `HYDROLIX_URL` to that URL. Adding an override env var would create a fourth knob in the OAuth surface, a partial-config guard, and a "verbatim vs append" carveout in the precedence chain, all to support a deployment shape that does not exist in our supported set. YAGNI.

**Alternatives:**
- Keep `HYDROLIX_OAUTH_RESOURCE_URL` as an explicit operator override: rejected as YAGNI; complicates the precedence chain (verbatim vs append) and adds a partial-config guard, neither of which earns its keep.
- Default `resource_url` to origin root (no `/mcp` suffix): rejected — the resource identifier should match where the MCP application actually lives, and dropping `/mcp` would also defeat the narrow-Traefik-rule rationale established in `path-scoped-well-known-per-rfc-9728`.

**Binding:** `load_oauth_config()` SHALL NOT read any `HYDROLIX_OAUTH_RESOURCE_URL` env var. If a future deployment surfaces a genuine need for a custom advertised resource URL, an override env var can be added additively (non-breaking) by inserting a tier 0 ahead of the current chain.

### Decision: www-authenticate-extension

**Choice:** Extend the existing `WWW-Authenticate: Bearer` header on 401 responses with `resource_metadata="<url>"` where `<url>` is the absolute URL at which this worker actually serves the metadata document — same scheme/authority as `OAuthConfig.resource_url`, path `/.well-known/oauth-protected-resource` + `OAuthConfig.resource_url.path`. The string is computed once at `create_app()` time alongside route registration; the 401 handler reads it from config.

**Why:** RFC 9728 §5.1 specifies this parameter as the mechanism for pointing clients to the metadata document. The existing 401 response path already constructs the `WWW-Authenticate` header; this is a one-field addition. Reusing the same source of truth as the route registration (`OAuthConfig.resource_url`) guarantees the pointer can never drift from where the document actually lives.

**Alternatives:**
- Add a separate `Link:` header: non-standard for OAuth; clients wouldn't know to look there.
- Omit the parameter: allowed by RFC 9728 but degrades client discoverability.
- Construct the URL from the request's `Host` header at 401-emit time: opens up Host-header spoofing as an attack on the discovery URL.

**Binding:** The `WWW-Authenticate` header on every 401 from an authenticated endpoint MUST include `resource_metadata="<absolute-url>"`. The `<absolute-url>` MUST be derived from `OAuthConfig.resource_url` (same scheme/authority, well-known suffix inserted between authority and path component) — NOT from the request's `Host` header. There SHALL be exactly one canonical metadata URL per worker, identical to the URL the route is actually registered at.

### Decision: traefik-allowlist-for-metadata

**Choice:** Within a Hydrolix cluster deployment, the Traefik load balancer fronting the MCP worker MUST be updated (in the cluster-ops repo, not here) to allow unauthenticated `GET /.well-known/oauth-protected-resource/mcp` through to the worker, **routed to the MCP service** (Traefik fronts many services and we don't want this rule leaking to others). This change cannot enforce that itself; it can only document the dependency so the cluster-ops change ships in lockstep. This resolves the open question deferred from `oauth-config-and-preflight` (design.md "Traefik routing").

**Why:** RFC 9728 §3 forbids protecting the metadata endpoint with the credentials it describes, but Hydrolix cluster Traefik instances front the worker and apply auth at the edge. If Traefik rejects the path before it reaches the worker, the endpoint is invisible to clients regardless of how it is registered in `create_app()` — the failure mode looks like a server bug but is an ingress-policy bug. The path-scoped placement (`/mcp` suffix) keeps the allowlist rule narrow enough that it does not affect any other service behind the same Traefik instance. See `path-scoped-well-known-per-rfc-9728` above for why the path is scoped rather than at origin root.

**Alternatives:**
- Rely on Traefik defaulting to permissive: not the case for cluster deployments; auth-at-edge is the norm.
- Serve the metadata document from Traefik itself: drifts from `OAuthConfig.resource_url`/`issuer` resolution and duplicates state.
- Broad allowlist at `/.well-known/oauth-protected-resource` (no `/mcp` suffix): would also allow unauthenticated traffic to any future neighboring service's protected-resource-metadata endpoint, defeating the per-service scoping.

**Binding:** The PR description for this change MUST link to (or block on) the corresponding cluster-ops change that adds a Traefik allowlist rule with both an **exact path match** on `/.well-known/oauth-protected-resource/mcp` and a **service match** routing to the MCP worker. Stdio-transport deployments and standalone worker deployments are not affected.

## Risks / Trade-offs

- [Risk] Bind-URL fallback requires host+port from server config inside `create_app()` → `create_app()` already receives this config; no new coupling needed.
- [Risk] Unauthenticated endpoint used for SSRF fingerprinting → document is static and contains only the public issuer URL; risk negligible.
- [Risk] Cluster Traefik rejects `/.well-known/oauth-protected-resource/mcp` before it reaches the worker → out-of-repo dependency; see `traefik-allowlist-for-metadata` decision above. Mitigation: ship the Traefik rule alongside this change and add a post-deploy smoke check that the path returns 200 unauthenticated from outside the cluster.
- [Risk] Strict RFC-9728 clients that bypass `WWW-Authenticate`-driven discovery and probe origin root `/.well-known/oauth-protected-resource` will see 404 → acceptable per `path-scoped-well-known-per-rfc-9728`: the path-scoped location is the RFC-canonical one for a resource identified by `<base>/mcp`. Clients following RFC 9728 §3 derivation arrive at the correct path; clients following the `WWW-Authenticate: resource_metadata=` pointer always get the absolute URL.

## Open Questions

*none*
