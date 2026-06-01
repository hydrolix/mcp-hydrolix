*Covers OAuth activation gating, issuer precedence, canonical IdP endpoint derivation, JWKS URI override, and fail-open startup preflight.*

## ADDED Requirements

### Requirement: Activation Gated On Env Vars

The server SHALL activate OAuth if and only if `HYDROLIX_OAUTH_AUDIENCE` is set AND a usable issuer is resolvable via this precedence:

1. `HYDROLIX_OAUTH_ISSUER` if non-empty (explicit override).
2. `canonical_idp_endpoints(HYDROLIX_URL).issuer` if `HYDROLIX_URL` is non-empty.
3. Otherwise unresolved — OAuth not activated.

Without activation and without partial config, the server is byte-identical to a build without OAuth code. `HYDROLIX_URL` alone is not an OAuth signal.

**Partial configuration** — server SHALL raise `OAuthConfigError` at startup for:
- `HYDROLIX_OAUTH_AUDIENCE` set but neither `HYDROLIX_OAUTH_ISSUER` nor `HYDROLIX_URL` set.
- `HYDROLIX_OAUTH_ISSUER` set but `HYDROLIX_OAUTH_AUDIENCE` unset.
- Any of `HYDROLIX_OAUTH_JWKS_URI`, `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS`, `HYDROLIX_OAUTH_REQUIRED_SCOPES` set but `HYDROLIX_OAUTH_AUDIENCE` unset.

When `HYDROLIX_OAUTH_AUDIENCE` + `HYDROLIX_URL` are set and `canonical_idp_endpoints` raises `NotImplementedError`, that is NOT partial config — `NotImplementedError` propagates unwrapped.

#### Scenario: No OAuth Vars Set

- **WHEN** no `HYDROLIX_OAUTH_*` vars and no `HYDROLIX_URL` are set
- **THEN** the server SHALL NOT emit any log line containing `OAuth`
- **AND** `/.well-known/oauth-protected-resource` SHALL return 404
- **AND** MCP tool endpoints with no bearer token SHALL behave as on a build with no OAuth code

#### Scenario: Audience Set But No Issuer Resolvable

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` is set
- **AND** neither `HYDROLIX_OAUTH_ISSUER` nor `HYDROLIX_URL` is set
- **THEN** the worker SHALL raise `OAuthConfigError` during factory initialization
- **AND** SHALL NOT serve any request

#### Scenario: Issuer Derivation Attempted Before HDX-11431

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_URL` are both set, `HYDROLIX_OAUTH_ISSUER` unset
- **AND** the derivation stub raises `NotImplementedError`
- **THEN** the worker SHALL terminate at factory initialization
- **AND** the propagated exception SHALL be `NotImplementedError`, not `OAuthConfigError`
- **AND** the error message SHALL contain `HDX-11431`

#### Scenario: Issuer Derived From Cluster URL Post-HDX-11431

