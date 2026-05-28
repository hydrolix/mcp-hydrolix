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

`OAuthHydrolixAuthProvider` claims any bearer token whose `iss` matches the resolved OAuth issuer. When it claims a token and verification fails, it SHALL raise HTTP 401 with `WWW-Authenticate: Bearer`. The shape of that header (including the `resource_metadata=` parameter pointing at the RFC 9728 metadata endpoint) is owned by `oauth-resource-metadata`; this change does not duplicate or override those requirements. Requests with no `Authorization` header SHALL fall through to the SA credential chain.

#### Scenario: Invalid Bearer After Successful Activation

- **WHEN** OAuth has activated successfully for the worker
- **AND** a request arrives with `Authorization: Bearer <invalid-jwt>` whose `iss` matches the OAuth issuer
- **THEN** `OAuthHydrolixAuthProvider` SHALL claim the bearer and raise 401
- **AND** the response status SHALL be 401
- **AND** the response SHALL include a `WWW-Authenticate: Bearer` header (with the `resource_metadata=` parameter per `oauth-resource-metadata`)

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

### Requirement: Unrecognized Issuer Surfaces As Deployment Warning

When a bearer token reaches the chain whose `iss` matches **neither** `OAuthConfig.issuer` (the configured OAuth IdP) **nor** the canonical service-account `iss` shape (`<HYDROLIX_URL>/config`) — i.e. every backend in the chain has deferred (returned `None`) — the worker SHALL:

1. Reject the request with HTTP 401 (no backend can authenticate it).
2. Emit exactly one **WARNING**-level log line per such request, before returning the 401, identifying this as a likely deployment / IdP-misconfiguration signal rather than an ordinary unauthorized-login attempt. The log line:
   - SHALL include the unverified `iss` value from the JWT (the routing claim, already inspected by the verifier for dispatch).
   - SHALL include the configured `OAuthConfig.issuer` value (so the operator can see the mismatch immediately).
   - SHALL include a short, fixed phrase identifying the failure mode (e.g. `"bearer iss matched no chain backend — likely IdP misconfiguration"`), greppable in log aggregation.
   - SHALL NOT include the raw JWT, the `Authorization` header value, the JWT signature segment, or any base64url-encoded JWT segment (covered by `oauth-log-redaction`'s invariant).

The WARNING level (not ERROR) reflects that the worker still functioned correctly — it rejected an unauthenticatable request — but signals operator attention because the pattern usually means a config drift (wrong IdP URL, stale IdP after rotation, audience renamed, SA issuer suffix changed), not an attacker. The individual backends in the chain (`OAuthHydrolixAuthProvider`, `BearerAuthBackend`, `GetParamAuthBackend`) SHALL remain silent on their own deferrals; the consolidated WARNING is emitted **once**, at the chain boundary where the all-backends-deferred outcome is observable.

#### Scenario: Bearer With Unknown Issuer Yields 401 And WARNING

- **WHEN** OAuth is active with `OAuthConfig.issuer="https://idp.example.com/realms/test"` and `HYDROLIX_URL="https://cluster.example.com"` (so the SA `iss` shape is `https://cluster.example.com/config`)
- **AND** a request arrives with `Authorization: Bearer <jwt>` whose `iss="https://other-idp.example.com/realms/something"` (matches neither the configured OAuth issuer nor the SA `iss` shape)
- **THEN** the response status SHALL be 401
- **AND** the auth layer SHALL emit exactly one WARNING-level log record for this request
- **AND** that log record SHALL contain the unverified `iss` value `"https://other-idp.example.com/realms/something"`
- **AND** that log record SHALL contain the configured `OAuthConfig.issuer` value `"https://idp.example.com/realms/test"`
- **AND** that log record SHALL NOT contain the raw JWT or any of its base64url-encoded segments

#### Scenario: Routine Deferrals Stay Silent

- **WHEN** OAuth is active and a request arrives with a valid SA bearer (`iss` ends in `/config`, signature verifies) — i.e. `OAuthHydrolixAuthProvider` defers but `BearerAuthBackend` claims
- **THEN** no WARNING-level "unrecognized issuer" log record SHALL be emitted
- **AND** the request SHALL be authenticated normally via the SA chain

#### Scenario: Per-Backend Silent Deferral Preserved

- **WHEN** any individual backend in the chain returns `None` (defers) for a given request
- **THEN** that backend SHALL NOT emit a log line for its own deferral
- **AND** any WARNING about an unrecognized issuer SHALL be emitted only by the chain owner after observing that all backends have deferred
