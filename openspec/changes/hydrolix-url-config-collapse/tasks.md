## 1. Core Config -- URL Parsing and Precedence Chain (mcp_env.py)

- [ ] 1.1 Add `logging` and `urllib.parse.urlparse` / `ParseResult` imports; add module-level `logger`
- [ ] 1.2 Parse `HYDROLIX_URL` eagerly in `HydrolixConfig.__init__` and store as `self._parsed_url: Optional[ParseResult]`; validate scheme in {http, https} and non-empty hostname; raise `ValueError` on malformed URL
- [ ] 1.3 Update `host` property to follow precedence: `HYDROLIX_HTTP_QUERY_HOST` > `HYDROLIX_HOST` > URL hostname
- [ ] 1.4 Update `port` property to follow precedence: `HYDROLIX_HTTP_QUERY_PORT` > `HYDROLIX_PORT` > URL-derived (443/80) > hard default 8088
- [ ] 1.5 Update `secure` property to follow precedence: `HYDROLIX_HTTP_QUERY_SECURE` > `HYDROLIX_SECURE` > URL-derived (scheme == "https") > hard default True
- [ ] 1.6 Rename `api_host` property to `version_api_host` with precedence: `HYDROLIX_VERSION_API_HOST` > `HYDROLIX_API_HOST` > URL hostname > fallback to `host`
- [ ] 1.7 Rename `api_port` property to `version_api_port` with precedence: `HYDROLIX_VERSION_API_PORT` > `HYDROLIX_API_PORT` > URL-derived > `443 if secure else 80`
- [ ] 1.8 Add new `version_api_secure` property with precedence: `HYDROLIX_VERSION_API_SECURE` > resolved `secure`
- [ ] 1.9 Update `_validate_required_vars` to accept any of `HYDROLIX_URL` / `HYDROLIX_HOST` / `HYDROLIX_HTTP_QUERY_HOST`; require `HYDROLIX_URL` specifically when transport is http/sse
- [ ] 1.10 Update `HydrolixConfig` class docstring to document new vars, precedence, and requirements

## 2. Deprecation Detection and Messaging (mcp_env.py)

- [ ] 2.1 Add `ALIAS_RENAMES` dict and `DEPRECATED_ALIASES` tuple at module level
- [ ] 2.2 Add `_detect_deprecated_aliases()` helper returning list of set deprecated var names
- [ ] 2.3 Add `_classify_deprecation(aliases)` helper returning `"external"`, `"internal"`, or `None` based on `HYDROLIX_NAME`
- [ ] 2.4 Add `_external_deprecation_warned` and `_internal_deprecation_warned` module-level sentinels
- [ ] 2.5 Define `EXTERNAL_DEPRECATION_MESSAGE` and `INTERNAL_DEPRECATION_MESSAGE` module-level constants
- [ ] 2.6 Emit external WARNING log from `HydrolixConfig.__init__` (after `_validate_required_vars`), guarded by sentinel
- [ ] 2.7 Store `self._deprecated_aliases` and `self._deprecation_audience` as instance state; expose as readable properties
- [ ] 2.8 Add `deprecation_notice` property returning the external message string or `None`

## 3. FastMCP Wiring and Version-Gated Internal Log (mcp_server.py)

- [ ] 3.1 Pass `instructions=HYDROLIX_CONFIG.deprecation_notice` to `FastMCP()` constructor
- [ ] 3.2 Update `/version` probe URL construction: `api_host` -> `version_api_host`, `api_port` -> `version_api_port`, scheme source from `secure` -> `version_api_secure`
- [ ] 3.3 Add `_maybe_emit_internal_deprecation_log(parsed_version)` helper with version >= 6.1 gate, audience check, and sentinel guard
- [ ] 3.4 Call `_maybe_emit_internal_deprecation_log` from `_check_parameterized_query_support` after successful version parse

## 4. Tests -- URL Parsing and Precedence (tests/test_mcp_env.py)

