*Pure claim validation layer: iss-based routing for chain composability, issuer exact-match, audience allowlist, optional scope enforcement, and end-to-end bearer acceptance — no I/O at request time.*

## Context

- `OAuthConfig` (from `oauth-config-and-preflight`) delivers `issuer`, `audience`, and `required_scopes` as already-validated values.
- SA bearer tokens are JWTs (`iss = {HYDROLIX_URL}/config`) sharing the `Authorization: Bearer` header; `canonical_idp_endpoints` ([HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441)) guarantees `OAuthConfig.issuer != HYDROLIX_URL`.
- This change produces an `OAuthHydrolixAuthProvider` instance that returns an `OAuthBearerToken` on success or `None` on deferral. Downstream the chain-activation change consumes this provider, but understanding this spec doesn't require reading that one.

## Goals / Non-Goals

**Goals:**
- iss-based routing.
- Issuer exact-match.
- Audience allowlist.
- Required-scopes enforcement.
- End-to-end bearer acceptance.

**Non-Goals:**
- Refresh-token, introspection, DPoP.
- Parsing env vars.
- Composing with SA chain.
- Startup conflation check.

## Decisions

### Decision: iss-based-routing-for-chain-composability

- **Choice:** `OAuthHydrolixAuthProvider` peeks `iss` without signature verification. If `iss` matches the resolved OAuth issuer URL, it claims the bearer; otherwise returns `None` and defers.
- **Why:** SA tokens share the `Authorization: Bearer` header. Without routing, the OAuth verifier would consume them, signature check would fail, and SA auth would break. The `iss` claim is the only reliable discriminator; the unverified peek is routing-only.
- **Alternatives:**
    - Shape-based detection via JWT header `alg` — rejected; SA and OAuth tokens may share the same algorithm.
    - "Just try it" fall-through — rejected; a token claimed by one auth protocol must not be accidentally accepted by another auth protocol
- **Binding:** `OAuthHydrolixAuthProvider` MUST extract `iss` without signature verification before dispatching. A non-JWT-shaped bearer MUST be deferred (`None`), not rejected.
- **Note on unknown-issuer tokens:** A token whose `iss` matches neither the OAuth issuer nor the SA `iss` shape defers silently from this verifier — no log line is emitted here. Final-outcome handling for a bearer that defers through the entire chain (likely a deployment / IdP-misconfiguration signal rather than an unauthorized login attempt) is owned by `oauth-auth-chain-and-activation`, which has end-to-end visibility into "no backend claimed this bearer." This change deliberately stays silent on deferral so the chain owner can emit one well-scoped WARNING rather than N per-backend log lines.

### Decision: non-conflation-as-verifier-invariant

- **Choice:** Non-conflation is enforced by the routing predicate: `iss = HYDROLIX_URL` won't match `OAuthConfig.issuer`, so the OAuth verifier defers and no backend claims it; the chain returns 401.
- **Why:** A startup check duplicates the guarantee `canonical_idp_endpoints` already provides (`OAuthConfig.issuer != HYDROLIX_URL`) — no added security, just unnecessary coupling to the `HYDROLIX_URL` env-var surface.
- **Alternatives:** Startup check raising `OAuthConfigError` — rejected; couples this module to `HYDROLIX_URL` env state.
- **Binding:** `OAuthHydrolixAuthProvider` MUST NOT reference `HYDROLIX_URL`. Non-conflation MUST be tested with a hardcoded cluster URL as `iss`, asserting 401 independent of env state.

### Decision: audience-as-set-intersection

- **Choice:** A JWT is accepted if any value in its `aud` claim (normalized to a set) intersects `OAuthConfig.audience`.
- **Why:** JWTs may carry a single `aud` string or an array; the allowlist is comma-separated. Set intersection handles both.
- **Alternatives:** Require all allowlist values in `aud` — rejected; not standard OIDC practice.
- **Binding:** MUST accept when any `aud` value is in the allowlist; MUST reject when none are.

### Decision: scope-claim-union

- **Choice:** Scope enforcement checks both `scope` (space-delimited) and `scp` (array); all configured scopes must be present via either claim.
- **Why:** IdPs vary in scope claim name; supporting both avoids IdP-specific config.
- **Alternatives:** Check only `scope` or only `scp` — rejected; each breaks a major IdP family.
- **Binding:** When `required_scopes` is non-empty, MUST accept via `scope` or `scp`. If neither present, MUST reject.

### Decision: no-io-at-request-time

- **Choice:** Pure in-memory claim validation; JWKS key material loaded at startup and cached.
- **Why:** JWKS prefetch is `oauth-config-and-preflight`'s responsibility; per-request I/O adds latency outside scope.
- **Alternatives:** Lazy JWKS fetch per request — rejected; duplicates preflight and adds latency.
- **Binding:** `OAuthHydrolixAuthProvider` MUST NOT make outbound calls at request time. JWKS MUST be provided at construction.

## Risks / Trade-offs

- Clock skew: verified that FastMCP `JWTVerifier` (3.3.0, `fastmcp/server/auth/providers/jwt.py`) accepts no `leeway` parameter on `__init__` and applies none internally (PyJWT default 0; hand-rolled `exp < time.time()` check has no tolerance either). Clients with skewed clocks against the IdP will see spurious 401s near token expiry. This is **unmitigated by this change**; a follow-up would have to extend FastMCP itself (or wrap its verify call) to add tolerance. Out of scope here.
- JWKS key rotation: out of scope; worker restart required to pick up rotated keys.
