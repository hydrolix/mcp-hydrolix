*Remove the agent's FORMAT clause; keep the driver's.*

**Tracking:** HDX-12410

## Context

- `HttpClient._prep_query` in clickhouse-connect appends `\n FORMAT Native` to every non-insert query and parses the response as Native. A user-supplied FORMAT clause therefore always collides with it.
- Verified 2026-09-16 against ClickHouse 26 in the compose stack and against a Hydrolix query head (qe-innovations-3, v6.4.0-rc.1): `SELECT 1 FORMAT JSON` fails with code 62 through the driver and succeeds when sent alone over HTTP.
- `inject_limit` re-serialises through sqlglot when it can parse the statement, which happens to drop a trailing semicolon; when sqlglot cannot parse (summary-table statements), the raw text reaches the driver.

## Goals / Non-Goals

- Goals: make an agent's trailing FORMAT clause or semicolon harmless; keep every other byte of the statement.
- Non-Goals: choosing a wire format (the driver does), refusing statements, parsing SQL.

## Decisions

### Decision: remove-not-impose

- **Choice:** Strip the trailing top-level `FORMAT <name>` and let the driver's `FORMAT Native` stand.
- **Why:** The driver reads Native and imposes it itself. Synthesising `FORMAT JSONCompact` would break result parsing; raw-HTTP implementations that speak JSON need that, this one does not.
- **Alternatives:** Switch to raw HTTP with JSONCompact — rewrites the execution path. Reject statements with a FORMAT clause — turns the most common agent habit into an error.
- **Binding:** `run_select_query` MUST call `normalize_statement` before `inject_limit`, and MUST NOT change the statement in any other way here.

### Decision: clickhouse-lexer-scanner

- **Choice:** A character scanner that drops `--`, `#`, `#!` line comments and nested block comments, consumes single-quoted strings (with backslash escapes) and backtick or double-quoted identifiers whole, records parenthesis depth, and marks a keyword after `identifier.` or `AS` as an identifier.
- **Why:** A regex on the tail mis-reads `-- FORMAT JSON` in a comment, a literal ending the statement, or a column named `format`. sqlglot cannot be used because it does not parse every valid Hydrolix statement.
- **Alternatives:** Tail regex — the cases above. sqlglot — fails on summary-table SQL.
- **Binding:** Only a top-level `FORMAT` followed by a bare word is removed; `format(...)`, `AS format` and `ORDER BY format` are untouched.

## Risks / Trade-offs

- [Agent still gets an error for other syntax] → unchanged behaviour; the cluster's message is returned as before.
- [Statement is only comments] → the empty text reaches the cluster and fails as it does today.
