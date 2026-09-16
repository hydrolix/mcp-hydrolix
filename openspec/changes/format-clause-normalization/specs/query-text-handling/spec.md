## ADDED Requirements

### Requirement: Format Clause Removed

Before executing a statement, `run_select_query` MUST remove a trailing top-level `FORMAT <name>` clause and MUST leave a `format(...)` function call, a column or alias named `format`, and any FORMAT keyword inside a string literal or comment untouched.

#### Scenario: Strips Trailing Format Clause

- **WHEN** the text is `SELECT a FROM db.t FORMAT JSONEachRow;`
- **THEN** the statement executed is `SELECT a FROM db.t`
- **AND** the result reports the FORMAT clause as removed

#### Scenario: Keeps Format Function Call

- **WHEN** the text is `SELECT format('{}', a) FROM db.t`
- **THEN** the statement is unchanged

#### Scenario: Keeps Format Alias

- **WHEN** the text is `SELECT toString(1) AS format FROM db.t`
- **THEN** the statement is unchanged

#### Scenario: Agent Format Clause Runs On The Cluster

- **GIVEN** a running cluster
- **WHEN** `run_select_query` receives a SELECT ending in `FORMAT JSON;`
- **THEN** the rows are returned

### Requirement: Trailing Semicolon And Comments Removed

`run_select_query` MUST drop leading and trailing comments and one trailing semicolon, and MUST leave any other semicolon in place.

#### Scenario: Drops Trailing Semicolon And Comments

- **WHEN** the text is `/* lead */ SELECT 1 FROM db.t;  -- trail`
- **THEN** the statement executed is `SELECT 1 FROM db.t`

#### Scenario: Leaves Inner Semicolons Alone

- **WHEN** the text is `SELECT 1; SELECT 2`
- **THEN** the statement is unchanged

### Requirement: Comments Read Like ClickHouse

The scanner MUST treat `--`, `#` and `#!` as line comments, MUST nest block comments, and MUST consume string literals and quoted identifiers whole.

#### Scenario: Apostrophe In Hash Comment

- **WHEN** the text is `SELECT 1 # it's` followed by a newline and `; DROP TABLE x`
- **THEN** the semicolon and `DROP` are seen as statement elements, not as part of a string

#### Scenario: Nested Block Comment

- **WHEN** the text is `SELECT 1 /* a /* b */ ; DROP */`
- **THEN** only `SELECT` and `1` are statement elements

#### Scenario: Statement Ending In A Literal

- **WHEN** the text is `SELECT count() FROM db.t WHERE name = 'x'`
- **THEN** the statement is unchanged
