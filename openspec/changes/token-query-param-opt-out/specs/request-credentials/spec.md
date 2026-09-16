## ADDED Requirements

### Requirement: Token Query Parameter Opt-Out

The server MUST accept a service-account token from the `?token=` query parameter unless `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM` is exactly `false` (case-insensitive); any other value keeps it on. The Bearer header backend MUST always be first in the chain. When the parameter is disabled the server MUST log it at startup.

#### Scenario: On By Default

- **WHEN** `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM` is unset
- **THEN** the authentication chain is the Bearer backend followed by the query-parameter backend

#### Scenario: Disabled By Env

- **WHEN** `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM=false`
- **THEN** the authentication chain contains only the Bearer backend

#### Scenario: Only Explicit False Disables

- **WHEN** `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM=off`
- **THEN** the query-parameter backend is still present

#### Scenario: Disabling Logs

- **WHEN** `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM=false` and the configuration is built
- **THEN** an info log naming the variable is emitted
