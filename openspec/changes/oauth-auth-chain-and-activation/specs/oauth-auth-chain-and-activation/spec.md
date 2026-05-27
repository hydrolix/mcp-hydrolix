*Per-worker auth chain that enforces OAuth bearer validation fail-closed and routes bearer-less requests to the SA credential path.*

## ADDED Requirements

### Requirement: Activation Runs Per Uvicorn Worker

Workers re-import `webapp.py` under uvicorn's spawn-based multiprocessing, so the `mcp` singleton lives only in each worker's own address space. OAuth activation SHALL therefore happen inside `webapp.py:create_app()`, once per worker process, before `mcp.http_app(...)` is called. (The implementation site is fixed by the design; see "Activation Site Is `webapp.py:create_app()`".) Each uvicorn worker SHALL independently run OIDC discovery and JWKS preflight against its own in-process `mcp` instance. The supervisor process SHALL NOT mutate `mcp.auth` before workers spawn. This architecture was established by [HDX-10675](https://hydrolix.atlassian.net/browse/HDX-10675) (the gunicorn → uvicorn migration).

#### Scenario: Multi-Worker Activation

- **WHEN** the server is started with `MCP_WORKERS=4` and OAuth env vars set
- **THEN** each of the 4 worker processes SHALL successfully activate OAuth against its own in-process `mcp` object
- **AND** no worker SHALL serve requests with `mcp.auth` set to the pre-activation credential chain
- **AND** the supervisor process SHALL NOT mutate `mcp.auth` before workers spawn

### Requirement: Auth Chain Is Flat

`ChainedAuthBackend` exists at `mcp_hydrolix/auth/mcp_providers.py` with unchanged semantics: first non-None result wins; a raised exception propagates. The new capability introduced here is the *composition* when OAuth is active — one extra element prepended. The resulting chain SHALL always be a single flat `ChainedAuthBackend`; nesting SHALL NOT be used.

When OAuth is active, the worker SHALL install `mcp.auth` as a single flat `ChainedAuthBackend` whose ordered backend list is exactly `[OAuthHydrolixAuthProvider, BearerAuthBackend(service_account), GetParamAuthBackend(service_account, TOKEN_PARAM)]`. The chain SHALL NOT be nested — there SHALL NOT be an outer `ChainedAuthBackend` wrapping an inner `ChainedAuthBackend`. When OAuth is not active, `mcp.auth` SHALL be the existing two-element chain `[BearerAuthBackend(service_account), GetParamAuthBackend(service_account, TOKEN_PARAM)]`.

#### Scenario: Chain Has Three Backends When Oauth Is Active

- **WHEN** OAuth is active and the worker has finished factory initialization
- **THEN** `mcp.auth` SHALL be a `ChainedAuthBackend` instance
- **AND** its `backends` list SHALL have exactly three elements in the order `[OAuthHydrolixAuthProvider, BearerAuthBackend, GetParamAuthBackend]`

#### Scenario: Chain Has Two Backends When Oauth Is Inactive

- **WHEN** OAuth is not active and the worker has finished factory initialization
- **THEN** `mcp.auth` SHALL be a `ChainedAuthBackend` with exactly two elements `[BearerAuthBackend, GetParamAuthBackend]` (the pre-OAuth shape preserved)

#### Scenario: Chain Is Not Nested

- **WHEN** the auth chain is constructed (whether OAuth is active or inactive)
- **THEN** no element of the `backends` list SHALL itself be a `ChainedAuthBackend`

### Requirement: Active Verifier Is Fail-Closed

Once OAuth is successfully activated for a worker, `OAuthHydrolixAuthProvider` claims any bearer token whose `iss` matches the resolved OAuth issuer. When it claims a token and verification fails, it SHALL raise HTTP 401 with an RFC 6750 `WWW-Authenticate: Bearer` challenge and the RFC 9728 `resource_metadata=` header. Requests presenting no `Authorization` header SHALL fall through to the service-account credential chain (see "SA Credential Fallback Preserved"), not 401.

#### Scenario: Invalid Bearer After Successful Activation

- **WHEN** OAuth has activated successfully for the worker
- **AND** a request arrives with `Authorization: Bearer <invalid-jwt>` whose `iss` matches the OAuth issuer
- **THEN** `OAuthHydrolixAuthProvider` SHALL claim the bearer and raise 401
- **AND** the response status SHALL be 401
- **AND** the response SHALL include a `WWW-Authenticate: Bearer` header

#### Scenario: Missing Bearer After Successful Activation Internal SA Path

- **WHEN** OAuth has activated successfully for the worker
- **AND** a request arrives with no `Authorization` header but valid SA credentials in the configured location
- **THEN** the chained credential backend SHALL accept the request via the SA path

### Requirement: SA Credential Fallback Preserved

When OAuth is active, requests that present no `Authorization: Bearer` header SHALL be routed through the existing service-account credential chain. Because `OAuthHydrolixAuthProvider` defers (returns `None`) when the bearer's `iss` does not match the OAuth issuer, SA bearer JWTs (whose `iss` ends in `/config`) are correctly deferred to `BearerAuthBackend` in the same flat chain. An invalid bearer token whose `iss` matches the OAuth issuer SHALL result in immediate 401 rejection; the SA chain SHALL NEVER be consulted as a fallback for a bearer that the OAuth verifier has claimed.

#### Scenario: No Bearer SA Credential Present

- **WHEN** OAuth is active and a request arrives with no `Authorization` header but valid SA credentials in the configured location
- **THEN** the request SHALL be authenticated via the SA chain
- **AND** the request SHALL succeed if the SA chain accepts the credential

#### Scenario: Bearer Present OAuth Verifier Fails

- **WHEN** OAuth is active and a request arrives with an invalid `Authorization: Bearer <jwt>` whose `iss` matches the OAuth issuer
- **THEN** `OAuthHydrolixAuthProvider` SHALL claim the bearer and raise 401
- **AND** the SA chain SHALL NOT be consulted as a fallback for that request

#### Scenario: Sa Bearer Jwt Is Authenticated By Bearer Auth Backend When Oauth Is Active

- **WHEN** OAuth is active and a request arrives with `Authorization: Bearer <sa-jwt>` where the SA JWT's `iss` ends in `/config` (the canonical service-account issuer suffix) and the SA JWT's signature verifies against the service-account public key
- **THEN** `OAuthHydrolixAuthProvider` SHALL return `None` (defer; see oauth-jwt-verifier's "OAuth Verifier Claims Bearers By Iss Match")
- **AND** `BearerAuthBackend` SHALL authenticate the request
- **AND** the chain SHALL stop after `BearerAuthBackend` succeeds
