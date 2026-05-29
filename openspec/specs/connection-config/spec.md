# Spec: connection-config

## Purpose

Defines the `HydrolixConfig` class behaviour for parsing environment variables, deriving connection properties, and handling the migration from deprecated per-component env vars to the unified `HYDROLIX_URL` variable. Covers validation at construction time, property-level precedence rules, and the transitional deprecation notification layer (external WARNING log, internal version-gated ERROR log, LLM advisory via FastMCP instructions).

## Requirements

### Requirement: HYDROLIX_URL parsing and validation

`HydrolixConfig` SHALL parse the `HYDROLIX_URL` environment variable at construction time and store it as an internal `ParseResult`. If the value is unset or empty, the parsed result SHALL be `None`. If set, the scheme MUST be `http` or `https` and the hostname MUST be non-empty; otherwise `HydrolixConfig.__init__` SHALL raise `ValueError` with the offending value.

#### Scenario: Valid HTTPS URL
- **WHEN** `HYDROLIX_URL=https://mycluster.hydrolix.live`
- **THEN** ✅ `HydrolixConfig` constructs successfully and the parsed URL hostname is `mycluster.hydrolix.live` with scheme `https`

#### Scenario: Valid HTTP URL
- **WHEN** `HYDROLIX_URL=http://dev-cluster.internal`
- **THEN** ✅ `HydrolixConfig` constructs successfully with hostname `dev-cluster.internal` and scheme `http`

#### Scenario: URL with trailing slash
- **WHEN** `HYDROLIX_URL=https://mycluster.hydrolix.live/`
- **THEN** ✅ construction succeeds (trailing path is ignored for derivation purposes)

#### Scenario: URL with userinfo
- **WHEN** `HYDROLIX_URL=https://user:pass@mycluster.hydrolix.live`
- **THEN** ✅ construction succeeds; hostname resolves to `mycluster.hydrolix.live` (userinfo is silently ignored)

#### Scenario: URL with explicit port
- **WHEN** `HYDROLIX_URL=https://mycluster.hydrolix.live:9443`
- **THEN** ✅ construction succeeds; the URL port component is ignored for derivation (scheme-default ports are used instead)

#### Scenario: Malformed URL -- missing scheme
- **WHEN** `HYDROLIX_URL=mycluster.hydrolix.live`
- **THEN** ❌ `HydrolixConfig.__init__` raises `ValueError`

#### Scenario: Malformed URL -- unsupported scheme
- **WHEN** `HYDROLIX_URL=ftp://mycluster.hydrolix.live`
- **THEN** ❌ `HydrolixConfig.__init__` raises `ValueError`

#### Scenario: Malformed URL -- no hostname
- **WHEN** `HYDROLIX_URL=https://`
- **THEN** ❌ `HydrolixConfig.__init__` raises `ValueError`

#### Scenario: Malformed URL -- empty after strip
- **WHEN** `HYDROLIX_URL=   `
- **THEN** ✅ treated as unset (`None`); no `ValueError` from URL parsing itself

### Requirement: Connection target validation

The connection target (cluster identity) MUST come from either `HYDROLIX_URL` or the deprecated `HYDROLIX_HOST` alias. `HYDROLIX_HTTP_QUERY_HOST` is an override on top of the connection target and SHALL NEVER be sufficient on its own — it provides no cluster identity, only an override for the ClickHouse HTTP query endpoint. If neither `HYDROLIX_URL` nor `HYDROLIX_HOST` is set, `HydrolixConfig.__init__` SHALL raise `ValueError` naming both options (and not `HYDROLIX_HTTP_QUERY_HOST`).

This requirement is the baseline applicable to all transports. The "HYDROLIX_URL required for HTTP/SSE transport" requirement further restricts the http/sse case: there, `HYDROLIX_HOST` alone is also insufficient and `HYDROLIX_URL` specifically is required.

#### Scenario: No connection target set
- **WHEN** neither `HYDROLIX_URL` nor `HYDROLIX_HOST` is set
- **THEN** ❌ `HydrolixConfig.__init__` raises `ValueError` listing both `HYDROLIX_URL` and `HYDROLIX_HOST` (and not `HYDROLIX_HTTP_QUERY_HOST`)

