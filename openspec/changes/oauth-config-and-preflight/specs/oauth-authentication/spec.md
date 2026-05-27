*Covers OAuth activation gating, issuer precedence, canonical IdP endpoint derivation, JWKS URI override, and fail-open startup preflight.*

## ADDED Requirements

### Requirement: Activation Gated On Env Vars

The server SHALL activate OAuth bearer authentication for the HTTP and SSE transports if and only if `HYDROLIX_OAUTH_AUDIENCE` is set to a non-empty value AND a usable issuer is resolvable. The issuer is resolved with the following precedence:

1. `HYDROLIX_OAUTH_ISSUER` if set to a non-empty value (explicit operator override).
2. Otherwise, if `HYDROLIX_URL` is set to a non-empty value, the issuer is derived from it via `canonical_idp_endpoints` (see "Canonical IdP Endpoint Derivation Is A Single Contained Function").
3. Otherwise, the issuer is unresolved and OAuth is not activated.

When OAuth is not activated and no partial configuration is present (defined below), the server SHALL behave byte-identically to a build without OAuth code: no new endpoints, no `WWW-Authenticate` headers, no OAuth log lines, and the existing service-account credential chain handles all requests. `HYDROLIX_URL` alone is not a signal of OAuth intent — it belongs to [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441) and has non-OAuth uses — so its presence does not break the byte-identical guarantee.

**Partial configuration** is any of these operator-misconfiguration cases, and the server SHALL raise `OAuthConfigError` at startup in each:
- `HYDROLIX_OAUTH_AUDIENCE` is set but neither `HYDROLIX_OAUTH_ISSUER` nor `HYDROLIX_URL` is set.
- `HYDROLIX_OAUTH_ISSUER` is set but `HYDROLIX_OAUTH_AUDIENCE` is unset.
- Any optional OAuth var (`HYDROLIX_OAUTH_JWKS_URI`, `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS`, `HYDROLIX_OAUTH_REQUIRED_SCOPES`, `HYDROLIX_OAUTH_RESOURCE_URL`) is set but `HYDROLIX_OAUTH_AUDIENCE` is unset.

The byte-identical guarantee above does not apply to partial configuration; the intent is to surface misconfiguration loudly rather than silently ignore operator-set OAuth knobs.

**The pre-[HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) stub case is not partial configuration.** When `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_URL` are set, `HYDROLIX_OAUTH_ISSUER` is unset, and `canonical_idp_endpoints` raises `NotImplementedError`, the config is valid — the system just can't derive the issuer until [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) lands. `NotImplementedError` propagates directly (not wrapped as `OAuthConfigError`), so operators can tell "I set something wrong" from "this code path doesn't exist yet" in logs.

#### Scenario: No OAuth Vars Set

- **WHEN** the server starts the HTTP transport with neither `HYDROLIX_OAUTH_ISSUER` nor `HYDROLIX_URL` set
- **AND** `HYDROLIX_OAUTH_AUDIENCE` is also unset
- **THEN** the server SHALL NOT emit any log line containing the substring `OAuth`
- **AND** requests to `/.well-known/oauth-protected-resource` SHALL return 404
- **AND** requests to MCP tool endpoints with no bearer token SHALL behave exactly as on a build with no OAuth code

#### Scenario: Audience Set But No Issuer Resolvable

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` is set
- **AND** neither `HYDROLIX_OAUTH_ISSUER` nor `HYDROLIX_URL` is set
- **THEN** the worker SHALL raise `OAuthConfigError` during factory initialization
- **AND** SHALL NOT serve any request

#### Scenario: Issuer Derivation Attempted Before HDX-11431

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_URL` are both set
- **AND** `HYDROLIX_OAUTH_ISSUER` is unset
- **AND** [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) has not yet landed (the derivation stub raises `NotImplementedError`)
- **THEN** the worker SHALL terminate at factory initialization
- **AND** the propagated exception SHALL be `NotImplementedError`, not `OAuthConfigError`
- **AND** the error message SHALL contain the substring `HDX-11431`

#### Scenario: Issuer Derived From Cluster URL Post-HDX-11431

