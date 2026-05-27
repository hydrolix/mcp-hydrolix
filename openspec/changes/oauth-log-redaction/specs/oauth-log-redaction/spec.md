*Defines what the MCP auth layer MAY and SHALL NOT include in log output to prevent JWT credential leakage.*

## ADDED Requirements

### Requirement: No JWT Credential Material In Logs

No `logger.*` call in the MCP auth layer (`mcp_hydrolix/auth/oauth.py`, `mcp_hydrolix/auth/mcp_providers.py`, `mcp_hydrolix/mcp_server.py`, `mcp_hydrolix/webapp.py`) SHALL emit any of the following:

- The raw JWT in its concatenated `header.payload.signature` form.
- The JWT signature segment, whether standalone or embedded in any larger value.
- The base64url-encoded header or payload segments.
- The full `Authorization` header value.
- JWKS private exponents or any other private key material.

Decoded claim values (`sub`, `aud`, `iss`, `iat`, `exp`, `jti`, `scope`, `client_id`, and custom claims) MAY be logged — decoded claims are not credentials and cannot be used to forge a JWT without the IdP's signing key. Operator-configured values (resolved issuer URL, audience allowlist, required scopes) MAY also be logged.

When an exception message could include raw token bytes (e.g. a JWT parser error that quotes the malformed input), the auth layer SHALL log only the exception class name. The full exception message MUST NOT be included in the log record for those paths.

#### Scenario: Successful Activation Log Content

- **WHEN** OAuth activates successfully at startup (OIDC discovery and JWKS preflight both succeed)
- **THEN** the INFO activation log line MAY include the resolved issuer URL, the audience allowlist, and the required scopes
- **AND** SHALL NOT include the raw JWKS response body
- **AND** SHALL NOT include any private key material
- **AND** SHALL NOT include the raw OIDC discovery response body

#### Scenario: Valid Bearer Accepted Log Content

- **WHEN** OAuth is active and a request presents a valid bearer token that is accepted
- **THEN** any log line emitted by the auth layer MAY include decoded claim values (`sub`, `aud`, `iss`, `client_id`, etc.)
- **AND** SHALL NOT include the raw `Authorization` header value
- **AND** SHALL NOT include the JWT's signature segment
- **AND** SHALL NOT include the base64url-encoded header or payload segments

#### Scenario: Invalid Bearer Rejected Log Content

- **WHEN** OAuth is active and a request presents an invalid bearer token that fails verification
- **THEN** any log line emitted by the auth layer for the rejection SHALL NOT include the raw token
- **AND** SHALL NOT include the JWT's signature segment
- **AND** SHALL NOT include the base64url-encoded header or payload segments
- **AND** the log line MAY include the exception class name
- **AND** the log line MAY include any decoded claim values the verifier successfully parsed before the point of rejection

### Requirement: Log Redaction Invariant Is Tested

The log-redaction guarantee SHALL be backed by a `caplog`-based test module (`tests/auth/test_log_redaction.py`) that runs the full request path and asserts that no log record's `message` or `args` contains any prohibited content. The test module SHALL cover all 6 of the following call paths:

1. Successful activation (OIDC discovery + JWKS preflight both succeed).
2. Discovery failure (network error at startup).
3. Valid bearer accepted (token passes all verification checks).
4. Invalid bearer rejected (token fails verification).
5. SA path with no bearer (no `Authorization` header; credential chain handles the request).
6. `OAuthConfigError` raised (partial or malformed `HYDROLIX_OAUTH_*` configuration).

The test module SHALL run on every PR as part of the standard `pytest` suite. A future `logger.exception(exc)` that leaks a token via the exception message SHALL cause this test to fail loudly.

#### Scenario: Discovery Failure Does Not Log Bearer

- **WHEN** OIDC discovery fails at startup (network error)
- **AND** a subsequent request arrives with any `Authorization: Bearer <jwt>` value
- **THEN** no log record emitted during startup or request handling SHALL contain the raw JWT, its signature segment, or its base64url-encoded header/payload segments

#### Scenario: Sa Path Does Not Log Bearer Absence As Token

- **WHEN** a request arrives with no `Authorization` header
- **THEN** no log record SHALL contain a bearer token or token fragment
- **AND** the log record MAY note that no bearer was present

#### Scenario: Oauth Config Error Does Not Log Partial Config Secrets

- **WHEN** `OAuthConfigError` is raised during factory initialization (partial `HYDROLIX_OAUTH_*` configuration)
- **THEN** no log record SHALL contain JWKS private exponents or any private key material
- **AND** the error message in the log record SHALL be the `OAuthConfigError` message, not a raw token or key value
