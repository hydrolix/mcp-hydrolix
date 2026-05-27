*Add a JWT claim verifier for OAuth bearer tokens: iss-based routing for chain composability, issuer, audience, required-scopes, and end-to-end bearer acceptance.*

## Why

Cluster operators need a way to gate MCP tool access on OIDC-issued bearer tokens. The core verifier — iss-based routing, issuer match, audience allowlist, required scopes, and signature check — is the independently reviewable piece that downstream composition (`oauth-auth-chain-and-activation`) mounts into the request path. Separating it from configuration parsing (`oauth-config-and-preflight`) and chain assembly makes each piece auditable in isolation.

## What Changes

- Add `OAuthBearerToken` and `OAuthHydrolixAuthProvider` to `mcp_hydrolix/auth/oauth.py`, implementing JWT claim verification via FastMCP's `JWTVerifier`.
- Implement iss-based routing: peek the `iss` claim without signature verification to decide whether to claim or defer a bearer. Hydrolix SA tokens are also JWTs (different `iss`, EdDSA key source); the OAuth verifier defers any bearer whose `iss` does not match the resolved OAuth issuer URL (returns `None`), so SA auth is not broken.
- Enforce issuer exact-match: any JWT whose `iss` does not match the resolved issuer URL (from `OAuthConfig.issuer`) is either deferred (routing predicate) or rejected with 401 (post-claim verification).
- Enforce non-conflation as a verifier invariant: `iss=<HYDROLIX_URL>` is unreachable as an authenticated principal because the routing predicate defers it and no other backend claims it.
- Enforce audience allowlist: any JWT whose `aud` does not intersect `OAuthConfig.audience` is rejected with 401.
- Enforce required scopes when `OAuthConfig.required_scopes` is non-empty.
- Accept well-formed bearers end-to-end: a JWT that passes all claim checks is dispatched to the MCP tool layer.

## Capabilities

### New

- `oauth-jwt-verifier` — pure claim validation for OAuth bearer tokens: issuer, audience, scopes, end-to-end acceptance

### Modified

*none*

## Impact

- `mcp_hydrolix/auth/oauth.py`: New `OAuthBearerToken` and `OAuthHydrolixAuthProvider` classes; claim-validation logic.
- `fastmcp` `JWTVerifier`: new external-dependency integration point (already a dep from `oauth-config-and-preflight`).
- `tests/auth/test_oauth_verifier.py`: New test module using mocked JWTs and a mock JWKS; no I/O at test time.
- No new env vars (all configuration consumed from `OAuthConfig`, parsed upstream by `oauth-config-and-preflight`).
- Downstream: `oauth-auth-chain-and-activation` composes `OAuthHydrolixAuthProvider` with the SA chain.
