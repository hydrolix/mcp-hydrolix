*Pure claim validation layer: iss-based routing for chain composability, issuer exact-match, audience allowlist, optional scope enforcement, and end-to-end bearer acceptance — no I/O at request time beyond JWKS key lookup.*

## Context

- `OAuthConfig` (parsed by `oauth-config-and-preflight`) delivers `issuer`, `audience`, and `required_scopes` as already-validated values; the verifier is a consumer, not a parser.
- FastMCP exposes a `JWTVerifier` abstraction; `OAuthHydrolixAuthProvider` wraps it and implements FastMCP's `AuthProvider` protocol.
- Hydrolix service-account (SA) bearer tokens are also JWTs — EdDSA/Ed25519, with `iss = urljoin(HYDROLIX_URL, "/config")` and `aud = "config-api"`, signed with an Ed25519 key from a K8s secret (no JWKS). They are structurally indistinguishable from OAuth-issued JWTs by shape; only the `iss` claim differs. `OAuthHydrolixAuthProvider` uses `iss`-based routing to avoid consuming SA bearers.
- `HYDROLIX_URL` (cluster public URL, [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441)) and `OAuthConfig.issuer` are distinct by construction; the canonical derivation function (`canonical_idp_endpoints`) guarantees `issuer != hydrolix_url`. Non-conflation is enforced by the routing predicate (see `iss-based-routing-for-chain-composability`) and the verifier's issuer exact-match.
- `OAuthBearerToken` is the token type returned by the verifier for authenticated requests; `oauth-auth-chain-and-activation` (downstream) composes it with the SA credential chain.
- Test isolation: tests mint JWTs in-process (no live IdP), mock JWKS endpoint, and assert on claim-check outcomes.

## Goals / Non-Goals

**Goals:**

- Implement iss-based routing for chain composability (new): peek `iss` without signature verification to decide whether to claim or defer a bearer.
- Implement issuer exact-match rejection (R05): any JWT with `iss ≠ OAuthConfig.issuer` that the OAuth verifier has claimed returns 401.
- Implement audience allowlist rejection (R06): any JWT with no `aud` value intersecting `OAuthConfig.audience` returns 401.
- Implement required-scopes enforcement (R07): when `OAuthConfig.required_scopes` is non-empty, reject JWTs missing any listed scope.
- Accept well-formed bearers end-to-end (R12): a JWT passing all checks is dispatched to the MCP tool layer.

**Non-Goals:**

- Refresh-token flow, token introspection, or DPoP — JWKS local verification only.
- Parsing `HYDROLIX_OAUTH_*` env vars — that is `oauth-config-and-preflight`'s responsibility.
- Composing with the SA credential chain — that is `oauth-auth-chain-and-activation`'s responsibility.
- Adding a startup check that `HYDROLIX_OAUTH_ISSUER != HYDROLIX_URL` — the routing predicate and the verifier's issuer exact-match make the conflated case unreachable without coupling to [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441)'s env-var surface.

## Decisions

### Decision: iss-based-routing-for-chain-composability

- **Choice:** `OAuthHydrolixAuthProvider` peeks the `iss` claim from an incoming bearer without verifying the signature. If `iss` matches the resolved OAuth issuer URL, the provider claims the bearer (proceeds to full verification). Otherwise it returns `None` and defers to the next backend in the auth chain.
- **Why:** Hydrolix SA tokens are JWTs and share the `Authorization: Bearer` header. Without a routing discriminator, the OAuth verifier would consume SA bearers — the signature check would fail (different key), and the chain would raise 401 rather than passing the token to the SA verifier. SA auth would silently break. The `iss` claim is the only reliable discriminator: SA tokens carry `iss = <HYDROLIX_URL>/config`, OAuth tokens carry an OIDC issuer URL. This mirrors turbine-api's `TokenValidator.validate_token()` approach, which peeks `iss` before dispatching to the matching verifier.
- **Security note:** The unverified peek is routing-only. Full signature, audience, expiry, and scope verification still gate every success path, so the peek introduces no authentication bypass.
- **Alternatives considered:** Shape-based detection (e.g., probing the JWT header `alg` field for `EdDSA` to identify SA tokens). Rejected because SA tokens are JWTs structurally; both SA and OAuth tokens may use `alg: RS256` or similar in future configurations. The discriminator must come from a payload claim, not from the header `alg`.
- **Binding:** `OAuthHydrolixAuthProvider` MUST use `PyJWT` `decode` with `options={"verify_signature": False}` (or equivalent) to extract `iss` before dispatching. A bearer that is not JWT-shaped (fewer than 3 parts, base64 decode fails, no `iss` claim) MUST be treated as "not mine" and deferred (`None`), not rejected (no 401, no log line).

