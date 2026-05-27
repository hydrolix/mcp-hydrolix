*3 phases, 18 tasks: implement verifier (including iss-based routing), add scenario tests (13), verify docs and integration.*

## 1. Core Implementation

- [ ] 1.1 Implement `OAuthBearerToken` dataclass: token type returned by the verifier for authenticated requests [implements: oauth-authentication/valid-bearer-authenticates-the-request-end-to-end, design/no-io-at-request-time] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean

- [ ] 1.2 Implement unverified `iss` peek in `OAuthHydrolixAuthProvider` using `PyJWT` `decode` with `options={"verify_signature": False}`: return `None` (defer) when `iss` does not match `OAuthConfig.issuer` or when the bearer is not JWT-shaped; no log line on deferral [implements: oauth-authentication/oauth-verifier-claims-bearers-by-iss-match, design/iss-based-routing-for-chain-composability] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean

- [ ] 1.3 Implement `OAuthHydrolixAuthProvider` with issuer exact-match: reject JWTs whose `iss` does not equal `OAuthConfig.issuer`; no reference to `HYDROLIX_URL` inside this class [implements: oauth-authentication/jwt-verification-rejects-mismatched-issuer, design/non-conflation-as-verifier-invariant] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean

- [ ] 1.4 Implement audience set-intersection check in `OAuthHydrolixAuthProvider`: accept JWT when any `aud` value intersects `OAuthConfig.audience` [implements: oauth-authentication/jwt-verification-rejects-mismatched-audience, design/audience-as-set-intersection] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean

- [ ] 1.5 Implement required-scopes check in `OAuthHydrolixAuthProvider`: when `OAuthConfig.required_scopes` is non-empty, require all scopes to be present in `scope` (space-delimited) or `scp` (array); reject if neither claim present [implements: oauth-authentication/required-scopes-enforced-when-configured, design/scope-claim-union] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean

## 2. Scenario Tests

- [ ] 2.1 Add test for scenario "Bearer With Oauth Issuer And Valid Signature Is Accepted": mint JWT with `iss` matching configured OAuth issuer, valid signature; assert authenticated principal returned and chain stops [implements: oauth-authentication/oauth-verifier-claims-bearers-by-iss-match, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_bearer_with_oauth_issuer_and_valid_signature_is_accepted` green

- [ ] 2.2 Add test for scenario "Bearer With Oauth Issuer And Invalid Signature Is Rejected With 401": mint JWT with `iss` matching OAuth issuer but bad signature; assert 401 with `WWW-Authenticate: Bearer` header containing `resource_metadata=` parameter and chain does not consult subsequent backends [implements: oauth-authentication/oauth-verifier-claims-bearers-by-iss-match, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_bearer_with_oauth_issuer_and_invalid_signature_is_rejected_with_401` green

- [ ] 2.3 Add test for scenario "Bearer With Service Account Issuer Is Deferred": mint JWT with `iss` ending in `/config`; assert `OAuthHydrolixAuthProvider` returns `None`, no exception raised, no log line emitted [implements: oauth-authentication/oauth-verifier-claims-bearers-by-iss-match, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_bearer_with_service_account_issuer_is_deferred` green

- [ ] 2.4 Add test for scenario "Malformed Bearer Is Deferred": pass a bearer value that is not JWT-shaped (e.g. a plain string, fewer than 3 dot-separated parts); assert `OAuthHydrolixAuthProvider` returns `None`, no exception raised [implements: oauth-authentication/oauth-verifier-claims-bearers-by-iss-match, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_malformed_bearer_is_deferred` green

- [ ] 2.5 Add test for scenario "Token Uses Cluster Url As Issuer": configure `OAuthConfig.issuer` to an OIDC URL; mint JWT with `iss` set to a hardcoded cluster URL string (e.g. `https://cluster.example.com`); assert chain rejects with 401 and no reference to real `HYDROLIX_URL` env state [implements: oauth-authentication/jwt-verification-rejects-mismatched-issuer, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_token_uses_cluster_url_as_issuer` green

- [ ] 2.6 Add test for scenario "Derived Issuer Differs From Hydrolix Url Conflation Rejected": configure `OAuthConfig.issuer` to the value derived via `canonical_idp_endpoints`; mint JWT with `iss="https://cluster.example.com"` (bare cluster URL); assert chain rejects with 401 [implements: oauth-authentication/jwt-verification-rejects-mismatched-issuer, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_derived_issuer_differs_from_hydrolix_url_conflation_rejected` green

- [ ] 2.7 Add test for scenario "Audience Not In Allowlist" [implements: oauth-authentication/jwt-verification-rejects-mismatched-audience, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_audience_not_in_allowlist` green

- [ ] 2.8 Add test for scenario "Second Allowlist Entry Matches" [implements: oauth-authentication/jwt-verification-rejects-mismatched-audience, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_second_allowlist_entry_matches` green

- [ ] 2.9 Add test for scenario "Missing Required Scope" [implements: oauth-authentication/required-scopes-enforced-when-configured, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_missing_required_scope` green

- [ ] 2.10 Add test for scenario "All Required Scopes Present Via Scope Claim" [implements: oauth-authentication/required-scopes-enforced-when-configured, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_all_required_scopes_present_via_scope_claim` green

- [ ] 2.11 Add test for scenario "All Required Scopes Present Via Scp Claim" [implements: oauth-authentication/required-scopes-enforced-when-configured, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_all_required_scopes_present_via_scp_claim` green

- [ ] 2.12 Add test for scenario "Well Formed Bearer Reaches The Mcp Tool Layer" [implements: oauth-authentication/valid-bearer-authenticates-the-request-end-to-end, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_well_formed_bearer_reaches_the_mcp_tool_layer` green

## 3. Integration Verification

- [ ] 3.1 Run full auth test suite to confirm no regressions [implements: meta/tests] — verify: `pytest -q tests/auth/` exits 0 with no failures or errors reported
