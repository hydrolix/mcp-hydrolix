## ADDED Requirements

### Requirement: Activation gated on operator env vars

The server SHALL activate OAuth bearer authentication for the HTTP and SSE transports if and only if `HYDROLIX_OAUTH_AUDIENCE` is set to a non-empty value AND a usable issuer is resolvable. The issuer is resolved with the following precedence:

1. `HYDROLIX_OAUTH_ISSUER` if set to a non-empty value (explicit operator override).
2. Otherwise, if `HYDROLIX_URL` is set to a non-empty value, the issuer is derived from it via the canonical IdP-derivation function (see "Canonical IdP endpoint derivation" requirement below).
3. Otherwise, the issuer is unresolved and OAuth is not activated.

When OAuth is not activated AND no partial configuration is present (i.e., none of `HYDROLIX_OAUTH_*` env vars are set), the server SHALL behave byte-identically to a build without OAuth code: no new endpoints exposed, no `WWW-Authenticate` headers emitted, no OAuth-related log lines emitted, and the existing service-account credential chain SHALL handle all requests.

Partial configuration — `HYDROLIX_OAUTH_AUDIENCE` set with no resolvable issuer, or `HYDROLIX_OAUTH_ISSUER` set with no `HYDROLIX_OAUTH_AUDIENCE` — is a fatal startup error: the server SHALL raise `OAuthConfigError`. This case is explicitly NOT covered by the byte-identical guarantee.

#### Scenario: No issuer and no cluster URL

- **WHEN** the server starts the HTTP transport with neither `HYDROLIX_OAUTH_ISSUER` nor `HYDROLIX_URL` set
- **AND** `HYDROLIX_OAUTH_AUDIENCE` is also unset
- **THEN** the server SHALL NOT emit any log line containing the substring `OAuth`
- **AND** requests to `/.well-known/oauth-protected-resource` SHALL return 404
- **AND** requests to MCP tool endpoints with no bearer token SHALL behave exactly as on a build with no OAuth code

#### Scenario: Audience set but no issuer resolvable

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` is set
- **AND** neither `HYDROLIX_OAUTH_ISSUER` nor `HYDROLIX_URL` is set
- **THEN** the worker SHALL raise `OAuthConfigError` during factory initialization
- **AND** SHALL terminate before handling any request
- **AND** under multi-worker uvicorn the supervisor port-binding remains intact, but workers crash-loop on respawn and SHALL NOT successfully serve MCP traffic while the misconfiguration persists

#### Scenario: Issuer derived from cluster URL

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_URL` are both set
- **AND** `HYDROLIX_OAUTH_ISSUER` is unset
- **THEN** the server SHALL resolve the issuer via the canonical IdP-derivation function
- **AND** OAuth SHALL activate using the derived issuer

#### Scenario: Explicit issuer overrides derivation

- **WHEN** `HYDROLIX_OAUTH_ISSUER`, `HYDROLIX_OAUTH_AUDIENCE`, and `HYDROLIX_URL` are all set
- **AND** the explicit `HYDROLIX_OAUTH_ISSUER` differs from the value that would be derived from `HYDROLIX_URL`
- **THEN** the server SHALL use the explicit `HYDROLIX_OAUTH_ISSUER` value
- **AND** SHALL NOT raise a startup error for the mismatch

#### Scenario: Issuer set but audience unset

- **WHEN** `HYDROLIX_OAUTH_ISSUER` is set but `HYDROLIX_OAUTH_AUDIENCE` is unset
- **THEN** the worker SHALL raise `OAuthConfigError` during factory initialization
- **AND** SHALL terminate before handling any request
- **AND** under multi-worker uvicorn the supervisor port-binding remains intact, but workers crash-loop on respawn and SHALL NOT successfully serve MCP traffic while the misconfiguration persists

### Requirement: Canonical IdP endpoint derivation is a single contained function

All knowledge of where the cluster's canonical IdP lives relative to `HYDROLIX_URL` SHALL be encapsulated in a single function that takes the cluster URL and returns an immutable record containing at least the issuer URL, the OIDC discovery URL, the JWKS URI, and the network-reachable address of the IdP. No other code in `mcp_hydrolix/auth/` SHALL encode the cluster-URL-to-IdP convention; any callsite that needs an IdP endpoint derived from `HYDROLIX_URL` SHALL call this function. The function SHALL NEVER return an `issuer` string-equal to its input `hydrolix_url` (this preserves the issuer/cluster-URL non-conflation invariant; see "JWT verification rejects mismatched issuer").

