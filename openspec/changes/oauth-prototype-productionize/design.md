## Context

The OAuth prototype on `il/feature/oauth-support/hdx-11133` is investigation-grade: it covers the functional shape (RS256 verifier, OIDC discovery, JWKS preflight, RFC 9728 metadata, SA-credential fallback) with 8 test files, but hasn't been re-verified against current `main` deps. HDX-11133 was scoped as a spike; production-readiness was out of scope. Prototype `main.py` calls `_maybe_activate_oauth()`, which `asyncio.run`s `try_activate_oauth(cfg)` and mutates `mcp.auth` — once, in the Gunicorn-era supervisor.

Since then, `main` absorbed HDX-10675 (gunicorn → uvicorn). The new entrypoint:

```
main.py: uvicorn.run("mcp_hydrolix.webapp:create_app", factory=True, workers=N)
webapp.py: create_app() -> mcp.http_app(...) wrapped in RequestTimeoutMiddleware
```

Workers spawn fresh interpreters via `multiprocessing.set_start_method("spawn")`, so each re-imports `webapp.py:create_app` and rebuilds `mcp`. **Supervisor-side `mcp.auth = provider` is invisible to workers.** The prototype's activation path is structurally broken on `main`.

The production IdP is the cluster-deployed OIDC proxy being developed concurrently by the turbine-API team under [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431). mcp-hydrolix talks plain OIDC discovery + JWKS, so the verifier is IdP-agnostic by construction; coverage runs against mock OIDC endpoints.

**Stakeholders**: cluster operators running mcp-hydrolix as an OAuth-authenticated pod behind Traefik at `/mcp`; internal o6r-managed pods using the SA-token chain; laptop/stdio users (no OAuth).