### Decision: non-conflation-as-verifier-invariant

- **Choice:** Non-conflation (rejecting `iss = HYDROLIX_URL`) is enforced structurally by the routing predicate: `iss = HYDROLIX_URL` will not match `OAuthConfig.issuer` (guaranteed distinct by `canonical_idp_endpoints`), so the OAuth verifier defers the bearer; no SA verifier claims it either (SA `iss` is `HYDROLIX_URL/config`, not bare `HYDROLIX_URL`); the chain's default unhandled-bearer path returns 401. No separate startup check is added.
- **Why:** Per the source design.md ("Non-conflation is a verifier invariant, not a startup check"): (a) [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441)'s runtime PR may not have landed, so `HYDROLIX_URL` may be unset at startup; (b) a startup check would couple this change to [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441)'s env-var surface for no security benefit. The routing predicate plus the chain default already enforce this. The mechanism is now the routing predicate, not a post-verification `iss` re-check: a conflated token (`iss = HYDROLIX_URL`) never reaches full verification because the OAuth verifier defers it and no backend claims it.
- **Alternatives:** Add `if OAuthConfig.issuer == hydrolix_url: raise OAuthConfigError` at startup — rejected because it requires reading `HYDROLIX_URL` in this module and adds a startup failure mode that provides no extra security over the routing-predicate check.
- **Binding:** `OAuthHydrolixAuthProvider` MUST NOT contain any reference to `HYDROLIX_URL`. The non-conflation property MUST be tested by minting a JWT with `iss` equal to a hardcoded cluster URL string and asserting 401 (via chain default), independent of real `HYDROLIX_URL` env state.

### Decision: audience-as-set-intersection

- **Choice:** Audience matching uses set intersection: a JWT is accepted if any value in its `aud` claim (normalized to a set) is present in `OAuthConfig.audience`.
- **Why:** `HYDROLIX_OAUTH_AUDIENCE` is a comma-separated allowlist (e.g. `mcp-hydrolix,config-api`); JWTs may carry a single `aud` string or an array. Set intersection handles both shapes and matches the allowlist semantics described in R06.
- **Alternatives:** Require all allowlist values to be present in `aud` — rejected; that would require every token to carry every audience, which is not standard OIDC practice.
- **Binding:** The verifier MUST accept a JWT whose `aud` contains any single value from the allowlist, and MUST reject a JWT whose `aud` contains no value from the allowlist.

### Decision: scope-claim-union

- **Choice:** Scope enforcement checks both `scope` (space-delimited string) and `scp` (array) claims; all configured scopes must be present.
- **Why:** R07 requires all listed scopes; real IdPs vary in claim name (`scope` vs `scp`). Supporting both avoids IdP-specific config.
- **Alternatives:** Check only `scope` — rejected because `scp` is common in Keycloak-family and OIDC proxy environments. Check only `scp` — rejected for the same reason in reverse.
- **Binding:** When `OAuthConfig.required_scopes` is non-empty, the verifier MUST check both `scope` and `scp` and accept a JWT that satisfies the required set via either claim. If neither claim is present, the JWT MUST be rejected.

### Decision: no-io-at-request-time

- **Choice:** The verifier performs pure in-memory claim validation at request time; JWKS key material is loaded at startup (preflight) and cached.
- **Why:** JWKS preflight is `oauth-config-and-preflight`'s responsibility. The verifier receives already-fetched key material. Per-request I/O would add latency and failure modes outside this sub-spec's scope.
- **Alternatives:** Lazy JWKS fetch per request — rejected; adds latency, is outside this sub-spec's scope, and duplicates preflight logic.
- **Binding:** `OAuthHydrolixAuthProvider` MUST NOT make outbound network calls at request time. JWKS key material MUST be provided at construction time.

## Risks / Trade-offs

- [Token clock skew] → Document a `leeway` parameter (e.g. 30s) for `exp` / `nbf` validation; default value should be conservative but nonzero.
- [JWKS key rotation between preflight and request] → Out of scope for this sub-spec; `oauth-config-and-preflight` owns JWKS lifecycle. Document that a worker restart is required to pick up rotated keys until a key-refresh mechanism is added in a follow-up.

## Open Questions

- Does FastMCP's `JWTVerifier` expose the `leeway` parameter for `exp`/`nbf` clock-skew tolerance, or must it be implemented in the wrapping layer?