#### Scenario: Exactly one derivation callsite

- **WHEN** a CI test imports every submodule under `mcp_hydrolix.auth` and collects all callsites that read `HYDROLIX_URL` or its parsed form to compute an IdP issuer, discovery URL, JWKS URI, or address
- **THEN** every such callsite SHALL delegate to a single named function exported from `mcp_hydrolix.auth.idp_endpoints`
- **AND** that function SHALL return a record containing at minimum: issuer URL, OIDC discovery URL, JWKS URI, and IdP network address

#### Scenario: Derivation result is immutable

- **WHEN** the derivation function is called with a `HYDROLIX_URL` value
- **THEN** the returned record SHALL be frozen (no mutable fields)
- **AND** calling the function twice with the same input SHALL return equal records

#### Scenario: Derived issuer is never equal to the input cluster URL

- **WHEN** the derivation function is called with any non-empty `HYDROLIX_URL` value
- **THEN** the returned `issuer` SHALL NOT be string-equal to the input `HYDROLIX_URL`

### Requirement: Activation runs per uvicorn worker

The server SHALL perform OAuth activation inside the `webapp.py:create_app()` factory, not in the supervisor process. Each uvicorn worker SHALL independently run OIDC discovery and JWKS preflight against its own `mcp` instance.

#### Scenario: Multi-worker activation

- **WHEN** the server is started with `MCP_WORKERS=4` and OAuth env vars set
- **THEN** each of the 4 worker processes SHALL successfully activate OAuth against its own in-process `mcp` object
- **AND** no worker SHALL serve requests with `mcp.auth` set to the pre-activation credential chain
- **AND** the supervisor process SHALL NOT call `try_activate_oauth`

### Requirement: Fail-open at startup, fail-closed at request time

If OIDC discovery or JWKS preflight fails at startup (network error, non-2xx HTTP, malformed JSON, missing `jwks_uri`), the worker SHALL emit a single WARNING log line and continue serving with the credential chain only — OAuth SHALL NOT be activated for that worker. Once OAuth is successfully activated for a worker, all subsequent invalid bearer tokens on authenticated endpoints SHALL be rejected with HTTP 401 and an RFC 6750 `WWW-Authenticate: Bearer` challenge. Requests presenting no `Authorization` header SHALL fall through to the service-account credential chain (see "SA credential fallback preserved"), not 401.

#### Scenario: Discovery network failure at startup

- **WHEN** the OIDC discovery endpoint is unreachable at worker startup
- **THEN** the worker SHALL log exactly one WARNING line containing `OAuth configured but not activated` and the network failure class name
- **AND** the worker SHALL continue serving with `mcp.auth` set to the credential chain
- **AND** SHALL NOT raise an exception at startup

#### Scenario: Invalid bearer after successful activation

- **WHEN** OAuth has activated successfully for the worker
- **AND** a request arrives with `Authorization: Bearer <invalid-jwt>`
- **THEN** the response status SHALL be 401
- **AND** the response SHALL include a `WWW-Authenticate: Bearer` header

#### Scenario: Missing bearer after successful activation, internal SA path

- **WHEN** OAuth has activated successfully for the worker
- **AND** a request arrives with no `Authorization` header but valid SA credentials in the configured location
- **THEN** the chained credential backend SHALL accept the request via the SA path

### Requirement: JWT verification rejects mismatched issuer

The OAuth verifier SHALL reject any JWT whose `iss` claim does not exactly match the **resolved issuer URL** — the value held in `OAuthConfig.issuer` after the precedence chain defined in "Activation gated on operator env vars" is applied (explicit `HYDROLIX_OAUTH_ISSUER`, else `canonical_idp_endpoints(HYDROLIX_URL).issuer`). The cluster public URL (`HYDROLIX_URL`, from HDX-11441) and the OAuth issuer URL are distinct concepts and SHALL NOT be conflated: a token presenting `iss=<HYDROLIX_URL>` SHALL be rejected unless the resolved issuer happens to equal that value, which the canonical IdP derivation function SHALL NOT produce (see "Canonical IdP endpoint derivation" requirement).

#### Scenario: Token issued by attacker matches signing key but wrong issuer

- **WHEN** a JWT is signed with the correct JWKS-published key but carries `iss="https://attacker.example.com/"`
- **THEN** verification SHALL fail
- **AND** the response SHALL be 401

#### Scenario: Token uses cluster URL as issuer

