*3 phases, 18 tasks: audit call sites, add caplog test helpers and 6 path tests, wire CI.*

## 1. Audit And Harden Auth Layer Log Calls

- [ ] 1.1a Audit `oauth.py` log calls: list every `logger.*` call on invalid-bearer and discovery-failure paths [implements: oauth-authentication/no-jwt-credential-material-in-logs, design/exception-class-name-only] — verify: `grep -n "logger\." mcp_hydrolix/auth/oauth.py` output reviewed and annotated for each call site

- [ ] 1.1b Replace identified calls in `oauth.py` with `logger.error(type(exc).__name__)` where they were logging `str(exc)` on token-handling paths [implements: oauth-authentication/no-jwt-credential-material-in-logs, design/exception-class-name-only] — verify: `grep -n "str(exc)" mcp_hydrolix/auth/oauth.py` shows zero matches on token-handling paths

- [ ] 1.2a Audit `mcp_providers.py` log calls: list every `logger.*` call that touches auth state or bearer context in the provider composition layer [implements: oauth-authentication/no-jwt-credential-material-in-logs, design/log-content-is-tested-invariant] — verify: `grep -n "logger\." mcp_hydrolix/auth/mcp_providers.py` output reviewed for any bearer or header-value references

- [ ] 1.2b Replace any `mcp_providers.py` log calls that emit `Authorization` header values or bearer strings with a redacted equivalent [implements: oauth-authentication/no-jwt-credential-material-in-logs, design/log-content-is-tested-invariant] — verify: `grep -n "logger\." mcp_hydrolix/auth/mcp_providers.py` shows no bearer or header-value references in log calls

- [ ] 1.3a Audit `mcp_server.py` log calls: list every `logger.*` call adjacent to auth logic that could emit JWT segments or the `Authorization` header value [implements: oauth-authentication/no-jwt-credential-material-in-logs, design/log-content-is-tested-invariant] — verify: `grep -n "logger\." mcp_hydrolix/mcp_server.py` output reviewed and annotated for auth-adjacent paths

- [ ] 1.3b Replace any `mcp_server.py` auth-adjacent log calls that emit raw JWT segments or the `Authorization` header value with redacted equivalents [implements: oauth-authentication/no-jwt-credential-material-in-logs, design/log-content-is-tested-invariant] — verify: `grep -n "logger\." mcp_hydrolix/mcp_server.py` shows no bearer token references in auth-adjacent paths

- [ ] 1.4a Audit `webapp.py` log calls: list every `logger.*` call in `_activate_oauth_if_configured` and confirm what each call currently emits [implements: oauth-authentication/no-jwt-credential-material-in-logs, design/log-content-is-tested-invariant] — verify: `grep -n "logger\." mcp_hydrolix/webapp.py` output reviewed and annotated for raw discovery/JWKS body references

- [ ] 1.4b Confirm `webapp.py` logs only the resolved issuer URL, audience, and required scopes — remove or redact any log call that emits raw JWKS or discovery response bodies [implements: oauth-authentication/no-jwt-credential-material-in-logs, design/log-content-is-tested-invariant] — verify: `grep -n "logger\." mcp_hydrolix/webapp.py` shows no raw discovery/JWKS body references

## 2. Implement Caplog Test Module

- [ ] 2.1 Create `tests/auth/test_log_redaction.py`; add `_assert_no_credential_leak(records)` helper that scans both `record.getMessage()` and `record.args` (flattened) for: raw JWT pattern (`\w+\.\w+\.\w+`), base64url segments of JWT length, and the literal `Authorization` header value [implements: oauth-authentication/log-redaction-invariant-is-tested, design/caplog-checks-args-and-message] — verify: `pytest -q tests/auth/test_log_redaction.py` import succeeds with no collection errors

- [ ] 2.2 Add test for scenario "Successful Activation Log Content": mock OIDC discovery + JWKS preflight to succeed; run activation under `caplog`; assert prohibited content absent [implements: oauth-authentication/no-jwt-credential-material-in-logs, meta/tests] — verify: `pytest -q tests/auth/test_log_redaction.py::test_successful_activation_log_content` green

- [ ] 2.3 Add test for scenario "Valid Bearer Accepted Log Content": activate OAuth with mock JWKS; present a well-formed signed JWT; assert no log record contains the raw token, signature segment, or encoded header/payload [implements: oauth-authentication/no-jwt-credential-material-in-logs, meta/tests] — verify: `pytest -q tests/auth/test_log_redaction.py::test_valid_bearer_accepted_log_content` green

- [ ] 2.4 Add test for scenario "Invalid Bearer Rejected Log Content": activate OAuth with mock JWKS; present an invalid JWT; assert no log record contains the raw token, signature segment, or encoded segments [implements: oauth-authentication/no-jwt-credential-material-in-logs, meta/tests] — verify: `pytest -q tests/auth/test_log_redaction.py::test_invalid_bearer_rejected_log_content` green

- [ ] 2.5 Add test for scenario "Discovery Failure Does Not Log Bearer": simulate network failure during OIDC discovery; then present a request with a bearer token; assert no log record for either phase contains the raw JWT or its segments [implements: oauth-authentication/log-redaction-invariant-is-tested, meta/tests] — verify: `pytest -q tests/auth/test_log_redaction.py::test_discovery_failure_does_not_log_bearer` green

- [ ] 2.6 Add test for scenario "Sa Path Does Not Log Bearer Absence As Token": present a request with no `Authorization` header via the SA path; assert no log record contains a bearer token fragment [implements: oauth-authentication/log-redaction-invariant-is-tested, meta/tests] — verify: `pytest -q tests/auth/test_log_redaction.py::test_sa_path_does_not_log_bearer_absence_as_token` green

- [ ] 2.7 Add test for scenario "Oauth Config Error Does Not Log Partial Config Secrets": trigger `OAuthConfigError` via partial `HYDROLIX_OAUTH_*` env; assert no log record contains JWKS private exponents or private key material [implements: oauth-authentication/log-redaction-invariant-is-tested, meta/tests] — verify: `pytest -q tests/auth/test_log_redaction.py::test_oauth_config_error_does_not_log_partial_config_secrets` green

## 3. Ci And Documentation

- [ ] 3.1 Confirm `tests/auth/test_log_redaction.py` is collected by the default `pytest` invocation with no extra flags; add to `pyproject.toml` test paths if the auth directory is not already included [implements: oauth-authentication/log-redaction-invariant-is-tested, meta/tooling] — verify: `uv run pytest tests/auth/test_log_redaction.py` exits 0 from a clean checkout

- [ ] 3.2 Add a comment block above each modified `logger.*` call in the auth layer explaining why the call is redacted (exception class name only, no header value, etc.) for future-maintainer awareness [implements: design/exception-class-name-only, meta/docs] — verify: `grep -n "redact\|credential\|token" mcp_hydrolix/auth/oauth.py mcp_hydrolix/auth/mcp_providers.py` surfaces at least one explanatory comment per modified call site

- [ ] 3.3 Update `docs/oauth.md` security checklist to mark "No JWT bytes in logs" as signed off, citing `tests/auth/test_log_redaction.py` as the enforcement mechanism [implements: oauth-authentication/log-redaction-invariant-is-tested, meta/docs] — verify: `grep -n "test_log_redaction" docs/oauth.md` returns at least one match
