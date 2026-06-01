*Expose the RFC 9728 protected-resource-metadata endpoint and resolve the resource URL from operator configuration.*

## Why

MCP clients that implement OAuth discovery need a standards-compliant `/.well-known/oauth-protected-resource` document to locate the authorization server and construct token requests. Without it, clients must be configured out-of-band. The resource URL that populates the `resource` field is derived from `HYDROLIX_URL` (with a bind-URL fallback) because the public cluster URL differs from the address the MCP worker binds to.

## Family Context / Forward References

One of 5 changes decomposing OAuth bearer authentication for [HDX-11442](https://hydrolix.atlassian.net/browse/HDX-11442). All five target the shared capability `oauth-authentication`. Dependency order:

- `oauth-config-and-preflight` — root of the dep graph; this change consumes `OAuthConfig.issuer` from it.
- `oauth-resource-metadata` (this change) — depends on `oauth-config-and-preflight`.
- `oauth-jwt-verifier` — depends on `oauth-config-and-preflight`.
- `oauth-auth-chain-and-activation` — depends on `oauth-jwt-verifier`.
- `oauth-log-redaction` — orthogonal.

## What Changes

- A `GET /.well-known/oauth-protected-resource/mcp` endpoint is available when OAuth is active, returning an RFC 9728 JSON document; returns 404 when OAuth is inactive. The path is the RFC 9728 §3 canonical location for a resource identified by `<base>/mcp` (well-known suffix inserted between authority and resource path).
- The endpoint is reachable without authentication (RFC 9728 §3 requirement).
- HTTP 401 responses on authenticated endpoints include a `resource_metadata` pointer to the metadata endpoint in their `WWW-Authenticate` header (requires `oauth-jwt-verifier` or `oauth-auth-chain-and-activation` to be landed; the metadata endpoint itself is independently exercisable).
- `OAuthConfig.resource_url` is resolved from a two-tier precedence chain (`HYDROLIX_URL` + `/mcp` → server bind URL + `/mcp`). The `/mcp` suffix is the FastMCP mount path (`webapp.py:19`), sourced from the same constant in code. No env-var override is provided in this change — `resource_url` is purely advertised in discovery surfaces (RFC 9728 JSON + `WWW-Authenticate` pointer) and does not gate token verification, so a dedicated override would be YAGNI given the supported deployment models. An override env var can be added additively later if a real need surfaces.

## Capabilities

### New

*none*

### Modified

- `oauth-authentication` — adds the RFC 9728 protected-resource-metadata endpoint and the two-tier resource URL precedence chain (`HYDROLIX_URL` + `/mcp` → server bind URL + `/mcp`)

## Impact

- **mcp_hydrolix/auth/oauth.py**: `OAuthConfig` and `load_oauth_config()`
- **mcp_hydrolix/webapp.py**: route registration and 401 response headers
- **tests/test_oauth_resource_metadata.py**: new test module
- **Upstream dependency**: `oauth-config-and-preflight` must land first
- **Hydrolix cluster deployment (out-of-repo)**: Traefik fronts many services in the cluster, so the new ingress rule must be **narrowly scoped**: exact path match on `/.well-known/oauth-protected-resource/mcp`, routed to the MCP service, allowing unauthenticated `GET`. Without this rule Traefik will reject discovery requests before they reach the application; with a broader rule the unauthenticated path would leak to neighboring services. This must be coordinated with the o6r / cluster ops change that ships alongside this code. Resolves the Traefik open question deferred from `oauth-config-and-preflight`.
