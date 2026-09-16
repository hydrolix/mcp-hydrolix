## ADDED Requirements

### Requirement: Query Purpose Comment

`run_select_query` MUST accept an optional `purpose` string and `execute_query` MUST send it as `hdx_query_comment` with whitespace collapsed to single spaces and at most 256 characters; when the sanitized purpose is empty the setting MUST be absent.

#### Scenario: Purpose Sets Query Comment

- **WHEN** `execute_query` is called with `comment="  top errors\nlast hour "`
- **THEN** the request settings contain `hdx_query_comment` equal to `top errors last hour`

#### Scenario: Purpose Truncated To Budget

- **WHEN** the purpose is 1000 characters long
- **THEN** the recorded comment is 256 characters long

#### Scenario: No Purpose No Comment

- **WHEN** `execute_query` is called without a comment
- **THEN** the request settings do not contain `hdx_query_comment`

#### Scenario: Tool Forwards Purpose

- **WHEN** `run_select_query` is called with `purpose="why"`
- **THEN** `execute_query` receives `comment="why"`
