*Extend `HydrolixCredentialChain.get_middleware()` with an optional OAuth provider parameter, yielding a flat three-element `ChainedAuthBackend` when OAuth is active, installed per worker inside `webapp.py:create_app()`.*

## Goals / Non-Goals

**Goals**:
- Compose `OAuthHydrolixAuthProvider` into a flat `ChainedAuthBackend` alongside the existing SA credential chain.
- Install the resulting chain via `mcp.auth` assignment inside `create_app()`.
- Preserve the two-element SA credential chain unchanged when OAuth is inactive.

**Non-Goals**:
- OIDC discovery and JWKS preflight (owned by `oauth-config-and-preflight`).
- JWT claim validation logic (owned by `oauth-jwt-verifier`).
- Log redaction of OAuth material (owned by `oauth-log-redaction`).
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
- **Alternatives**: supervisor-side; FastMCP lifespan; per-request lazy; `subprocess_setup` callback — all rejected.
- **Binding**: `_activate_oauth_if_configured()` MUST appear in `create_app()` before `mcp.http_app(...)`. No other call site is valid.

### Decision: asyncio-run-inside-the-factory

- **Choice**: `try_activate_oauth(cfg)` is driven with a fresh `asyncio.run(...)` call inside `create_app()`, before the event loop starts.
- **Why**: uvicorn imports the factory before `Server.serve()`; the loop is not yet running. `multiprocessing` spawn workers start with no running loop. This is the only safe site.
- **Alternatives**: `loop.run_until_complete(...)` (requires an existing loop); delegating to lifespan (loop exists but `http_app` already constructed); thread executor (unnecessary indirection).
- **Binding**: If `create_app()` is invoked under an active event loop, `asyncio.run` raises `RuntimeError`. The activation code SHALL catch this and re-raise with a message naming the test setup as the likely cause.

### Decision: configure-auth-via-mcp-auth-assignment-not-fastmcp-constructor

- **Choice**: Assign `mcp.auth = <chain>` inside `create_app()` rather than passing `auth=...` to the `FastMCP(...)` constructor.
- **Why**: `mcp` is a module-level singleton with tools registered at import time. Constructing a new `FastMCP(auth=...)` would require relocating all tool registrations — outside this sub-spec's scope. `mcp.auth` is a public FastMCP attribute that `http_app(...)` reads at the same point.
- **Alternatives**: `FastMCP(auth=...)` constructor (requires relocating registrations); `http_app(auth=...)` (unsupported parameter).
- **Binding**: Install via `mcp.auth = chain` where `chain` is the `ChainedAuthBackend` from `HydrolixCredentialChain.get_middleware()`. No `auth=` argument is passed to `http_app(...)`.

### Decision: chain-construction-lives-in-hydrolixcredentialchain

- **Choice**: `HydrolixCredentialChain.get_middleware()` gains an optional `oauth_provider: AuthProvider | None = None` parameter. When non-None, it prepends `oauth_provider` to the `ChainedAuthBackend` backends list, yielding a flat three-element chain. When None, the existing two-element list is returned unchanged.
- **Why**: One construction site means SA wiring is never duplicated; the two paths differ by a single parameter. `ChainedAuthBackend` itself is not modified.
- **Alternatives**: Ad-hoc construction in `webapp.py:create_app()` — rejected; duplicates SA wiring and risks drift on future refactors.
- **Binding**: The returned chain SHALL always be a flat `ChainedAuthBackend` — never nested. Satisfies the `auth-chain-is-flat` requirement.

## Risks / Trade-offs

- **`asyncio.run` fragile under refactor** → Test that asserts `RuntimeError` when `create_app()` is invoked under an active loop.
- **Workers diverge if preflight fails** → Fail-open per `oauth-config-and-preflight`: workers that succeed serve with OAuth; others serve SA credential chain only with a WARNING log.
- **SA credential chain not consulted for OAuth-claimed bearer** → Intended. Tests MUST cover: invalid OAuth-claimed bearer → 401; SA bearer (different `iss`) → SA credential chain; no-bearer → SA credential chain.
