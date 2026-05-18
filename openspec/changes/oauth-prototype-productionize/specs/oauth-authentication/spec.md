## ADDED Requirements

### Requirement: Activation gated on operator env vars

The server SHALL activate OAuth bearer authentication for the HTTP and SSE transports if and only if `HYDROLIX_OAUTH_AUDIENCE` is set to a non-empty value AND a usable issuer is resolvable. The issuer is resolved with the following precedence:

1. `HYDROLIX_OAUTH_ISSUER` if set to a non-empty value (explicit operator override).
2. Otherwise, if `HYDROLIX_URL` is set to a non-empty value, the issuer is derived from it via the canonical IdP-derivation function (see "Canonical IdP endpoint derivation" requirement below).
3. Otherwise, the issuer is unresolved and OAuth is not activated.

When OAuth is not activated AND no partial configuration is present (defined below), the server SHALL behave byte-identically to a build without OAuth code: no new endpoints exposed, no `WWW-Authenticate` headers emitted, no OAuth-related log lines emitted, and the existing service-account credential chain SHALL handle all requests. The byte-identical guarantee is independent of `HYDROLIX_URL` state — that variable belongs to HDX-11441 and has uses other than OAuth, so its presence alone is NOT a signal of OAuth intent.

**Partial configuration** is any of the following:
- `HYDROLIX_OAUTH_AUDIENCE` is set but no issuer is resolvable via the precedence chain above.
- `HYDROLIX_OAUTH_ISSUER` is set but `HYDROLIX_OAUTH_AUDIENCE` is unset.
- Any of the optional OAuth env vars (`HYDROLIX_OAUTH_JWKS_URI`, `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS`, `HYDROLIX_OAUTH_REQUIRED_SCOPES`, `HYDROLIX_OAUTH_RESOURCE_URL`) is set without an activatable config (i.e., without both `HYDROLIX_OAUTH_AUDIENCE` and a resolvable issuer).

Partial configuration is a fatal startup error: the server SHALL raise `OAuthConfigError`. This case is explicitly NOT covered by the byte-identical guarantee. The intent is to surface misconfiguration loudly rather than silently ignore operator-set OAuth knobs.

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

#### Scenario: Issuer derivation attempted before HDX-11431

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_URL` are both set
- **AND** `HYDROLIX_OAUTH_ISSUER` is unset
- **AND** HDX-11431 has not yet landed (the derivation stub raises `NotImplementedError`)
- **THEN** the worker SHALL terminate at factory initialization with a clear error message referencing HDX-11431
- **AND** operators SHALL be expected to set `HYDROLIX_OAUTH_ISSUER` explicitly until HDX-11431 publishes the cluster-URL-to-IdP convention

#### Scenario: Issuer derived from cluster URL (post-HDX-11431)

- **WHEN** HDX-11431 has landed and the derivation function returns a valid record
- **AND** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_URL` are both set, with `HYDROLIX_OAUTH_ISSUER` unset
- **THEN** the server SHALL resolve the issuer via `canonical_idp_endpoints(HYDROLIX_URL).issuer`
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

#### Scenario: HYDROLIX_URL set, audience unset, no other OAuth vars

- **WHEN** `HYDROLIX_URL` is set
- **AND** no `HYDROLIX_OAUTH_*` env vars are set
- **THEN** OAuth SHALL NOT activate
- **AND** the server SHALL behave byte-identically to a build without OAuth code

#### Scenario: Optional OAuth var set without audience

- **WHEN** any of `HYDROLIX_OAUTH_JWKS_URI`, `HYDROLIX_OAUTH_REQUIRED_SCOPES`, `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS`, or `HYDROLIX_OAUTH_RESOURCE_URL` is set
- **AND** `HYDROLIX_OAUTH_AUDIENCE` is unset
- **THEN** the worker SHALL raise `OAuthConfigError` during factory initialization

### Requirement: Canonical IdP endpoint derivation is a single contained function

All knowledge of where the cluster's canonical IdP lives relative to `HYDROLIX_URL` SHALL be encapsulated in a single function exported from `mcp_hydrolix.auth.idp_endpoints` that takes the cluster URL and returns an immutable record containing at least the issuer URL, the OIDC discovery URL, the JWKS URI, and the network-reachable address of the IdP.

Until [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431) publishes the cluster-URL-to-IdP convention, this function SHALL raise `NotImplementedError` with a message referencing HDX-11431. As a consequence, the URL-derivation activation path is unreachable in production until HDX-11431 lands; operators MUST set `HYDROLIX_OAUTH_ISSUER` explicitly during this period.

