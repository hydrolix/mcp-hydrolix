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

### Decision: sqlglot-tokenizer

- **Choice:** Use sqlglot's ClickHouse tokenizer to find the statement's last significant tokens; no hand-written scanner and no parse.
- **Why:** The tokenizer already knows the dialect's comment forms (`--`, `#`, `#!`, nested `/* */`), string literals and quoted identifiers, and tokenizing needs no grammar, so summary-table statements that sqlglot's parser cannot read still tokenize. The maintainer does not want a SQL lexer maintained in this repository (review of the first cut, which shipped one).
- **Alternatives:** A hand-written scanner — the first cut; correct, but a lexer to maintain. sqlglot's parser — fails on summary-table SQL. A tail regex — misreads `-- FORMAT JSON` in a comment, a literal ending the statement, or a column named `format`.
- **Binding:** Only a trailing `FORMAT` keyword token followed by a bare word is removed; `format(...)`, `AS format` and `ORDER BY format` are untouched; text the tokenizer cannot read passes through unchanged.

## Risks / Trade-offs

- [Agent still gets an error for other syntax] → unchanged behaviour; the cluster's message is returned as before.
- [Statement is only comments] → the empty text reaches the cluster and fails as it does today.
