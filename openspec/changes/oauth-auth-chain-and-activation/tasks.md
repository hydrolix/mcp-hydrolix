*4 phases, 20 tasks: auth chain extension, per-worker activation wiring, tests, and docs.*

## 1. Auth Chain Assembly — `HydrolixCredentialChain.get_middleware()`

- [ ] 1.1 Add `oauth_provider: AuthProvider | None = None` to `get_middleware()`; when non-None prepend it to produce `[oauth_provider, BearerAuthBackend, GetParamAuthBackend]`; when None return the existing two-element list [implements: oauth-authentication/auth-chain-is-flat, design/chain-construction-lives-in-hydrolixcredentialchain] — verify: `ruff check mcp_hydrolix/auth/mcp_providers.py` clean

- [ ] 1.2 Add docstring to `get_middleware()` stating: returned `ChainedAuthBackend` is never nested; when `oauth_provider` is set it is the first element [implements: oauth-authentication/auth-chain-is-flat, meta/docs] — verify: `ruff check mcp_hydrolix/auth/mcp_providers.py` clean

## 2. Per-Worker Activation — `webapp.py`

- [ ] 2.1a Add `_activate_oauth_if_configured()` to `webapp.py`: call `load_oauth_config()` (imported from `mcp_hydrolix.auth.oauth`, provided by `oauth-config-and-preflight`); return early (without modifying `mcp.auth`) when `load_oauth_config()` returns `None` — the baseline two-element chain remains installed [implements: oauth-authentication/activation-runs-per-uvicorn-worker, design/activation-site-is-webapp-py-create-app] — verify: `ruff check mcp_hydrolix/webapp.py` clean

- [ ] 2.1b Inside `_activate_oauth_if_configured()`, call `asyncio.run(try_activate_oauth(cfg))` where `try_activate_oauth` is imported from `mcp_hydrolix.auth.oauth` (provided by `oauth-config-and-preflight`). Per its fail-open contract, the primitive returns an `OAuthHydrolixAuthProvider` on success or `None` on preflight failure (and has already emitted the WARNING itself); the wrapper does NOT catch network/HTTP/JSON exceptions from the primitive. Do catch `RuntimeError` from `asyncio.run` itself (i.e. factory invoked under an active loop) and re-raise naming test setup as the likely cause [implements: design/asyncio-run-inside-the-factory] — verify: `ruff check mcp_hydrolix/webapp.py` clean

- [ ] 2.1c Inside `_activate_oauth_if_configured()`, if `resolved_provider` is not None, call `HydrolixCredentialChain().get_middleware(oauth_provider=resolved_provider)` and assign the resulting three-element `ChainedAuthBackend` to `mcp.auth` [implements: oauth-authentication/auth-chain-is-flat, design/configure-auth-via-mcp-auth-assignment-not-fastmcp-constructor] — verify: `grep -n 'mcp.auth' mcp_hydrolix/webapp.py` returns the assignment line

- [ ] 2.1d When `resolved_provider` is `None` (preflight failed), `_activate_oauth_if_configured()` returns without modifying `mcp.auth`; the worker keeps the two-element baseline SA credential chain. The WARNING has already been emitted by `try_activate_oauth` per `oauth-config-and-preflight`'s fail-open contract; no additional log line here [implements: oauth-authentication/activation-runs-per-uvicorn-worker, design/activation-site-is-webapp-py-create-app] — verify: `grep -n 'OAuth configured but not activated' mcp_hydrolix/webapp.py` returns no matches (the only emitter is `mcp_hydrolix/auth/oauth.py`)

- [ ] 2.2 Call `_activate_oauth_if_configured()` inside `create_app()` before `mcp.http_app(...)` [implements: design/activation-site-is-webapp-py-create-app] — verify: `grep -n '_activate_oauth_if_configured' mcp_hydrolix/webapp.py` appears before `mcp.http_app`

## 3. Tests

