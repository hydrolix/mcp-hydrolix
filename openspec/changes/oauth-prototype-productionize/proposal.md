## Why

The OAuth 2.1 prototype on `il/feature/oauth-support/hdx-11133` covers the intended shape — RS256 verifier, OIDC discovery, fail-open startup, fail-closed request-time, RFC 9728 metadata, in-cluster JWKS backchannel, SA-credential fallback — with 8 test files. But it is investigation-grade: the tests haven't been re-verified against current `main` deps, the security checklist isn't signed off, and end-to-end validation against the production IdP (a cluster-deployed OIDC proxy being built concurrently by the turbine-API team under HDX-11431) hasn't happened.

It also predates the gunicorn→uvicorn migration (HDX-10675). The prototype mutates `mcp.auth` once in the Gunicorn supervisor — but on `main`, uvicorn spawns workers that re-import `webapp.py:create_app` from scratch, so supervisor-side mutations don't propagate. The activation path is structurally broken on `main`.

Shipping this is the prerequisite for the cluster-served auth story: the in-cluster mcp-hydrolix pod behind Traefik at `/mcp`, with the cluster-deployed IdP proxy issuing bearers. The verifier is OIDC-agnostic by construction (plain discovery + JWKS), so this change can land in parallel with HDX-11431.

## What Changes

- Rebase `il/feature/oauth-support/hdx-11133` onto current `main`; resolve `mcp_hydrolix/main.py` conflicts against the uvicorn factory entrypoint and drop the prototype's `gunicorn.app.base.BaseApplication` / `CoreApplication` dead code.
- Move OAuth activation from supervisor-side `main.py:_maybe_activate_oauth()` into the per-worker `webapp.py:create_app()` factory. `asyncio.run(try_activate_oauth(cfg))` is safe inside the factory (workers have no running loop yet at factory-import time); under a running loop it raises `RuntimeError` as the intended loud-failure mode.
- Activate OAuth iff `HYDROLIX_OAUTH_AUDIENCE` is set and an issuer is resolvable: explicit `HYDROLIX_OAUTH_ISSUER` wins, else derived via `canonical_idp_endpoints(HYDROLIX_URL)`, else no activation. Partial configuration is a fatal `OAuthConfigError` at startup, not a silent no-op. When no OAuth env vars are set, behavior is byte-identical to `main`.
- Introduce `canonical_idp_endpoints(hydrolix_url)` in a new `mcp_hydrolix/auth/idp_endpoints.py` — the **one deliberate exception** to track 1's IdP-agnosticism, the only place encoding the cluster-URL-to-IdP convention. The body raises `NotImplementedError` referencing HDX-11431 until the turbine-API team publishes the convention; until then, explicit `HYDROLIX_OAUTH_ISSUER` is the only activatable issuer source.
- Add the issuer/URL non-conflation guard: a JWT with `iss=<HYDROLIX_URL>` is rejected with 401, distinct from a JWT with `iss=<HYDROLIX_OAUTH_ISSUER>`.
- Audit `logger.*` call sites in `oauth.py`, `mcp_providers.py`, `mcp_server.py`, `webapp.py` against the spec's credential-leak contract: raw JWT, signature segment, base64url header/payload segments, full `Authorization` header value, and JWKS private exponents are excluded from logs. Decoded claims are permitted.
- Port `docs/oauth.md`: updated for the uvicorn entrypoint, the `mcp-hydrolix,config-api` audience example, and the 16-row HDX-11133 security checklist verbatim with per-row sign-off or carve-out annotations.

This change preserves the prototype's existing env-var surface unchanged: `HYDROLIX_OAUTH_ISSUER`, `HYDROLIX_OAUTH_AUDIENCE`, `HYDROLIX_OAUTH_JWKS_URI`, `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS`, `HYDROLIX_OAUTH_REQUIRED_SCOPES`, `HYDROLIX_OAUTH_RESOURCE_URL`.

**Two-track structure** (see design.md): (1) the mcp-hydrolix codebase is as IdP-agnostic as possible — verifier takes issuer + JWKS URI as config and doesn't care which IdP issued the token, with the single named exception of `canonical_idp_endpoints`; (2) the rollout and end-to-end testing story is bound to the cluster-deployed OIDC proxy built under [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431). Track 1 lets work proceed in parallel with HDX-11431; track 2 is what the validation gates and operator docs target.

## Capabilities

### New Capabilities

- `oauth-authentication`: Bearer-token authentication for the HTTP/SSE MCP transports, activated by `HYDROLIX_OAUTH_ISSUER`+`HYDROLIX_OAUTH_AUDIENCE`. Covers OIDC discovery + JWKS preflight at startup (fail-open with WARNING log), per-request JWT verification with chained SA-credential fallback (fail-closed with 401 + RFC 6750 `WWW-Authenticate`), RFC 9728 protected-resource-metadata endpoint, log redaction guarantees, and the issuer/URL non-conflation invariant.

### Modified Capabilities

None. `openspec/specs/` is empty; no existing capability requirements are being changed.

## Impact

- **Code**: new `mcp_hydrolix/auth/oauth.py` and `mcp_hydrolix/auth/idp_endpoints.py` (the single IdP coupling seam); modified `mcp_hydrolix/auth/mcp_providers.py` (`ChainedAuthBackend`, `HydrolixCredentialChain`), `mcp_hydrolix/main.py` (drop Gunicorn class + supervisor-side activation), `mcp_hydrolix/webapp.py` (host OAuth activation in factory); `pyproject.toml` + `uv.lock` (new FastMCP `JWTVerifier` dep).
- **APIs**: new unauthenticated `/.well-known/oauth-protected-resource` (RFC 9728) when OAuth is active; authenticated MCP endpoints gain a 401 + `WWW-Authenticate: Bearer realm=…, resource_metadata=…` response path.
- **Tests**: 8 prototype `tests/auth/test_*.py` files port over pending re-verification against current `main` (assume rework, not clean port). New tests cover the issuer/URL non-conflation guard, the log-redaction contract, the activation-gate precedence chain, and the `canonical_idp_endpoints` stub.
- **Docs**: `docs/oauth.md` updated for the uvicorn entrypoint, the audience example, and the `Security checklist (HDX-11133 section 4)` section with per-row annotations.
- **Dependencies**: FastMCP `JWTVerifier` and its transitive crypto/JWT deps.
- **Deployments**: no OAuth env vars → zero behavioral change. With OAuth env vars set: internal SA-credential callers continue to work via the chained fallback; valid IdP-issued bearers succeed; invalid bearers get 401.
- **Related work**: HDX-11441 (`HYDROLIX_URL`) has spec PR [#101](https://github.com/hydrolix/mcp-hydrolix/pull/101) open; runtime PR not yet open. This change doesn't depend on it landing first.
