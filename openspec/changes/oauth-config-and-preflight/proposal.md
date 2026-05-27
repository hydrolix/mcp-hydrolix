*Adds configuration loading, activation gating, canonical IdP endpoint derivation, JWKS URI override, and fail-open startup preflight for OAuth bearer authentication.*

## Why

mcp-hydrolix needs a well-defined configuration layer before any OAuth-adjacent feature can ship: the rules governing which env vars activate OAuth, how the issuer is resolved, how insecure JWKS URIs are guarded, and what happens when OIDC discovery fails at startup must all be specified and tested independently of the verifier, the resource-metadata endpoint, and the auth-chain wiring. This change establishes that foundation.

## What Changes

- OAuth bearer authentication activates only when `HYDROLIX_OAUTH_AUDIENCE` is set and an issuer is resolvable; without those vars the server is byte-identical to a build without OAuth code.
- Partial or conflicting `HYDROLIX_OAUTH_*` configuration causes a fatal startup error surfaced as `OAuthConfigError`.
- All cluster-URL-to-IdP endpoint knowledge is encapsulated in a single module; no other code may encode that mapping.
- Plain-HTTP JWKS URIs are rejected at startup unless an explicit insecure opt-in flag is set.
- OIDC discovery and JWKS preflight failures at startup are fail-open: the worker logs a warning and continues without OAuth active.

## Capabilities

### New

*none*

### Modified

- `oauth-authentication` — adds the env-var activation gate, canonical IdP endpoint derivation, JWKS URI override and insecure transport flag, and fail-open OIDC discovery + JWKS startup preflight

## Impact

- **mcp_hydrolix/auth/oauth.py**: config loading and error types
- **mcp_hydrolix/auth/idp_endpoints.py** (new): IdP endpoint encapsulation module
- **mcp_hydrolix/webapp.py**: startup activation wiring
- **tests/auth/**: new test modules
- No new production dependencies
