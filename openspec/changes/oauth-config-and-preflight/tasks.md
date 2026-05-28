*5 phases, 22 tasks; new IdP module, config loader, startup preflight primitive, 14 scenario tests, docs.*

## 1. IdP Endpoint Module

- [ ] 1.1 Create `mcp_hydrolix/auth/idp_endpoints.py`: `CanonicalIdPEndpoints` as `@dataclass(frozen=True)` with fields `issuer: str`, `discovery_url: str`, `jwks_uri: str`, `address: str` [implements: design/single-idp-coupling-point, spec/canonical-idp-endpoint-derivation-is-a-single-contained-function] — verify: `ruff check mcp_hydrolix/auth/idp_endpoints.py` clean; module imports without error
- [ ] 1.2 Add `canonical_idp_endpoints(hydrolix_url: str) -> CanonicalIdPEndpoints` stub raising `NotImplementedError` with message containing `HDX-11431` [implements: design/single-idp-coupling-point] — verify: `pytest -q tests/auth/test_oauth_config_and_preflight.py::test_stub_raises_not_implemented_error_until_hdx_11431` green

## 2. Config Loader

- [ ] 2.1 Add `OAuthConfigError` to `mcp_hydrolix/auth/oauth.py` [implements: design/two-distinct-fatal-startup-exceptions] — verify: `from mcp_hydrolix.auth.oauth import OAuthConfigError` succeeds
- [ ] 2.2 Add `OAuthConfig` frozen dataclass in `mcp_hydrolix/auth/oauth.py` with fields: `issuer: str`, `audience: list[str]`, `required_scopes: list[str]`, `jwks_uri: str | None`, `allow_insecure_jwks: bool` (`resource_url` is added by `oauth-resource-metadata`) [implements: spec/activation-gated-on-env-vars, spec/jwks-uri-override-and-insecure-transport-flag] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean
- [ ] 2.3a Implement issuer precedence in `load_oauth_config()`: explicit `HYDROLIX_OAUTH_ISSUER` > `canonical_idp_endpoints(HYDROLIX_URL).issuer` > unset [implements: design/single-idp-coupling-point] — verify: `pytest -q tests/auth/test_oauth_config_and_preflight.py::test_explicit_issuer_overrides_derivation` green
- [ ] 2.3b Raise `OAuthConfigError` for all partial-config cases [implements: design/two-distinct-fatal-startup-exceptions] — verify: `pytest -q tests/auth/test_oauth_config_and_preflight.py::test_partial_config_raises` green
- [ ] 2.3c Let `NotImplementedError` from `canonical_idp_endpoints` propagate unwrapped [implements: design/two-distinct-fatal-startup-exceptions] — verify: `pytest -q tests/auth/test_oauth_config_and_preflight.py::test_not_implemented_error_propagates_unwrapped` green
- [ ] 2.4 Insecure-JWKS guard: `http://` `HYDROLIX_OAUTH_JWKS_URI` without `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS=true` raises `OAuthConfigError` before any network call [implements: spec/jwks-uri-override-and-insecure-transport-flag] — verify: `pytest -q tests/auth/test_oauth_config_and_preflight.py::test_plain_http_jwks_rejected_by_default` green

## 3. Startup Preflight Primitive

- [ ] 3.1 Implement `try_activate_oauth(cfg: OAuthConfig) -> OAuthHydrolixAuthProvider | None` in `mcp_hydrolix/auth/oauth.py`: perform async OIDC discovery (GET `cfg.issuer + "/.well-known/openid-configuration"`), retrieve JWKS URI (use `cfg.jwks_uri` if set, else field from discovery response), verify JWKS endpoint is reachable; **catch** any network error, non-2xx HTTP response, malformed JSON, or missing `jwks_uri` field, log one WARNING `OAuth configured but not activated <ExcClass>`, and return `None`; on success return a configured `OAuthHydrolixAuthProvider`. The primitive owns the WARNING emission per the fail-open contract in design.md; callers check the return value rather than catching exceptions [implements: oauth-authentication/startup-preflight-is-fail-open] — verify: `pytest -q tests/auth/test_try_activate_oauth.py` green
- [ ] 3.2 No code outside `mcp_hydrolix/auth/idp_endpoints.py` encodes IdP URL structure [implements: design/single-idp-coupling-point] — verify: `grep -rl "HYDROLIX_URL" mcp_hydrolix/auth/ --include="*.py" | sort` outputs exactly `mcp_hydrolix/auth/idp_endpoints.py` and `mcp_hydrolix/auth/oauth.py`, AND `grep -n "HYDROLIX_URL" mcp_hydrolix/auth/oauth.py` shows only `os.environ`/`os.getenv` calls (no string concatenation or f-strings)

## 4. Tests

All tests in `tests/auth/test_oauth_config_and_preflight.py`.

- [ ] 4.1 `test_no_oauth_vars_set` [implements: oauth-authentication/activation-gated-on-env-vars] — verify green
- [ ] 4.2 `test_audience_set_but_no_issuer_resolvable` [implements: oauth-authentication/activation-gated-on-env-vars] — verify green
- [ ] 4.3 `test_issuer_derivation_attempted_before_hdx_11431` [implements: oauth-authentication/activation-gated-on-env-vars] — verify green
- [ ] 4.4 `test_issuer_derived_from_cluster_url_post_hdx_11431` (monkeypatch `canonical_idp_endpoints`) [implements: oauth-authentication/activation-gated-on-env-vars] — verify green
- [ ] 4.5 `test_explicit_issuer_overrides_derivation` [implements: oauth-authentication/activation-gated-on-env-vars] — verify green
- [ ] 4.6 `test_issuer_set_but_audience_unset` [implements: oauth-authentication/activation-gated-on-env-vars] — verify green
- [ ] 4.7 `test_hydrolix_url_set_without_oauth_vars` [implements: oauth-authentication/activation-gated-on-env-vars] — verify green
- [ ] 4.8 `test_optional_oauth_var_set_without_audience` [implements: oauth-authentication/activation-gated-on-env-vars] — verify green
- [ ] 4.9 `test_stub_raises_not_implemented_error_until_hdx_11431` [implements: oauth-authentication/canonical-idp-endpoint-derivation-is-a-single-contained-function] — verify green
- [ ] 4.10 `test_eventual_return_shape_is_immutable_and_complete` (monkeypatch stub) [implements: oauth-authentication/canonical-idp-endpoint-derivation-is-a-single-contained-function] — verify green
- [ ] 4.11 `test_eventual_derived_issuer_is_never_equal_to_input_cluster_url` (monkeypatch stub) [implements: oauth-authentication/canonical-idp-endpoint-derivation-is-a-single-contained-function] — verify green
- [ ] 4.12 `test_plain_http_jwks_rejected_by_default` [implements: oauth-authentication/jwks-uri-override-and-insecure-transport-flag] — verify green
- [ ] 4.13 `test_plain_http_jwks_allowed_when_explicitly_opted_in` [implements: oauth-authentication/jwks-uri-override-and-insecure-transport-flag] — verify green
- [ ] 4.14 `test_discovery_network_failure_at_startup` [implements: oauth-authentication/startup-preflight-is-fail-open] — verify green

## 5. Documentation

- [ ] 5.1 Update/create `docs/oauth.md`: all `HYDROLIX_OAUTH_*` vars, issuer precedence chain, interim requirement for explicit `HYDROLIX_OAUTH_ISSUER` until [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431), OIDC discovery latency, insecure-JWKS opt-in [implements: meta/docs] — verify: `docs/oauth.md` contains substrings `HYDROLIX_OAUTH_ISSUER` and `HDX-11431`