When the function eventually returns a result (after HDX-11431 lands and the body is replaced), the returned record SHALL be frozen, SHALL contain the four named fields, and SHALL never return an `issuer` string-equal to its input `hydrolix_url` (preserving the issuer/cluster-URL non-conflation invariant; see "JWT verification rejects mismatched issuer").

#### Scenario: Stub raises NotImplementedError until HDX-11431

- **WHEN** `canonical_idp_endpoints` is called with any value of `hydrolix_url` before HDX-11431 has landed
- **THEN** the function SHALL raise `NotImplementedError`
- **AND** the exception message SHALL contain the substring `HDX-11431`

#### Scenario: Eventual return shape is immutable and complete

- **WHEN** HDX-11431 has landed and `canonical_idp_endpoints` is called with a `hydrolix_url` value, returning successfully
- **THEN** the returned record SHALL be frozen (no mutable fields)
- **AND** the record SHALL expose `issuer`, `discovery_url`, `jwks_uri`, and `address` as string-typed fields
- **AND** calling the function twice with the same input SHALL return equal records

#### Scenario: Eventual derived issuer is never equal to the input cluster URL

- **WHEN** HDX-11431 has landed and `canonical_idp_endpoints` is called with any non-empty `hydrolix_url` value, returning successfully
- **THEN** the returned `issuer` SHALL NOT be string-equal to the input `hydrolix_url`

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

When OAuth is active, the server SHALL expose `/.well-known/oauth-protected-resource` returning a JSON document conforming to RFC 9728. This endpoint SHALL NOT require authentication. The JSON SHALL include at minimum the `resource`, `authorization_servers`, and `bearer_methods_supported` keys. The `resource` field SHALL take the value of `OAuthConfig.resource_url` after the precedence chain defined in the "Resource URL configuration" requirement. The `authorization_servers` array SHALL contain the resolved issuer URL (the value of `OAuthConfig.issuer` after precedence resolution).

#### Scenario: Metadata endpoint returns RFC 9728 JSON

- **WHEN** OAuth is active and an unauthenticated GET request reaches `/.well-known/oauth-protected-resource`
- **THEN** the response status SHALL be 200
- **AND** the response body SHALL be JSON containing `resource`, `authorization_servers`, and `bearer_methods_supported` keys
- **AND** the `authorization_servers` array SHALL contain the resolved issuer URL (the value of `OAuthConfig.issuer` after precedence resolution)
- **AND** the `resource` field SHALL equal `OAuthConfig.resource_url`

#### Scenario: 401 references metadata URL

- **WHEN** a request to an authenticated endpoint is rejected with 401
- **THEN** the `WWW-Authenticate` header SHALL include a `resource_metadata=<url>` parameter pointing to the protected-resource-metadata URL

### Requirement: Resource URL configuration

The `resource` field in the RFC 9728 document SHALL be resolved with the following precedence:

1. `HYDROLIX_OAUTH_RESOURCE_URL` if set to a non-empty value (explicit operator override).
2. Otherwise, if `HYDROLIX_URL` is set, the resource URL SHALL default to the cluster public URL (`HYDROLIX_URL`).
3. Otherwise, the resource URL SHALL default to the server's configured base URL (host and port the worker is bound to).

`HYDROLIX_OAUTH_RESOURCE_URL` SHALL NOT affect any other aspect of authentication: it does not change the `iss` match target, does not change the JWKS URI, and does not change OAuth activation. Setting it without an activatable config triggers the partial-configuration error path (see "Activation gated on operator env vars").

#### Scenario: Explicit resource URL wins

- **WHEN** `HYDROLIX_OAUTH_RESOURCE_URL="https://mcp.example.com/api"` is set alongside an activatable OAuth config
- **THEN** the `resource` field in the RFC 9728 JSON SHALL equal `"https://mcp.example.com/api"`

#### Scenario: Resource URL defaults to HYDROLIX_URL

- **WHEN** OAuth is active, `HYDROLIX_OAUTH_RESOURCE_URL` is unset, and `HYDROLIX_URL="https://cluster.example.com"` is set
- **THEN** the `resource` field in the RFC 9728 JSON SHALL equal `"https://cluster.example.com"`

#### Scenario: Resource URL falls back to server bind URL

- **WHEN** OAuth is active, `HYDROLIX_OAUTH_RESOURCE_URL` is unset, and `HYDROLIX_URL` is unset (issuer was resolved via explicit `HYDROLIX_OAUTH_ISSUER`)
- **THEN** the `resource` field in the RFC 9728 JSON SHALL equal the server's bound base URL (scheme + host + port that the worker is serving on)

#### Scenario: Resource URL set without audience

- **WHEN** `HYDROLIX_OAUTH_RESOURCE_URL` is set
- **AND** `HYDROLIX_OAUTH_AUDIENCE` is unset
- **THEN** the worker SHALL raise `OAuthConfigError` during factory initialization

