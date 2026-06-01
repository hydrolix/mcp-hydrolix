*3 phases, 12 tasks: config extension, route registration, and test coverage.*

## 1. Config Extension

- [ ] 1.1 Add `resource_url` field to `OAuthConfig`: add a `resource_url: str` field to the `OAuthConfig` dataclass in `mcp_hydrolix/auth/oauth.py` [implements: oauth-authentication/resource-url-configuration, design/resource-url-bind-url-fallback] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean and `mypy mcp_hydrolix/auth/oauth.py` passes

- [ ] 1.2 Implement two-tier precedence in `load_oauth_config()`: resolve `resource_url` from (1) `HYDROLIX_URL` with `/mcp` appended (collapsing any trailing slash), or (2) the bind base URL (passed in as a parameter) with `/mcp` appended; assign to `OAuthConfig.resource_url`. Source the `/mcp` literal from the same constant used by `webapp.py` for the FastMCP mount, not a duplicated string. Do NOT read any `HYDROLIX_OAUTH_RESOURCE_URL` env var (see `no-resource-url-override` design decision) [implements: oauth-authentication/resource-url-configuration, design/resource-url-bind-url-fallback, design/no-resource-url-override] — verify: `ruff check mcp_hydrolix/auth/oauth.py` clean

## 2. Route and Header Registration

- [ ] 2.1 Register path-scoped metadata route in `create_app()`: add an unauthenticated GET handler on the ASGI app at the path `/.well-known/oauth-protected-resource` + `urlparse(OAuthConfig.resource_url).path` (i.e. `/.well-known/oauth-protected-resource/mcp` for the default chain), returning the RFC 9728 JSON document (`resource`, `authorization_servers`, `bearer_methods_supported`) when OAuth is active; register no route when OAuth is inactive so the path returns 404 via the default not-found handler. The handler MUST be registered before any auth middleware [implements: oauth-authentication/rfc-9728-protected-resource-metadata-endpoint, design/path-scoped-well-known-per-rfc-9728] — verify: `ruff check mcp_hydrolix/webapp.py` clean

- [ ] 2.2 Pass bind base URL into `load_oauth_config()` from `create_app()`: update the `create_app()` call site to derive the bind base URL (scheme + host + port from uvicorn/server config) and pass it to `load_oauth_config()` for the bind-URL fallback in task 1.2 [implements: oauth-authentication/resource-url-configuration, design/resource-url-bind-url-fallback] — verify: `ruff check mcp_hydrolix/webapp.py` clean

- [ ] 2.3 Compute the canonical metadata absolute URL once in `create_app()`: derive `metadata_url = <resource_url scheme+authority> + "/.well-known/oauth-protected-resource" + urlparse(resource_url).path` from `OAuthConfig.resource_url`, store it on config (or a small companion struct) so both the route handler and the 401 path read the same value [implements: design/www-authenticate-extension] — verify: `ruff check mcp_hydrolix/webapp.py` clean

- [ ] 2.4 Extend `WWW-Authenticate` 401 header with `resource_metadata=`: update the 401 response path to append `resource_metadata="<metadata_url>"` to the `WWW-Authenticate: Bearer` header, reading the precomputed `metadata_url` from config (task 2.3). MUST NOT construct the URL from the request's `Host` header [implements: oauth-authentication/rfc-9728-protected-resource-metadata-endpoint, design/www-authenticate-extension] — verify: `ruff check mcp_hydrolix/` clean

## 3. Test Coverage

- [ ] 3.1 Add test for scenario "Metadata Endpoint Returns RFC 9728 JSON At Path-Scoped Location" [implements: oauth-authentication/rfc-9728-protected-resource-metadata-endpoint, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_metadata_endpoint_returns_rfc_9728_json_at_path_scoped_location` green

- [ ] 3.2 Add test for scenario "Worker Does Not Claim Root Well-Known Path" (asserts the worker itself returns 404 at `/.well-known/oauth-protected-resource` with no `/mcp` suffix in default config — worker-scope only, not a cluster-wide assertion) [implements: oauth-authentication/rfc-9728-protected-resource-metadata-endpoint, design/path-scoped-well-known-per-rfc-9728, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_worker_does_not_claim_root_well_known_path` green

- [ ] 3.3 Add test for scenario "401 References Path-Scoped Metadata URL" [implements: oauth-authentication/rfc-9728-protected-resource-metadata-endpoint, design/www-authenticate-extension, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_401_references_path_scoped_metadata_url` green

- [ ] 3.4 Add test for scenario "Metadata Endpoint Returns 404 When OAuth Inactive" [implements: oauth-authentication/rfc-9728-protected-resource-metadata-endpoint, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_metadata_endpoint_returns_404_when_oauth_inactive` green

- [ ] 3.5 Add test for scenario "Resource URL Defaults To Hydrolix URL Plus Mount Path" [implements: oauth-authentication/resource-url-configuration, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_resource_url_defaults_to_hydrolix_url_plus_mount_path` green

- [ ] 3.6 Add test for scenario "Resource URL Defaults To Hydrolix URL With Trailing Slash Plus Mount Path" (asserts single slash, no duplicate) [implements: oauth-authentication/resource-url-configuration, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_resource_url_defaults_to_hydrolix_url_with_trailing_slash_plus_mount_path` green

- [ ] 3.7 Add test for scenario "Resource URL Falls Back To Server Bind URL Plus Mount Path" [implements: oauth-authentication/resource-url-configuration, meta/tests] — verify: `pytest -q tests/test_oauth_resource_metadata.py::test_resource_url_falls_back_to_server_bind_url_plus_mount_path` green