- [ ] 4.1 Add env isolation fixture (`autouse=True`) clearing all `HYDROLIX_*` env vars
- [ ] 4.2 Test URL parsing happy paths (https, http, IPv6, userinfo, trailing slash, empty path, port-ignored)
- [ ] 4.3 Test URL validation errors (missing scheme, unsupported scheme, no hostname, empty-after-strip)
- [ ] 4.4 Test external sufficiency: `HYDROLIX_URL` alone resolves all six properties correctly
- [ ] 4.5 Test external sufficiency with split ports
- [ ] 4.6 Test full precedence chain for each of host/port/secure (new > alias > URL > default)
- [ ] 4.7 Test full precedence chain for version_api_host/version_api_port
- [ ] 4.8 Test `version_api_secure` inheritance and explicit override scenarios
- [ ] 4.9 Test backwards compatibility: `HYDROLIX_HOST` alone preserves pre-change defaults bit-for-bit
- [ ] 4.10 Test in-cluster post-migration shape (all new vars)
- [ ] 4.11 Test in-cluster transition shape (all deprecated aliases)
- [ ] 4.12 Test connection target validation errors (none set, transport-specific requirement)

## 5. Tests -- Deprecation Classification and Messaging (tests/test_mcp_env_deprecation.py)

- [ ] 5.1 Add env isolation fixture clearing all `HYDROLIX_*` vars and resetting both sentinels
- [ ] 5.2 Test `_detect_deprecated_aliases()` for single, multiple, all, and none cases
- [ ] 5.3 Test `_classify_deprecation()` for external, internal, none, and partial-migration cases
- [ ] 5.4 Test external WARNING log fires once at `HydrolixConfig.__init__`; no duplicate on second construction
- [ ] 5.5 Test internal audience does NOT trigger startup WARNING log
- [ ] 5.6 Test `deprecation_notice` returns message for external, `None` for internal, `None` for no-deprecation
- [ ] 5.7 Test no-deprecation path: only new vars set (with or without `HYDROLIX_NAME`) -> no log, notice is `None`

## 6. Tests -- Version-Gated Internal Deprecation (tests/test_internal_deprecation_version_gate.py)

- [ ] 6.1 Add fixture resetting `_internal_deprecation_warned` sentinel and `_parameterized_queries_supported` cache
- [ ] 6.2 Test internal audience + version 6.1.0 -> ERROR log fires exactly once
- [ ] 6.3 Test internal audience + versions 6.2.0, 7.0.0, 6.1.0-5-gabcdef12 -> ERROR log fires
- [ ] 6.4 Test internal audience + versions 6.0.9, 5.12.0, 5.0.0 -> no log
- [ ] 6.5 Test internal audience + probe HTTP error -> no log; subsequent success with 6.1 -> log fires
- [ ] 6.6 Test internal audience + non-200 response -> no log
- [ ] 6.7 Test internal audience + unparseable body -> no log
- [ ] 6.8 Test external audience + any version response -> no log from probe path
- [ ] 6.9 Test no-deprecation + any version response -> no log from probe path

## 7. Update Existing Tests (tests/test_parameterized_queries.py)

- [ ] 7.1 Rename mock attribute `api_host` -> `version_api_host` in all probe-path tests
- [ ] 7.2 Rename mock attribute `api_port` -> `version_api_port` in all probe-path tests
- [ ] 7.3 Audit `mock_config.secure` usage in probe path and switch to `mock_config.version_api_secure` where it drives the probe scheme

## 8. Documentation (README.md)

- [ ] 8.1 Document `HYDROLIX_URL` as primary config var with external sufficiency note
- [ ] 8.2 Document `HYDROLIX_HTTP_QUERY_HOST/PORT/SECURE` and `HYDROLIX_VERSION_API_HOST/PORT/SECURE` as endpoint overrides
- [ ] 8.3 Mark five deprecated vars with migration guidance for both audiences
- [ ] 8.4 Update minimal out-of-cluster example to use `HYDROLIX_URL`
- [ ] 8.5 Update "Required Variables" note with the three-option requirement and transport-specific rule
