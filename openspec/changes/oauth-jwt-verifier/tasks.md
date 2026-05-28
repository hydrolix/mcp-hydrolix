*3 phases, 18 tasks: implement verifier (including iss-based routing), add scenario tests (13), verify docs and integration.*

## 1. Core Implementation

- [ ] 1.1 Add `OAuthBearerToken` dataclass to `mcp_hydrolix/auth/oauth.py` [implements: oauth-authentication/valid-bearer-authenticates-the-request-end-to-end, design/no-io-at-request-time] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean

- [ ] 1.2 Add unverified `iss` peek in `OAuthHydrolixAuthProvider` (PyJWT `decode` with `verify_signature=False`); return `None` when `iss` doesn't match or bearer is not JWT-shaped; no log on deferral [implements: oauth-authentication/oauth-verifier-claims-bearers-by-iss-match, design/iss-based-routing-for-chain-composability] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean

- [ ] 1.3 Add issuer exact-match check; no reference to `HYDROLIX_URL` inside this class [implements: oauth-authentication/jwt-verification-rejects-mismatched-issuer, design/non-conflation-as-verifier-invariant] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean

- [ ] 1.4 Add audience set-intersection check: accept when any `aud` value intersects `OAuthConfig.audience` [implements: oauth-authentication/jwt-verification-rejects-mismatched-audience, design/audience-as-set-intersection] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean

- [ ] 1.5 Add required-scopes check: all scopes must appear in `scope` (space-delimited) or `scp` (array); reject if neither present [implements: oauth-authentication/required-scopes-enforced-when-configured, design/scope-claim-union] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean

## 2. Scenario Tests

- [ ] 2.1 Test "Bearer With Oauth Issuer And Valid Signature Is Accepted" [implements: oauth-authentication/oauth-verifier-claims-bearers-by-iss-match, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_bearer_with_oauth_issuer_and_valid_signature_is_accepted` green

- [ ] 2.2 Test "Bearer With Oauth Issuer And Invalid Signature Is Rejected With 401" [implements: oauth-authentication/oauth-verifier-claims-bearers-by-iss-match, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_bearer_with_oauth_issuer_and_invalid_signature_is_rejected_with_401` green

- [ ] 2.3 Test "Bearer With Service Account Issuer Is Deferred": assert `None` returned, no exception, no log line [implements: oauth-authentication/oauth-verifier-claims-bearers-by-iss-match, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_bearer_with_service_account_issuer_is_deferred` green

- [ ] 2.4 Test "Malformed Bearer Is Deferred": assert `None` returned, no exception [implements: oauth-authentication/oauth-verifier-claims-bearers-by-iss-match, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_malformed_bearer_is_deferred` green

- [ ] 2.5 Test "Token Uses Cluster Url As Issuer": hardcoded cluster URL as `iss`, no real `HYDROLIX_URL` env state [implements: oauth-authentication/jwt-verification-rejects-mismatched-issuer, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_token_uses_cluster_url_as_issuer` green

- [ ] 2.6 Test "Derived Issuer Differs From Hydrolix Url Conflation Rejected" [implements: oauth-authentication/jwt-verification-rejects-mismatched-issuer, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_derived_issuer_differs_from_hydrolix_url_conflation_rejected` green

- [ ] 2.7 Test "Audience Not In Allowlist" [implements: oauth-authentication/jwt-verification-rejects-mismatched-audience, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_audience_not_in_allowlist` green

- [ ] 2.8 Test "Second Allowlist Entry Matches" [implements: oauth-authentication/jwt-verification-rejects-mismatched-audience, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_second_allowlist_entry_matches` green

- [ ] 2.9 Test "Missing Required Scope" [implements: oauth-authentication/required-scopes-enforced-when-configured, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_missing_required_scope` green

- [ ] 2.10 Test "All Required Scopes Present Via Scope Claim" [implements: oauth-authentication/required-scopes-enforced-when-configured, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_all_required_scopes_present_via_scope_claim` green

- [ ] 2.11 Test "All Required Scopes Present Via Scp Claim" [implements: oauth-authentication/required-scopes-enforced-when-configured, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_all_required_scopes_present_via_scp_claim` green

- [ ] 2.12 Test "Well Formed Bearer Reaches The Mcp Tool Layer" [implements: oauth-authentication/valid-bearer-authenticates-the-request-end-to-end, meta/tests] — verify: `pytest -q tests/auth/test_oauth_jwt_verifier.py::test_well_formed_bearer_reaches_the_mcp_tool_layer` green

## 3. Integration Verification

- [ ] 3.1 Confirm the new verifier test module is importable alongside existing auth tests with no name collisions or fixture conflicts [implements: oauth-authentication/valid-bearer-authenticates-the-request-end-to-end, meta/tests] — verify: `pytest -q tests/auth/` exits 0 with no failures or errors reported
