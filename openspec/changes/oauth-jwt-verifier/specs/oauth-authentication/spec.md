*Pure claim validation for OAuth bearer tokens: iss-based routing for chain composability, issuer exact-match, audience allowlist, required scopes, and end-to-end bearer acceptance.*

## ADDED Requirements

### Requirement: OAuth Verifier Claims Bearers By Iss Match

`OAuthHydrolixAuthProvider` SHALL act as a chain-composable backend: it claims a bearer iff the bearer's `iss` claim exactly matches the resolved OAuth issuer URL, and otherwise defers to the next backend in the auth chain. The discriminator is `iss` because Hydrolix service-account bearer tokens are also JWTs (different `iss`, EdDSA, different signing-key source) and share the `Authorization: Bearer` header; shape-based detection would route SA bearers to the OAuth verifier and break SA auth.

The provider SHALL peek the `iss` claim without verifying the signature — purely for routing. Full signature/audience/expiry/scope verification still gates every success path, so the unverified peek is not a security gap.

Three return modes:
1. Bearer with `iss` matching OAuth issuer + verification succeeds → return authenticated principal.
2. Bearer with `iss` matching OAuth issuer + verification fails (bad sig, bad aud, expired, missing scope, etc.) → raise 401 with `WWW-Authenticate: Bearer realm=…, resource_metadata=<rfc9728-url>` header.
3. Bearer with `iss` not matching OAuth issuer, OR bearer malformed (not JWT-shaped, base64 decode fails, no `iss` claim) → return `None` (defer to next backend in the chain). No log line, no 401.

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

- **GIVEN** OAuth is active and a request presents a JWT whose `iss` ends in `/config` (the canonical service-account issuer suffix)
- **WHEN** `OAuthHydrolixAuthProvider` evaluates the bearer
- **THEN** the OAuth verifier SHALL return `None` without raising
- **AND** SHALL emit no log line for the deferral
- **AND** the next backend in the chain SHALL receive the request

#### Scenario: Malformed Bearer Is Deferred

- **GIVEN** OAuth is active and a request presents an `Authorization: Bearer …` value that is not a JWT (fewer than 3 base64url-separated parts, base64 decode fails, or no `iss` claim parsable)
- **WHEN** `OAuthHydrolixAuthProvider` evaluates the bearer
- **THEN** the OAuth verifier SHALL return `None` without raising
- **AND** the next backend in the chain SHALL receive the request

### Requirement: JWT Verification Rejects Mismatched Issuer

When the OAuth verifier has claimed a bearer (its `iss` matches the resolved OAuth issuer — see "OAuth Verifier Claims Bearers By Iss Match"), the verifier enforces a **non-conflation invariant**: the resolved OAuth issuer URL SHALL NEVER equal `HYDROLIX_URL` (the cluster public URL), enforced upstream by `canonical_idp_endpoints` (specified in `oauth-config-and-preflight`) and independently re-asserted at the verifier layer by the `iss` exact-match check.

This requirement's effective scope is the non-conflation guarantee. The verifier's issuer exact-match is the enforcement mechanism: it is structurally impossible for `iss = HYDROLIX_URL` to satisfy the routing predicate (since `canonical_idp_endpoints` guarantees `issuer != hydrolix_url`), but the scenarios below make this invariant explicit and testable independent of real `HYDROLIX_URL` env state.

#### Scenario: Token Uses Cluster Url As Issuer

- **GIVEN** `OAuthConfig.issuer="https://idp.example.com/realms/hydrolix"` and `HYDROLIX_URL="https://cluster.example.com"` (if set)
- **WHEN** a JWT is presented with `iss="https://cluster.example.com"`
- **THEN** the chain rejects the request with 401 (the OAuth verifier defers because the conflated `iss` does not match the resolved OAuth issuer, and no other backend claims it)

#### Scenario: Derived Issuer Differs From Hydrolix Url Conflation Rejected

- **GIVEN** `HYDROLIX_OAUTH_ISSUER` is unset and `HYDROLIX_URL="https://cluster.example.com"` is set
- **AND** OAuth has activated with the resolved issuer derived via `canonical_idp_endpoints(HYDROLIX_URL).issuer`
- **WHEN** a JWT is presented with `iss="https://cluster.example.com"` (matching `HYDROLIX_URL`, not the derived issuer)
- **THEN** the chain rejects the request with 401 (the OAuth verifier defers because the conflated `iss` does not match the resolved OAuth issuer, and no other backend claims it)

