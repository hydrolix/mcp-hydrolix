*Register an unauthenticated RFC 9728 metadata route and add a resource-URL precedence resolver to `OAuthConfig`.*

## Context

- OAuth activation, `OAuthConfig` shape, and the partial-config error path are defined by `oauth-config-and-preflight`. This change adds one field to that config and registers one new route.
- New routes are registered on the ASGI app returned by `create_app()` in `webapp.py` (FastAPI/Starlette under FastMCP).
- The `WWW-Authenticate: Bearer` header is already emitted by the JWT verifier on 401 responses; this change appends a `resource_metadata=` parameter.
- RFC 9728 §3 forbids protecting the metadata endpoint with the credentials it describes.
- `HYDROLIX_URL` is owned by `hydrolix-url-config-collapse`; this change consumes it.

## Goals / Non-Goals

**Goals:**
- One new route, registered only when OAuth is active.
- `OAuthConfig.resource_url` resolved at `create_app()` time.
- Partial-config error for `HYDROLIX_OAUTH_RESOURCE_URL` without audience, consistent with other optional-var guards.
- No new external dependencies.

**Non-Goals:**
- RFC 9728 metadata when OAuth is inactive (returns 404).
- Authorization server metadata endpoint (RFC 8414) — belongs to the IdP.
- Caching or signing the document.

## Decisions

### Decision: metadata-route-placement

**Choice:** Register `/.well-known/oauth-protected-resource` as a plain Starlette/FastAPI route on the ASGI app inside `create_app()`, guarded by the same `oauth_active` flag used for the JWT verifier middleware.

**Why:** The route must be unauthenticated, so it cannot go through the auth middleware stack. Registering it directly on the app object before mounting FastMCP tools is the simplest placement that bypasses auth while remaining inside the same ASGI process.

**Alternatives:**
- Mount as a sub-application at the ASGI root: more complexity, no benefit.
- Add via FastMCP `custom_routes`: FastMCP's custom route surface is not yet stable and may apply auth middleware.

**Binding:** The route handler MUST be registered before any auth middleware is applied to the app, so that unauthenticated GET requests reach the handler directly.

### Decision: resource-url-bind-url-fallback

**Choice:** When both `HYDROLIX_OAUTH_RESOURCE_URL` and `HYDROLIX_URL` are absent, `OAuthConfig.resource_url` is populated from the server's bind address (host + port from the uvicorn/Hypercorn config) at `create_app()` time, not from a fallback string constant.

**Why:** A hardcoded fallback like `http://localhost:8000` would be correct only for development; production workers may bind to non-default ports or addresses. Reading the actual bind config is the only way to produce a correct default.

**Alternatives:**
- Leave `resource_url` as `None` and skip the `resource` field: violates RFC 9728 §4.1 (field REQUIRED).
- Use `127.0.0.1` as default: incorrect for remote-transport deployments.

**Binding:** `create_app()` MUST pass the resolved bind base URL into `OAuthConfig` (or into a `resource_url` resolver) so the route handler can read it from config, not re-derive it at request time.

### Decision: www-authenticate-extension

**Choice:** Extend the existing `WWW-Authenticate: Bearer` header on 401 responses with `resource_metadata="<url>"` where `<url>` is the absolute URL of the metadata endpoint constructed from the bind base URL.

**Why:** RFC 9728 §5.1 specifies this parameter as the mechanism for pointing clients to the metadata document. The existing 401 response path already constructs the `WWW-Authenticate` header; this is a one-field addition.

**Alternatives:**
- Add a separate `Link:` header: non-standard for OAuth; clients wouldn't know to look there.
- Omit the parameter: allowed by RFC 9728 but degrades client discoverability.

**Binding:** The `WWW-Authenticate` header on every 401 from an authenticated endpoint MUST include `resource_metadata="<absolute-url>"`. The URL MUST use the same base URL source as `OAuthConfig.resource_url` when the bind-URL fallback is active.

## Risks / Trade-offs

- [Risk] Bind-URL fallback requires host+port from server config inside `create_app()` → `create_app()` already receives this config; no new coupling needed.
- [Risk] Unauthenticated endpoint used for SSRF fingerprinting → document is static and contains only the public issuer URL; risk negligible.

## Open Questions

*none*
