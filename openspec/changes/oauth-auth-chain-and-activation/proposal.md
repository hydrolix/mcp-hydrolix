*Extend `HydrolixCredentialChain.get_middleware()` to accept an optional `OAuthHydrolixAuthProvider` and prepend it to the existing `ChainedAuthBackend`, then install the resulting chain per uvicorn worker inside `webapp.py:create_app()`.*

## Why

The MCP server needs a single, consistent auth chain that enforces OAuth bearer validation when OAuth is active while preserving the existing service-account credential path. `ChainedAuthBackend` already exists in `mcp_hydrolix/auth/mcp_providers.py`; this change adds the OAuth-active composition path — three elements flat — without modifying the class's semantics. The `mcp` singleton must receive this chain inside `webapp.py:create_app()` so each spawned uvicorn worker owns its own activated instance.

## What Changes

- When OAuth is active, each worker's `mcp.auth` becomes a flat three-element chain: OAuth verifier first, SA bearer and get-param backends second and third.
- When OAuth is inactive, the existing two-element SA chain is preserved unchanged.
- An invalid bearer token claimed by the OAuth verifier results in immediate HTTP 401; the SA chain is never consulted as a fallback for that token.
- Requests with no `Authorization` header fall through to the SA chain.
- Per-worker activation is idempotent; each worker activates independently.

## Capabilities

### New

- `oauth-auth-chain-and-activation` — per-worker auth chain assembly and fail-closed OAuth bearer enforcement

### Modified

*none*

## Impact

- `mcp_hydrolix/auth/mcp_providers.py`: extend `HydrolixCredentialChain.get_middleware()`
- `mcp_hydrolix/webapp.py`: add per-worker OAuth activation call inside `create_app()`
- No new external dependencies; composes types from `oauth-jwt-verifier`
- No public API changes; no data migrations