- **WHEN** `canonical_idp_endpoints` is replaced with a test implementation returning `CanonicalIdPEndpoints(issuer="https://idp.example.com/realms/hydrolix", discovery_url="https://idp.example.com/realms/hydrolix/.well-known/openid-configuration", jwks_uri="https://idp.example.com/realms/hydrolix/protocol/openid-connect/certs", address="idp.example.com")` for the given `hydrolix_url`
- **AND** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_URL` are set, `HYDROLIX_OAUTH_ISSUER` unset
- **THEN** the server SHALL resolve the issuer via `canonical_idp_endpoints(HYDROLIX_URL).issuer`
- **AND** OAuth SHALL activate using the derived issuer

#### Scenario: Explicit Issuer Overrides Derivation

- **WHEN** `HYDROLIX_OAUTH_ISSUER`, `HYDROLIX_OAUTH_AUDIENCE`, and `HYDROLIX_URL` are all set
- **AND** the explicit issuer differs from the value that would be derived from `HYDROLIX_URL`
- **THEN** the server SHALL use `HYDROLIX_OAUTH_ISSUER`
- **AND** SHALL NOT raise a startup error for the mismatch

#### Scenario: Issuer Set But Audience Unset

- **WHEN** `HYDROLIX_OAUTH_ISSUER` is set but `HYDROLIX_OAUTH_AUDIENCE` is unset
- **THEN** the worker SHALL raise `OAuthConfigError` during factory initialization

#### Scenario: Hydrolix URL Set Without OAuth Vars

- **WHEN** `HYDROLIX_URL` is set and no `HYDROLIX_OAUTH_*` vars are set
- **THEN** OAuth SHALL NOT activate
- **AND** the server SHALL be byte-identical to a build without OAuth code

#### Scenario: Optional OAuth Var Set Without Audience

- **WHEN** any of `HYDROLIX_OAUTH_JWKS_URI`, `HYDROLIX_OAUTH_REQUIRED_SCOPES`, or `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS` is set and `HYDROLIX_OAUTH_AUDIENCE` is unset
- **THEN** the worker SHALL raise `OAuthConfigError` during factory initialization

### Requirement: Canonical IdP Endpoint Derivation Is A Single Contained Function

`canonical_idp_endpoints(hydrolix_url: str) -> CanonicalIdPEndpoints` in `mcp_hydrolix.auth.idp_endpoints` is the sole location for cluster-URL-to-IdP knowledge. Until [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) lands, it SHALL raise `NotImplementedError` with a message containing `HDX-11431`. When implemented, the returned record SHALL be frozen with fields `issuer`, `discovery_url`, `jwks_uri`, `address`, and SHALL never return `issuer` equal to the input `hydrolix_url`.

#### Scenario: Stub Raises Not Implemented Error Until HDX-11431

- **WHEN** `canonical_idp_endpoints` is called with any `hydrolix_url`
- **THEN** the function SHALL raise `NotImplementedError` with message containing `HDX-11431`

#### Scenario: Eventual Return Shape Is Immutable And Complete

- **WHEN** `canonical_idp_endpoints` is replaced with a test implementation returning a `CanonicalIdPEndpoints` record
- **AND** called with any non-empty `hydrolix_url`
- **THEN** the record SHALL be frozen, expose `issuer`, `discovery_url`, `jwks_uri`, `address` as strings, and equal records returned for equal inputs

#### Scenario: Eventual Derived Issuer Is Never Equal To Input Cluster URL

- **WHEN** `canonical_idp_endpoints` is replaced with a test implementation and called with any non-empty `hydrolix_url`
- **THEN** the returned `issuer` SHALL NOT be string-equal to `hydrolix_url`

### Requirement: JWKS URI Override And Insecure Transport Flag

`load_oauth_config()` SHALL accept `HYDROLIX_OAUTH_JWKS_URI` for in-cluster deployments. When that URI uses `http://` and `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS` is not `"true"`, `load_oauth_config()` SHALL raise `OAuthConfigError` before any network call. When `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS=true` is also set, the `http://` URI is accepted.

#### Scenario: Plain HTTP JWKS Rejected By Default

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_OAUTH_ISSUER` are set
- **AND** `HYDROLIX_OAUTH_JWKS_URI="http://idp.internal/realms/x/protocol/openid-connect/certs"`
- **AND** `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS` is unset
- **THEN** `load_oauth_config()` SHALL raise `OAuthConfigError`

#### Scenario: Plain HTTP JWKS Allowed When Explicitly Opted In

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_OAUTH_ISSUER` are set
- **AND** `HYDROLIX_OAUTH_JWKS_URI="http://idp.internal/.../certs"` and `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS="true"` are set
- **THEN** `load_oauth_config()` SHALL accept the configuration

### Requirement: Startup Preflight Is Fail-Open

On OIDC discovery or JWKS preflight failure (network error, non-2xx, malformed JSON, missing `jwks_uri`), the worker SHALL emit one WARNING containing `OAuth configured but not activated` and continue serving credential-chain only.

#### Scenario: Discovery Network Failure At Startup

- **WHEN** the OIDC discovery endpoint is unreachable at worker startup
- **THEN** the worker SHALL log exactly one WARNING containing `OAuth configured but not activated` and the network failure class name
- **AND** the worker SHALL continue serving with `mcp.auth` set to the credential chain
- **AND** SHALL NOT raise an exception at startup
