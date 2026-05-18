## Context

The OAuth prototype on `il/feature/oauth-support/hdx-11133` is an investigation-grade implementation of OAuth 2.1 bearer authentication for the MCP HTTP/SSE transports. It covers the intended functional shape (RS256 verifier, OIDC discovery, JWKS preflight, RFC 9728 metadata, SA-credential fallback) and ships with 8 test files under `tests/auth/`. It has not been re-verified against current `main` dependencies. The production IdP is a cluster-deployed OIDC proxy being developed concurrently by a separate team. mcp-hydrolix talks plain OIDC discovery + JWKS verification, so the verifier is IdP-agnostic by construction — unit and integration coverage is built against the OIDC protocol surface (mock JWKS, mock discovery endpoints), not against any specific IdP product. The prototype was developed against the Gunicorn-based supervisor that existed at the time (`gunicorn.app.base.BaseApplication` / `CoreApplication` in `mcp_hydrolix/main.py`). HDX-11133 was scoped as an investigation; production-readiness was explicitly out of scope.

Meanwhile, `main` has absorbed HDX-10675 (the gunicorn→uvicorn migration). The new HTTP path is:

```
main.py: uvicorn.run("mcp_hydrolix.webapp:create_app", factory=True, workers=N)
webapp.py: create_app() -> mcp.http_app(...) wrapped in RequestTimeoutMiddleware
```

Workers are spawned via `multiprocessing.set_start_method("spawn", force=True)`, so each worker is a fresh interpreter that re-imports `webapp.py:create_app` and rebuilds `mcp` from scratch. Module-level mutation in the supervisor process is invisible to workers.

The prototype's startup path is structurally incompatible with this model:

```python
# prototype main.py
def _maybe_activate_oauth() -> None:
    cfg = load_oauth_config()           # may raise OAuthConfigError
    if cfg is None: return
    provider = asyncio.run(try_activate_oauth(cfg))  # network I/O
    if provider is not None:
        mcp.auth = provider             # mutation in supervisor
```

Under uvicorn factory mode, that `mcp.auth = provider` happens once in the supervisor and is then discarded — workers re-import `mcp_server.py` and see `mcp.auth = HydrolixCredentialChain(None)` again.

**Stakeholders**: operators running mcp-hydrolix as an OAuth-authenticated cluster service (in-cluster pod reverse-proxied via Traefik at `/mcp`); operators running mcp-hydrolix as an internal o6r-managed pod relying on SA-token chain; external/laptop users running over stdio (no OAuth).