#### Scenario: Only HYDROLIX_URL set
- **WHEN** only `HYDROLIX_URL=https://cluster.example.com` is set (no `HYDROLIX_HOST`, no `HYDROLIX_HTTP_QUERY_HOST`)
- **THEN** ✅ construction succeeds

#### Scenario: Only HYDROLIX_HOST set (backwards compat, stdio only)
- **WHEN** only `HYDROLIX_HOST=cluster.example.com` is set and `HYDROLIX_MCP_SERVER_TRANSPORT=stdio` (no `HYDROLIX_URL`, no `HYDROLIX_HTTP_QUERY_HOST`)
- **THEN** ✅ construction succeeds (deprecated path; http/sse case is covered by the transport requirement)

#### Scenario: Only HYDROLIX_HTTP_QUERY_HOST set
- **WHEN** only `HYDROLIX_HTTP_QUERY_HOST=turbine-query` is set (no `HYDROLIX_URL`, no `HYDROLIX_HOST`)
- **THEN** ❌ `HydrolixConfig.__init__` raises `ValueError` naming `HYDROLIX_URL` and `HYDROLIX_HOST` (HTTP_QUERY_HOST is an override, never a standalone connection target)

#### Scenario: HYDROLIX_HTTP_QUERY_HOST as override on top of URL
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_HTTP_QUERY_HOST=turbine-query` are set
- **THEN** ✅ construction succeeds (HTTP_QUERY_HOST is a valid override on top of a connection target)

### Requirement: HYDROLIX_URL required for HTTP/SSE transport

When `HYDROLIX_MCP_SERVER_TRANSPORT` is `http` or `sse`, `HYDROLIX_URL` specifically MUST be set. If missing, `HydrolixConfig.__init__` SHALL raise `ValueError` naming both `HYDROLIX_URL` and the transport setting, even if `HYDROLIX_HOST` or `HYDROLIX_HTTP_QUERY_HOST` is set.

#### Scenario: HTTP transport without HYDROLIX_URL
- **WHEN** `HYDROLIX_MCP_SERVER_TRANSPORT=http` and `HYDROLIX_HOST=myhost` but `HYDROLIX_URL` is unset
- **THEN** ❌ `HydrolixConfig.__init__` raises `ValueError` mentioning both `HYDROLIX_URL` and `HYDROLIX_MCP_SERVER_TRANSPORT`

#### Scenario: SSE transport without HYDROLIX_URL
- **WHEN** `HYDROLIX_MCP_SERVER_TRANSPORT=sse` and `HYDROLIX_HTTP_QUERY_HOST=myhost` but `HYDROLIX_URL` is unset
- **THEN** ❌ `HydrolixConfig.__init__` raises `ValueError`

#### Scenario: Stdio transport without HYDROLIX_URL
- **WHEN** `HYDROLIX_MCP_SERVER_TRANSPORT=stdio` and `HYDROLIX_HOST=myhost` but `HYDROLIX_URL` is unset
- **THEN** ✅ construction succeeds (HYDROLIX_URL is not required for stdio)

### Requirement: Host property precedence

The `host` property SHALL follow the precedence chain: `HYDROLIX_HTTP_QUERY_HOST` > `HYDROLIX_HOST` (deprecated alias) > `HYDROLIX_URL` hostname. If none resolve, construction fails per the connection target validation requirement.

#### Scenario: Only HYDROLIX_URL
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` (no host overrides)
- **THEN** ✅ `host` returns `cluster.example.com`

#### Scenario: HYDROLIX_HOST alias only
- **WHEN** `HYDROLIX_HOST=myhost.example.com` (no URL, no HTTP_QUERY_HOST)
- **THEN** ✅ `host` returns `myhost.example.com`

#### Scenario: HYDROLIX_HTTP_QUERY_HOST wins over alias
- **WHEN** `HYDROLIX_HTTP_QUERY_HOST=turbine-query` and `HYDROLIX_HOST=myhost.example.com`
- **THEN** ✅ `host` returns `turbine-query`

#### Scenario: HYDROLIX_HTTP_QUERY_HOST wins over URL
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_HTTP_QUERY_HOST=turbine-query`
- **THEN** ✅ `host` returns `turbine-query`

#### Scenario: Deprecated alias wins over URL-derived
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_HOST=override.example.com`
- **THEN** ✅ `host` returns `override.example.com`

