*Statement-shape guard applied to user SQL before it reaches the cluster: one read statement, no SETTINGS, FORMAT stripped.*

## ADDED Requirements

### Requirement: Read Statement Allow List

`run_select_query` MUST refuse any statement whose first significant word is not one of `SELECT`, `WITH`, `SHOW`, `DESC`, `DESCRIBE`, `EXPLAIN` (case-insensitive), and the refusal reason MUST name a write or DDL keyword when the first word is one, or suggest the closest read keyword when it is within two edits of one.

#### Scenario: Allows Each Read Prefix

- **WHEN** a statement begins with any allowed prefix, in any letter case
- **THEN** the preflight does not block it

#### Scenario: Blocks Write Statement With Reason

- **WHEN** a statement begins with `INSERT` or `DROP`
- **THEN** the preflight blocks it
- **AND** the reason says the tool is read-only and names the keyword

#### Scenario: Suggests Closest Read Keyword For Typo

- **WHEN** a statement begins with `SELCT`
- **THEN** the preflight blocks it
- **AND** the reason asks "Did you mean SELECT?"

#### Scenario: Blocks Statement Not Starting With A Word

- **WHEN** a statement begins with `(`
- **THEN** the preflight blocks it with the read-only reason

#### Scenario: Blocks Empty Query

- **WHEN** the statement is empty, whitespace, or comments only
- **THEN** the preflight blocks it with the reason `Empty query.`

### Requirement: Single Statement Guard

The preflight MUST refuse a text containing more than one statement, MUST drop a single trailing semicolon, MUST ignore semicolons inside string literals and comments, and MUST treat string literals and quoted identifiers as part of the statement so that one closing the statement is preserved and one following a semicolon counts as a second statement.

#### Scenario: Blocks Multiple Statements

- **WHEN** the text is `SELECT 1; DROP TABLE db.t`
- **THEN** the preflight blocks it with the reason `Only single statements are supported.`

#### Scenario: Drops Trailing Semicolon

- **WHEN** the text is `SELECT 1 FROM db.t;` followed by a comment
- **THEN** the statement passed on is `SELECT 1 FROM db.t`

#### Scenario: Ignores Semicolon Inside String Literal

- **WHEN** a string literal contains `;` or an escaped quote
- **THEN** the preflight does not block the statement

#### Scenario: Blocks Literal After Semicolon

- **WHEN** the text is `SELECT 1; 'x'`
- **THEN** the preflight blocks it with the reason `Only single statements are supported.`

#### Scenario: Preserves Trailing Literal

- **WHEN** a statement ends in a string literal, a backtick identifier or a double-quoted identifier
- **THEN** the statement passed on is the full text, unchanged

### Requirement: Settings Clause Refused

The preflight MUST refuse a top-level `SETTINGS` clause on user SQL; it MUST treat a word directly after an identifier and `.` as an identifier and a word directly after `AS` as an alias, but not a word after a numeric literal's trailing dot or after a closing quote; and `strip_conflicting_settings` MUST raise `UnparseableQueryError` only for a query that carries a `SETTINGS` keyword and cannot be parsed, never for one that merely spells "settings" inside an identifier or literal.
<!-- settle: explore/fail-closed-settings -->

#### Scenario: Blocks Top Level Settings Clause

- **WHEN** the text is `SELECT a FROM db.t SETTINGS readonly = 0`
- **THEN** the preflight blocks it with the SETTINGS reason

#### Scenario: Allows System Settings Table

- **WHEN** the text selects from `system.settings`
- **THEN** the preflight does not block it

#### Scenario: Allows Nested Settings For Stripper

- **WHEN** a SETTINGS clause appears only inside a parenthesised subquery
- **THEN** the preflight does not block it
- **AND** the nested clause is left to `strip_conflicting_settings`

#### Scenario: Blocks Settings After Numeric Literal

- **WHEN** a top-level SETTINGS clause follows `1.`, a string literal or a quoted identifier
- **THEN** the preflight blocks it with the SETTINGS reason

#### Scenario: Allows Settings As Alias

- **WHEN** the text is `SELECT toString(1) AS settings FROM db.t`
- **THEN** the preflight does not block it

#### Scenario: Refuses Unparseable Query With Settings

- **GIVEN** a query that carries a SETTINGS keyword and that sqlglot cannot parse
- **WHEN** `strip_conflicting_settings` runs with protected keys
- **THEN** it raises `UnparseableQueryError`

#### Scenario: Ignores Settings Substring In Identifier

- **GIVEN** a query sqlglot cannot parse whose only "settings" is a column name and a literal
- **WHEN** `strip_conflicting_settings` runs with protected keys
- **THEN** it returns the query unchanged

### Requirement: Format Clause Removed

The preflight MUST remove a trailing top-level `FORMAT <name>` clause and MUST leave a `format(...)` function call untouched.

#### Scenario: Strips Trailing Format Clause

- **WHEN** the text is `SELECT a FROM db.t FORMAT JSONEachRow;`
- **THEN** the statement passed on is `SELECT a FROM db.t`
- **AND** the result reports the FORMAT clause as removed

#### Scenario: Keeps Format Function Call

- **WHEN** the text is `SELECT format('{}', a) FROM db.t`
- **THEN** the statement passed on is unchanged

### Requirement: Comments Ignored

The preflight MUST ignore `--`, `#` and `#!` line comments and nested `/* */` block comments, as ClickHouse's lexer does, when classifying the statement, and MUST strip leading and trailing comments from the statement passed on.

#### Scenario: Ignores Leading And Trailing Comments

- **WHEN** the text has comments before and after `SELECT 1 FROM db.t`
- **THEN** the statement passed on is `SELECT 1 FROM db.t`

#### Scenario: Ignores Keyword Inside Comment

- **WHEN** a comment contains `SETTINGS` and a second statement
- **THEN** the preflight does not block the statement

#### Scenario: Ignores Hash Comment

- **WHEN** the statement is followed by `#` and `#!` line comments containing an apostrophe
- **THEN** the preflight does not block it
- **AND** the statement passed on excludes the comments

#### Scenario: Blocks Statement Hidden Behind Hash Comment

- **WHEN** a `#` comment containing an apostrophe is followed on the next line by `; DROP TABLE`
- **THEN** the preflight blocks it with the reason `Only single statements are supported.`

#### Scenario: Handles Nested Block Comment

- **WHEN** a block comment contains a nested block comment and then `; DROP TABLE`
- **THEN** the preflight does not block the statement
- **AND** the statement passed on excludes the whole comment

### Requirement: Preflight Applied To Run Select Query

`run_select_query` MUST run the preflight before any cell-limit resolution or execution, MUST raise `ToolError` carrying the block reason for a blocked statement without contacting the cluster, and MUST execute the normalised statement with the caller's `purpose` passed through.

#### Scenario: Refused Statement Raises Tool Error

- **WHEN** `run_select_query` receives `INSERT INTO db.t VALUES (1)`
- **THEN** it raises `ToolError` mentioning read-only
- **AND** `execute_query` is never awaited

#### Scenario: Executes Normalised Statement

- **WHEN** `run_select_query` receives a SELECT ending in `FORMAT JSON;` with a `purpose`
- **THEN** `execute_query` receives the statement without FORMAT or semicolon
- **AND** receives the purpose as its comment