**Binding prior work**:
- HDX-10675 — `webapp.py:create_app` is the activation site.
- HDX-11441 (`HYDROLIX_URL`) — separates "cluster URL" from "OAuth issuer URL". Spec PR [#101](https://github.com/hydrolix/mcp-hydrolix/pull/101) open; runtime PR not yet open. This change adds the non-conflation guard regardless.
- Prototype `oauth.py` public surface (`OAuthConfig`, `load_oauth_config`, `try_activate_oauth`, `OAuthBearerToken`, `OAuthHydrolixAuthProvider`) is the starting point — preserved by default, revised if rebase or review reveals an issue.

## Two-track structure: IdP-agnostic code, IdP-coupled rollout

Two goals look contradictory but aren't:

1. **Code is as IdP-agnostic as possible.** The verifier consumes standard OIDC discovery + JWKS; nothing in `oauth.py`, `webapp.py`, the env-var surface, or the test fixtures encodes which OIDC product issues the tokens. The **one deliberate exception** — encapsulated in a single function (see "Single IdP coupling point" below) — is inferring the canonical IdP endpoints from `HYDROLIX_URL`.

2. **Rollout and end-to-end testing are coupled to HDX-11431.** The "exercise against IdP" gate, the operator-facing docs, and the security checklist all target the cluster-deployed proxy — not Keycloak, not a generic OIDC provider, not the prototype's investigation-time fixtures.

Track 1 is what lets this work proceed in parallel with HDX-11431. Track 2 is what delivers a coherent, testable feature when both pieces meet. Read the rest of this doc with the split in mind: code constraints live on track 1 and are IdP-agnostic; validation and rollout constraints live on track 2 and target HDX-11431.

## Goals / Non-Goals

### Goals

- Land the prototype's OAuth functionality on `main` with all CI green, after re-verifying it against current dependencies and exercising it end-to-end against the cluster-deployed IdP proxy.
- Move OAuth activation into the per-worker factory so workers > 1 actually authenticate.
- Preserve byte-identical behavior when OAuth env vars are unset.
- Add a runtime test asserting `iss=HYDROLIX_URL` is rejected (non-conflation invariant).
- Audit and lock down log content so no JWT bytes can leak.
- Land documentation (`docs/oauth.md`) updated for the uvicorn entrypoint.

### Non-Goals

- Implementing `HYDROLIX_URL` itself (HDX-11441, separate change tracked by spec PR [#101](https://github.com/hydrolix/mcp-hydrolix/pull/101)). The non-conflation test treats `HYDROLIX_URL` as a string operators may have set; it does not require the URL-derivation logic from HDX-11441 to be present.
- Refresh-token flow, token introspection, or DPoP. The verifier uses local JWKS verification only.
- Adding new audience values beyond `mcp-hydrolix,config-api`.
- Adding `webapp.py` to the prototype branch as part of the rebase merge; `webapp.py` is owned by `main` and OAuth code must adapt to it.
- Restructuring `auth/mcp_providers.py` beyond what's required to compose the OAuth verifier with the SA chain.

## Decisions

### Decision: Activation site moves to `webapp.py:create_app()`

OAuth activation happens inside the factory, once per worker process. The flow is:

```python
# webapp.py (post-merge)
def create_app():
    config = get_config()
    _activate_oauth_if_configured()     # NEW; mutates module-level mcp.auth
    app = mcp.http_app(...)
    app = RequestTimeoutMiddleware(app, timeout=config.mcp_timeout)
    return app
```

**Why here**: Workers re-import `webapp.py`; the supervisor never imports `mcp_server.mcp` (the lazy-import note in `main.py` is explicit about this). The factory is the only place `mcp` is guaranteed to exist in the worker's address space.

**Not a FastMCP lifespan event**: Lifespan events fire after `http_app` is constructed; mutating `mcp.auth` before construction is simpler when activation fails and we want to keep serving with the credential chain. Lifespan would also couple OAuth preflight to MCP server lifespan unnecessarily.

**Rejected alternatives**: activate in the supervisor (fails — `mcp.auth` doesn't propagate to spawn workers); per-request lazy activation (first-request latency, worker race window); `subprocess_setup` callback (uvicorn doesn't expose one cleanly, same per-worker I/O cost as the factory path).

### Decision: Single IdP coupling point — `canonical_idp_endpoints(hydrolix_url)`

All knowledge of where the cluster's canonical IdP lives relative to `HYDROLIX_URL` is encapsulated in one function in a new module `mcp_hydrolix/auth/idp_endpoints.py`:

```python
@dataclass(frozen=True)
class CanonicalIdPEndpoints:
    issuer: str           # value the JWT `iss` claim must match
    discovery_url: str    # OIDC discovery endpoint
    jwks_uri: str         # JWKS endpoint (may be cluster-internal backchannel)
    address: str          # network-reachable host[:port] of the IdP service

def canonical_idp_endpoints(hydrolix_url: str) -> CanonicalIdPEndpoints:
    ...
```

This is the one place the cluster-URL-to-IdP convention lives. Reviewers can grep `canonical_idp_endpoints` to find every IdP-coupled callsite. Returning a single immutable record (instead of exposing a class with one method per endpoint) forces any IdP-shaped change to flow through one signature; future "the JWKS URI scheme changed" updates one body and one set of unit tests.

**Config resolution**: `load_oauth_config()` resolves the issuer with precedence `HYDROLIX_OAUTH_ISSUER` (explicit) > `canonical_idp_endpoints(HYDROLIX_URL).issuer` (derived) > unset (no activation). `HYDROLIX_OAUTH_JWKS_URI` follows the same pattern; `.address` is reserved for future health checks / observability and may be unused initially.

**Body raises `NotImplementedError` until HDX-11431**: The URL convention is the turbine-API team's deliverable. Placeholder URLs were considered and rejected — they'd produce activation flows that look correct in tests but talk to an IdP that won't exist on the eventually-published convention. The strict behavior is honest about the current capability surface and forces operators to set `HYDROLIX_OAUTH_ISSUER` explicitly during the interim. Tests pin the eventual contract via the spec's post-HDX-11431 scenarios; replacing the body is a one-function diff.

**Why not put it in HDX-11441's module**: HDX-11441 owns `HYDROLIX_URL` parsing and should not know what OAuth is. Keeping the function in `auth/` keeps the dependency direction right.

### Decision: `asyncio.run(try_activate_oauth(cfg))` replaced with `asyncio.run` *inside* the factory (top-level, no running loop)

The factory runs in the worker's main thread before uvicorn has started its event loop, so a fresh `asyncio.run(try_activate_oauth(cfg))` call is safe. We document this explicitly in the activation code and add a test that runs `create_app()` from within an active asyncio loop and asserts a clear error (so future refactors that move the factory under a running loop fail loudly).

**Why this is safe**: uvicorn imports the factory before calling `Server.serve()`; the loop is not yet running. `multiprocessing` spawn workers start with no running loop.

**Risk**: If the factory is ever invoked under an active loop (e.g. in-process test harnesses), `asyncio.run` raises `RuntimeError`. The activation code should catch and re-raise this with a message pointing at the test setup. (Non-normative — SHALL is reserved for spec requirements.)

### Decision: `_maybe_activate_oauth` becomes `_activate_oauth_if_configured` in `webapp.py`

Symbol moves from `main.py` to `webapp.py`; the prototype's `_maybe_activate_oauth` is deleted. The "maybe" prefix becomes "if_configured" to make the env-var gate explicit at the call site. `tests/auth/test_main_oauth_activation.py` renames to `test_webapp_oauth_activation.py` with monkeypatch targets updated.

### Decision: Two distinct fatal-startup exceptions

The factory has two ways to fatally abort startup:

- `OAuthConfigError` from `load_oauth_config()` for partial / malformed `HYDROLIX_OAUTH_*` configuration (operator error).
- `NotImplementedError` from `canonical_idp_endpoints` for the pre-HDX-11431 stub case — propagates directly, **not** wrapped as `OAuthConfigError`, so operators can distinguish "I set something wrong" from "this code path doesn't exist yet."

Network/discovery failures stay fail-open (the worker logs WARNING and serves with the credential chain only). Spec normatively captures both paths in "Activation gated on operator env vars" and "Fail-open at startup, fail-closed at request time"; this section is rationale.

**Multi-worker consequence**: a worker raising either fatal exception crashes; uvicorn respawns and the same error repeats. Operators get a clear message via uvicorn's error log and the worker-startup-failure backoff path.

### Decision: Non-conflation is a verifier invariant, not a startup check

The verifier rejects any JWT whose `iss` doesn't exactly match the resolved issuer; that's sufficient to make `iss=<HYDROLIX_URL>` unreachable. We don't add a startup check that `HYDROLIX_OAUTH_ISSUER != HYDROLIX_URL` because (a) HDX-11441's runtime PR hasn't landed, so `HYDROLIX_URL` may be unset, and (b) a startup check would couple this change to HDX-11441's env-var surface for no security benefit.

The test (`tests/auth/test_oauth_verifier.py::test_iss_equal_to_hydrolix_url_rejected`) mints a token with `iss` set to a hypothetical cluster URL and asserts 401, independent of real `HYDROLIX_URL` state.

### Decision: Log content is a tested invariant

`tests/auth/test_log_redaction.py` runs the full request path under `caplog` and asserts no log record contains the raw JWT, the signature segment, the encoded header/payload segments, the `Authorization` header value, or JWKS private exponents. Call paths covered: successful activation, discovery failure, valid bearer accepted, invalid bearer rejected, SA path with no bearer, OAuthConfigError raised. This backs the security-checklist sign-off from the ticket.

### Decision: Drop Gunicorn dead code as part of this rebase

Prototype `main.py` still imports `gunicorn.app.base.BaseApplication` and defines `CoreApplication`; `main` has neither and `pyproject.toml` no longer carries the `gunicorn` dep. The rebase drops the Gunicorn imports, `CoreApplication`, the supervisor-side OAuth activation call, and any leftover `gunicorn` references in `pyproject.toml` or test mocks. Leaving them in would diverge prototype `main.py` from `main` in ways unrelated to OAuth.

## Risks / Trade-offs

- **OIDC discovery latency per worker startup** — hundreds of ms per worker, parallel across workers, bounded by `DISCOVERY_TIMEOUT_SEC=10.0`. Document the cost in `docs/oauth.md`.
- **Workers diverge if some preflights fail** — fail-open contract: workers that succeed serve with OAuth, others with SA-only; operators see WARNING lines and investigate. A follow-up could add `oauth_activation_failures_total{worker_id}`.
- **`asyncio.run` inside the factory is fragile under refactor** — if the factory is later invoked under a running loop, `asyncio.run` raises `RuntimeError`. Mitigated by an explicit test asserting the loud failure under a running loop.
- **Non-conflation test must not depend on real `HYDROLIX_URL` state** — tests run in worker processes with the real env. Monkeypatch the env var inside the test and mint the token with a hardcoded string.
- **Log redaction regression** — a future `logger.exception(exc)` could leak a token via the exception message. `test_log_redaction.py` runs on every PR and fails loudly.

## Migration Plan

1. **Branch hygiene** (this worktree, `il/feature/oauth-hdx-11442`):
   - Cherry-pick or merge `il/feature/oauth-support/hdx-11133` onto the current branch base.
   - Resolve `mcp_hydrolix/main.py` conflict by accepting `main`'s uvicorn entrypoint and dropping the prototype's `_maybe_activate_oauth` from `main.py` entirely.
   - Resolve `pyproject.toml` by accepting `main`'s deps and re-adding the prototype's new FastMCP JWT verifier dep.

2. **Port activation to `webapp.py`**:
   - Add `_activate_oauth_if_configured()` (renamed from `_maybe_activate_oauth`) in `webapp.py`.
   - Call it inside `create_app()` before `mcp.http_app(...)`.

3. **Add the IdP coupling seam**:
   - Create `mcp_hydrolix/auth/idp_endpoints.py` with `CanonicalIdPEndpoints` and `canonical_idp_endpoints(hydrolix_url)`. Body raises `NotImplementedError` referencing HDX-11431. No placeholder URLs.
   - Wire `load_oauth_config()` to attempt derivation when `HYDROLIX_OAUTH_ISSUER` is unset and `HYDROLIX_URL` is set. `NotImplementedError` propagates through factory initialization; the worker terminates with the HDX-11431-referencing message.
   - Add `tests/auth/test_idp_endpoints.py`: the stub raises `NotImplementedError` with `HDX-11431` in the message; the eventual-return contract (frozen four-field record, equal on same input, non-conflation invariant) as xfail/skipped tests that flip to passing when the body is replaced.

4. **Test fixups**:
   - Rename `tests/auth/test_main_oauth_activation.py` → `tests/auth/test_webapp_oauth_activation.py`; update monkeypatch targets to `mcp_hydrolix.webapp`.
   - Add `tests/auth/test_oauth_verifier.py::test_iss_equal_to_hydrolix_url_rejected`.
   - Add `tests/auth/test_log_redaction.py` covering 6 call paths.
   - Add `tests/auth/test_oauth_config.py::test_issuer_derived_from_hydrolix_url_when_unset` and `::test_explicit_issuer_overrides_derivation`.
   - Add `tests/auth/test_webapp_multiworker.py` (smoke test exercising `create_app()` twice in the same test process to assert idempotence in isolation; full multi-worker is covered by integration tests on the staging cluster).

5. **Docs**:
   - Port `docs/oauth.md`; update the deployment section to reference `mcp_hydrolix.webapp:create_app` (drop any Gunicorn instructions).
   - Document `HYDROLIX_OAUTH_AUDIENCE="mcp-hydrolix,config-api"` as the example operators should configure.
   - Add a `Security checklist (HDX-11133 section 4)` section reproducing the 16-row checklist verbatim, each row annotated `Signed off:` (with one-line justification) or `Carved out:` (with a `HDX-\d+` follow-up ticket). If the plan doc can't be located, document that in the section and treat the missing rows as carve-outs requiring follow-up tickets before OAuth is enabled in production.
   - Do **not** port `docs/keycloak-mcp-client.json`. It's a HDX-11133 investigation artifact tied to a specific Keycloak setup; the production client registration doc lands in a follow-up once the IdP proxy publishes its registration shape.

6. **Verification gates** (before opening PR):
   - `uv run pytest tests/auth/` and `uv run pytest` (full suite) — all green.
   - Grep: no file under `mcp_hydrolix/auth/` outside `idp_endpoints.py` references `HYDROLIX_URL` for IdP derivation. (One-time implementation check, not a runtime invariant.)
   - Docs: `docs/oauth.md` contains the audience example and the annotated security checklist section.
   - Manual (no OAuth vars): hit MCP tool endpoint, confirm byte-identical behavior to current `main`.
   - Manual (against cluster-deployed IdP proxy): valid bearer → 200; junk bearer → 401 + `WWW-Authenticate`; no bearer → SA chain handles.

7. **Rollback**: unset the OAuth env vars on every running deployment. The activation gate is a no-op without them, so the merged code becomes byte-identical to pre-merge `main` for those deployments.

## Open Questions

- Traefik routing: the spec commits to `/.well-known/oauth-protected-resource` (RFC 9728 default). Confirm before merge that the staging cluster's Traefik rules don't rewrite the `/mcp` prefix in a way that hides the unscoped well-known path. If they do, scope to `/mcp/.well-known/...` and update the spec.
- Prometheus counter for OAuth activation failures + per-request verification outcomes — useful for operability, deferred to a follow-up unless on-call surfaces a need.
