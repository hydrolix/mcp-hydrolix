*Per-request credentials on the gateway path: no request runs as the service account, and a token in the URL is opt-in.*

## ADDED Requirements

### Requirement: Request Credential Required Mode

With `HYDROLIX_REQUIRE_REQUEST_CREDENTIAL=true`, `creds_with(None)` MUST raise `MissingRequestCredentialError` instead of returning the environment credential, a request carrying its own credential MUST still be honoured, startup MUST refuse the setting on the stdio transport, and the readiness probe MUST pass its mounted credential explicitly. The default MUST keep the environment fallback.
<!-- settle: explore/hardening-scope -->

#### Scenario: Missing Request Credential Is Refused

- **GIVEN** the http transport, the setting on, and `HYDROLIX_TOKEN` set
- **WHEN** `creds_with(None)` is called
- **THEN** it raises `MissingRequestCredentialError` mentioning a per-request credential

#### Scenario: Request Credential Still Honoured

- **GIVEN** the setting on
- **WHEN** `creds_with` is called with a request credential
- **THEN** it returns that credential

#### Scenario: Required Mode Rejects Stdio Transport

- **GIVEN** the stdio transport and the setting on
- **WHEN** the configuration is constructed
- **THEN** it raises `ValueError` naming http or sse

#### Scenario: Default Mode Keeps Environment Fallback

- **GIVEN** the setting unset and `HYDROLIX_TOKEN` set
- **WHEN** `creds_with(None)` is called
- **THEN** it returns the environment service-account credential

#### Scenario: Query Without Credential Fails Closed

- **GIVEN** the setting on and no per-request credential
- **WHEN** `execute_query` runs
- **THEN** it raises `ToolError` mentioning a per-request credential

#### Scenario: Readiness Probe Passes Mounted Credential

- **GIVEN** the setting on, no per-request credential, and a mounted service-account token
- **WHEN** the readiness probe runs
- **THEN** the client is created with the mounted credential and the probe returns 200

### Requirement: Token Query Parameter Opt In

The `?token=` query parameter MUST NOT be accepted unless `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM=true`, the Authorization header MUST always be accepted, and enabling the parameter MUST log a warning at startup.

#### Scenario: Query Parameter Backend Off By Default

- **GIVEN** `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM` unset
- **THEN** the credential chain contains only the bearer backend

#### Scenario: Query Parameter Backend Enabled By Env

- **GIVEN** `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM=true`
- **THEN** the credential chain contains the bearer backend followed by the query-parameter backend

#### Scenario: Enabling Query Parameter Logs Warning

- **GIVEN** `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM=true`
- **WHEN** the configuration is constructed
- **THEN** a warning naming the variable is logged