### Requirement: Port property precedence

The `port` property SHALL follow the precedence chain: `HYDROLIX_HTTP_QUERY_PORT` > `HYDROLIX_PORT` (deprecated alias) > URL-derived (443 for https, 80 for http) > hard default `8088`.

#### Scenario: URL-derived port (HTTPS)
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` (no port overrides)
- **THEN** ✅ `port` returns `443`

#### Scenario: URL-derived port (HTTP)
- **WHEN** `HYDROLIX_URL=http://cluster.example.com` (no port overrides)
- **THEN** ✅ `port` returns `80`

#### Scenario: Hard default (no URL, no overrides)
- **WHEN** `HYDROLIX_HOST=myhost` (no URL, no port vars)
- **THEN** ✅ `port` returns `8088`

#### Scenario: HYDROLIX_HTTP_QUERY_PORT wins
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_HTTP_QUERY_PORT=8088`
- **THEN** ✅ `port` returns `8088`

#### Scenario: Deprecated alias wins over URL-derived
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_PORT=9000`
- **THEN** ✅ `port` returns `9000`

#### Scenario: New var wins over deprecated alias
- **WHEN** `HYDROLIX_HTTP_QUERY_PORT=8088` and `HYDROLIX_PORT=9000`
- **THEN** ✅ `port` returns `8088`

### Requirement: Secure property precedence

The `secure` property SHALL follow the precedence chain: `HYDROLIX_HTTP_QUERY_SECURE` > `HYDROLIX_SECURE` (deprecated alias) > URL-derived (scheme == "https") > hard default `True`.

#### Scenario: URL-derived secure (HTTPS)
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` (no secure overrides)
- **THEN** ✅ `secure` returns `True`

#### Scenario: URL-derived secure (HTTP)
- **WHEN** `HYDROLIX_URL=http://cluster.example.com` (no secure overrides)
- **THEN** ✅ `secure` returns `False`

#### Scenario: Hard default (no URL, no overrides)
- **WHEN** `HYDROLIX_HOST=myhost` (no URL, no secure vars)
- **THEN** ✅ `secure` returns `True`

#### Scenario: HYDROLIX_HTTP_QUERY_SECURE override
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_HTTP_QUERY_SECURE=false`
- **THEN** ✅ `secure` returns `False`

#### Scenario: Deprecated alias wins over URL-derived
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_SECURE=false`
- **THEN** ✅ `secure` returns `False`

### Requirement: Version API host precedence

The `version_api_host` property SHALL follow the precedence chain: `HYDROLIX_VERSION_API_HOST` > `HYDROLIX_API_HOST` (deprecated alias) > URL hostname > fallback to resolved `host`.

#### Scenario: Only HYDROLIX_URL
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` (no version-api overrides)
- **THEN** ✅ `version_api_host` returns `cluster.example.com`

#### Scenario: Fallback to resolved host
- **WHEN** `HYDROLIX_HOST=myhost` (no URL, no version-api host vars)
- **THEN** ✅ `version_api_host` returns `myhost`

#### Scenario: HYDROLIX_VERSION_API_HOST wins
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_VERSION_API_HOST=version`
- **THEN** ✅ `version_api_host` returns `version`

#### Scenario: Deprecated alias wins over URL-derived
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_API_HOST=version`
- **THEN** ✅ `version_api_host` returns `version`

### Requirement: Version API port precedence

The `version_api_port` property SHALL follow the precedence chain: `HYDROLIX_VERSION_API_PORT` > `HYDROLIX_API_PORT` (deprecated alias) > URL-derived (443/80 by scheme) > `443` if secure else `80`.

#### Scenario: Default from secure=True
- **WHEN** `HYDROLIX_HOST=myhost` (no URL, no version-api port vars, secure defaults to True)
- **THEN** ✅ `version_api_port` returns `443`

#### Scenario: URL-derived (HTTPS)
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` (no version-api overrides)
- **THEN** ✅ `version_api_port` returns `443`

#### Scenario: HYDROLIX_VERSION_API_PORT wins
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_VERSION_API_PORT=23925`
- **THEN** ✅ `version_api_port` returns `23925`

#### Scenario: Deprecated alias wins over URL-derived
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_API_PORT=23925`
- **THEN** ✅ `version_api_port` returns `23925`