### Requirement: JWT Verification Rejects Mismatched Audience

The OAuth verifier SHALL reject any JWT whose `aud` claim, when normalized to a set, contains no value present in the configured audience allowlist (`OAuthConfig.audience`, parsed from `HYDROLIX_OAUTH_AUDIENCE` by `oauth-config-and-preflight`). Matching uses set intersection: a JWT is accepted when any one value in its `aud` set is present in the allowlist (see design decision `audience-as-set-intersection`).

#### Scenario: Audience Not In Allowlist

- **GIVEN** `OAuthConfig.audience={"mcp-hydrolix", "config-api"}` (parsed from `HYDROLIX_OAUTH_AUDIENCE="mcp-hydrolix,config-api"`)
- **WHEN** a JWT is presented with `aud="some-other-service"`
- **THEN** verification SHALL fail with 401

#### Scenario: Second Allowlist Entry Matches

- **GIVEN** `OAuthConfig.audience={"mcp-hydrolix", "config-api"}`
- **WHEN** a JWT is presented with `aud="config-api"`
- **THEN** verification SHALL succeed (other claims permitting)

### Requirement: Required Scopes Enforced When Configured

When `OAuthConfig.required_scopes` is non-empty (parsed from `HYDROLIX_OAUTH_REQUIRED_SCOPES` by `oauth-config-and-preflight`), the verifier SHALL require the JWT's `scope` (space-delimited string) or `scp` (array) claim to include every listed scope. If neither claim is present, the JWT SHALL be rejected. When `OAuthConfig.required_scopes` is empty, no scope check is performed (see design decision `scope-claim-union`).

#### Scenario: Missing Required Scope

- **GIVEN** `OAuthConfig.required_scopes={"read", "write"}` (parsed from `HYDROLIX_OAUTH_REQUIRED_SCOPES="read,write"`)
- **WHEN** a JWT is presented with `scope="read"` (missing `write`)
- **THEN** verification SHALL fail with 401

#### Scenario: All Required Scopes Present Via Scope Claim

- **GIVEN** `OAuthConfig.required_scopes={"read", "write"}`
- **WHEN** a JWT is presented with `scope="read write"` (both scopes present as space-delimited string)
- **THEN** verification SHALL succeed (other claims permitting)

#### Scenario: All Required Scopes Present Via Scp Claim

- **GIVEN** `OAuthConfig.required_scopes={"read", "write"}`
- **WHEN** a JWT is presented with `scp=["read", "write"]` and no `scope` claim
- **THEN** verification SHALL succeed (other claims permitting)

### Requirement: Valid Bearer Authenticates The Request End To End

When OAuth is active, a request presenting an `Authorization: Bearer <jwt>` header with a JWT that satisfies all of the following SHALL be authenticated and dispatched to the MCP tool layer with no further bearer-related rejection from the auth chain:

- `iss` exactly matches `OAuthConfig.issuer` (routing predicate satisfied; OAuth verifier claims the bearer).
- Signature verifies against the JWKS key material loaded at startup.
- `aud` intersects `OAuthConfig.audience`.
- `exp` is in the future (within allowed clock skew).
- All scopes in `OAuthConfig.required_scopes` are present in `scope` or `scp` (when `required_scopes` is non-empty).

No I/O beyond JWKS key lookup occurs at request time (see design decision `no-io-at-request-time`).

#### Scenario: Well Formed Bearer Reaches The Mcp Tool Layer

- **GIVEN** OAuth is active and JWKS key material has been loaded at startup
- **WHEN** a request to an MCP tool endpoint presents an `Authorization: Bearer <jwt>` header
- **AND** the JWT signature verifies against the loaded JWKS key material
- **AND** `iss` equals `OAuthConfig.issuer`, `aud` contains a value in `OAuthConfig.audience`, `exp` is in the future, and required scopes (if any) are present in `scope` or `scp`
- **THEN** the auth chain SHALL accept the request
- **AND** the MCP tool SHALL be invoked and its response returned with the appropriate HTTP status
