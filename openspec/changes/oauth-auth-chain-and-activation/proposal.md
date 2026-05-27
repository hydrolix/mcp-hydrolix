*Extend `HydrolixCredentialChain.get_middleware()` to accept an optional `OAuthHydrolixAuthProvider` and prepend it to the existing `ChainedAuthBackend`, then install the resulting chain per uvicorn worker inside `webapp.py:create_app()`.*

## Why

The MCP server needs a single, consistent auth chain that enforces OAuth bearer validation when OAuth is active while preserving the existing service-account credential path. `ChainedAuthBackend` already exists in `mcp_hydrolix/auth/mcp_providers.py`; this change adds the OAuth-active composition path — three elements flat — without modifying the class's semantics. The `mcp` singleton must receive this chain inside `webapp.py:create_app()` so each spawned uvicorn worker owns its own activated instance.

## What Changes

- Extend `HydrolixCredentialChain.get_middleware()` with an optional `oauth_provider=None` parameter. When non-None, the `ChainedAuthBackend` it constructs has `OAuthHydrolixAuthProvider` prepended as the first element, yielding a flat three-element chain: `[OAuthHydrolixAuthProvider, BearerAuthBackend(sa), GetParamAuthBackend(sa, TOKEN_PARAM)]`. When None, the existing two-element chain is returned unchanged.
- Call `_activate_oauth_if_configured()` inside `webapp.py:create_app()` before `mcp.http_app(...)`, passing the resolved provider (or `None`) to `get_middleware()` and assigning the result to `mcp.auth`.
- `OAuthHydrolixAuthProvider` (from `oauth-jwt-verifier`) claims a bearer iff its `iss` matches the OAuth issuer; it defers (returns `None`) otherwise. This makes flat composition safe: an SA bearer JWT (with `/config`-suffixed `iss`) is deferred by the OAuth provider and picked up by `BearerAuthBackend`.
- An invalid bearer token whose `iss` matches the OAuth issuer results in HTTP 401 with `WWW-Authenticate: Bearer` and the RFC 9728 `resource_metadata=` header from the OAuth provider. The SA chain is never tried for that request.
- Requests with no `Authorization` header fall through to the SA chain unchanged.
- Per-worker activation is idempotent: each uvicorn worker activates independently against its own `mcp` singleton.

## Capabilities

### New

- `oauth-auth-chain-and-activation` — per-worker auth chain assembly and fail-closed OAuth bearer enforcement

### Modified

*none*

## Impact

- `mcp_hydrolix/auth/mcp_providers.py`: extend `HydrolixCredentialChain.get_middleware()` with `oauth_provider=None`; no changes to `ChainedAuthBackend` class semantics.
- `mcp_hydrolix/webapp.py`: add `_activate_oauth_if_configured()` call inside `create_app()` before `mcp.http_app(...)`.
- No new external dependencies; composes types from the `oauth-jwt-verifier` sub-spec (`OAuthBearerToken`, `OAuthHydrolixAuthProvider`).
- No public API changes; the `mcp.auth` seam is an internal FastMCP attribute.
- No data migrations.
