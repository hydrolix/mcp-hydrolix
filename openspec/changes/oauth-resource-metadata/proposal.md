*Expose the RFC 9728 protected-resource-metadata endpoint and resolve the resource URL from operator configuration.*

## Why

MCP clients that implement OAuth discovery need a standards-compliant `/.well-known/oauth-protected-resource` document to locate the authorization server and construct token requests. Without it, clients must be configured out-of-band. The resource URL that populates the `resource` field must be configurable because the public cluster URL differs from the address the MCP worker binds to.

## Family Context

One of 5 sub-specs decomposing OAuth bearer authentication for [HDX-11442](https://hydrolix.atlassian.net/browse/HDX-11442). All five target the shared capability `oauth-authentication`. Dependency order:

- `oauth-config-and-preflight` — root of the dep graph; this change consumes `OAuthConfig.issuer` from it.
- `oauth-resource-metadata` (this change) — depends on `oauth-config-and-preflight`.
- `oauth-jwt-verifier` — depends on `oauth-config-and-preflight`.
- `oauth-auth-chain-and-activation` — depends on `oauth-jwt-verifier`.
- `oauth-log-redaction` — orthogonal.

## What Changes

- A `/.well-known/oauth-protected-resource` endpoint is available when OAuth is active, returning an RFC 9728 JSON document; returns 404 when OAuth is inactive.
- The endpoint is reachable without authentication (RFC 9728 §3 requirement).
- HTTP 401 responses on authenticated endpoints include a `resource_metadata` pointer to the metadata endpoint in their `WWW-Authenticate` header (requires `oauth-jwt-verifier` or `oauth-auth-chain-and-activation` to be landed; the metadata endpoint itself is independently exercisable).
- `OAuthConfig.resource_url` is resolved from a three-tier precedence chain (`HYDROLIX_OAUTH_RESOURCE_URL` → `HYDROLIX_URL` → server bind URL).
- Setting `HYDROLIX_OAUTH_RESOURCE_URL` without `HYDROLIX_OAUTH_AUDIENCE` triggers the partial-configuration error path defined in `oauth-config-and-preflight`.

## Capabilities

### New

*none*

### Modified

- `oauth-authentication` — adds the RFC 9728 protected-resource-metadata endpoint and the three-tier resource URL precedence chain (`HYDROLIX_OAUTH_RESOURCE_URL` → `HYDROLIX_URL` → server bind URL)

## Impact

- **mcp_hydrolix/auth/oauth.py**: `OAuthConfig` and `load_oauth_config()`
- **mcp_hydrolix/webapp.py**: route registration and 401 response headers
- **tests/test_oauth_resource_metadata.py**: new test module
- **Upstream dependency**: `oauth-config-and-preflight` must land first