### Requirement: JWKS URI override and insecure transport flag

The verifier SHALL accept an explicit `HYDROLIX_OAUTH_JWKS_URI` override for in-cluster deployments where the public discovery URL is not reachable from the pod. By default the verifier SHALL reject any JWKS URI whose scheme is `http`. When `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS=true` is set, the verifier SHALL accept `http://` JWKS URIs to support cluster-internal backchannel calls.

#### Scenario: Plain HTTP JWKS rejected by default

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_OAUTH_ISSUER` are set to activate OAuth
- **AND** `HYDROLIX_OAUTH_JWKS_URI="http://idp.internal/realms/x/protocol/openid-connect/certs"` is set
- **AND** `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS` is unset
- **THEN** `load_oauth_config()` SHALL raise `OAuthConfigError` at startup (the insecure-scheme check fires before any preflight)

#### Scenario: Plain HTTP JWKS allowed when explicitly opted in

- **WHEN** `HYDROLIX_OAUTH_AUDIENCE` and `HYDROLIX_OAUTH_ISSUER` are set to activate OAuth
- **AND** `HYDROLIX_OAUTH_JWKS_URI="http://idp.internal/.../certs"` is set
- **AND** `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS="true"` is set
- **THEN** `load_oauth_config()` SHALL accept the configuration and the verifier SHALL fetch keys from that URL at startup

### Requirement: No JWT credential material in logs

The intent of this requirement is to prevent credential leakage via logs. Across `mcp_hydrolix/auth/oauth.py`, `mcp_hydrolix/auth/mcp_providers.py`, `mcp_hydrolix/mcp_server.py`, and `mcp_hydrolix/webapp.py`, no `logger.*` call SHALL emit any of the following:

- The raw JWT as presented in the `Authorization` header (`header.payload.signature` concatenated form).
- The signature segment of a JWT, alone or as part of any other value.
- The base64url-encoded header or payload segments of a JWT (logging these alongside any other public information would let an attacker reconstruct the presented token).
- The full `Authorization` header value (which contains the raw token).
- JWKS private exponents or any other private key material.

**Decoded claim values** (including `sub`, `aud`, `iss`, `iat`, `exp`, `jti`, `scope`, `client_id`, and custom claims) MAY be logged at the auth layer's discretion. Decoded claims are not credentials — they cannot be used to forge a JWT without the IdP's signing key. Operator-set configuration values (resolved issuer URL, audience allowlist, required scopes) MAY also be logged.

Failure paths SHALL log only the exception class name when the exception's message could include raw token bytes (for example, JWT parser errors that quote the malformed input). For exceptions whose messages are known not to include token bytes, the message MAY be logged.

#### Scenario: Successful activation log content

- **WHEN** OAuth activates successfully at startup
- **THEN** the INFO log line MAY include the resolved issuer URL, the audience allowlist, and the required scopes

#### Scenario: Valid bearer accepted log content

- **WHEN** OAuth is active and a valid bearer token is accepted
- **THEN** any log line emitted by the auth layer MAY include decoded claim values (`sub`, `aud`, `iss`, `client_id`, etc.)
- **AND** SHALL NOT include the raw `Authorization` header value
- **AND** SHALL NOT include the JWT's signature segment or its base64url-encoded header/payload segments

#### Scenario: Invalid bearer rejected log content

- **WHEN** OAuth is active and a request presents an invalid bearer token that fails verification
- **THEN** any log line emitted by the auth layer for the rejection SHALL NOT include the raw token, the signature segment, or the encoded header/payload segments
- **AND** the line MAY include the exception class name and any decoded claim values the verifier successfully parsed before rejection

### Requirement: Valid bearer authenticates the request end-to-end

When OAuth is active, a request presenting an `Authorization: Bearer <jwt>` header with a JWT whose signature verifies against the JWKS, whose `iss` matches the resolved issuer URL, whose `aud` matches at least one configured audience value, whose `exp` is in the future, and (if `HYDROLIX_OAUTH_REQUIRED_SCOPES` is configured) whose scope claim covers all required scopes SHALL be authenticated and dispatched to the MCP tool layer, with no further bearer-related rejection emitted by the auth chain.

#### Scenario: Well-formed bearer reaches the MCP tool layer

- **WHEN** OAuth is active and a request to an MCP tool endpoint presents an `Authorization: Bearer <jwt>` header
- **AND** the JWT signature verifies against the JWKS
- **AND** `iss` equals the resolved issuer URL, `aud` contains a value in the configured allowlist, `exp` is in the future, and required scopes (if any) are present
- **THEN** the auth chain SHALL accept the request
- **AND** the MCP tool SHALL be invoked and its response returned with the appropriate HTTP status

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
