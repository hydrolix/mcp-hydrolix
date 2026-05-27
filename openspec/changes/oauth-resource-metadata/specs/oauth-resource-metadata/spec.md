*RFC 9728 protected-resource-metadata endpoint and resource URL precedence chain, active only when OAuth is enabled.*

## ADDED Requirements

### Requirement: RFC 9728 Protected Resource Metadata Endpoint

When OAuth is active (as defined by `oauth-config-and-preflight`), the server SHALL expose `GET /.well-known/oauth-protected-resource` returning a JSON document conforming to [RFC 9728](https://www.rfc-editor.org/rfc/rfc9728). This endpoint SHALL NOT require authentication. The JSON body SHALL include at minimum:

- `resource`: the value of `OAuthConfig.resource_url` after the precedence chain defined in "Resource URL Configuration".
- `authorization_servers`: a JSON array containing exactly the resolved issuer URL (`OAuthConfig.issuer` as set by `oauth-config-and-preflight`).
- `bearer_methods_supported`: a JSON array containing at least `"header"`.

When OAuth is inactive, `GET /.well-known/oauth-protected-resource` SHALL return HTTP 404.

When a request to an authenticated endpoint is rejected with HTTP 401, the `WWW-Authenticate` response header SHALL include a `resource_metadata=<url>` parameter whose value is the absolute URL of the protected-resource-metadata endpoint (i.e. the server bind base URL concatenated with `/.well-known/oauth-protected-resource`).

#### Scenario: Metadata Endpoint Returns RFC 9728 JSON

- **GIVEN** OAuth is active
- **WHEN** an unauthenticated GET request is made to `/.well-known/oauth-protected-resource`
- **THEN** the response status SHALL be 200
- **AND** the `Content-Type` header SHALL be `application/json`
- **AND** the response body SHALL be valid JSON containing `resource`, `authorization_servers`, and `bearer_methods_supported` keys
- **AND** `authorization_servers` SHALL be an array containing `OAuthConfig.issuer`
- **AND** `resource` SHALL equal `OAuthConfig.resource_url`

#### Scenario: 401 References Metadata URL

- **GIVEN** OAuth is active
- **WHEN** a request to an authenticated endpoint is rejected with HTTP 401
- **THEN** the `WWW-Authenticate` response header SHALL include a `resource_metadata=` parameter
- **AND** the parameter value SHALL be the absolute URL of the `/.well-known/oauth-protected-resource` endpoint on this server

#### Scenario: Metadata Endpoint Returns 404 When OAuth Inactive

- **GIVEN** OAuth is inactive (no `HYDROLIX_OAUTH_AUDIENCE` set)
- **WHEN** a GET request is made to `/.well-known/oauth-protected-resource`
- **THEN** the response status SHALL be 404

### Requirement: Resource URL Configuration

The `resource` field in the RFC 9728 document SHALL be resolved from `OAuthConfig.resource_url` using the following three-tier precedence chain:

1. `HYDROLIX_OAUTH_RESOURCE_URL` if set to a non-empty value (explicit operator override).
2. Otherwise, if `HYDROLIX_URL` is set to a non-empty value, the resource URL SHALL default to `HYDROLIX_URL`.
3. Otherwise, the resource URL SHALL default to the server's configured base URL (scheme + host + port that the worker is bound to).

`HYDROLIX_OAUTH_RESOURCE_URL` SHALL NOT affect any other aspect of authentication: it does not change the `iss` match target, does not alter the JWKS URI, and does not change OAuth activation logic. Setting `HYDROLIX_OAUTH_RESOURCE_URL` when `HYDROLIX_OAUTH_AUDIENCE` is unset SHALL raise `OAuthConfigError` at startup via the partial-config error path defined in `oauth-config-and-preflight`.

#### Scenario: Explicit Resource URL Wins

- **GIVEN** `HYDROLIX_OAUTH_RESOURCE_URL="https://mcp.example.com/api"` is set alongside an activatable OAuth config
- **WHEN** the server starts and OAuth activates
- **THEN** `OAuthConfig.resource_url` SHALL equal `"https://mcp.example.com/api"`
- **AND** the `resource` field in the RFC 9728 JSON SHALL equal `"https://mcp.example.com/api"`

#### Scenario: Resource URL Defaults To Hydrolix URL

- **GIVEN** `HYDROLIX_OAUTH_RESOURCE_URL` is unset
- **AND** `HYDROLIX_URL="https://cluster.example.com"` is set
- **AND** OAuth is active
- **WHEN** `OAuthConfig.resource_url` is resolved
- **THEN** `OAuthConfig.resource_url` SHALL equal `"https://cluster.example.com"`
- **AND** the `resource` field in the RFC 9728 JSON SHALL equal `"https://cluster.example.com"`

#### Scenario: Resource URL Falls Back To Server Bind URL

- **GIVEN** `HYDROLIX_OAUTH_RESOURCE_URL` is unset
- **AND** `HYDROLIX_URL` is unset
- **AND** OAuth is active with an explicit `HYDROLIX_OAUTH_ISSUER`
- **WHEN** `OAuthConfig.resource_url` is resolved
- **THEN** `OAuthConfig.resource_url` SHALL equal the server's bound base URL (scheme + host + port)
- **AND** the `resource` field in the RFC 9728 JSON SHALL equal that bound base URL

#### Scenario: Resource URL Set Without Audience Triggers Partial Config Error

- **GIVEN** `HYDROLIX_OAUTH_RESOURCE_URL` is set to a non-empty value
- **AND** `HYDROLIX_OAUTH_AUDIENCE` is unset
- **WHEN** the server starts (factory initialization runs)
- **THEN** the worker SHALL raise `OAuthConfigError`
- **AND** SHALL NOT serve any requests
