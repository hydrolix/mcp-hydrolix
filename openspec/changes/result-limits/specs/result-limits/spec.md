## ADDED Requirements

### Requirement: Result Byte Cap

Every query executed via `execute_query` MUST carry `hdx_query_max_result_bytes` from `HYDROLIX_QUERY_MAX_RESULT_BYTES` (default 67108864); a configured value below 10000 or not an integer MUST fail configuration.

#### Scenario: Byte Cap Sent With Every Query

- **WHEN** `HYDROLIX_QUERY_MAX_RESULT_BYTES` is unset and a query executes
- **THEN** the request settings contain `hdx_query_max_result_bytes` equal to 67108864

#### Scenario: Byte Cap Override From Env

- **WHEN** `HYDROLIX_QUERY_MAX_RESULT_BYTES=4194304`
- **THEN** the request settings contain `hdx_query_max_result_bytes` equal to 4194304

#### Scenario: Byte Cap Below Floor Rejected

- **WHEN** `HYDROLIX_QUERY_MAX_RESULT_BYTES` is `9999`, `0`, `-1` or `lots`
- **THEN** `HydrolixConfig` raises `ValueError` naming the variable

### Requirement: Caller Lowerable Cell Cap

`HYDROLIX_MAX_RESULT_CELLS_LIMIT` MUST default to 200000. When it is positive, a `max_cells` of 0 or above the cap MUST be reduced to the cap and reported as capped by the operator; a value below the cap MUST be honoured. `0` MUST disable the cap, and the server MUST warn at startup when it is `0` on the http or sse transport.

#### Scenario: Default Cell Cap Is Positive

- **WHEN** `HYDROLIX_MAX_RESULT_CELLS_LIMIT` is unset
- **THEN** `max_result_cells_limit` is 200000

#### Scenario: Zero Max Cells Is Capped By Default

- **WHEN** a caller passes `max_cells=0` with the default configuration
- **THEN** the effective limit is 200000 and it is reported as capped by the operator

#### Scenario: Caller Can Lower Below Cap

- **WHEN** a caller passes `max_cells=500`
- **THEN** the effective limit is 500 and it is not reported as capped

#### Scenario: Explicit Zero Limit Disables Cap

- **WHEN** `HYDROLIX_MAX_RESULT_CELLS_LIMIT=0` and a caller passes `max_cells=0`
- **THEN** the effective limit is 0 and it is not reported as capped

#### Scenario: Zero Limit Warns On Http

- **WHEN** `HYDROLIX_MAX_RESULT_CELLS_LIMIT=0` and the transport is http
- **THEN** a warning naming the variable is logged at configuration time
