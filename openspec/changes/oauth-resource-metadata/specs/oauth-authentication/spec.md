*RFC 9728 protected-resource-metadata endpoint and resource URL precedence chain, active only when OAuth is enabled.*

## ADDED Requirements

### Requirement: RFC 9728 Protected Resource Metadata Endpoint

When OAuth is active (as defined by `oauth-config-and-preflight`), the server SHALL expose an unauthenticated `GET` endpoint serving a JSON document conforming to [RFC 9728](https://www.rfc-editor.org/rfc/rfc9728). The endpoint path SHALL be `/.well-known/oauth-protected-resource` concatenated with the path component of `OAuthConfig.resource_url`, per RFC 9728 §3 (well-known suffix inserted between authority and resource path). Because the MCP application is mounted at `/mcp` (see `webapp.py`), and the resource URL precedence chain (see "Resource URL Configuration") produces a `resource_url` whose path component is `/mcp` for all non-operator-overridden tiers, the canonical endpoint path is **`/.well-known/oauth-protected-resource/mcp`**.

The endpoint SHALL NOT require authentication. The JSON body SHALL include at minimum:

- `resource`: the value of `OAuthConfig.resource_url` after the precedence chain defined in "Resource URL Configuration".
- `authorization_servers`: a JSON array containing exactly the resolved issuer URL (`OAuthConfig.issuer` as set by `oauth-config-and-preflight`).
- `bearer_methods_supported`: a JSON array containing at least `"header"`.

When OAuth is inactive, a `GET` request to the metadata endpoint path SHALL return HTTP 404.

When a request to an authenticated endpoint is rejected with HTTP 401, the `WWW-Authenticate` response header SHALL include a `resource_metadata="<url>"` parameter whose value is the absolute URL of the protected-resource-metadata endpoint as actually served by this worker — i.e. the same scheme/authority used for `OAuthConfig.resource_url` concatenated with `/.well-known/oauth-protected-resource` and the path component of `OAuthConfig.resource_url`. For the default `HYDROLIX_URL`-based config this resolves to `<HYDROLIX_URL>/.well-known/oauth-protected-resource/mcp`.

#### Scenario: Metadata Endpoint Returns RFC 9728 JSON At Path-Scoped Location

- **WHEN** OAuth is active with `HYDROLIX_URL="https://cluster.example.com"` (so `OAuthConfig.resource_url == "https://cluster.example.com/mcp"`) and an unauthenticated GET request is made to `/.well-known/oauth-protected-resource/mcp`
- **THEN** the response status SHALL be 200
- **AND** the `Content-Type` header SHALL be `application/json`
- **AND** the response body SHALL be valid JSON containing `resource`, `authorization_servers`, and `bearer_methods_supported` keys
- **AND** `authorization_servers` SHALL be an array containing `OAuthConfig.issuer`
- **AND** `resource` SHALL equal `"https://cluster.example.com/mcp"`

#### Scenario: Worker Does Not Claim Root Well-Known Path

- **WHEN** OAuth is active with `HYDROLIX_URL="https://cluster.example.com"` and a GET request to `/.well-known/oauth-protected-resource` (root, no `/mcp` suffix) reaches **this worker** directly (e.g. in an isolated test or a direct in-cluster hit, not through ingress)
- **THEN** this worker SHALL respond 404 — it does not register a handler for the origin root path

This scenario constrains worker behavior only. It does NOT require the cluster as a whole to return 404 at that path: the origin root `/.well-known/oauth-protected-resource` is deliberately left unclaimed by the MCP worker so that a future, broader-scoped service (e.g. one whose resource identifier has no path component) MAY claim it via cluster routing without conflicting with this worker.

#### Scenario: 401 References Path-Scoped Metadata URL

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE="mcp-test"` and `HYDROLIX_OAUTH_ISSUER="https://idp.example.com/realms/test"` are set, OAuth is active (and an auth chain capable of emitting 401 is present, i.e. `oauth-jwt-verifier` or `oauth-auth-chain-and-activation` has landed), and a GET request to `/mcp/tools/list` arrives with an invalid bearer token
- **THEN** the `WWW-Authenticate` response header SHALL include a `resource_metadata=` parameter
- **AND** the parameter value SHALL be the absolute URL of the path-scoped metadata endpoint (i.e. ending in `/.well-known/oauth-protected-resource/mcp`)

#### Scenario: Metadata Endpoint Returns 404 When OAuth Inactive

- **WHEN** OAuth is inactive (no `HYDROLIX_OAUTH_AUDIENCE` set) and a GET request is made to `/.well-known/oauth-protected-resource/mcp`
- **THEN** the response status SHALL be 404

### Requirement: Resource URL Configuration

The `resource` field in the RFC 9728 document SHALL be resolved from `OAuthConfig.resource_url` using the following two-tier precedence chain. Both tiers SHALL append the FastMCP mount path (`/mcp`, as configured in `webapp.py`) so the resulting `resource_url` identifies the MCP application as a path-scoped resource per RFC 9728 §3.

1. If `HYDROLIX_URL` is set to a non-empty value, the resource URL SHALL be `HYDROLIX_URL` with `/mcp` appended (collapsing any duplicate or trailing slash).
2. Otherwise, the resource URL SHALL default to the server's configured base URL (scheme + host + port that the worker is bound to) with `/mcp` appended.

There is deliberately no operator override env var for `resource_url`. `resource_url` is purely advertised in the RFC 9728 metadata document and in the `WWW-Authenticate: resource_metadata=` pointer — it does not participate in server-side token verification, issuer matching, JWKS URI selection, or activation logic. Any operator who needs to advertise a different URL than `<HYDROLIX_URL>/mcp` can set `HYDROLIX_URL` to that URL; a dedicated override would be additive and non-breaking to introduce later if a deployment need actually emerges.

#### Scenario: Resource URL Defaults To Hydrolix URL Plus Mount Path

- **WHEN** `HYDROLIX_URL="https://cluster.example.com"` is set, OAuth is active, and `OAuthConfig.resource_url` is resolved
- **THEN** `OAuthConfig.resource_url` SHALL equal `"https://cluster.example.com/mcp"`
- **AND** the `resource` field in the RFC 9728 JSON SHALL equal `"https://cluster.example.com/mcp"`

#### Scenario: Resource URL Defaults To Hydrolix URL With Trailing Slash Plus Mount Path

- **WHEN** `HYDROLIX_URL="https://cluster.example.com/"` is set, OAuth is active, and `OAuthConfig.resource_url` is resolved
- **THEN** `OAuthConfig.resource_url` SHALL equal `"https://cluster.example.com/mcp"` (single slash, no duplicate)

#### Scenario: Resource URL Falls Back To Server Bind URL Plus Mount Path

- **WHEN** `HYDROLIX_URL` is unset, OAuth is active with an explicit `HYDROLIX_OAUTH_ISSUER`, and `OAuthConfig.resource_url` is resolved
- **THEN** `OAuthConfig.resource_url` SHALL equal the server's bound base URL (scheme + host + port) with `/mcp` appended
- **AND** the `resource` field in the RFC 9728 JSON SHALL equal that value
