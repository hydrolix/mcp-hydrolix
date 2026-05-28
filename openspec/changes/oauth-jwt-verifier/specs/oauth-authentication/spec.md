*Pure claim validation for OAuth bearer tokens: iss-based routing for chain composability, issuer exact-match, audience allowlist, required scopes, and end-to-end bearer acceptance.*

## ADDED Requirements

### Requirement: OAuth Verifier Claims Bearers By Iss Match

`OAuthHydrolixAuthProvider` SHALL act as a chain-composable backend, claiming a bearer iff its `iss` claim exactly matches the resolved OAuth issuer URL, otherwise deferring. The `iss` peek occurs without signature verification (routing only); full verification still gates every success path.

Three return modes:
1. `iss` matches + verification succeeds → return authenticated principal.
2. `iss` matches + verification fails → raise 401 with `WWW-Authenticate: Bearer realm=…, resource_metadata=<rfc9728-url>`.
3. `iss` does not match, OR bearer is not JWT-shaped → return `None` (defer). No log line, no 401.

#### Scenario: Bearer With Oauth Issuer And Valid Signature Is Accepted

- **GIVEN** OAuth is active and a request presents a JWT whose `iss` equals the resolved OAuth issuer
- **WHEN** the JWT's signature verifies against the JWKS and its other claims are well-formed
- **THEN** the verifier SHALL return an authenticated principal
- **AND** the chain SHALL stop without consulting subsequent backends

#### Scenario: Bearer With Oauth Issuer And Invalid Signature Is Rejected With 401

- **GIVEN** OAuth is active and a request presents a JWT whose `iss` equals the resolved OAuth issuer
- **WHEN** the JWT's signature does not verify
- **THEN** the verifier SHALL raise 401
- **AND** the response SHALL include `WWW-Authenticate: Bearer` with a `resource_metadata=<url>` parameter
- **AND** the chain SHALL NOT consult subsequent backends

#### Scenario: Bearer With Service Account Issuer Is Deferred

- **GIVEN** OAuth is active and a request presents a JWT whose `iss` ends in `/config`
- **WHEN** `OAuthHydrolixAuthProvider` evaluates the bearer
- **THEN** the OAuth verifier SHALL return `None` without raising
- **AND** SHALL emit no log line for the deferral
- **AND** the next backend in the chain SHALL receive the request

#### Scenario: Malformed Bearer Is Deferred

- **GIVEN** OAuth is active and a request presents a bearer value that is not a JWT
- **WHEN** `OAuthHydrolixAuthProvider` evaluates the bearer
- **THEN** the OAuth verifier SHALL return `None` without raising
- **AND** the next backend in the chain SHALL receive the request

### Requirement: JWT Verification Rejects Mismatched Issuer

The verifier enforces a non-conflation invariant: `iss` exact-match makes it structurally impossible for a token with `iss = HYDROLIX_URL` to be claimed (since `canonical_idp_endpoints` guarantees `issuer != HYDROLIX_URL`). The scenarios below make this testable independent of real env state. `OAuthHydrolixAuthProvider` MUST NOT reference `HYDROLIX_URL`.

#### Scenario: Token Uses Cluster Url As Issuer

- **GIVEN** `OAuthConfig.issuer="https://idp.example.com/realms/hydrolix"` and `HYDROLIX_URL="https://cluster.example.com"` (if set)
- **WHEN** a JWT is presented with `iss="https://cluster.example.com"`
- **THEN** the chain rejects the request with 401

#### Scenario: Derived Issuer Differs From Hydrolix Url Conflation Rejected

- **GIVEN** OAuth has activated with issuer derived via `canonical_idp_endpoints(HYDROLIX_URL).issuer`
- **WHEN** a JWT is presented with `iss="https://cluster.example.com"` (matching `HYDROLIX_URL`, not the derived issuer)
- **THEN** the chain rejects the request with 401

### Requirement: JWT Verification Rejects Mismatched Audience

The verifier SHALL reject any JWT whose `aud` claim (normalized to a set) contains no value present in `OAuthConfig.audience`. Matching uses set intersection (see design decision `audience-as-set-intersection`).

#### Scenario: Audience Not In Allowlist

- **GIVEN** `OAuthConfig.audience={"mcp-hydrolix", "config-api"}`
- **WHEN** a JWT is presented with `aud="some-other-service"`
- **THEN** verification SHALL fail with 401

#### Scenario: Second Allowlist Entry Matches

- **GIVEN** `OAuthConfig.audience={"mcp-hydrolix", "config-api"}`
- **WHEN** a JWT is presented with `aud="config-api"`
- **THEN** verification SHALL succeed (other claims permitting)

### Requirement: Required Scopes Enforced When Configured

When `OAuthConfig.required_scopes` is non-empty, the verifier SHALL require every listed scope to appear in `scope` (space-delimited) or `scp` (array). If neither claim is present, the JWT SHALL be rejected. When `required_scopes` is empty, no scope check is performed (see design decision `scope-claim-union`).

#### Scenario: Missing Required Scope

- **GIVEN** `OAuthConfig.required_scopes={"read", "write"}`
- **WHEN** a JWT is presented with `scope="read"` (missing `write`)
- **THEN** verification SHALL fail with 401

#### Scenario: All Required Scopes Present Via Scope Claim

- **GIVEN** `OAuthConfig.required_scopes={"read", "write"}`
- **WHEN** a JWT is presented with `scope="read write"`
- **THEN** verification SHALL succeed (other claims permitting)

#### Scenario: All Required Scopes Present Via Scp Claim

- **GIVEN** `OAuthConfig.required_scopes={"read", "write"}`
- **WHEN** a JWT is presented with `scp=["read", "write"]` and no `scope` claim
- **THEN** verification SHALL succeed (other claims permitting)

### Requirement: Valid Bearer Authenticates The Request End To End

When OAuth is active, a JWT satisfying all of the following SHALL be authenticated and dispatched to the MCP tool layer: `iss` matches `OAuthConfig.issuer`; signature verifies against startup-loaded JWKS; `aud` intersects `OAuthConfig.audience`; `exp` in the future; all `required_scopes` present in `scope` or `scp`. No I/O beyond JWKS key lookup occurs at request time (see design decision `no-io-at-request-time`).

#### Scenario: Well Formed Bearer Reaches The Mcp Tool Layer

- **GIVEN** OAuth is active and JWKS key material has been loaded at startup
- **WHEN** a request presents a JWT where signature verifies, `iss` equals `OAuthConfig.issuer`, `aud` contains a value in `OAuthConfig.audience`, `exp` is in the future, and required scopes (if any) are present
- **THEN** the auth chain SHALL accept the request
- **AND** the MCP tool SHALL be invoked and its response returned
