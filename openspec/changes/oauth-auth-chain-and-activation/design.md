*Extend `HydrolixCredentialChain.get_middleware()` with an optional OAuth provider parameter, yielding a flat three-element `ChainedAuthBackend` when OAuth is active, installed per worker inside `webapp.py:create_app()`.*

## Goals / Non-Goals

**Goals**:
- Compose `OAuthHydrolixAuthProvider` into a flat `ChainedAuthBackend` alongside the existing SA credential chain.
- Install the resulting chain via `mcp.auth` assignment inside `create_app()`.
- Preserve the two-element SA credential chain unchanged when OAuth is inactive.

**Non-Goals**:
- OIDC discovery and JWKS preflight (owned by `oauth-config-and-preflight`).
- JWT claim validation logic (owned by `oauth-jwt-verifier`).
- Log redaction of OAuth material (owned by `oauth-log-redaction`, upcoming).
- RFC 9728 resource metadata endpoint (owned by `oauth-resource-metadata`).

## Context

- Each uvicorn worker re-imports `webapp.py` via `multiprocessing` spawn; the `mcp` singleton lives only in the worker's address space — the supervisor cannot propagate `mcp.auth` across the spawn boundary.
- [HDX-10675](https://hydrolix.atlassian.net/browse/HDX-10675) established `webapp.py:create_app()` as the per-worker factory.
- `mcp` is a module-level singleton; tools are registered via `@mcp.tool` at import time — it cannot be reconstructed per worker without relocating all registrations.
- `ChainedAuthBackend` in `mcp_hydrolix/auth/mcp_providers.py`: first non-None result wins; a raised exception propagates. This change adds a composition path; it does not modify the class.
- `OAuthHydrolixAuthProvider` (from `oauth-jwt-verifier`) defers (`None`) when the bearer's `iss` doesn't match the OAuth issuer — making flat composition safe with the SA credential chain.
- FastMCP exposes `mcp.auth` as a post-construction assignment seam read by `http_app(...)`.

## Decisions

### Decision: activation-site-is-webapp-py-create-app

- **Choice**: OAuth activation (OIDC discovery, JWKS preflight, `mcp.auth` assignment) happens inside `create_app()` before `mcp.http_app(...)`, once per worker.
- **Why**: `create_app()` is the only place `mcp` is in the worker's address space. Supervisor-side activation fails — `mcp.auth` does not cross the spawn boundary. FastMCP lifespan fires after `http_app` is constructed. Per-request activation introduces first-request latency and a race window.
- **Binding**: `_activate_oauth_if_configured()` MUST appear in `create_app()` before `mcp.http_app(...)`. No other call site is valid.

### Decision: asyncio-run-inside-create-app

- **Choice**: `try_activate_oauth(cfg)` is driven with a fresh `asyncio.run(...)` call inside `create_app()`, before the event loop starts.
- **Why**: The `asyncio.run` loop here is a **temporary, setup-only** construct — built to drive one OIDC discovery + JWKS preflight round-trip, then torn down before uvicorn's serving loop ever exists. The two loops never coexist (uvicorn's `Server.serve()` runs after `create_app()` returns), so this is not a "two concurrent runtimes" pattern; it's the canonical Python idiom for running async I/O from a sync context with no live loop. `multiprocessing` spawn workers start with no running loop, so `create_app()` is the only safe site.
- **Alternatives**: `loop.run_until_complete(...)` (requires an existing loop); delegating to lifespan (loop exists but `http_app` already constructed); thread executor (unnecessary indirection).
- **Binding**: If `create_app()` is invoked under an active event loop, `asyncio.run` raises `RuntimeError`. The activation code SHALL catch this and re-raise with a message naming the test setup as the likely cause.

### Decision: configure-auth-via-mcp-auth-assignment-not-fastmcp-constructor

