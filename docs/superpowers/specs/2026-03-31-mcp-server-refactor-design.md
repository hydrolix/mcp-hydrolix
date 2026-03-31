# Design: Split `mcp_server.py` into Smaller Modules

**Date:** 2026-03-31
**Branch:** il/hdx-10938-parameterized-query

## Goal

`mcp_server.py` is 1043 lines with seven distinct responsibilities. The goal is to split it into smaller, focused modules while keeping all MCP tool definitions in `mcp_server.py` to avoid FastMCP registration complexity.

## New Module Structure

```
mcp_hydrolix/
  models.py          # Data types — new (~100 lines)
  column_analysis.py # Column classification and summary table logic — new (~230 lines)
  mcp_server.py      # Infrastructure, query execution, tools — trimmed (~710 lines)
  __init__.py        # Unchanged
  main.py            # Unchanged
  mcp_env.py         # Unchanged
  metrics.py         # Unchanged
  utils.py           # Unchanged
  auth/              # Unchanged
  log/               # Unchanged
```

## Module Contents

### `models.py` (new)

Pure data types with no local dependencies. Imports only from stdlib and third-party libraries.

Contents moved from `mcp_server.py`:
- `Column`, `AliasColumn`, `AggregateColumn`, `SummaryColumn` dataclasses
- `ColumnType` union alias
- `_SystemCol`, `SystemCol` marker
- `Table` pydantic dataclass (with `sql_fields()`, `serialize_columns()`)
- `HdxQueryResult` TypedDict

### `column_analysis.py` (new)

Column classification logic and summary table detection. Imports from `models.py` and third-party libs (`sqlglot`, `graphlib`). No dependency on `mcp_server.py`.

Contents moved from `mcp_server.py`:
- `result_to_table`
- `extract_function_from_type`
- `get_merge_function`
- `detect_aggregate_aliases`
- `_enrich_column_metadata`
- `summary_tips_for_columns`

Note: `_describe_columns` and `_query_targets_summary_table` are **not** moved. Both call `execute_query`, which lives in `mcp_server.py`. Moving them would create a circular import (`column_analysis` → `mcp_server` → `column_analysis`). They stay in `mcp_server.py`.

### `mcp_server.py` (trimmed)

Everything that depends on the connection pool, `mcp` instance, or `execute_query`.

Retains:
- Module-level setup: logger, `load_dotenv`, `HYDROLIX_CONFIG`, `mcp` instance
- `get_request_credential()`
- `create_hydrolix_client()`, pool setup, signal handlers
- `_parse_hydrolix_version()`, `_check_parameterized_query_support()`
- `execute_query()`, `execute_cmd()`
- `/health` and `/metrics` HTTP endpoints
- `MetricsMiddleware`
- `_describe_columns()`, `_query_targets_summary_table()` (kept here to avoid circular import)
- `_resolve_cell_limit()`, `_build_truncation_response()`
- All `@mcp.tool()` definitions: `list_databases`, `get_table_info`, `list_tables`, `run_select_query`

## Dependency Graph

Arrows mean "depends on":

```
mcp_server.py  →  column_analysis.py  →  models.py
mcp_server.py  →  models.py
```

No circular imports. Clean acyclic dependency direction.

## Test Import Updates

Tests that import directly from `mcp_hydrolix.mcp_server` need updating where the symbol moves:

| File | Symbol | New import location |
|---|---|---|
| `test_summary_tables.py` | `Column`, `AliasColumn`, `AggregateColumn`, `SummaryColumn` | `mcp_hydrolix.models` |
| `test_summary_tables.py` | `detect_aggregate_aliases`, `_enrich_column_metadata`, `extract_function_from_type`, `get_merge_function` | `mcp_hydrolix.column_analysis` |
| `test_parameterized_queries.py` | `HdxQueryResult`, `Table` | `mcp_hydrolix.models` |
| `test_query_settings.py` | `HdxQueryResult` | `mcp_hydrolix.models` |
| `test_mcp_server.py` | `_build_truncation_response`, `_resolve_cell_limit` | stay in `mcp_hydrolix.mcp_server` |

`__init__.py` is unchanged — it only re-exports tool functions (`list_databases`, `list_tables`, etc.), all of which stay in `mcp_server.py`.

## What Does Not Change

- `main.py` — imports only `mcp` from `mcp_server`, unchanged
- `conftest.py` — imports `mcp` and `create_hydrolix_client`, both stay in `mcp_server.py`
- `__init__.py` — unchanged
- All tool docstrings and tool logic — no behavior changes
- Public API surface of `mcp_hydrolix` package — unchanged

## Out of Scope

- Reorganizing within `mcp_server.py` beyond what the extraction requires
- Moving `_resolve_cell_limit` / `_build_truncation_response` out (they are tightly coupled to `run_select_query`)
- Changing any logic, behavior, or tests beyond import path updates
