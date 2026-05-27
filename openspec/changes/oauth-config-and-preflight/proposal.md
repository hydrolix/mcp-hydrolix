*Adds configuration loading, activation gating, canonical IdP endpoint derivation, JWKS URI override, and fail-open startup preflight for OAuth bearer authentication.*

## Why

mcp-hydrolix needs a well-defined configuration layer before any OAuth-adjacent feature can ship: the rules governing which env vars activate OAuth, how the issuer is resolved, how insecure JWKS URIs are guarded, and what happens when OIDC discovery fails at startup must all be specified and tested independently of the verifier, the resource-metadata endpoint, and the auth-chain wiring. This change establishes that foundation.

## What Changes

- Add `load_oauth_config()` that reads and validates `HYDROLIX_OAUTH_*` env vars and raises `OAuthConfigError` for partial configuration.
- Add activation gating: OAuth activates only when `HYDROLIX_OAUTH_AUDIENCE` is set and an issuer is resolvable via explicit `HYDROLIX_OAUTH_ISSUER` or via derivation from `HYDROLIX_URL`.
- Add `canonical_idp_endpoints(hydrolix_url)` in a new `auth/idp_endpoints.py` module as the single encapsulation point for cluster-URL-to-IdP knowledge.
- Add JWKS URI override (`HYDROLIX_OAUTH_JWKS_URI`) with an insecure-transport guard that rejects `http://` URIs unless `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS=true` is set.
- Add fail-open startup preflight: OIDC discovery or JWKS fetch failures at startup log a WARNING and continue serving with the credential chain; they do not crash the worker.
- Distinguish two fatal-startup exception types: `OAuthConfigError` for operator misconfiguration, `NotImplementedError` (propagated directly) for the pre-[HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) stub case.

## Capabilities

### New

- `oauth-config-and-preflight` — OAuth activation gating, env-var config loading, IdP endpoint derivation, and startup preflight

### Modified

*none*

## Impact

- **mcp_hydrolix/auth/oauth.py**: Add or update `OAuthConfig` dataclass, `load_oauth_config()`, `OAuthConfigError`.
- **mcp_hydrolix/auth/idp_endpoints.py** (new file): `CanonicalIdPEndpoints` frozen dataclass and `canonical_idp_endpoints()` stub.
- **mcp_hydrolix/webapp.py**: `_activate_oauth_if_configured()` helper calls `load_oauth_config()` and handles fail-open preflight errors; called from `create_app()`.
- **tests/auth/**: New test modules for config loading, idp-endpoint stub contract, and startup preflight behavior.
- No new production dependencies beyond what the JWT verifier already requires.
