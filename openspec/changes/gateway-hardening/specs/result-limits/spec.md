*A result byte cap on every query and a cell cap a caller can only lower.*

## ADDED Requirements

### Requirement: Result Byte Cap

Every query issued through `execute_query` MUST carry `hdx_query_max_result_bytes` from `HYDROLIX_QUERY_MAX_RESULT_BYTES` (default 64 MiB), and a configured value below 10000 MUST be rejected at startup.

#### Scenario: Byte Cap Sent With Every Query

- **GIVEN** `HYDROLIX_QUERY_MAX_RESULT_BYTES` is unset
- **WHEN** `execute_query` runs
- **THEN** the settings sent contain `hdx_query_max_result_bytes` equal to 67108864

#### Scenario: Byte Cap Override From Env

- **GIVEN** `HYDROLIX_QUERY_MAX_RESULT_BYTES=4194304`
- **WHEN** `execute_query` runs
- **THEN** the settings sent contain `hdx_query_max_result_bytes` equal to 4194304

#### Scenario: Byte Cap Below Floor Rejected

- **GIVEN** `HYDROLIX_QUERY_MAX_RESULT_BYTES` is 9999, 0, negative, or not a number
- **WHEN** the configuration is constructed
- **THEN** it raises `ValueError` naming the variable

### Requirement: Caller Lowerable Cell Cap

`HYDROLIX_MAX_RESULT_CELLS_LIMIT` MUST default to 200000; a caller's `max_cells` above the limit or equal to 0 MUST be capped to it, a caller MAY lower the budget below it, and an explicit 0 limit MUST disable the cap.
<!-- settle: explore/hardening-scope -->

#### Scenario: Default Cell Cap Is Positive

- **GIVEN** `HYDROLIX_MAX_RESULT_CELLS_LIMIT` is unset
- **THEN** `max_result_cells_limit` is 200000

#### Scenario: Zero Max Cells Is Capped By Default

- **GIVEN** `HYDROLIX_MAX_RESULT_CELLS_LIMIT` is unset
- **WHEN** a caller passes `max_cells=0`
- **THEN** the effective limit is 200000 and it is reported as capped by the operator

#### Scenario: Caller Can Lower Below Cap

- **GIVEN** `HYDROLIX_MAX_RESULT_CELLS_LIMIT` is unset
- **WHEN** a caller passes `max_cells=500`
- **THEN** the effective limit is 500 and it is not reported as capped

#### Scenario: Explicit Zero Limit Disables Cap

- **GIVEN** `HYDROLIX_MAX_RESULT_CELLS_LIMIT=0`
- **WHEN** a caller passes `max_cells=0`
- **THEN** the effective limit is 0 and it is not reported as capped
