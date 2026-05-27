*3 phases, 13 tasks: config extension, route registration, and test coverage.*

## 1. Config Extension

- [ ] 1.1 Add `resource_url` field to `OAuthConfig`: add a `resource_url: str` field to the `OAuthConfig` dataclass in `mcp_hydrolix/auth/config.py` [implements: oauth-resource-metadata/resource-url-configuration, design/resource-url-bind-url-fallback] — verify: `ruff check mcp_hydrolix/auth/config.py` clean and `mypy mcp_hydrolix/auth/config.py` passes

- [ ] 1.2 Implement three-tier precedence in `load_oauth_config()`: resolve `resource_url` from `HYDROLIX_OAUTH_RESOURCE_URL` → `HYDROLIX_URL` → bind base URL (passed in as a parameter) and assign to `OAuthConfig.resource_url` [implements: oauth-resource-metadata/resource-url-configuration, design/resource-url-bind-url-fallback] — verify: `ruff check mcp_hydrolix/auth/config.py` clean

- [ ] 1.3 Add partial-config guard for `HYDROLIX_OAUTH_RESOURCE_URL` without audience: inside `load_oauth_config()`, when `HYDROLIX_OAUTH_RESOURCE_URL` is set and `HYDROLIX_OAUTH_AUDIENCE` is unset, raise `OAuthConfigError` (consistent with the other optional-var guards in `oauth-config-and-preflight`) [implements: oauth-resource-metadata/resource-url-configuration] — verify: `ruff check mcp_hydrolix/auth/config.py` clean

## 2. Route and Header Registration

- [ ] 2.1 Register `/.well-known/oauth-protected-resource` route in `create_app()`: add an unauthenticated GET handler on the ASGI app that returns the RFC 9728 JSON document (with `resource`, `authorization_servers`, `bearer_methods_supported`) when OAuth is active; return 404 when inactive [implements: oauth-resource-metadata/rfc-9728-protected-resource-metadata-endpoint, design/metadata-route-placement] — verify: `ruff check mcp_hydrolix/webapp.py` clean

- [ ] 2.2 Pass bind base URL into `load_oauth_config()` from `create_app()`: update the `create_app()` call site to derive the bind base URL (scheme + host + port from uvicorn/server config) and pass it to `load_oauth_config()` for the bind-URL fallback [implements: oauth-resource-metadata/resource-url-configuration, design/resource-url-bind-url-fallback] — verify: `ruff check mcp_hydrolix/webapp.py` clean

- [ ] 2.3 Extend `WWW-Authenticate` 401 header with `resource_metadata=`: update the 401 response path to append `resource_metadata="<absolute-url>"` to the `WWW-Authenticate: Bearer` header, where the URL is derived from the bind base URL + `/.well-known/oauth-protected-resource` [implements: oauth-resource-metadata/rfc-9728-protected-resource-metadata-endpoint, design/www-authenticate-extension] — verify: `ruff check mcp_hydrolix/` clean

## 3. Test Coverage

- [ ] 3.1 Add test for scenario "Metadata Endpoint Returns RFC 9728 JSON" [implements: oauth-resource-metadata/rfc-9728-protected-resource-metadata-endpoint, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_metadata_endpoint_returns_rfc_9728_json` green

- [ ] 3.2 Add test for scenario "401 References Metadata URL" [implements: oauth-resource-metadata/rfc-9728-protected-resource-metadata-endpoint, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_401_references_metadata_url` green

- [ ] 3.3 Add test for scenario "Metadata Endpoint Returns 404 When OAuth Inactive" [implements: oauth-resource-metadata/rfc-9728-protected-resource-metadata-endpoint, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_metadata_endpoint_returns_404_when_oauth_inactive` green

- [ ] 3.4 Add test for scenario "Explicit Resource URL Wins" [implements: oauth-resource-metadata/resource-url-configuration, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_explicit_resource_url_wins` green

- [ ] 3.5 Add test for scenario "Resource URL Defaults To Hydrolix URL" [implements: oauth-resource-metadata/resource-url-configuration, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_resource_url_defaults_to_hydrolix_url` green

- [ ] 3.6 Add test for scenario "Resource URL Falls Back To Server Bind URL" [implements: oauth-resource-metadata/resource-url-configuration, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_resource_url_falls_back_to_server_bind_url` green

- [ ] 3.7 Add test for scenario "Resource URL Set Without Audience Triggers Partial Config Error" [implements: oauth-resource-metadata/resource-url-configuration, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_resource_url_set_without_audience_triggers_partial_config_error` green
