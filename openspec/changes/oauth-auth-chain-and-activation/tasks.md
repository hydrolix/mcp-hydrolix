*4 phases, 18 tasks: auth chain extension, per-worker activation wiring, tests, and docs.*

## 1. Auth Chain Assembly — `HydrolixCredentialChain.get_middleware()`

- [ ] 1.1 Extend `HydrolixCredentialChain.get_middleware()` in `mcp_hydrolix/auth/mcp_providers.py` with `oauth_provider: AuthProvider | None = None`. When non-None, prepend `oauth_provider` to the `ChainedAuthBackend`'s backends list, yielding `[oauth_provider, BearerAuthBackend(self), GetParamAuthBackend(self, TOKEN_PARAM)]`. When None, return the existing two-element list unchanged. [implements: oauth-auth-chain-and-activation/auth-chain-is-flat, design/chain-construction-lives-in-hydrolixcredentialchain] — verify: `ruff check mcp_hydrolix/auth/mcp_providers.py` clean

- [ ] 1.2 Add docstring to `HydrolixCredentialChain.get_middleware()` documenting the flat-chain contract: the returned `ChainedAuthBackend` is never nested; when `oauth_provider` is set it is the first element. [implements: oauth-auth-chain-and-activation/auth-chain-is-flat, meta/docs] — verify: `ruff check mcp_hydrolix/auth/mcp_providers.py` clean

## 2. Per-Worker Activation — `webapp.py`

- [ ] 2.1 Add `_activate_oauth_if_configured()` function to `mcp_hydrolix/webapp.py`: reads `OAuthConfig`, runs `asyncio.run(try_activate_oauth(cfg))`, calls `chain.get_middleware(oauth_provider=resolved_provider)`, assigns the result to `mcp.auth` [implements: oauth-auth-chain-and-activation/activation-runs-per-uvicorn-worker, design/activation-site-is-webapp-py-create-app, design/asyncio-run-inside-the-factory, design/configure-auth-via-mcp-auth-assignment-not-fastmcp-constructor] — verify: `ruff check mcp_hydrolix/webapp.py` clean

- [ ] 2.2 Call `_activate_oauth_if_configured()` inside `create_app()` before `mcp.http_app(...)` [implements: design/activation-site-is-webapp-py-create-app] — verify: `grep -n '_activate_oauth_if_configured' mcp_hydrolix/webapp.py` appears before `mcp.http_app`

- [ ] 2.3 Catch `RuntimeError` from `asyncio.run` inside `_activate_oauth_if_configured()` and re-raise with a message naming the test setup as the likely cause [implements: design/asyncio-run-inside-the-factory] — verify: `ruff check mcp_hydrolix/webapp.py` clean

## 3. Tests

- [ ] 3.1 Add test for scenario "Multi-Worker Activation": call `create_app()` twice in the same test process and assert each call sets a `ChainedAuthBackend` on the `mcp` singleton independently [implements: oauth-auth-chain-and-activation/activation-runs-per-uvicorn-worker, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_multi_worker_activation` green

- [ ] 3.2 Add test for scenario "Chain Has Three Backends When Oauth Is Active": with OAuth active, assert `mcp.auth` is a `ChainedAuthBackend` with exactly three elements in the order `[OAuthHydrolixAuthProvider, BearerAuthBackend, GetParamAuthBackend]` [implements: oauth-auth-chain-and-activation/auth-chain-is-flat, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_chain_has_three_backends_when_oauth_is_active` green

- [ ] 3.3 Add test for scenario "Chain Has Two Backends When Oauth Is Inactive": with no OAuth config, assert `mcp.auth` is a `ChainedAuthBackend` with exactly two elements `[BearerAuthBackend, GetParamAuthBackend]` [implements: oauth-auth-chain-and-activation/auth-chain-is-flat, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_chain_has_two_backends_when_oauth_is_inactive` green

- [ ] 3.4 Add test for scenario "Chain Is Not Nested": for both OAuth-active and OAuth-inactive configurations, assert no element of `mcp.auth.backends` is itself a `ChainedAuthBackend` [implements: oauth-auth-chain-and-activation/auth-chain-is-flat, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_chain_is_not_nested` green

- [ ] 3.5 Add test for scenario "Invalid Bearer After Successful Activation": with OAuth active, send a request with `Authorization: Bearer <invalid-jwt>` whose `iss` matches the OAuth issuer; assert 401 + `WWW-Authenticate: Bearer` header [implements: oauth-auth-chain-and-activation/active-verifier-is-fail-closed, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_invalid_bearer_after_successful_activation` green

- [ ] 3.6 Add test for scenario "Missing Bearer After Successful Activation Internal SA Path": with OAuth active, send a request with no `Authorization` header but valid SA credentials; assert chained backend accepts via SA path [implements: oauth-auth-chain-and-activation/active-verifier-is-fail-closed, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_missing_bearer_after_successful_activation_internal_sa_path` green

- [ ] 3.7 Add test for scenario "No Bearer SA Credential Present": with OAuth active and no `Authorization` header, assert request succeeds via SA chain [implements: oauth-auth-chain-and-activation/sa-credential-fallback-preserved, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_no_bearer_sa_credential_present` green

- [ ] 3.8 Add test for scenario "Bearer Present OAuth Verifier Fails": with OAuth active and an invalid bearer token whose `iss` matches the OAuth issuer, assert 401 and that the SA chain is never called [implements: oauth-auth-chain-and-activation/sa-credential-fallback-preserved, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_bearer_present_oauth_verifier_fails` green

- [ ] 3.9 Add test for scenario "Sa Bearer Jwt Is Authenticated By Bearer Auth Backend When Oauth Is Active": with OAuth active, send a request with `Authorization: Bearer <sa-jwt>` (iss ends in `/config`); assert `OAuthHydrolixAuthProvider` returns None, `BearerAuthBackend` authenticates, and the chain stops after `BearerAuthBackend` succeeds [implements: oauth-auth-chain-and-activation/sa-credential-fallback-preserved, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_sa_bearer_jwt_is_authenticated_by_bearer_auth_backend_when_oauth_is_active` green

- [ ] 3.10 Add test that invoking `create_app()` under an active asyncio event loop raises `RuntimeError` with a message pointing at test setup [implements: design/asyncio-run-inside-the-factory, meta/tests] — verify: `pytest -q tests/test_oauth_auth_chain_and_activation.py::test_create_app_under_active_loop_raises` green

## 4. Documentation and Rollout

- [ ] 4.1 Update `docs/oauth.md` activation section: document `webapp.py:create_app()` as the per-worker activation site; document that `mcp.auth` is assigned before `http_app(...)` and that the chain is flat [implements: meta/docs, design/activation-site-is-webapp-py-create-app] — verify: `grep 'create_app' docs/oauth.md` returns at least one line

- [ ] 4.2 Document `HydrolixCredentialChain.get_middleware()` composition in code comments: describe the flat-chain contract and the `oauth_provider=` parameter semantics in `mcp_hydrolix/auth/mcp_providers.py` [implements: meta/docs, oauth-auth-chain-and-activation/sa-credential-fallback-preserved] — verify: `ruff check mcp_hydrolix/auth/mcp_providers.py` clean

- [ ] 4.3 Confirm rollback procedure: document that unsetting OAuth env vars makes activation a no-op, restoring byte-identical behavior to a build without OAuth code [implements: meta/rollout] — verify: rollback note present in `docs/oauth.md` or inline comment in `_activate_oauth_if_configured`
