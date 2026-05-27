*Add a JWT claim verifier for OAuth bearer tokens: iss-based routing for chain composability, issuer, audience, required-scopes, and end-to-end bearer acceptance.*

## Why

Cluster operators need a way to gate MCP tool access on OIDC-issued bearer tokens. The core verifier — iss-based routing, issuer match, audience allowlist, required scopes, and signature check — is the independently reviewable piece that downstream composition (`oauth-auth-chain-and-activation`) mounts into the request path. Separating it from configuration parsing (`oauth-config-and-preflight`) and chain assembly makes each piece auditable in isolation.

## What Changes

- OAuth bearer tokens are routed to the OAuth verifier by `iss` claim; service-account bearers are deferred to the SA backend (iss-based routing for chain composability).
- JWTs with an issuer that does not match the configured OAuth issuer URL are rejected with 401.
- JWTs with no `aud` value in the configured audience allowlist are rejected with 401.
- JWTs missing a required scope (when scopes are configured) are rejected with 401.
- Well-formed bearers satisfying all claim checks are authenticated and dispatched to the MCP tool layer.

## Capabilities

### New

*none*

### Modified

- `oauth-authentication` — JWT claim validation: iss-based routing for chain composability, signature/audience/scopes/expiry verification, non-conflation invariant, end-to-end happy path

## Impact

- `mcp_hydrolix/auth/oauth.py`: new verifier classes.
- `fastmcp` `JWTVerifier`: integration point (existing dep from `oauth-config-and-preflight`).
- `tests/auth/test_oauth_jwt_verifier.py`: new test module.
- Downstream: `oauth-auth-chain-and-activation`.
