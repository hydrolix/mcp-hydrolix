*Extend `HydrolixCredentialChain.get_middleware()` with an optional OAuth provider parameter, yielding a flat three-element `ChainedAuthBackend` when OAuth is active, installed per worker inside `webapp.py:create_app()`.*

## Context

- Each uvicorn worker re-imports `webapp.py` via `multiprocessing` spawn; the `mcp` singleton lives only in the worker's address space. The supervisor cannot propagate `mcp.auth` to workers.
- [HDX-10675](https://hydrolix.atlassian.net/browse/HDX-10675) established `webapp.py:create_app()` as the per-worker factory; activation must happen here.
- `mcp` is a module-level singleton with decorator-bound tools registered at import time; it cannot be reconstructed per worker without relocating all tool registrations.
- `ChainedAuthBackend` already exists at `mcp_hydrolix/auth/mcp_providers.py:26` with unchanged semantics: first non-None result wins; a raised exception propagates immediately. This change adds a new composition path; it does not modify the class.
- `OAuthHydrolixAuthProvider` (from `oauth-jwt-verifier`) claims a bearer iff its `iss` matches the resolved OAuth issuer; it defers (returns `None`) otherwise. This contract makes flat composition safe.
- `HydrolixCredentialChain` is the existing SA credential path, constructing `[BearerAuthBackend(self), GetParamAuthBackend(self, TOKEN_PARAM)]` today.
- FastMCP exposes `mcp.auth` as a post-construction assignment seam; `http_app(...)` reads it when building the ASGI app.

## Goals / Non-Goals

**Goals:**
- Extend `HydrolixCredentialChain.get_middleware()` with `oauth_provider=None` so the OAuth-active and OAuth-inactive paths differ by a single flag.
- When OAuth is active, install a single flat `ChainedAuthBackend` with backends `[OAuthHydrolixAuthProvider, BearerAuthBackend(sa), GetParamAuthBackend(sa, TOKEN_PARAM)]` on `mcp.auth` inside `create_app()` before `mcp.http_app(...)` is called.
- When OAuth is inactive, leave `mcp.auth` as the existing two-element chain unchanged.
- Keep `asyncio.run` outside any running event loop; fail loudly if invoked under one.

**Non-Goals:**
- Modifying `ChainedAuthBackend`'s class semantics (unchanged).
- Restructuring tool registrations or moving the `mcp` singleton into the factory.
- Refresh-token flow, token introspection, or DPoP.
- Adding Prometheus counters for activation failures (deferred).

## Decisions

### Decision: Activation Site Is `webapp.py:create_app()`

- **Choice**: OAuth activation (OIDC discovery, JWKS preflight, `mcp.auth` assignment) happens inside `create_app()` before `mcp.http_app(...)`, once per worker.
- **Why**: Workers re-import `webapp.py`; the supervisor never imports `mcp_server.mcp`. `create_app()` is the only place `mcp` is guaranteed to be in the worker's address space. Rejected alternatives: supervisor-side activation (fails — `mcp.auth` does not propagate across spawn boundary); FastMCP lifespan event (fires after `http_app` is constructed, complicating fail-open logic); per-request lazy activation (first-request latency, worker race window); `subprocess_setup` callback (uvicorn does not expose one cleanly).
- **Alternatives**: supervisor-side, FastMCP lifespan, per-request lazy, subprocess_setup callback — all rejected above.
- **Binding**: The activation call `_activate_oauth_if_configured()` MUST appear in `create_app()` before the `mcp.http_app(...)` line. No other call site is valid.

### Decision: `asyncio.run` Inside The Factory

- **Choice**: The async `try_activate_oauth(cfg)` coroutine is driven with a fresh `asyncio.run(...)` call at the top level of `create_app()`, before the event loop starts.
- **Why**: uvicorn imports the factory before calling `Server.serve()`; the loop is not yet running. `multiprocessing` spawn workers start with no running loop. This is the only safe site.
- **Alternatives**: `loop.run_until_complete(...)` (requires an existing loop, not present at factory time); delegating to lifespan (loop exists but `http_app` already constructed); thread executor (unnecessary indirection).
- **Binding**: If `create_app()` is ever invoked under an active event loop, `asyncio.run` raises `RuntimeError`. The activation code SHALL catch this and re-raise with a message pointing at the test setup, so future refactors fail loudly rather than silently.

### Decision: Configure Auth via `mcp.auth` Assignment Not `FastMCP` Constructor

- **Choice**: Assign `mcp.auth = <chain>` inside `create_app()` rather than passing `auth=...` to the `FastMCP(...)` constructor.
- **Why**: `mcp` is a module-level singleton; every tool is registered via `@mcp.tool` at import time. Constructing a new `FastMCP(auth=...)` inside `create_app()` would require relocating all tool registrations — a structural change outside this sub-spec's scope. `mcp.auth` is a public, documented FastMCP attribute; the value written there is identical to what the constructor's `auth=` parameter would store, and `http_app(...)` reads it at the same point when building the ASGI app.
- **Alternatives**: Pass `auth=` to constructor (requires moving all tool registrations); call `http_app(auth=...)` (not a supported parameter on `http_app`).
- **Binding**: The install seam is `mcp.auth = chain` where `chain` is the `ChainedAuthBackend` returned by `HydrolixCredentialChain.get_middleware()` (see "Chain Construction Lives In HydrolixCredentialChain"). `http_app(...)` reads `mcp.auth`; no `auth=` argument is passed to it.

### Decision: Chain Construction Lives In HydrolixCredentialChain

- **Choice**: `HydrolixCredentialChain.get_middleware()` gains an optional `oauth_provider: AuthProvider | None = None` parameter. When non-None, the returned `ChainedAuthBackend`'s backends list is `[oauth_provider, BearerAuthBackend(self), GetParamAuthBackend(self, TOKEN_PARAM)]`. When None, the existing two-element list `[BearerAuthBackend(self), GetParamAuthBackend(self, TOKEN_PARAM)]` is returned unchanged. Activation in `webapp.py:create_app()` calls `chain.get_middleware(oauth_provider=resolved_oauth_provider_or_None)`.
- **Why**: Centralising construction in one method means the SA wiring (`BearerAuthBackend(self)`, `GetParamAuthBackend(self, TOKEN_PARAM)`) is never duplicated. The OAuth-active and OAuth-inactive paths differ by a single parameter, which is easy to test and easy to audit. The `ChainedAuthBackend` class itself is not modified; only its instantiation site gains a new code path.
- **Alternatives considered and rejected**: Constructing the chain ad-hoc in `webapp.py:create_app()` directly. Rejected because it duplicates the per-backend construction logic and risks the two construction sites drifting in the SA wiring (e.g., `BearerAuthBackend(self)` becomes inconsistent if `HydrolixCredentialChain` is refactored).
- **Binding**: The `auth-chain-is-flat` requirement.

## Risks / Trade-offs

- **`asyncio.run` is fragile under refactor** → Mitigated by an explicit test that invokes `create_app()` from within an active asyncio loop and asserts `RuntimeError` with a clear message.
- **Workers diverge if some preflights fail** → Fail-open contract (per `oauth-config-and-preflight`): workers that succeed serve with OAuth; others serve with SA-only. Operators see WARNING lines. A future Prometheus counter can surface this operationally.
- **SA chain never consulted for OAuth-claimed bearer** → This is the intended security property, not a risk. Tests MUST cover both "OAuth-claimed invalid bearer → 401, SA not tried" and "SA bearer (different iss) → SA path via BearerAuthBackend" and "no bearer → SA path".

## Migration Plan

1. Extend `HydrolixCredentialChain.get_middleware()` in `mcp_hydrolix/auth/mcp_providers.py` with `oauth_provider=None`.
2. Add `_activate_oauth_if_configured()` to `webapp.py`; call it in `create_app()` before `mcp.http_app(...)`, passing the resolved provider to `get_middleware(oauth_provider=...)`.
3. Add tests: multi-worker smoke, invalid-bearer (OAuth-claimed) → 401, SA bearer → SA path, no-bearer → SA path, bearer-fails (OAuth-claimed) → SA not consulted, `asyncio.run` under active loop → loud failure, flat-chain shape assertions.
4. Rollback: unset OAuth env vars on every running deployment. Without them, activation is a no-op and behavior is byte-identical to pre-merge `main`.