- **Choice**: Assign `mcp.auth = <chain>` inside `create_app()` rather than passing `auth=...` to the `FastMCP(...)` constructor.
- **Why**: `mcp` is a module-level singleton with tools registered at import time. Constructing a new `FastMCP(auth=...)` would require relocating all tool registrations — outside this change's scope. `mcp.auth` is a public FastMCP attribute that `http_app(...)` reads at the same point.
- **Alternatives**: `FastMCP(auth=...)` constructor (requires relocating registrations); `http_app(auth=...)` (unsupported parameter).
- **Binding**: Install via `mcp.auth = chain` where `chain` is the `ChainedAuthBackend` from `HydrolixCredentialChain.get_middleware()`. No `auth=` argument is passed to `http_app(...)`.

### Decision: chain-construction-lives-in-hydrolixcredentialchain

- **Choice**: `HydrolixCredentialChain.get_middleware()` gains an optional `oauth_provider: AuthProvider | None = None` parameter. When non-None, it prepends `oauth_provider` to the `ChainedAuthBackend` backends list, yielding a flat three-element chain. When None, the existing two-element list is returned unchanged.
- **Why**: `HydrolixCredentialChain` is the business-logic-specific, fully-bound authentication implementation. `ChainedAuthBackend`, as the generic utility combinator for creating a chain, is not modified simply by the introduction of another composable link.
- **Alternatives**: Ad-hoc construction in `webapp.py:create_app()` — rejected; duplicates SA wiring and risks drift on future refactors.
- **Binding**: The returned chain SHALL always be a flat `ChainedAuthBackend` — never nested. Satisfies the `auth-chain-is-flat` requirement.

### Decision: unrecognized-issuer-warning-at-chain-boundary

- **Choice**: When every backend in the chain defers (`None`) for a bearer-bearing request, the chain owner SHALL (a) emit exactly one WARNING-level log line — including the unverified `iss` claim from the JWT, the configured `OAuthConfig.issuer`, and a fixed greppable failure-mode phrase — and (b) increment a `mcp_hydrolix_unrecognized_issuer_total` counter by 1, before returning 401. Per-backend deferrals stay silent on both surfaces; emission happens only at the boundary where the all-defer outcome is observable. Tokens that are claimed by *some* backend (even if that backend then rejects them) do not trigger either surface.
- **Why**: An `iss` matching neither the OAuth IdP nor the SA shape almost always indicates a deployment problem (wrong IdP URL, stale realm after rotation, audience renamed, SA suffix changed) rather than an unauthorized login attempt. The WARNING is grep-friendly for one-shot diagnosis from a log aggregator; the counter is rate-alertable from Prometheus without parsing log records and lets ops set SLOs (e.g. `rate(...[5m]) > 0` for N minutes → page on-call). Routing both through the chain owner (rather than each backend) avoids N emissions per request, prevents drift if backends are added or reordered, and is the only site where "no one claimed this" is observable. The counter is intentionally unlabeled — an attacker-controlled `iss` value would blow up label cardinality if used as a label.
- **Alternatives**:
    - Per-backend WARNING on each deferral — rejected; turns every legitimate routing decision into noise.
    - ERROR level — rejected; the request was handled correctly, ERROR would page.
    - Suppress entirely — rejected; this is exactly the signal operators need when an IdP rotates or an audience drifts.
    - Include the JWT or its segments in the log — rejected; violates the redaction invariant in `oauth-log-redaction`.
    - Label the counter by `iss` — rejected; attacker-controlled cardinality (each fake `iss` would create a new time series).
- **Binding**: The WARNING and counter increment SHALL both be emitted at the chain-owner site (where all-defer is observable) and nowhere else in the auth layer. The log record's content SHALL NOT contain any prohibited material listed in `oauth-log-redaction`'s `no-jwt-credential-material-in-logs` requirement; the unverified `iss` is permitted because decoded claim values are explicitly allowed by that change.

## Risks / Trade-offs

- **`asyncio.run` fragile under refactor** → documented by test that asserts `RuntimeError` when `create_app()` is invoked under an active loop.
- **Workers diverge if preflight fails** → Mitigated by fail-open behavior per `oauth-config-and-preflight`: workers that succeed serve with OAuth; others serve SA credential chain only with a WARNING log.
- **SA credential chain not consulted for OAuth-claimed bearer** → Intended. Tests MUST cover: invalid OAuth-claimed bearer → 401; SA bearer (different `iss`) → SA credential chain; no-bearer → SA credential chain.
