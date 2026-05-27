*Adds configuration loading, activation gating, canonical IdP endpoint derivation, JWKS URI override, and fail-open startup preflight for OAuth bearer authentication.*

## Why

mcp-hydrolix needs a well-defined configuration layer before any OAuth-adjacent feature can ship: the rules governing which env vars activate OAuth, how the issuer is resolved, how insecure JWKS URIs are guarded, and what happens when OIDC discovery fails at startup must all be specified and tested independently of the verifier, the resource-metadata endpoint, and the auth-chain wiring. This change establishes that foundation.

## Family Context

One of 5 sub-specs decomposing OAuth bearer authentication for [HDX-11442](https://hydrolix.atlassian.net/browse/HDX-11442). All five target the shared capability `oauth-authentication`. Dependency order:

- `oauth-config-and-preflight` (this change) — root of the dep graph; no upstream deps.
- `oauth-resource-metadata` — depends on this change (consumes `OAuthConfig.issuer` / `OAuthConfig.resource_url`).
- `oauth-jwt-verifier` — depends on this change (consumes `OAuthConfig.issuer`, `audience`, `required_scopes`).
- `oauth-auth-chain-and-activation` — depends on `oauth-jwt-verifier` (composes its provider with the SA chain).
- `oauth-log-redaction` — orthogonal; can land anywhere in the sequence.

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

- **mcp_hydrolix/auth/oauth.py**: config loading, error types, and `try_activate_oauth()` preflight primitive
- **mcp_hydrolix/auth/idp_endpoints.py** (new): IdP endpoint encapsulation module
- **tests/auth/**: new test modules
- No new production dependencies
