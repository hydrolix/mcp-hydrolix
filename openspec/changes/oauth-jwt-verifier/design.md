*Pure claim validation layer: iss-based routing for chain composability, issuer exact-match, audience allowlist, optional scope enforcement, and end-to-end bearer acceptance — no I/O at request time.*

## Context

- `OAuthConfig` (from `oauth-config-and-preflight`) delivers `issuer`, `audience`, and `required_scopes` as already-validated values.
- SA bearer tokens are JWTs (`iss = HYDROLIX_URL/config`) sharing the `Authorization: Bearer` header; `canonical_idp_endpoints` ([HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441)) guarantees `OAuthConfig.issuer != HYDROLIX_URL`.
- This sub-spec produces an `OAuthHydrolixAuthProvider` instance that returns an `OAuthBearerToken` on success or `None` on deferral. Downstream the chain-activation sub-spec consumes this provider, but understanding this spec doesn't require reading that one.

## Goals / Non-Goals

**Goals:** iss-based routing; issuer exact-match; audience allowlist; required-scopes enforcement; end-to-end bearer acceptance.

**Non-Goals:** Refresh-token, introspection, DPoP; parsing env vars; composing with SA chain; startup conflation check.

## Decisions

### Decision: iss-based-routing-for-chain-composability

- **Choice:** `OAuthHydrolixAuthProvider` peeks `iss` without signature verification. If `iss` matches the resolved OAuth issuer URL, it claims the bearer; otherwise returns `None` and defers.
- **Why:** SA tokens share the `Authorization: Bearer` header. Without routing, the OAuth verifier would consume them, signature check would fail, and SA auth would break. The `iss` claim is the only reliable discriminator; the unverified peek is routing-only.
- **Alternatives:** Shape-based detection via JWT header `alg` — rejected; SA and OAuth tokens may share the same algorithm.
- **Binding:** `OAuthHydrolixAuthProvider` MUST extract `iss` without signature verification before dispatching. A non-JWT-shaped bearer MUST be deferred (`None`), not rejected.

### Decision: non-conflation-as-verifier-invariant

- **Choice:** Non-conflation enforced by the routing predicate: `iss = HYDROLIX_URL` won't match `OAuthConfig.issuer`, so the OAuth verifier defers and no backend claims it; the chain returns 401. No startup check.
- **Why:** `HYDROLIX_URL` may be unset at startup; a startup check couples this module to that env-var surface for no security benefit.
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

- Clock skew: document a `leeway` parameter (e.g. 30 s) for `exp`/`nbf`.
- JWKS key rotation: out of scope; worker restart required to pick up rotated keys.

## Assumptions

- **Clock-skew leeway**: We assume FastMCP's `JWTVerifier` does not expose a `leeway` parameter. If it does, we will wire `HYDROLIX_OAUTH_LEEWAY_SEC` (default 30 s) to it as a follow-up task.