- **WHEN** `HYDROLIX_OAUTH_ISSUER="https://idp.example.com/realms/hydrolix"` and `HYDROLIX_URL="https://cluster.example.com"`
- **AND** a JWT is presented with `iss="https://cluster.example.com"`
- **THEN** verification SHALL fail with 401, even if all other claims are well-formed

#### Scenario: Derived issuer differs from HYDROLIX_URL, conflation rejected

- **WHEN** `HYDROLIX_OAUTH_ISSUER` is unset and `HYDROLIX_URL="https://cluster.example.com"` is set
- **AND** OAuth has activated with the resolved issuer derived via `canonical_idp_endpoints(HYDROLIX_URL).issuer`
- **AND** a JWT is presented with `iss="https://cluster.example.com"` (matching `HYDROLIX_URL`, not the derived issuer)
- **THEN** verification SHALL fail with 401

### Requirement: JWT verification rejects mismatched audience

The OAuth verifier SHALL reject any JWT whose `aud` claim, when normalized to a set, contains no value present in the configured audience allowlist parsed from `HYDROLIX_OAUTH_AUDIENCE`.

#### Scenario: Audience not in allowlist

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE="mcp-hydrolix,config-api"`
- **AND** a JWT is presented with `aud="some-other-service"`
- **THEN** verification SHALL fail with 401

#### Scenario: Second allowlist entry matches

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE="mcp-hydrolix,config-api"`
- **AND** a JWT is presented with `aud="config-api"`
- **THEN** verification SHALL succeed (other claims permitting)

### Requirement: Required scopes enforced when configured

When `HYDROLIX_OAUTH_REQUIRED_SCOPES` is set, the verifier SHALL require the JWT's `scope` (space-delimited) or `scp` claim to include every listed scope.

#### Scenario: Missing required scope

- **WHEN** `HYDROLIX_OAUTH_REQUIRED_SCOPES="read,write"`
- **AND** a JWT is presented with `scope="read"`
- **THEN** verification SHALL fail with 401

### Requirement: RFC 9728 protected-resource-metadata endpoint

When OAuth is active, the server SHALL expose `/.well-known/oauth-protected-resource` returning a JSON document conforming to RFC 9728, advertising the resource URL, configured issuer, and supported bearer methods. This endpoint SHALL NOT require authentication.

#### Scenario: Metadata endpoint returns RFC 9728 JSON

- **WHEN** OAuth is active and an unauthenticated GET request reaches `/.well-known/oauth-protected-resource`
- **THEN** the response status SHALL be 200
- **AND** the response body SHALL be JSON containing `resource`, `authorization_servers`, and `bearer_methods_supported` keys
- **AND** the `authorization_servers` array SHALL contain the resolved issuer URL (the value of `OAuthConfig.issuer` after precedence resolution)

#### Scenario: 401 references metadata URL

- **WHEN** a request to an authenticated endpoint is rejected with 401
- **THEN** the `WWW-Authenticate` header SHALL include a `resource_metadata=<url>` parameter pointing to the protected-resource-metadata URL

### Requirement: JWKS URI override and insecure transport flag

The verifier SHALL accept an explicit `HYDROLIX_OAUTH_JWKS_URI` override for in-cluster deployments where the public discovery URL is not reachable from the pod. By default the verifier SHALL reject any JWKS URI whose scheme is `http`. When `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS=true` is set, the verifier SHALL accept `http://` JWKS URIs to support cluster-internal backchannel calls.

#### Scenario: Plain HTTP JWKS rejected by default

- **WHEN** `HYDROLIX_OAUTH_JWKS_URI="http://idp.internal/realms/x/protocol/openid-connect/certs"` is set
- **AND** `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS` is unset
- **THEN** `load_oauth_config()` SHALL raise `OAuthConfigError` at startup

#### Scenario: Plain HTTP JWKS allowed when explicitly opted in

- **WHEN** `HYDROLIX_OAUTH_JWKS_URI="http://idp.internal/.../certs"` is set
- **AND** `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS="true"` is set
- **THEN** the verifier SHALL fetch keys from that URL at startup

### Requirement: No raw JWT or claim payload in logs

