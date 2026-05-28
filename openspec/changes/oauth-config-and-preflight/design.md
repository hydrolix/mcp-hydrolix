*A single `load_oauth_config()` function owns all env-var parsing; one frozen dataclass owns IdP endpoint knowledge; two distinct exception types surface fatal-startup errors.*

## Context

- `mcp_hydrolix/auth/oauth.py` contains a draft from prior OAuth prototype work; this spec's behavioral contract supersedes the prototype's shape.
- `webapp.py:create_app()` is the per-worker factory ([HDX-10675](https://hydrolix.atlassian.net/browse/HDX-10675)); runs before uvicorn's event loop starts.
- `HYDROLIX_URL` is provided by [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441); consumed here as a plain string; no URL-parsing logic added.
- The cluster-URL-to-IdP convention is [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431)'s deliverable; the derivation function is a stub until it lands.
- The non-conflation invariant (issuer ≠ cluster URL) is enforced at request time by `oauth-jwt-verifier`. See `non-conflation-is-a-verifier-invariant` below.

## OAuthConfig Fields Owned By This Change

`OAuthConfig` is defined here with: `issuer`, `audience`, `required_scopes`, `jwks_uri`, `allow_insecure_jwks`. The `resource_url` field is added by `oauth-resource-metadata` in a later change.

## Goals / Non-Goals

**Goals:**
- Single entry point for all `HYDROLIX_OAUTH_*` validation.
- Single encapsulation point for IdP endpoint knowledge.
- Visually distinct fatal-startup exception types.
- Fail-open network failures at startup.

**Fail-open contract**: `try_activate_oauth()` catches OIDC discovery, JWKS preflight, and HTTP/JSON errors internally; emits the single `WARNING "OAuth configured but not activated <ExcClass>"` log line itself; and returns `None`. Callers (notably `oauth-auth-chain-and-activation`'s wiring function) check the return value rather than catching exceptions.

**Non-Goals:**
- `canonical_idp_endpoints` body ([HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431)).
- Request-time bearer verification (`oauth-jwt-verifier`, `oauth-auth-chain-and-activation`).
- RFC 9728 resource-metadata endpoint (`oauth-resource-metadata`).
- Log-redaction (`oauth-log-redaction`).

## Decisions

### Decision: single-idp-coupling-point

- **Choice:** All IdP endpoint knowledge lives in `canonical_idp_endpoints()` in `mcp_hydrolix/auth/idp_endpoints.py`, returning a frozen dataclass with fields `issuer`, `discovery_url`, `jwks_uri`, `address`.
- **Why:** A single function forces all IdP-shaped changes through one signature and one test suite; `grep canonical_idp_endpoints` is a complete audit of IdP coupling in an otherwise IdP-agnostic codebase.
- **Alternatives:** Separate per-field getters — rejected (IdP knowledge scatters); placing it in [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441)'s module — rejected (wrong dependency direction; that module should not know about OAuth).
- **Binding:** No code outside `mcp_hydrolix/auth/idp_endpoints.py` SHALL encode how IdP endpoint URLs relate to `HYDROLIX_URL`. `load_oauth_config()` SHALL call `canonical_idp_endpoints` when `HYDROLIX_OAUTH_ISSUER` is unset and `HYDROLIX_URL` is set; it SHALL NOT inline URL-construction logic.

### Decision: two-distinct-fatal-startup-exceptions

- **Choice:** `OAuthConfigError` for operator-misconfigured vars; `NotImplementedError` from `canonical_idp_endpoints` propagates unwrapped for the pre-[HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) stub.
- **Why:** The two cases demand different operator actions — "fix your env vars" vs. "wait for [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431)". Wrapping both under one exception type sends operators on a misconfiguration hunt when the real problem is a missing implementation.
- **Alternatives:** Single `OAuthStartupError` — rejected (conflates operationally distinct causes); catch and log + disable — rejected (silences a real capability gap).
- **Binding:** `load_oauth_config()` SHALL raise `OAuthConfigError` for all partial-configuration cases and SHALL NOT catch `NotImplementedError` from `canonical_idp_endpoints`.

### Decision: non-conflation-is-a-verifier-invariant

- **Choice:** No startup check compares `HYDROLIX_OAUTH_ISSUER` against `HYDROLIX_URL`; the non-conflation invariant is enforced at request time by `oauth-jwt-verifier`.
- **Why:** A startup check would couple this change to [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441)'s env-var surface (`HYDROLIX_URL` may be unset) with no security benefit — the verifier rejects a conflated issuer at request time regardless.
- **Alternatives:** Startup assertion comparing the two vars — rejected; [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441) may not have landed and the coupling is not worth the marginal value.
- **Binding:** `load_oauth_config()` SHALL NOT compare `HYDROLIX_OAUTH_ISSUER` against `HYDROLIX_URL`. The conflation test belongs in `oauth-jwt-verifier`'s suite, not here.

## Risks / Trade-offs

- OIDC discovery adds O(hundreds of ms) per worker startup; bounded by a discovery timeout constant; document in `docs/oauth.md`.
- Workers diverge if some preflights fail (some serve with OAuth, others SA-only); operators see WARNING lines per worker; a follow-up can add a Prometheus counter.
- `asyncio.run()` in the factory is fragile if moved under a running loop; a test asserting loud `RuntimeError` in that case guards against future refactors.
- Stub `NotImplementedError` may surprise operators combining `HYDROLIX_OAUTH_AUDIENCE` with `HYDROLIX_URL`; the exception message MUST contain `HDX-11431` and `docs/oauth.md` MUST document the interim requirement for explicit `HYDROLIX_OAUTH_ISSUER`.

## Migration Plan

Unset all `HYDROLIX_OAUTH_*` env vars to restore pre-OAuth behavior; no data or schema changes.

## Open Questions

- Traefik routing: confirm staging cluster rules do not rewrite the `/mcp` prefix in a way that hides `/.well-known/oauth-protected-resource` before `oauth-resource-metadata` ships.
