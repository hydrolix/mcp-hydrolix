*Expose the RFC 9728 protected-resource-metadata endpoint and resolve the resource URL from operator configuration.*

## Why

MCP clients that implement OAuth discovery need a standards-compliant `/.well-known/oauth-protected-resource` document to locate the authorization server and construct token requests. Without it, clients must be configured out-of-band. The resource URL that populates the `resource` field must be configurable because the public cluster URL differs from the address the MCP worker binds to.

## What Changes

- Add a `/.well-known/oauth-protected-resource` endpoint that returns an RFC 9728 JSON document when OAuth is active; returns 404 when OAuth is inactive.
- The endpoint is unauthenticated by design (RFC 9728 §3 requirement).
- `WWW-Authenticate` 401 responses on authenticated endpoints include a `resource_metadata=<url>` parameter pointing to the metadata endpoint.
- Introduce `OAuthConfig.resource_url` resolved via a three-tier precedence chain: `HYDROLIX_OAUTH_RESOURCE_URL` → `HYDROLIX_URL` → server bind URL.
- Setting `HYDROLIX_OAUTH_RESOURCE_URL` without an activatable OAuth config (no `HYDROLIX_OAUTH_AUDIENCE`) triggers the partial-configuration error path defined in `oauth-config-and-preflight`.

## Capabilities

### New

- `oauth-resource-metadata` — RFC 9728 metadata endpoint and resource URL precedence chain

### Modified

*none*

## Impact

- **mcp_hydrolix/auth/config.py**: Add `resource_url` field to `OAuthConfig`; extend `load_oauth_config()` with the three-tier precedence chain.
- **mcp_hydrolix/webapp.py**: Register `/.well-known/oauth-protected-resource` route; inject `resource_metadata=` into `WWW-Authenticate` headers on 401 responses.
- **tests/test_oauth_resource_metadata.py**: New test module covering all scenarios.
- **No new external dependencies**: endpoint uses stdlib JSON serialization via the existing ASGI framework.
- **Upstream dependency**: `oauth-config-and-preflight` must land first; this change consumes `OAuthConfig.issuer` and the partial-config error path it defines.
