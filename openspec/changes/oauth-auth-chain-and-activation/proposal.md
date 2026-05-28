*When OAuth is active, each MCP worker validates bearer tokens via the OAuth verifier first, falling back to the existing SA credential chain for non-bearer requests; chain composition and per-worker activation are wired in this change.*

## Family Context / Forward References

One of 5 changes decomposing OAuth bearer authentication for [HDX-11442](https://hydrolix.atlassian.net/browse/HDX-11442). All five target the shared capability `oauth-authentication`. Dependency order:

- `oauth-config-and-preflight` — root of the dep graph.
- `oauth-resource-metadata` — depends on `oauth-config-and-preflight`.
- `oauth-jwt-verifier` — depends on `oauth-config-and-preflight`; this change consumes its `OAuthHydrolixAuthProvider`.
- `oauth-auth-chain-and-activation` (this change) — depends on `oauth-jwt-verifier`.
- `oauth-log-redaction` — orthogonal.

## Why

The MCP server needs a single, consistent auth chain that enforces OAuth bearer validation when OAuth is active while preserving the existing SA credential chain. `ChainedAuthBackend` already exists in `mcp_hydrolix/auth/mcp_providers.py`; this change adds the OAuth-active composition path — three elements flat — without modifying the class's semantics. The `mcp` singleton must receive this chain inside `webapp.py:create_app()` so each spawned uvicorn worker owns its own activated instance.

## What Changes

- When OAuth is active, each worker's `mcp.auth` becomes a flat three-element chain: OAuth verifier first, SA bearer and get-param backends second and third.
- When OAuth is inactive, the existing two-element SA credential chain is preserved unchanged.
- An invalid bearer token claimed by the OAuth verifier results in immediate HTTP 401; the SA credential chain is never consulted as a fallback for that token.
- Requests with no `Authorization` header fall through to the SA credential chain.
- Per-worker activation is idempotent; each worker activates independently.

## Capabilities

### New

*none*

### Modified

- `oauth-authentication`:
  - Flat three-element auth chain `[OAuth, BearerSA, GetParamSA]` when OAuth is active, two-element SA credential chain when inactive.
  - Per-worker activation in `webapp.py:create_app()`.
  - Request-time fail-closed behavior for OAuth-claimed bearers.
  - SA credential fallback preservation.

## Impact

- `mcp_hydrolix/auth/mcp_providers.py`: extend `HydrolixCredentialChain.get_middleware()`
- `mcp_hydrolix/webapp.py`: add per-worker OAuth activation call inside `create_app()`
- No new external dependencies; composes types from `oauth-jwt-verifier`
- No public API changes; no data migrations
