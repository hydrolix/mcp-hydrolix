## ADDED Requirements

### Requirement: Result Byte Cap

Every query executed via `execute_query` MUST carry `hdx_query_max_result_bytes` from `HYDROLIX_QUERY_MAX_RESULT_BYTES` (default 67108864); a configured value below 10000 or not an integer MUST fail configuration with a message that names the variable under the baked brand prefix.

#### Scenario: Byte Cap Sent With Every Query

- **WHEN** `HYDROLIX_QUERY_MAX_RESULT_BYTES` is unset and a query executes
- **THEN** the request settings contain `hdx_query_max_result_bytes` equal to 67108864

#### Scenario: Byte Cap Override From Env

- **WHEN** `HYDROLIX_QUERY_MAX_RESULT_BYTES=4194304`
- **THEN** the request settings contain `hdx_query_max_result_bytes` equal to 4194304

#### Scenario: Byte Cap Below Floor Rejected

- **WHEN** `HYDROLIX_QUERY_MAX_RESULT_BYTES` is `9999`, `0`, `-1` or `lots`
- **THEN** `HydrolixConfig` raises `ValueError` naming the variable

### Requirement: Cancelled Result Carries A Remedy

When the cluster cancels a query because its result exceeded a server-side size limit (TOO_MANY_ROWS_OR_BYTES), the `ToolError` MUST carry the cluster's message and a remedy (fewer columns, a LIMIT, or a narrower time range). The tool description MUST NOT describe the byte cap.

#### Scenario: Result Limit Error Gets A Remedy

- **WHEN** the client raises an error containing `TOO_MANY_ROWS_OR_BYTES`
- **THEN** the `ToolError` message ends with the remedy

#### Scenario: Other Errors Are Passed Through Unchanged

- **WHEN** the client raises a syntax error
- **THEN** the `ToolError` message carries it without the remedy

### Requirement: Caller Lowerable Cell Cap

`HYDROLIX_MAX_RESULT_CELLS_LIMIT` MUST default to 0, which leaves the caller's `max_cells` alone. When it is positive, a `max_cells` of 0 or above the cap MUST be reduced to the cap and reported as capped by the operator; a value below the cap MUST be honoured. The server MUST NOT warn about the value an operator chose.

#### Scenario: Default Cell Cap Is Unlimited

- **WHEN** `HYDROLIX_MAX_RESULT_CELLS_LIMIT` is unset
- **THEN** `max_result_cells_limit` is 0

#### Scenario: Zero Max Cells Is Uncapped By Default

- **WHEN** a caller passes `max_cells=0` with the default configuration
- **THEN** the effective limit is 0 and it is not reported as capped

#### Scenario: Zero Max Cells Is Capped When Operator Sets Limit

- **WHEN** `HYDROLIX_MAX_RESULT_CELLS_LIMIT=200000` and a caller passes `max_cells=0`
- **THEN** the effective limit is 200000 and it is reported as capped by the operator

#### Scenario: Caller Can Lower Below Cap

- **WHEN** `HYDROLIX_MAX_RESULT_CELLS_LIMIT=200000` and a caller passes `max_cells=500`
- **THEN** the effective limit is 500 and it is not reported as capped

#### Scenario: Caller Cannot Exceed Cap

- **WHEN** `HYDROLIX_MAX_RESULT_CELLS_LIMIT=200000` and a caller passes `max_cells=5000000`
- **THEN** the effective limit is 200000 and it is reported as capped by the operator
