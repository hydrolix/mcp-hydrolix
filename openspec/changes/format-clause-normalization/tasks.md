*3 phases, 5 tasks.*

**Tracking:** HDX-12410

## 1. Implementation

- [x] 1.1 Add `mcp_hydrolix/statement.py`: `tokenize` (sqlglot's ClickHouse tokenizer) and `normalize_statement` [implements: query-text-handling/format-clause-removed, query-text-handling/trailing-semicolon-and-comments-removed, query-text-handling/comments-read-like-clickhouse, design/sqlglot-tokenizer] — verify: `pytest -q tests/test_statement.py::TestTokenize tests/test_statement.py::TestNormalizeStatement` green
- [x] 1.2 Call `normalize_statement` at the top of `run_select_query`, before `inject_limit` [implements: query-text-handling/format-clause-removed, design/remove-not-impose] — verify: `grep -n normalize_statement mcp_hydrolix/mcp_server.py` shows the import and one call

## 2. Tests

- [x] 2.1 Unit scenarios for the scanner and the normaliser [implements: meta/tests] — verify: `pytest -q tests/test_statement.py -m "not integration_clickhouse"` green
- [x] 2.2 Integration scenario "Agent Format Clause Runs On The Cluster" against the compose ClickHouse [implements: query-text-handling/format-clause-removed, meta/tests] — verify: `docker compose up -d --wait && pytest -q tests/test_statement.py -m integration_clickhouse` green

## 3. Docs

- [x] 3.1 Document the removal in `README.md` (tool bullet) and `docs/CONFIG.md` ("Query text handling") [implements: meta/docs] — verify: `grep -n "FORMAT" README.md docs/CONFIG.md` non-empty