### Requirement: Version API secure inherits from resolved secure

The `version_api_secure` property SHALL follow the precedence: explicit `HYDROLIX_VERSION_API_SECURE` > resolved `secure` property. There is no deprecated alias for this property.

#### Scenario: Inherits from URL-derived secure
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` (no explicit version_api_secure)
- **THEN** ✅ `version_api_secure` returns `True` (inherits from `secure=True`)

#### Scenario: Inherits from HTTP secure override
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_HTTP_QUERY_SECURE=false`
- **THEN** ✅ `version_api_secure` returns `False` (inherits from resolved `secure=False`, not URL scheme)

#### Scenario: Explicit override diverges from query secure
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_HTTP_QUERY_SECURE=false` and `HYDROLIX_VERSION_API_SECURE=true`
- **THEN** ✅ `secure` returns `False` and `version_api_secure` returns `True`

#### Scenario: Inherits through deprecated alias path
- **WHEN** `HYDROLIX_HOST=host` and `HYDROLIX_SECURE=false` (no URL, no explicit version_api_secure)
- **THEN** ✅ `version_api_secure` returns `False`

### Requirement: External sufficiency

With `HYDROLIX_URL=https://cluster.example.com` set alone (plus credentials), all six derived properties SHALL resolve correctly: `host=cluster.example.com`, `port=443`, `secure=True`, `version_api_host=cluster.example.com`, `version_api_port=443`, `version_api_secure=True`.

#### Scenario: HYDROLIX_URL alone resolves all properties
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and no other connection vars are set
- **THEN** ✅ `host` is `cluster.example.com`, `port` is `443`, `secure` is `True`, `version_api_host` is `cluster.example.com`, `version_api_port` is `443`, `version_api_secure` is `True`

#### Scenario: External sufficiency with split ports
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` and `HYDROLIX_HTTP_QUERY_PORT=8088` and `HYDROLIX_VERSION_API_PORT=9090`
- **THEN** ✅ hostnames and secure still from URL; `port` is `8088`, `version_api_port` is `9090`, `version_api_secure` is `True`

### Requirement: Backwards compatibility with HYDROLIX_HOST-only configs

When only `HYDROLIX_HOST` is set (no URL, no new vars), the derived property values MUST match the pre-change behavior bit-for-bit: `port=8088`, `secure=True`, `version_api_host` falls back to `host`, `version_api_port=443`, `version_api_secure=True`.

#### Scenario: Legacy HYDROLIX_HOST-only configuration
- **WHEN** `HYDROLIX_HOST=myhost.example.com` and no other connection vars
- **THEN** ✅ `host` is `myhost.example.com`, `port` is `8088`, `secure` is `True`, `version_api_host` is `myhost.example.com`, `version_api_port` is `443`, `version_api_secure` is `True`

### Requirement: In-cluster post-migration shape

With `HYDROLIX_URL` plus all new override vars (`HYDROLIX_HTTP_QUERY_HOST`, `HYDROLIX_HTTP_QUERY_PORT`, `HYDROLIX_HTTP_QUERY_SECURE`, `HYDROLIX_VERSION_API_HOST`, `HYDROLIX_VERSION_API_PORT`), every override SHALL win. `version_api_secure` SHALL be `False` via inheritance when `HYDROLIX_HTTP_QUERY_SECURE=false`.

#### Scenario: Post-migration hkt env shape
- **WHEN** `HYDROLIX_URL=https://cluster.example.com`, `HYDROLIX_HTTP_QUERY_HOST=turbine-query`, `HYDROLIX_HTTP_QUERY_PORT=8088`, `HYDROLIX_HTTP_QUERY_SECURE=false`, `HYDROLIX_VERSION_API_HOST=version`, `HYDROLIX_VERSION_API_PORT=23925`
- **THEN** ✅ `host` is `turbine-query`, `port` is `8088`, `secure` is `False`, `version_api_host` is `version`, `version_api_port` is `23925`, `version_api_secure` is `False`

### Requirement: In-cluster transition shape (deprecated aliases)