- [ ] 3.1 "Multi-Worker Activation": call `create_app()` twice sequentially; assert each returns an app whose `mcp.auth` is a `ChainedAuthBackend` with `OAuthHydrolixAuthProvider` first [implements: oauth-authentication/activation-runs-per-uvicorn-worker, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_multi_worker_activation` green

- [ ] 3.2 "Chain Has Three Backends When OAuth Is Active": assert `mcp.auth.backends` is exactly `[OAuthHydrolixAuthProvider, BearerAuthBackend, GetParamAuthBackend]` [implements: oauth-authentication/auth-chain-is-flat, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_chain_has_three_backends_when_oauth_is_active` green

- [ ] 3.3 "Chain Has Two Backends When OAuth Is Inactive": assert `mcp.auth.backends` is exactly `[BearerAuthBackend, GetParamAuthBackend]` [implements: oauth-authentication/auth-chain-is-flat, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_chain_has_two_backends_when_oauth_is_inactive` green

- [ ] 3.4 "Chain Is Not Nested": assert no element of `mcp.auth.backends` is itself a `ChainedAuthBackend` (both active and inactive) [implements: oauth-authentication/auth-chain-is-flat, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_chain_is_not_nested` green

- [ ] 3.5 "Invalid Bearer After Activation": OAuth active, request with bearer whose `iss` matches issuer but is invalid; assert 401 + `WWW-Authenticate: Bearer` with a `resource_metadata=` parameter (parameter shape owned by `oauth-resource-metadata`) [implements: oauth-authentication/active-verifier-is-fail-closed, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_invalid_bearer_after_successful_activation` green

- [ ] 3.6 "Missing Bearer SA Path": OAuth active, no `Authorization` header, valid SA credentials; assert accepted via SA path [implements: oauth-authentication/active-verifier-is-fail-closed, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_missing_bearer_after_successful_activation_internal_sa_path` green

- [ ] 3.7 "No Bearer SA Credential Present": OAuth active, no `Authorization` header; assert success via SA chain [implements: oauth-authentication/sa-credential-fallback-preserved, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_no_bearer_sa_credential_present` green

- [ ] 3.8 "Bearer Present OAuth Verifier Fails": OAuth active, invalid bearer with matching `iss`; assert 401 and SA chain never called [implements: oauth-authentication/sa-credential-fallback-preserved, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_bearer_present_oauth_verifier_fails` green

- [ ] 3.9 "SA Bearer JWT Deferred": OAuth active, bearer with `iss` ending in `/config`; assert `OAuthHydrolixAuthProvider` returns None and `BearerAuthBackend` authenticates [implements: oauth-authentication/sa-credential-fallback-preserved, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_sa_bearer_jwt_is_authenticated_by_bearer_auth_backend_when_oauth_is_active` green

- [ ] 3.10 `create_app()` under active event loop raises `RuntimeError` pointing at test setup [implements: design/asyncio-run-inside-the-factory, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_create_app_under_active_loop_raises` green

- [ ] 3.11 Implement the chain-boundary unrecognized-issuer WARNING: wrap the chain dispatch (in `HydrolixCredentialChain.get_middleware()` or an adjacent helper called from `mcp.auth`) so that when all backends in the chain return `None` for a bearer-bearing request, the wrapper emits one WARNING-level log line containing the unverified `iss` claim, `OAuthConfig.issuer`, and the fixed phrase `"bearer iss matched no chain backend — likely IdP misconfiguration"`, then returns 401. No-bearer requests SHALL NOT trigger this path. The wrapper SHALL be the sole emitter — individual backends remain silent on their own deferrals [implements: oauth-authentication/unrecognized-issuer-surfaces-as-deployment-warning, design/unrecognized-issuer-warning-at-chain-boundary] — verify: `ruff check mcp_hydrolix/auth/mcp_providers.py` clean

- [ ] 3.12 "Bearer With Unknown Issuer Yields 401 And WARNING": OAuth active, bearer whose `iss` matches neither `OAuthConfig.issuer` nor the SA `iss` shape; assert 401 + exactly one WARNING-level log record containing both the unverified `iss` and the configured `OAuthConfig.issuer`, and assert the record contains no raw JWT or base64url segments (cross-check with `oauth-log-redaction`'s caplog helper if available) [implements: oauth-authentication/unrecognized-issuer-surfaces-as-deployment-warning, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_bearer_with_unknown_issuer_yields_401_and_warning` green

- [ ] 3.13 "Routine Deferrals Stay Silent": OAuth active, valid SA bearer (defers from OAuth verifier, claimed by `BearerAuthBackend`); assert no WARNING-level "unrecognized issuer" log record is emitted [implements: oauth-authentication/unrecognized-issuer-surfaces-as-deployment-warning, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_routine_deferrals_stay_silent` green

## 4. Documentation and Rollout

- [ ] 4.1 Update `docs/oauth.md`: document `create_app()` as per-worker activation site and flat chain shape [implements: meta/docs, design/activation-site-is-webapp-py-create-app] — verify: `grep 'create_app' docs/oauth.md` returns at least one line

- [ ] 4.2 Add inline comments to `get_middleware()` describing flat-chain contract and `oauth_provider=` semantics [implements: meta/docs, oauth-authentication/sa-credential-fallback-preserved] — verify: `ruff check mcp_hydrolix/auth/mcp_providers.py` clean

- [ ] 4.3 Document rollback: unsetting OAuth env vars makes activation a no-op [implements: meta/rollout] — verify: rollback note present in `docs/oauth.md` or inline comment in `_activate_oauth_if_configured`