**Binding context from prior work**:
- HDX-10675 (uvicorn factory entrypoint) — `webapp.py:create_app` is the activation site.
- HDX-11441 (`HYDROLIX_URL`) — separates "cluster public URL" from "OAuth issuer URL". The spec PR is in flight ([#101](https://github.com/hydrolix/mcp-hydrolix/pull/101), open at time of writing); the runtime implementation has not yet started. This change adds the runtime guard that enforces non-conflation regardless of whether `HYDROLIX_URL` is a real env var yet.
- The prototype's existing public surface in `oauth.py` (`OAuthConfig`, `load_oauth_config`, `try_activate_oauth`, `OAuthBearerToken`, `OAuthHydrolixAuthProvider`) is the starting point for this work; the rebase preserves the symbols by default but treats every contract as in-scope for revision if rebase or review reveals an issue.

## Two-track structure: IdP-agnostic code, IdP-coupled rollout

This change pursues two goals that look contradictory at first glance but are not. Read this section before reading the goals, decisions, or migration plan — the apparent tension between them resolves once the two tracks are named.

1. **Product-level implementation (the mcp-hydrolix codebase) is as IdP-agnostic as possible.** The verifier consumes standard OIDC discovery + JWKS and validates RFC 7519 JWT claims. Nothing in `oauth.py`, `webapp.py`, the env-var surface, or the test fixtures encodes knowledge of which OIDC product issues the tokens. Unit and integration tests run against mock OIDC endpoints — there is no Keycloak-specific code path, no IdP-proxy-specific code path, no branching on a vendor. A developer reading or modifying this code should not need to know which IdP runs in production. The **one deliberate exception** is the ability to infer the cluster's canonical IdP endpoints from `HYDROLIX_URL`; that knowledge is encapsulated in a single, well-defined function (see the "Single IdP coupling point" decision below) so the seam is contained, named, and easy to keep small.

2. **Rollout and end-to-end testing are coupled to the cluster-deployed OIDC proxy** being built by the turbine-API team under [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431). The "exercise against IdP" validation gate, the operator-facing onboarding docs, and the security checklist sign-off all target the cluster-deployed proxy — not Keycloak, not a generic OIDC provider, and not the prototype's investigation-time fixtures. Wherever the migration plan refers to "the IdP" or "the cluster-deployed IdP proxy", that's HDX-11431.

The first track is what lets this work proceed in parallel with HDX-11431. The second track is what makes this change deliver a coherent, testable, operator-usable feature when both pieces meet. Decisions, gates, and migration steps below should be read with this split in mind: if a statement constrains code, it lives on track 1 and is IdP-agnostic; if a statement constrains validation or rollout, it lives on track 2 and is bound to HDX-11431.

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

**Why here, not in `main.py`**: Workers re-import `webapp.py`; the supervisor never imports `mcp_server.mcp` at all (the lazy-import note in `main.py` is explicit about this). The factory is the only place where `mcp` is guaranteed to exist in the worker's address space.

**Why not a FastMCP lifespan event**: Lifespan events fire after `http_app` is constructed; if activation fails we want the worker to log WARNING and continue serving with the credential chain, which is simpler if we mutate `mcp.auth` before constructing the app. Lifespan events would also conflate "OAuth preflight" with "MCP server lifespan", coupling two unrelated lifecycles.

**Alternatives considered**:
1. *Activate in `main.py` supervisor before `uvicorn.run`*: Doesn't work — supervisor's `mcp.auth` doesn't propagate to spawn workers.
2. *Per-request lazy activation*: Adds first-request latency and a race window between workers; rejected.
3. *Activate in a separate worker `subprocess_setup` callback*: Possible, but uvicorn does not expose a clean hook and we'd still be re-running the same I/O once per worker. The factory path achieves the same with less plumbing.

### Decision: Single IdP coupling point — `canonical_idp_endpoints(hydrolix_url)`

All knowledge of where the cluster's canonical IdP (the cluster-deployed OIDC proxy from HDX-11431) lives relative to `HYDROLIX_URL` is encapsulated in a single function with a fixed signature:

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

This function is THE one deliberate exception to track 1's IdP-agnosticism. Everywhere else in the code, the OAuth machinery accepts an issuer URL + JWKS URI from configuration and verifies tokens without caring where those URLs come from. This function is where the cluster-URL-to-IdP convention lives. Nothing else in `auth/` may encode that convention; if a callsite needs to know "where is the IdP for this cluster?", it calls this function.

**Where it lives**: `mcp_hydrolix/auth/idp_endpoints.py` (new module). Physically separate from `oauth.py` to make the seam unmistakable — code reviewers should be able to grep `canonical_idp_endpoints` and find every IdP-coupled callsite in one pass.

**How it's used in config resolution**: `load_oauth_config()` adopts a precedence chain mirroring HDX-11441's pattern:
- `HYDROLIX_OAUTH_ISSUER` (explicit) wins if set.
- Otherwise, if `HYDROLIX_URL` is set, the issuer is derived via `canonical_idp_endpoints(HYDROLIX_URL).issuer`.
- Otherwise, OAuth is not activated (consistent with the existing gate).

`HYDROLIX_OAUTH_JWKS_URI` follows the same pattern: explicit override wins; otherwise the JWKS URI is normally discovered via OIDC, but `canonical_idp_endpoints(...).jwks_uri` MAY be used as the in-cluster backchannel value when the proxy publishes one. The `.address` field is reserved for future use (health checks, observability) and may be unused in the initial implementation.

**Body is a stub until HDX-11431 publishes conventions**: The cluster-URL-to-IdP URL convention is the turbine-API team's deliverable. Until HDX-11431 names the convention (e.g. "the IdP proxy is served at `{HYDROLIX_URL}/oauth`" or at a sibling subdomain), this function ships with a documented placeholder body that returns endpoints derivable in the simplest way consistent with the current best guess, plus a clearly-marked TODO and the test that pins down the eventual contract. Replacing the body when conventions land is a one-function diff.

**Why a single function, not a class or module**: A class with multiple methods would invite each callsite to grab one piece of IdP knowledge in isolation, scattering the coupling. A function returning a single immutable record forces every consumer to think of the IdP as one named, located entity, and forces any IdP-shaped change to flow through one signature. Future "the JWKS URI uses a different scheme" or "the IdP moved to a different subdomain" changes update one body and one set of unit tests.

**Alternatives considered**:
1. *Inline derivation in `load_oauth_config()` only for issuer*: Diffuses the coupling — if we later need to derive the JWKS URI too, we'd add a second inline derivation. Centralizing now prevents that drift.
2. *Class with method per endpoint*: Adds API surface without buying anything; the dataclass-returned-by-function shape gives readers everything in one read.
3. *Move the function into HDX-11441*: HDX-11441 owns `HYDROLIX_URL` parsing and URL-derivation. Putting the OAuth-shaped derivation there couples HDX-11441 to OAuth, which is the opposite of what we want; HDX-11441 should not know what OAuth is. Keeping the function in `auth/` puts the dependency in the right direction.

### Decision: `asyncio.run(try_activate_oauth(cfg))` replaced with `asyncio.run` *inside* the factory (top-level, no running loop)

The factory runs in the worker's main thread before uvicorn has started its event loop, so a fresh `asyncio.run(try_activate_oauth(cfg))` call is safe. We document this explicitly in the activation code and add a test that runs `create_app()` from within an active asyncio loop and asserts a clear error (so future refactors that move the factory under a running loop fail loudly).

**Why this is safe**: uvicorn imports the factory before calling `Server.serve()`; the loop is not yet running. `multiprocessing` spawn workers start with no running loop.

**Risk**: If the factory is ever invoked under an active loop (e.g. in-process test harnesses), `asyncio.run` raises `RuntimeError`. The activation code SHALL catch and re-raise this with a message pointing at the test setup.

### Decision: `_maybe_activate_oauth` becomes `_activate_oauth_if_configured` in `webapp.py`

Symbol moved from `mcp_hydrolix/main.py` to `mcp_hydrolix/webapp.py`. The prototype's `_maybe_activate_oauth` in `main.py` is deleted. `tests/auth/test_main_oauth_activation.py` is renamed to `tests/auth/test_webapp_oauth_activation.py` and its monkeypatching targets are updated.

**Rationale for the rename**: The new function is no longer called from `main.py`, and the "maybe" prefix is replaced with the more explicit "if_configured" to signal the env-var gate at the call site.

### Decision: `OAuthConfigError` is fatal in the factory

The factory raises `OAuthConfigError` if `load_oauth_config()` raises (malformed `HYDROLIX_OAUTH_*` vars). Network/discovery failures stay fail-open. This mirrors the prototype's split: config errors are operator errors and the worker MUST refuse to start; transient network failures during preflight MUST NOT prevent serving SA-credential traffic.

**Multi-worker consequence**: One worker raising `OAuthConfigError` on import will kill that worker; uvicorn will respawn and the same error will repeat. This is the desired loud-failure mode for misconfiguration. Operators get a clear error message via uvicorn's error log and the supervisor's worker-startup-failure backoff path.

### Decision: Non-conflation guard is a verifier-layer test, not a config-layer check

The check that `iss != HYDROLIX_URL` is enforced by the JWT verifier rejecting any token whose `iss` doesn't exactly match `HYDROLIX_OAUTH_ISSUER`. We do NOT add a startup-time check that `HYDROLIX_OAUTH_ISSUER != HYDROLIX_URL` because:
- HDX-11441's runtime implementation has not landed (spec PR [#101](https://github.com/hydrolix/mcp-hydrolix/pull/101) is in flight, implementation PR not yet open); `HYDROLIX_URL` may be unset at the time this change merges.
- The verifier's strict `iss` match is sufficient — there is no path where a token with `iss=HYDROLIX_URL` is accepted.
- A startup-time check would couple this change to HDX-11441's env-var surface.

The test that codifies this invariant lives in `tests/auth/test_oauth_verifier.py::test_iss_equal_to_hydrolix_url_rejected` (new). It is independent of whether `HYDROLIX_URL` is set in the test environment — it mints a token whose `iss` is a string value matching a hypothetical cluster URL and asserts 401.

### Decision: Log content is a tested invariant, not just a code-review item

Add `tests/auth/test_log_redaction.py` that runs the full request path under `caplog`, asserts that no log record's formatted message contains:
- The raw JWT (`Bearer <token>`),
- The token's `b64.b64.sig` segments,
- The serialized claims dict.

Tested call sites: successful activation, discovery failure, valid bearer accepted, invalid bearer rejected, SA path with no bearer, OAuthConfigError raised. This is what backs the "16-row security checklist" sign-off requirement from the ticket.

### Decision: Drop Gunicorn dead code as part of this rebase, not in a follow-up

The prototype's `mcp_hydrolix/main.py` still references `gunicorn.app.base.BaseApplication` and the `CoreApplication` wrapper. `main` has none of this and `pyproject.toml` on `main` no longer has a `gunicorn` dep. The rebase MUST drop:
- The Gunicorn imports and `CoreApplication` class,
- The OAuth activation call from `main.py`,
- Any `gunicorn` references in `pyproject.toml` or test mocks.

Leaving them in would be a merge-shaped landmine — the prototype's `main.py` would diverge from `main` in ways unrelated to OAuth.

## Risks / Trade-offs

- **OIDC discovery latency at worker startup** → Each worker pays a ~hundreds-of-ms cost; with `workers=8` that's still parallel and bounded by `DISCOVERY_TIMEOUT_SEC=10.0`. Mitigation: the existing 10-second timeout is sufficient; document the cost in `docs/oauth.md`.
- **One worker activates, another fails the preflight** → Workers diverge: some serve with OAuth, others with SA-only. Mitigation: this matches the fail-open contract (better than refusing to serve); operators see the WARNING log lines and can investigate. A follow-up could add a metric counter `oauth_activation_failures_total{worker_id}` for observability.
- **`asyncio.run` inside the factory is fragile under future refactors** → If the factory is later moved under a running loop, activation breaks loudly. Mitigation: explicit test that the factory raises a clear error under a running loop; comment in the code points at this constraint.
- **Test-environment leakage** → The non-conflation test must not depend on `HYDROLIX_URL` being unset; tests run in worker processes with the real env. Mitigation: monkeypatch the env var inside the test, mint the token with a hardcoded string, and assert 401 — no dependency on real `HYDROLIX_URL` state.
- **Log redaction regression** → A future refactor adds a `logger.exception(exc)` that prints the exception message containing a token. Mitigation: the `test_log_redaction.py` suite is run on every PR; CI fails loudly.

## Migration Plan

1. **Branch hygiene** (this worktree, `il/feature/oauth-hdx-11442`):
   - Cherry-pick or merge `il/feature/oauth-support/hdx-11133` onto the current branch base.
   - Resolve `mcp_hydrolix/main.py` conflict by accepting `main`'s uvicorn entrypoint and dropping the prototype's `_maybe_activate_oauth` from `main.py` entirely.
   - Resolve `pyproject.toml` by accepting `main`'s deps and re-adding the prototype's new FastMCP JWT verifier dep.

2. **Port activation to `webapp.py`**:
   - Add `_activate_oauth_if_configured()` (renamed from `_maybe_activate_oauth`) in `webapp.py`.
   - Call it inside `create_app()` before `mcp.http_app(...)`.

3. **Add the IdP coupling seam**:
   - Create `mcp_hydrolix/auth/idp_endpoints.py` with the `CanonicalIdPEndpoints` dataclass and the `canonical_idp_endpoints(hydrolix_url)` function. Ship a documented placeholder body with a TODO referencing HDX-11431 and the best-guess derivation consistent with current information.
   - Wire `load_oauth_config()` to use it for issuer derivation when `HYDROLIX_OAUTH_ISSUER` is unset and `HYDROLIX_URL` is set.
   - Add `tests/auth/test_idp_endpoints.py` covering the return shape (immutable, all four fields populated), input/output stability (same input → equal record), and the placeholder-body behavior so the test fails when HDX-11431 publishes a different convention and the body is updated.

4. **Test fixups**:
   - Rename `tests/auth/test_main_oauth_activation.py` → `tests/auth/test_webapp_oauth_activation.py`; update monkeypatch targets to `mcp_hydrolix.webapp`.
   - Add `tests/auth/test_oauth_verifier.py::test_iss_equal_to_hydrolix_url_rejected`.
   - Add `tests/auth/test_log_redaction.py` covering 6 call paths.
   - Add `tests/auth/test_oauth_config.py::test_issuer_derived_from_hydrolix_url_when_unset` and `::test_explicit_issuer_overrides_derivation`.
   - Add `tests/auth/test_webapp_multiworker.py` (smoke test exercising `create_app()` twice in the same test process to assert idempotence in isolation; full multi-worker is covered by integration tests on the staging cluster).

5. **Docs**:
   - Port `docs/oauth.md` onto this branch; update the "Out-of-cluster deployment" section to reference `mcp_hydrolix.webapp:create_app` instead of any Gunicorn instructions.
   - Do not port `docs/keycloak-mcp-client.json` — it was a HDX-11133 investigation artifact tied to a specific Keycloak setup, not a production reference. The production OIDC client registration document will land in a follow-up once the IdP proxy publishes its registration shape.

6. **Verification gates** (before opening PR):
   - `uv run pytest tests/auth/` — all green.
   - `uv run pytest` (full suite) — all green.
   - Manual: start server with no OAuth env vars, hit MCP tool endpoint, confirm byte-identical behavior to current `main`.
   - Manual: start server against the cluster-deployed IdP proxy, present a valid bearer, confirm 200; present junk bearer, confirm 401 + `WWW-Authenticate`; omit bearer, confirm SA chain handles.
   - Sign off on the 16-row security checklist from the HDX-11133 plan doc.

7. **Rollback**: If post-merge an issue surfaces, the safe rollback is to leave the OAuth env vars unset on every running deployment — the fail-closed activation is a no-op when env vars are absent, so the merged code is byte-identical to pre-merge `main` for those deployments.

## Open Questions

- **Resolved**: The 16-row security checklist from HDX-11133 plan doc section 4 SHALL be reproduced verbatim in `docs/oauth.md` under a "Security checklist (HDX-11133 section 4)" heading as part of this PR. Each row is annotated as either "Signed off" (with one-line justification) or "Carved out" (with a follow-up ticket reference). If the original plan doc cannot be located when this PR is prepared, the absence is itself documented in that section and the missing rows are treated as carve-outs requiring follow-up tickets before OAuth is enabled in production. See the "Security checklist sign-off is reproduced in-tree" spec requirement.
- Should the protected-resource-metadata endpoint be served under `/.well-known/oauth-protected-resource` (RFC 9728 default) or scoped to the MCP base path (`/mcp/.well-known/...`)? The prototype serves the unscoped path. Worth confirming with the Traefik routing rules on the staging cluster before merge.
- Do we want a Prometheus counter for OAuth activation failures and per-request OAuth verification outcomes? Useful for operability but adds scope; recommend deferring to a follow-up unless on-call surfaces a need.