With `HYDROLIX_URL` plus deprecated alias names (`HYDROLIX_HOST`, `HYDROLIX_PORT`, `HYDROLIX_SECURE`, `HYDROLIX_API_HOST`, `HYDROLIX_API_PORT`), aliases SHALL be honored and produce identical routing to the post-migration shape.

#### Scenario: Transition-period hkt env shape
- **WHEN** `HYDROLIX_URL=https://cluster.example.com`, `HYDROLIX_HOST=turbine-query`, `HYDROLIX_PORT=8088`, `HYDROLIX_SECURE=false`, `HYDROLIX_API_HOST=version`, `HYDROLIX_API_PORT=23925`
- **THEN** ✅ `host` is `turbine-query`, `port` is `8088`, `secure` is `False`, `version_api_host` is `version`, `version_api_port` is `23925`, `version_api_secure` is `False`

### Requirement: Version probe URL construction

The `/version` probe URL in `_check_parameterized_query_support` SHALL use `version_api_host`, `version_api_port`, and `version_api_secure` (not `api_host`, `api_port`, and `secure`).

#### Scenario: Out-of-cluster version URL
- **WHEN** `HYDROLIX_URL=https://cluster.example.com` (no overrides)
- **THEN** ✅ the `/version` probe URL is `https://cluster.example.com:443/version`

#### Scenario: In-cluster version URL
- **WHEN** `version_api_host=version`, `version_api_port=23925`, `version_api_secure=False`
- **THEN** ✅ the `/version` probe URL is `http://version:23925/version`

### Requirement: Deprecated alias detection

**(Transitional — will be REMOVED when the five deprecated aliases are dropped in a future change.)** A `_detect_deprecated_aliases()` helper SHALL return the list of deprecated env var names that are currently set. The five deprecated aliases are: `HYDROLIX_HOST`, `HYDROLIX_PORT`, `HYDROLIX_SECURE`, `HYDROLIX_API_HOST`, `HYDROLIX_API_PORT`.

#### Scenario: Single alias set
- **WHEN** only `HYDROLIX_HOST` is set among the deprecated names
- **THEN** ✅ `_detect_deprecated_aliases()` returns `["HYDROLIX_HOST"]`

#### Scenario: Multiple aliases set
- **WHEN** `HYDROLIX_HOST` and `HYDROLIX_API_PORT` are set
- **THEN** ✅ `_detect_deprecated_aliases()` returns `["HYDROLIX_HOST", "HYDROLIX_API_PORT"]`

#### Scenario: All five aliases set
- **WHEN** all of `HYDROLIX_HOST`, `HYDROLIX_PORT`, `HYDROLIX_SECURE`, `HYDROLIX_API_HOST`, `HYDROLIX_API_PORT` are set
- **THEN** ✅ `_detect_deprecated_aliases()` returns all five names

#### Scenario: No aliases set
- **WHEN** none of the five deprecated names are set
- **THEN** ✅ `_detect_deprecated_aliases()` returns an empty list

### Requirement: Deprecation audience classification

**(Transitional — will be REMOVED when the five deprecated aliases are dropped in a future change.)** A `_classify_deprecation()` helper SHALL classify the deprecation audience based on `HYDROLIX_NAME`:
- If no deprecated aliases are detected, return `None`.
- If `HYDROLIX_NAME` is set, return `"internal"`.
- If `HYDROLIX_NAME` is unset, return `"external"`.

#### Scenario: No deprecated aliases
- **WHEN** `_detect_deprecated_aliases()` returns `[]`
- **THEN** ✅ `_classify_deprecation([])` returns `None`

#### Scenario: External audience
- **WHEN** `HYDROLIX_HOST` is set and `HYDROLIX_NAME` is unset
- **THEN** ✅ `_classify_deprecation(["HYDROLIX_HOST"])` returns `"external"`

#### Scenario: Internal audience
- **WHEN** `HYDROLIX_HOST` is set and `HYDROLIX_NAME` is set
- **THEN** ✅ `_classify_deprecation(["HYDROLIX_HOST"])` returns `"internal"`

#### Scenario: Partial migration external user
- **WHEN** `HYDROLIX_HOST` is set and `HYDROLIX_URL` is set but `HYDROLIX_NAME` is unset
- **THEN** ✅ `_classify_deprecation(["HYDROLIX_HOST"])` returns `"external"` (partial-migration user still gets the LLM nudge)