- **WHEN** [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) has landed and the derivation function returns a valid record
- **AND** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_URL` are both set, with `HYDROLIX_OAUTH_ISSUER` unset
- **THEN** the server SHALL resolve the issuer via `canonical_idp_endpoints(HYDROLIX_URL).issuer`
- **AND** OAuth SHALL activate using the derived issuer

#### Scenario: Explicit Issuer Overrides Derivation

- **WHEN** `HYDROLIX_OAUTH_ISSUER`, `HYDROLIX_OAUTH_AUDIENCE`, and `HYDROLIX_URL` are all set
- **AND** the explicit `HYDROLIX_OAUTH_ISSUER` differs from the value that would be derived from `HYDROLIX_URL`
- **THEN** the server SHALL use the explicit `HYDROLIX_OAUTH_ISSUER` value
- **AND** SHALL NOT raise a startup error for the mismatch

#### Scenario: Issuer Set But Audience Unset

- **WHEN** `HYDROLIX_OAUTH_ISSUER` is set but `HYDROLIX_OAUTH_AUDIENCE` is unset
- **THEN** the worker SHALL raise `OAuthConfigError` during factory initialization
- **AND** SHALL NOT serve any request

#### Scenario: Hydrolix URL Set Without OAuth Vars

- **WHEN** `HYDROLIX_URL` is set
- **AND** no `HYDROLIX_OAUTH_*` env vars are set
- **THEN** OAuth SHALL NOT activate
- **AND** the server SHALL behave byte-identically to a build without OAuth code

#### Scenario: Optional OAuth Var Set Without Audience

- **WHEN** any of `HYDROLIX_OAUTH_JWKS_URI`, `HYDROLIX_OAUTH_REQUIRED_SCOPES`, `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS`, or `HYDROLIX_OAUTH_RESOURCE_URL` is set
- **AND** `HYDROLIX_OAUTH_AUDIENCE` is unset
- **THEN** the worker SHALL raise `OAuthConfigError` during factory initialization

### Requirement: Canonical IdP Endpoint Derivation Is A Single Contained Function

All knowledge of where the cluster's canonical IdP lives relative to `HYDROLIX_URL` SHALL be encapsulated in a single function that takes the cluster URL and returns an immutable record containing at least the issuer URL, the OIDC discovery URL, the JWKS URI, and the network-reachable address of the IdP. The function SHALL live in module `mcp_hydrolix.auth.idp_endpoints`.

Until [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) publishes the cluster-URL-to-IdP convention, this function SHALL raise `NotImplementedError` with a message referencing [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431). As a consequence, the URL-derivation activation path is unreachable in production until [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) lands; explicit `HYDROLIX_OAUTH_ISSUER` is the only activatable issuer source during the interim period.

When the function eventually returns a result (after [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) lands and the body is replaced), the returned record SHALL be frozen, SHALL contain the four named fields, and SHALL never return an `issuer` string-equal to its input `hydrolix_url` (preserving the issuer/cluster-URL non-conflation invariant; enforcement at request time is owned by `oauth-jwt-verifier`).

#### Scenario: Stub Raises Not Implemented Error Until HDX-11431

- **WHEN** `canonical_idp_endpoints` is called with any value of `hydrolix_url` before [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) has landed
- **THEN** the function SHALL raise `NotImplementedError`
- **AND** the exception message SHALL contain the substring `HDX-11431`

#### Scenario: Eventual Return Shape Is Immutable And Complete

- **WHEN** [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) has landed and `canonical_idp_endpoints` is called with a `hydrolix_url` value, returning successfully
- **THEN** the returned record SHALL be frozen (no mutable fields)
- **AND** the record SHALL expose `issuer`, `discovery_url`, `jwks_uri`, and `address` as string-typed fields
- **AND** calling the function twice with the same input SHALL return equal records

#### Scenario: Eventual Derived Issuer Is Never Equal To Input Cluster URL

- **WHEN** [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) has landed and `canonical_idp_endpoints` is called with any non-empty `hydrolix_url` value, returning successfully
- **THEN** the returned `issuer` SHALL NOT be string-equal to the input `hydrolix_url`

### Requirement: JWKS URI Override And Insecure Transport Flag

`load_oauth_config()` SHALL honor an explicit `HYDROLIX_OAUTH_JWKS_URI` value as the JWKS URI for in-cluster deployments where the public discovery URL is not reachable from the pod. By default, when `HYDROLIX_OAUTH_JWKS_URI` carries an `http://` scheme, `load_oauth_config()` SHALL raise `OAuthConfigError` at startup before any JWKS fetch is attempted. When `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS=true` is also set, `load_oauth_config()` SHALL accept the `http://` JWKS URI and the runtime verifier SHALL fetch keys from it (supporting cluster-internal backchannel calls).

#### Scenario: Plain HTTP JWKS Rejected By Default

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_OAUTH_ISSUER` are set to activate OAuth
- **AND** `HYDROLIX_OAUTH_JWKS_URI="http://idp.internal/realms/x/protocol/openid-connect/certs"` is set
- **AND** `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS` is unset
- **THEN** `load_oauth_config()` SHALL raise `OAuthConfigError` at startup (the insecure-scheme check fires before any preflight)

#### Scenario: Plain HTTP JWKS Allowed When Explicitly Opted In

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_OAUTH_ISSUER` are set to activate OAuth
- **AND** `HYDROLIX_OAUTH_JWKS_URI="http://idp.internal/.../certs"` is set
- **AND** `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS="true"` is set
- **THEN** `load_oauth_config()` SHALL accept the configuration and the verifier SHALL fetch keys from that URL at startup

### Requirement: Startup Preflight Is Fail-Open

If OIDC discovery or JWKS preflight fails at startup (network error, non-2xx HTTP, malformed JSON, missing `jwks_uri`), the worker SHALL emit a single WARNING log line and continue serving with the credential chain only — OAuth SHALL NOT be activated for that worker. This is the startup half of the fail-open/fail-closed contract; the fail-closed (request-time rejection) behavior when OAuth has successfully activated is owned by `oauth-auth-chain-and-activation`.

#### Scenario: Discovery Network Failure At Startup

- **WHEN** the OIDC discovery endpoint is unreachable at worker startup
- **THEN** the worker SHALL log exactly one WARNING line containing `OAuth configured but not activated` and the network failure class name
- **AND** the worker SHALL continue serving with `mcp.auth` set to the credential chain
- **AND** SHALL NOT raise an exception at startup
