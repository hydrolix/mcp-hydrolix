*A single `load_oauth_config()` function owns all env-var parsing; one frozen dataclass owns IdP endpoint knowledge; two distinct exception types surface fatal-startup errors.*

## Context

- `mcp_hydrolix/auth/oauth.py` (from prior investigation on `il/feature/oauth-support/hdx-11133`) contains draft `OAuthConfig`, `load_oauth_config()`, and `OAuthConfigError` — the behavioral contract here supersedes the prototype's shape where they differ.
- `webapp.py:create_app()` is the per-worker factory ([HDX-10675](https://hydrolix.atlassian.net/browse/HDX-10675)); it runs in a fresh spawn-worker before uvicorn's event loop starts, making `asyncio.run()` safe at that call site.
- `HYDROLIX_URL` is provided by [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441) and consumed here purely as a string; this change adds no URL-parsing logic of its own.
- The cluster-URL-to-IdP convention is the turbine-API team's deliverable under [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431); the derivation function body is a stub until that ticket lands.
- The non-conflation invariant (issuer ≠ cluster URL) is enforced at request time by `oauth-jwt-verifier`, not at startup; this design deliberately avoids a startup cross-check against `HYDROLIX_URL` to keep this change independent of [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441)'s runtime PR. See the `non-conflation-is-a-verifier-invariant` note below.

## Goals / Non-Goals

**Goals:**

- `load_oauth_config()` is the single entry point for all `HYDROLIX_OAUTH_*` env-var validation and `OAuthConfig` construction.
- `canonical_idp_endpoints(hydrolix_url)` is the single encapsulation point for IdP endpoint knowledge; every IdP-coupled callsite is reachable via `grep canonical_idp_endpoints`.
- Fatal startup errors from operator misconfiguration (`OAuthConfigError`) are visually distinct from fatal startup errors from incomplete implementation (`NotImplementedError`).
- Network/discovery failures at startup are fail-open: the worker logs WARNING and continues.

**Non-Goals:**

- Implementing the `canonical_idp_endpoints` body (that is [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431)'s deliverable; the stub ships here).
- Request-time bearer verification or fail-closed rejection (owned by `oauth-jwt-verifier` and `oauth-auth-chain-and-activation`).
- The RFC 9728 resource-metadata endpoint (owned by `oauth-resource-metadata`).
- Log-redaction guarantees (owned by `oauth-log-redaction`).

## Decisions

### Decision: single-idp-coupling-point

- **Choice:** All IdP endpoint knowledge is encapsulated in `canonical_idp_endpoints(hydrolix_url: str) -> CanonicalIdPEndpoints` in a new module `mcp_hydrolix/auth/idp_endpoints.py`, returning a `@dataclass(frozen=True)` with fields `issuer`, `discovery_url`, `jwks_uri`, `address`.
- **Why:** A single function with a single return type forces any IdP-shaped change to flow through one signature and one set of unit tests. The `grep canonical_idp_endpoints` invariant is enforced: no other code outside `idp_endpoints.py` may encode IdP URL structure. This function is the one deliberate IdP-coupling exception in an otherwise IdP-agnostic codebase.
- **Alternatives:** Separate `get_issuer(url)` / `get_jwks_uri(url)` functions — rejected because they allow IdP knowledge to scatter across callers. Placing the function in `HDX-11441`'s module — rejected because that module owns cluster-URL parsing and should not know what OAuth is; keeping it in `auth/` preserves the right dependency direction.
- **Binding:** No code outside `mcp_hydrolix/auth/idp_endpoints.py` SHALL encode how IdP endpoint URLs relate to `HYDROLIX_URL`. `load_oauth_config()` SHALL call `canonical_idp_endpoints` when `HYDROLIX_OAUTH_ISSUER` is unset and `HYDROLIX_URL` is set; it SHALL NOT inline any URL-construction logic.

### Decision: two-distinct-fatal-startup-exceptions

- **Choice:** `OAuthConfigError` is raised by `load_oauth_config()` for operator-misconfigured `HYDROLIX_OAUTH_*` vars; `NotImplementedError` from `canonical_idp_endpoints` propagates directly (not wrapped) for the pre-[HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) stub case.
- **Why:** The two cases require different operator responses: `OAuthConfigError` means "fix your env vars"; `NotImplementedError` means "this code path isn't implemented yet — wait for [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431)". Wrapping `NotImplementedError` in `OAuthConfigError` would send operators on a misconfiguration hunt when the actual problem is a missing implementation.
- **Alternatives:** Wrap all fatal errors in a single `OAuthStartupError` — rejected because it conflates two operationally distinct causes. Catch `NotImplementedError` and emit a friendly log + disable — rejected because the stub raises to signal "not yet implemented", not "transient failure"; silencing it would hide a real capability gap.
- **Binding:** `load_oauth_config()` SHALL raise `OAuthConfigError` for all partial-configuration cases and SHALL NOT catch `NotImplementedError` from `canonical_idp_endpoints`. The worker's factory initialization will propagate `NotImplementedError` to the uvicorn error log unchanged.

### Decision: non-conflation-is-a-verifier-invariant

- **Choice:** No startup check compares `HYDROLIX_OAUTH_ISSUER` against `HYDROLIX_URL`; the non-conflation invariant is enforced entirely at request time by the JWT verifier (in `oauth-jwt-verifier`).
- **Why:** A startup check would couple this change to [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441)'s env-var surface — `HYDROLIX_URL` may be unset at startup — with no security benefit: the verifier rejects `iss=<HYDROLIX_URL>` at request time regardless. The `canonical_idp_endpoints` post-condition (returned `issuer` ≠ input `hydrolix_url`) enforces non-conflation for the URL-derivation path by construction.
- **Alternatives:** Add a startup assertion that `HYDROLIX_OAUTH_ISSUER != os.environ.get("HYDROLIX_URL")` — rejected; [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441) may not have landed, and the coupling is not worth the marginal value.
- **Binding:** `load_oauth_config()` SHALL NOT compare `HYDROLIX_OAUTH_ISSUER` against `HYDROLIX_URL`. The test asserting `iss=HYDROLIX_URL` is rejected belongs in `oauth-jwt-verifier`'s test suite, not here.

## Risks / Trade-offs

- [OIDC discovery latency per worker startup, O(hundreds of ms)] → bounded by `DISCOVERY_TIMEOUT_SEC=10.0`; document the cost in `docs/oauth.md`.
- [Workers diverge if some preflights fail — some serve with OAuth, others with SA-only] → fail-open contract; operators see WARNING lines per worker and investigate; a follow-up can add `oauth_activation_failures_total` Prometheus counter.
- [`asyncio.run()` inside the factory is fragile if factory is later moved under a running loop] → add an explicit test asserting loud `RuntimeError` when `create_app()` is called under an active event loop, so future refactors fail fast.
- [Stub `NotImplementedError` may surprise operators who set both `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_URL`] → the exception message MUST contain `HDX-11431`; document the interim requirement for explicit `HYDROLIX_OAUTH_ISSUER` in `docs/oauth.md`.

## Migration Plan

- Unset all `HYDROLIX_OAUTH_*` env vars on any deployment to restore byte-identical pre-OAuth behavior; the activation gate is a no-op without them.
- No data migration required; no schema changes.

## Open Questions

- Traefik routing: confirm that the staging cluster's Traefik rules do not rewrite the `/mcp` prefix in a way that hides `/.well-known/oauth-protected-resource` before the `oauth-resource-metadata` sub-spec ships. (Out of scope for this sub-spec but noted here as a dependency for the resource-metadata change.)