### Requirement: External deprecation log at startup

**(Transitional — will be REMOVED when the five deprecated aliases are dropped in a future change.)** When the deprecation audience is `"external"`, `HydrolixConfig.__init__` SHALL emit a single WARNING-level log listing the offending deprecated alias(es) and advising the operator to set `HYDROLIX_URL`. The log SHALL fire at most once per process.

#### Scenario: External WARNING log fires
- **WHEN** `HYDROLIX_HOST` is set, `HYDROLIX_NAME` is unset, and `HydrolixConfig()` is constructed
- **THEN** ✅ a WARNING log is emitted containing the deprecated alias name(s) and mentioning `HYDROLIX_URL` as the migration target

#### Scenario: No duplicate logs
- **WHEN** `HydrolixConfig()` is constructed a second time in the same process with the same deprecated aliases
- **THEN** ✅ no additional WARNING log is emitted

#### Scenario: Internal audience does not trigger startup log
- **WHEN** `HYDROLIX_HOST` is set and `HYDROLIX_NAME` is set
- **THEN** ✅ `HydrolixConfig.__init__` does NOT emit a WARNING log for deprecation

### Requirement: deprecation_notice property for LLM delivery

**(Transitional — will be REMOVED when the five deprecated aliases are dropped in a future change.)** `HydrolixConfig.deprecation_notice` SHALL return a non-empty string containing the external deprecation advisory when `deprecation_audience` is `"external"`. It SHALL return `None` when `deprecation_audience` is `"internal"` or `None`.

#### Scenario: External deprecation notice
- **WHEN** `deprecation_audience` is `"external"`
- **THEN** ✅ `deprecation_notice` returns a string mentioning the deprecated alias(es) and `HYDROLIX_URL` as the sufficient migration target

#### Scenario: Internal deprecation notice is None
- **WHEN** `deprecation_audience` is `"internal"`
- **THEN** ✅ `deprecation_notice` returns `None` (internal deprecation MUST NOT reach the LLM)

#### Scenario: No deprecation
- **WHEN** no deprecated aliases are set
- **THEN** ✅ `deprecation_notice` returns `None`

### Requirement: FastMCP instructions wiring

**(Transitional — will be REMOVED when the five deprecated aliases are dropped in a future change.)** The `FastMCP` constructor SHALL receive `instructions=HYDROLIX_CONFIG.deprecation_notice`. When `deprecation_notice` is `None`, behavior matches the current codebase (no instructions). When non-`None`, every new MCP session's `InitializeResult.instructions` delivers the external advisory.

#### Scenario: External deprecation delivered per session
- **WHEN** external deprecated aliases are detected
- **THEN** ✅ `FastMCP` is constructed with `instructions` set to the external deprecation message, and each client session receives this in `InitializeResult.instructions`

#### Scenario: No deprecation -- no instructions
- **WHEN** no deprecated aliases are detected
- **THEN** ✅ `FastMCP` is constructed with `instructions=None`

### Requirement: Version-gated internal deprecation log

**(Transitional — will be REMOVED when the five deprecated aliases are dropped in a future change.)** When `deprecation_audience` is `"internal"` and the `/version` probe returns a parseable version >= 6.1, an ERROR-level log SHALL fire exactly once listing the deprecated aliases and their new replacements (`OLD -> NEW` pairs). The log SHALL NOT fire if:
- The audience is not `"internal"`.
- The parsed version is < 6.1.
- The `/version` probe fails (HTTP error, non-200, unparseable body).

#### Scenario: Internal log fires for version 6.1.0
- **WHEN** `deprecation_audience` is `"internal"` and `/version` returns `"v6.1.0"`
- **THEN** ✅ an ERROR log fires listing the deprecated aliases and their replacements

#### Scenario: Internal log fires for version 7.0.0
- **WHEN** `deprecation_audience` is `"internal"` and `/version` returns `"v7.0.0"`
- **THEN** ✅ an ERROR log fires (>= 6.1 satisfied)

#### Scenario: Internal log fires for dev version
- **WHEN** `deprecation_audience` is `"internal"` and `/version` returns `"v6.1.0-5-gabcdef12"`
- **THEN** ✅ an ERROR log fires (parsed as 6.1)

