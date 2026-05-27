*Per-worker auth chain that enforces OAuth bearer validation fail-closed and routes bearer-less requests to the SA credential chain.*

## ADDED Requirements

### Requirement: Activation Runs Per Uvicorn Worker

OAuth activation SHALL happen inside `webapp.py:create_app()`, once per worker process, before `mcp.http_app(...)` is called. Each uvicorn worker SHALL independently run OIDC discovery and JWKS preflight against its own in-process `mcp` instance. The supervisor process SHALL NOT mutate `mcp.auth` before workers spawn.

#### Scenario: Multi-Worker Activation

- **WHEN** `create_app()` is called twice sequentially in the same test process with `HYDROLIX_OAUTH_AUDIENCE="mcp-test"` and `HYDROLIX_OAUTH_ISSUER="https://idp.example.com/realms/test"` set, and OIDC discovery is mocked to succeed
- **THEN** each call returns an app whose `mcp.auth` is a `ChainedAuthBackend` with `OAuthHydrolixAuthProvider` as the first element of its `backends` list

### Requirement: Auth Chain Is Flat

When OAuth is active, the worker SHALL install `mcp.auth` as a single flat `ChainedAuthBackend` with backends `[OAuthHydrolixAuthProvider, BearerAuthBackend(service_account), GetParamAuthBackend(service_account, TOKEN_PARAM)]`. The chain SHALL NOT be nested. When OAuth is not active, `mcp.auth` SHALL be the existing two-element chain `[BearerAuthBackend(service_account), GetParamAuthBackend(service_account, TOKEN_PARAM)]`.

#### Scenario: Chain Has Three Backends When OAuth Is Active

- **WHEN** OAuth is active and the worker has finished factory initialization
- **THEN** `mcp.auth` SHALL be a `ChainedAuthBackend` instance
- **AND** its `backends` list SHALL have exactly three elements in the order `[OAuthHydrolixAuthProvider, BearerAuthBackend, GetParamAuthBackend]`

#### Scenario: Chain Has Two Backends When OAuth Is Inactive

- **WHEN** OAuth is not active and the worker has finished factory initialization
- **THEN** `mcp.auth` SHALL be a `ChainedAuthBackend` with exactly two elements `[BearerAuthBackend, GetParamAuthBackend]` (the pre-OAuth shape preserved)

#### Scenario: Chain Is Not Nested

- **WHEN** the auth chain is constructed (whether OAuth is active or inactive)
- **THEN** no element of the `backends` list SHALL itself be a `ChainedAuthBackend`

### Requirement: Active Verifier Is Fail-Closed

`OAuthHydrolixAuthProvider` claims any bearer token whose `iss` matches the resolved OAuth issuer. When it claims a token and verification fails, it SHALL raise HTTP 401 with `WWW-Authenticate: Bearer`. Requests with no `Authorization` header SHALL fall through to the SA credential chain.

#### Scenario: Invalid Bearer After Successful Activation

- **WHEN** OAuth has activated successfully for the worker
- **AND** a request arrives with `Authorization: Bearer <invalid-jwt>` whose `iss` matches the OAuth issuer
- **THEN** `OAuthHydrolixAuthProvider` SHALL claim the bearer and raise 401
- **AND** the response status SHALL be 401
- **AND** the response SHALL include a `WWW-Authenticate: Bearer` header

#### Scenario: Missing Bearer After Successful Activation Internal SA Path

- **WHEN** OAuth has activated successfully for the worker
- **AND** `HYDROLIX_SERVICE_ACCOUNT_TOKEN` is set to a valid SA JWT
- **AND** a request arrives with no `Authorization` header but valid SA credentials in the configured location
- **THEN** the chained credential backend SHALL accept the request via the SA path

### Requirement: SA Credential Fallback Preserved

When OAuth is active, requests with no `Authorization: Bearer` header SHALL be routed through the SA credential chain. `OAuthHydrolixAuthProvider` returns `None` when the bearer's `iss` does not match the OAuth issuer, so SA bearer JWTs are deferred to `BearerAuthBackend`. A bearer claimed by the OAuth verifier that fails validation SHALL result in immediate 401; the SA credential chain SHALL NOT be consulted as a fallback.

#### Scenario: No Bearer SA Credential Present

- **WHEN** OAuth is active, `HYDROLIX_SERVICE_ACCOUNT_TOKEN` is set to a valid SA JWT, and a request arrives with no `Authorization` header
- **THEN** the request SHALL be authenticated via the SA credential chain
- **AND** the request SHALL succeed if the SA credential chain accepts the credential

#### Scenario: Bearer Present OAuth Verifier Fails

- **WHEN** OAuth is active and a request arrives with an invalid `Authorization: Bearer <jwt>` whose `iss` matches the OAuth issuer
- **THEN** `OAuthHydrolixAuthProvider` SHALL claim the bearer and raise 401
- **AND** the SA credential chain SHALL NOT be consulted as a fallback for that request

#### Scenario: SA Bearer JWT Is Authenticated By Bearer Auth Backend When OAuth Is Active

- **WHEN** OAuth is active and a request arrives with `Authorization: Bearer <sa-jwt>` where the SA JWT's `iss` ends in `/config` (the canonical service-account issuer suffix) and the SA JWT's signature verifies against the service-account public key
- **THEN** `OAuthHydrolixAuthProvider` SHALL return `None` (the SA JWT's iss does not match OAuthConfig.issuer, so OAuthHydrolixAuthProvider returns None without raising)
- **AND** `BearerAuthBackend` SHALL authenticate the request
- **AND** the chain SHALL stop after `BearerAuthBackend` succeeds