Across `mcp_hydrolix/auth/oauth.py`, `mcp_hydrolix/auth/mcp_providers.py`, `mcp_hydrolix/mcp_server.py`, and `mcp_hydrolix/webapp.py`, no `logger.*` call SHALL emit a raw JWT, a full claims dict, an `Authorization` header value, or a JWKS private exponent. Identifying values that MAY be logged are: `iss` (URL), `aud` (allowlist values from config), `sub` (subject), `client_id`, configured `required_scopes`, HTTP method, HTTP path, and exception class names. Failure paths SHALL log only the exception class name, never the exception message if that message could include token bytes.

#### Scenario: Successful activation log content

- **WHEN** OAuth activates successfully at startup
- **THEN** the INFO log line MAY include `issuer`, `audience`, and `required_scopes`
- **AND** SHALL NOT include any value derived from a JWT

#### Scenario: SA token rejection log content

- **WHEN** the SA credential chain rejects a token
- **THEN** the DEBUG log line SHALL include only the exception class name
- **AND** SHALL NOT include the token, any claim value, or the exception message

### Requirement: Default audience allowlist

When `HYDROLIX_OAUTH_AUDIENCE` is parsed, the documented and tested default the operator is expected to configure SHALL be `mcp-hydrolix,config-api`. The default SHALL be documented in `docs/oauth.md`.

#### Scenario: Documented default

- **WHEN** the operator follows `docs/oauth.md` to register the OIDC client at the cluster-deployed IdP proxy
- **THEN** the documented `HYDROLIX_OAUTH_AUDIENCE` value SHALL be `mcp-hydrolix,config-api`

### Requirement: Valid bearer authenticates the request end-to-end

When OAuth is active, a request presenting an `Authorization: Bearer <jwt>` header with a JWT whose signature verifies against the JWKS, whose `iss` matches the resolved issuer URL, whose `aud` matches at least one configured audience value, whose `exp` is in the future, and (if `HYDROLIX_OAUTH_REQUIRED_SCOPES` is configured) whose scope claim covers all required scopes SHALL be authenticated and dispatched to the MCP tool layer, with no further bearer-related rejection emitted by the auth chain.

#### Scenario: Well-formed bearer reaches the MCP tool layer

- **WHEN** OAuth is active and a request to an MCP tool endpoint presents an `Authorization: Bearer <jwt>` header
- **AND** the JWT signature verifies against the JWKS
- **AND** `iss` equals the resolved issuer URL, `aud` contains a value in the configured allowlist, `exp` is in the future, and required scopes (if any) are present
- **THEN** the auth chain SHALL accept the request
- **AND** the MCP tool SHALL be invoked and its response returned with the appropriate HTTP status

### Requirement: Security checklist sign-off is reproduced in-tree

The 16-row security checklist from the HDX-11133 plan doc (`oauth-support-hdx-11133.md`, section 4) SHALL be reproduced verbatim in `docs/oauth.md` under a "Security checklist (HDX-11133 section 4)" heading before this change merges. Each row SHALL be annotated with one of:

- **Signed off** with a one-line justification (a code reference, test path, or rationale).
- **Carved out** with the issue or ticket tracking the residual work, and a brief reason the carve-out is acceptable for this PR.

If the original plan doc cannot be located, the absence SHALL be documented in `docs/oauth.md` and the missing rows SHALL be treated as carve-outs requiring follow-up tickets before the OAuth feature is enabled in any production environment.

#### Scenario: Checklist present and annotated

- **WHEN** a reviewer opens `docs/oauth.md` on this branch
- **THEN** a section titled `Security checklist (HDX-11133 section 4)` SHALL be present
- **AND** that section SHALL contain at least 16 rows OR a documented account of why fewer rows are reproduced
- **AND** each row SHALL carry either a "Signed off" annotation with one-line justification OR a "Carved out" annotation referencing a follow-up ticket

### Requirement: SA credential fallback preserved

When OAuth is active, requests that present no `Authorization: Bearer` header SHALL be routed through the existing service-account credential chain. The OAuth verifier and the SA chain SHALL be composed in that order; only after the OAuth verifier explicitly returns "no bearer present" SHALL the SA chain be consulted.

#### Scenario: No bearer, SA credential present

- **WHEN** OAuth is active and a request arrives with no `Authorization` header but valid SA credentials in the configured location
- **THEN** the request SHALL be authenticated via the SA chain
- **AND** the request SHALL succeed if the SA chain accepts the credential

#### Scenario: Bearer present, OAuth verifier fails

- **WHEN** OAuth is active and a request arrives with an invalid `Authorization: Bearer <jwt>`
- **THEN** the request SHALL be rejected with 401
- **AND** the SA chain SHALL NOT be consulted as a fallback for that request