#### Scenario: No log for version 6.0.9
- **WHEN** `deprecation_audience` is `"internal"` and `/version` returns `"v6.0.9"`
- **THEN** ✅ no deprecation log fires

#### Scenario: No log for version 5.x
- **WHEN** `deprecation_audience` is `"internal"` and `/version` returns `"v5.12.0"`
- **THEN** ✅ no deprecation log fires

#### Scenario: No log on probe failure
- **WHEN** `deprecation_audience` is `"internal"` and `/version` HTTP request raises an exception
- **THEN** ✅ no deprecation log fires; subsequent successful probe with version >= 6.1 SHALL fire the log

#### Scenario: No log on non-200 response
- **WHEN** `deprecation_audience` is `"internal"` and `/version` returns HTTP 500
- **THEN** ✅ no deprecation log fires

#### Scenario: No log on unparseable version
- **WHEN** `deprecation_audience` is `"internal"` and `/version` returns `"garbage"`
- **THEN** ✅ no deprecation log fires

#### Scenario: Log fires at most once
- **WHEN** the internal deprecation log has already fired
- **THEN** ✅ subsequent `/version` probes SHALL NOT emit a second log

#### Scenario: External audience -- no log from probe
- **WHEN** `deprecation_audience` is `"external"` and `/version` returns `"v6.1.0"`
- **THEN** ✅ no deprecation log fires from the probe path (external log was emitted at init time)

#### Scenario: No deprecation -- no log from probe
- **WHEN** no deprecated aliases are set and `/version` returns `"v6.1.0"`
- **THEN** ✅ no deprecation log fires from the probe path

### Requirement: Alias rename mapping

**(Transitional — will be REMOVED when the five deprecated aliases are dropped in a future change.)** The mapping of deprecated aliases to their replacements SHALL be:

| Deprecated | Replacement |
|---|---|
| `HYDROLIX_HOST` | `HYDROLIX_HTTP_QUERY_HOST` |
| `HYDROLIX_PORT` | `HYDROLIX_HTTP_QUERY_PORT` |
| `HYDROLIX_SECURE` | `HYDROLIX_HTTP_QUERY_SECURE` |
| `HYDROLIX_API_HOST` | `HYDROLIX_VERSION_API_HOST` |
| `HYDROLIX_API_PORT` | `HYDROLIX_VERSION_API_PORT` |

The internal deprecation message SHALL include `OLD -> NEW` pairs for each detected alias. The external deprecation message SHALL list the detected alias names and point to `HYDROLIX_URL` as the sufficient replacement.

#### Scenario: Internal message format
- **WHEN** `HYDROLIX_HOST` and `HYDROLIX_API_PORT` are the detected aliases and audience is internal
- **THEN** ✅ the internal log message includes `HYDROLIX_HOST -> HYDROLIX_HTTP_QUERY_HOST` and `HYDROLIX_API_PORT -> HYDROLIX_VERSION_API_PORT`

#### Scenario: External message format
- **WHEN** `HYDROLIX_HOST` is the detected alias and audience is external
- **THEN** ✅ the external message mentions `HYDROLIX_HOST` and advises setting `HYDROLIX_URL`

### Requirement: HydrolixConfig exposes deprecation state

**(Transitional — will be REMOVED when the five deprecated aliases are dropped in a future change.)** `HydrolixConfig` SHALL expose `deprecated_aliases` (list of detected deprecated var names) and `deprecation_audience` (`"external"`, `"internal"`, or `None`) as readable properties, so the version-gated probe hook can inspect them.

#### Scenario: Properties available for probe hook
- **WHEN** `HYDROLIX_HOST` is set and `HYDROLIX_NAME` is set
- **THEN** ✅ `HYDROLIX_CONFIG.deprecated_aliases` contains `"HYDROLIX_HOST"` and `HYDROLIX_CONFIG.deprecation_audience` is `"internal"`

#### Scenario: No deprecation state
- **WHEN** no deprecated aliases are set
- **THEN** ✅ `HYDROLIX_CONFIG.deprecated_aliases` is empty and `HYDROLIX_CONFIG.deprecation_audience` is `None`
