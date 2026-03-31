# mcp_server.py Module Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `mcp_hydrolix/mcp_server.py` into three focused modules by extracting data types into `models.py` and column/summary-table logic into `column_analysis.py`, leaving tools and infrastructure in `mcp_server.py`.

**Architecture:** `models.py` has no local deps. `column_analysis.py` imports from `models.py` only. `mcp_server.py` imports from both. No circular imports. All `@mcp.tool()` definitions remain in `mcp_server.py` to avoid FastMCP registration complexity.

**Tech Stack:** Python 3.13, FastMCP, pydantic, sqlglot, clickhouse-connect

**Baseline:** Run `uv run pytest tests/ -q --tb=no --ignore=tests/test_tool.py --ignore=tests/test_mcp_server.py` — must show 132 passed before starting.

---

### Task 1: Create `models.py`

**Files:**
- Create: `mcp_hydrolix/models.py`
- Modify: `mcp_hydrolix/mcp_server.py`

- [ ] **Step 1: Create `mcp_hydrolix/models.py` with all data types**

```python
import dataclasses as _dc
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, List, Optional, TypedDict, Union, get_type_hints

from pydantic import Field, field_serializer
from pydantic.dataclasses import dataclass as pydantic_dataclass


@dataclass(frozen=True)
class Column:
    """A plain dimension column."""

    column_category: ClassVar[str] = "Column"

    name: str
    type: str
    comment: Optional[str] = None


@dataclass(frozen=True)
class AliasColumn:
    """A grouper/dimension alias."""

    column_category: ClassVar[str] = "AliasColumn"

    name: str
    type: str
    default_expr: str
    comment: Optional[str] = None


@dataclass(frozen=True)
class AggregateColumn:
    """A column with AggregateFunction or SimpleAggregateFunction type."""

    column_category: ClassVar[str] = "AggregateColumn"

    name: str
    type: str
    base_function: str
    merge_function: str
    comment: Optional[str] = None


@dataclass(frozen=True)
class SummaryColumn:
    """An ALIAS column that transitively depends on aggregate functions."""

    column_category: ClassVar[str] = "SummaryColumn"

    name: str
    type: str
    default_expr: str
    comment: Optional[str] = None


ColumnType = Union[Column, AliasColumn, AggregateColumn, SummaryColumn]


class _SystemCol:
    """Marker: this field corresponds to a column in system.tables."""


SystemCol = _SystemCol()


@pydantic_dataclass
class Table:
    """Table with summary table detection (is_summary_table=True if aggregate
    columns are present)."""

    database: Annotated[str, SystemCol]
    name: Annotated[str, SystemCol]
    engine: Annotated[str, SystemCol]
    sorting_key: Annotated[str, SystemCol]
    primary_key: Annotated[str, SystemCol]
    total_rows: Annotated[Optional[int], SystemCol]
    total_bytes: Annotated[Optional[int], SystemCol]
    total_bytes_uncompressed: Annotated[Optional[int], SystemCol]
    parts: Annotated[Optional[int], SystemCol]
    active_parts: Annotated[Optional[int], SystemCol]
    columns: Optional[List[ColumnType]] = Field(default_factory=list)
    is_summary_table: Optional[bool] = None
    summary_table_info: Optional[str] = None

    @field_serializer("columns")
    def serialize_columns(self, columns: Optional[List[ColumnType]]) -> List[dict]:
        return [
            {**_dc.asdict(col), "column_category": type(col).column_category}
            for col in (columns or [])
        ]

    @classmethod
    def sql_fields(cls) -> List[str]:
        """Comma-separated column names for SELECT from system.tables."""
        hints = get_type_hints(cls, include_extras=True)
        return [
            name
            for name, hint in hints.items()
            if any(isinstance(m, _SystemCol) for m in getattr(hint, "__metadata__", ()))
        ]


class HdxQueryResult(TypedDict):
    columns: List[str]
    rows: List[List[Any]]
```

- [ ] **Step 2: Replace the import block at the top of `mcp_hydrolix/mcp_server.py`**

Replace this exact block (lines 1–53):

```python
import asyncio
import base64
import dataclasses as _dc
import logging
import re
import signal
import time
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from typing import (
    Annotated,
    Any,
    ClassVar,
    Dict,
    Final,
    List,
    Optional,
    Set,
    TypedDict,
    Union,
    cast,
    get_type_hints,
)

import clickhouse_connect
import sqlglot
import sqlglot.errors as sqlglot_errors
import sqlglot.expressions as sqlglot_exp
from clickhouse_connect import common
from clickhouse_connect.driver import httputil
from clickhouse_connect.driver.binding import format_query_value
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.tools.tool import ToolResult
from fastmcp.server.middleware import Middleware, MiddlewareContext
from jwt import DecodeError
from pydantic import Field, field_serializer
from pydantic.dataclasses import dataclass as pydantic_dataclass
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from mcp_hydrolix import metrics
from mcp_hydrolix.auth import (
    AccessToken,
    HydrolixCredential,
    HydrolixCredentialChain,
    ServiceAccountToken,
    UsernamePassword,
)
from mcp_hydrolix.mcp_env import HydrolixConfig, get_config
from mcp_hydrolix.utils import inject_limit, with_serializer
```

With:

```python
import asyncio
import base64
import logging
import signal
import time
from typing import (
    Any,
    Dict,
    Final,
    List,
    Optional,
    cast,
)

import clickhouse_connect
import sqlglot
import sqlglot.errors as sqlglot_errors
import sqlglot.expressions as sqlglot_exp
from clickhouse_connect import common
from clickhouse_connect.driver import httputil
from clickhouse_connect.driver.binding import format_query_value
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.tools.tool import ToolResult
from fastmcp.server.middleware import Middleware, MiddlewareContext
from jwt import DecodeError
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from mcp_hydrolix import metrics
from mcp_hydrolix.auth import (
    AccessToken,
    HydrolixCredential,
    HydrolixCredentialChain,
    ServiceAccountToken,
    UsernamePassword,
)
from mcp_hydrolix.mcp_env import HydrolixConfig, get_config
from mcp_hydrolix.models import ColumnType, HdxQueryResult, SummaryColumn, Table
from mcp_hydrolix.utils import inject_limit, with_serializer
```

- [ ] **Step 3: Remove the data type definitions from `mcp_hydrolix/mcp_server.py`**

Delete this entire block (currently after the imports, lines ~56–154):

```python
@dataclass(frozen=True)
class Column:
    """A plain dimension column."""

    column_category: ClassVar[str] = "Column"

    name: str
    type: str
    comment: Optional[str] = None


@dataclass(frozen=True)
class AliasColumn:
    """A grouper/dimension alias."""

    column_category: ClassVar[str] = "AliasColumn"

    name: str
    type: str
    default_expr: str
    comment: Optional[str] = None


@dataclass(frozen=True)
class AggregateColumn:
    """A column with AggregateFunction or SimpleAggregateFunction type."""

    column_category: ClassVar[str] = "AggregateColumn"

    name: str
    type: str
    base_function: str
    merge_function: str
    comment: Optional[str] = None


@dataclass(frozen=True)
class SummaryColumn:
    """An ALIAS column that transitively depends on aggregate functions."""

    column_category: ClassVar[str] = "SummaryColumn"

    name: str
    type: str
    default_expr: str
    comment: Optional[str] = None


ColumnType = Union[Column, AliasColumn, AggregateColumn, SummaryColumn]


class _SystemCol:
    """Marker: this field corresponds to a column in system.tables."""


SystemCol = _SystemCol()


@pydantic_dataclass
class Table:
    """Table with summary table detection (is_summary_table=True if aggregate
    columns are present)."""

    database: Annotated[str, SystemCol]
    name: Annotated[str, SystemCol]
    engine: Annotated[str, SystemCol]
    sorting_key: Annotated[str, SystemCol]
    primary_key: Annotated[str, SystemCol]
    total_rows: Annotated[Optional[int], SystemCol]
    total_bytes: Annotated[Optional[int], SystemCol]
    total_bytes_uncompressed: Annotated[Optional[int], SystemCol]
    parts: Annotated[Optional[int], SystemCol]
    active_parts: Annotated[Optional[int], SystemCol]
    columns: Optional[List[ColumnType]] = Field(default_factory=list)
    is_summary_table: Optional[bool] = None
    summary_table_info: Optional[str] = None

    @field_serializer("columns")
    def serialize_columns(self, columns: Optional[List[ColumnType]]) -> List[dict]:
        return [
            {**_dc.asdict(col), "column_category": type(col).column_category}
            for col in (columns or [])
        ]

    @classmethod
    def sql_fields(cls) -> List[str]:
        """Comma-separated column names for SELECT from system.tables."""
        hints = get_type_hints(cls, include_extras=True)
        return [
            name
            for name, hint in hints.items()
            if any(isinstance(m, _SystemCol) for m in getattr(hint, "__metadata__", ()))
        ]


class HdxQueryResult(TypedDict):
    columns: List[str]
    rows: List[List[Any]]
```

- [ ] **Step 4: Run the unit tests**

```bash
uv run pytest tests/ -q --tb=short --ignore=tests/test_tool.py --ignore=tests/test_mcp_server.py
```

Expected: 132 passed

- [ ] **Step 5: Commit**

```bash
git add mcp_hydrolix/models.py mcp_hydrolix/mcp_server.py
git commit -m "refactor: extract data models into models.py"
```

---

### Task 2: Create `column_analysis.py`

**Files:**
- Create: `mcp_hydrolix/column_analysis.py`
- Modify: `mcp_hydrolix/mcp_server.py`

- [ ] **Step 1: Create `mcp_hydrolix/column_analysis.py`**

```python
import logging
import re
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from typing import Dict, List, Optional, Set

import sqlglot
import sqlglot.errors as sqlglot_errors
import sqlglot.expressions as sqlglot_exp

from mcp_hydrolix.models import (
    AggregateColumn,
    AliasColumn,
    Column,
    ColumnType,
    SummaryColumn,
    Table,
)

logger = logging.getLogger("mcp-hydrolix")


def result_to_table(query_columns, result) -> List[Table]:
    sql_fields = Table.sql_fields()
    return [
        Table(**{k: v for k, v in zip(query_columns, row) if k in sql_fields}) for row in result
    ]


def extract_function_from_type(column_type: str) -> Optional[str]:
    """
    Extract aggregate function name from AggregateFunction type.
    Examples:
      "AggregateFunction(count, String)" -> "count"
      "AggregateFunction(sumIf, Float64)" -> "sumIf"
      "AggregateFunction(quantile(0.5), DateTime)" -> "quantile(0.5)"
      "AggregateFunction(exponentialMovingAverage(0.5), UInt32)" -> "exponentialMovingAverage(0.5)"
      "SimpleAggregateFunction(sum, Int64)" -> "sum"
      "String" -> None
    """
    match = re.match(r"^(?:Simple)?AggregateFunction\(([^,()]+(?:\([^)]*\))?)", column_type)
    if match:
        return match.group(1).strip()
    return None


def get_merge_function(base_function: str) -> str:
    """
    Generate -Merge function name from base function.
    For parameterized functions, parameters go AFTER "Merge":
      count -> countMerge
      countIf -> countIfMerge
      quantile(0.5) -> quantileMerge(0.5)
      exponentialMovingAverage(0.5) -> exponentialMovingAverageMerge(0.5)
    """
    match = re.match(r"^(\w+)(\(.+\))$", base_function)
    if match:
        func_name = match.group(1)
        params = match.group(2)
        return f"{func_name}Merge{params}"
    else:
        return f"{base_function}Merge"


def detect_aggregate_aliases(alias_definitions: Dict[str, str]) -> Set[str]:
    """
    Parse ALIAS column expressions via sqlglot AST, build alias dependency graph,
    topologically sort, and return the set of alias names that are aggregate
    (directly contain AggFunc OR transitively depend on another aggregate alias).
    Unparseable expressions are treated as non-aggregate. Circular dependencies
    return an empty set as a safe fallback.
    """
    parsed: dict[str, sqlglot_exp.Expression] = {}
    for name, sql in alias_definitions.items():
        try:
            parsed[name] = sqlglot.parse_one(sql, dialect="clickhouse")
        except sqlglot_errors.SqlglotError:
            logger.warning(
                "detect_aggregate_aliases: could not parse ALIAS expression for %r, "
                "treating as non-aggregate (column classification may be incorrect)",
                name,
            )

    alias_names = set(alias_definitions)

    @dataclass
    class _AliasInfo:
        is_direct_aggregation: bool
        alias_dependencies: Set[str]

    def _is_agg_node(n: sqlglot_exp.Expression) -> bool:
        return isinstance(n, sqlglot_exp.AggFunc) or (
            isinstance(n, sqlglot_exp.Anonymous) and str(n.this).endswith("Merge")
        )

    alias_dependency_meta: Dict[str, _AliasInfo] = {}
    for name, expr in parsed.items():
        aggregators: List[sqlglot_exp.Expression] = []
        alias_dependencies: Set[str] = set()
        for node in expr.walk(prune=_is_agg_node):
            if _is_agg_node(node):
                aggregators.append(node)
            elif isinstance(node, sqlglot_exp.Column):
                if node.name in alias_names:
                    alias_dependencies.add(node.name)
        alias_dependencies |= {
            n.name
            for agg in aggregators
            for n in agg.walk()
            if isinstance(n, sqlglot_exp.Column) and n.name in alias_names
        }
        alias_dependency_meta[name] = _AliasInfo(
            is_direct_aggregation=len(aggregators) > 0,
            alias_dependencies=alias_dependencies,
        )

    try:
        order = list(
            TopologicalSorter(
                {name: m.alias_dependencies - {name} for name, m in alias_dependency_meta.items()}
            ).static_order()
        )
    except CycleError:
        logger.warning(
            "detect_aggregate_aliases: circular dependency detected among ALIAS columns %r; "
            "treating all as non-aggregate (column classification may be incorrect)",
            list(alias_dependency_meta),
        )
        return set()

    is_aggregation: Dict[str, bool] = {}
    for name in order:
        alias_meta = alias_dependency_meta[name]
        is_aggregation[name] = alias_meta.is_direct_aggregation or any(
            is_aggregation.get(d, False) for d in alias_meta.alias_dependencies
        )

    return {name for name, is_agg in is_aggregation.items() if is_agg}


def _enrich_column_metadata(rows: List[Dict[str, str]]) -> List[ColumnType]:
    """
    Classify DESCRIBE TABLE rows into typed column objects (Column, AliasColumn,
    AggregateColumn, SummaryColumn). ALIAS columns whose expressions transitively
    depend on aggregate functions are detected via AST parsing and classified as
    SummaryColumn; all other ALIAS columns become AliasColumn. Columns with
    AggregateFunction/SimpleAggregateFunction types become AggregateColumn.
    Everything else is a plain Column.
    """
    alias_columns: Dict[str, str] = {
        r["name"]: r["default_expression"]
        for r in rows
        if r.get("default_type") == "ALIAS" and r.get("default_expression")
    }
    aggregate_alias_names = detect_aggregate_aliases(alias_columns) if alias_columns else set()

    def classify_column(r: Dict[str, str]) -> ColumnType:
        name = r["name"]
        col_type = r.get("type", "")
        comment = r.get("comment") or None

        if r.get("default_type") != "ALIAS":
            if col_type.startswith(("AggregateFunction(", "SimpleAggregateFunction(")):
                base_fn = extract_function_from_type(col_type)
                merge_fn = get_merge_function(base_fn) if base_fn else f"{col_type}Merge"
                return AggregateColumn(name, col_type, base_fn or "", merge_fn, comment)
            return Column(name, col_type, comment)
        elif name in aggregate_alias_names:
            return SummaryColumn(name, col_type, alias_columns[name], comment)
        else:
            return AliasColumn(name, col_type, r.get("default_expression", ""), comment)

    return [classify_column(r) for r in rows]


def summary_tips_for_columns(columns: list[ColumnType]) -> Optional[str]:
    """Build human-readable summary-table guidance from classified columns, or None if not a summary table."""
    aggregate_cols = [c for c in columns if isinstance(c, (AggregateColumn, SummaryColumn))]
    if len(aggregate_cols) == 0:
        return None
    dimension_cols = [c for c in columns if isinstance(c, (Column, AliasColumn))]
    return (
        f"This is a SUMMARY TABLE with {len(aggregate_cols)} aggregate column(s) and {len(dimension_cols)} dimension column(s). "
        "Columns with column_category='AggregateColumn' MUST be wrapped in their corresponding merge_function. "
        "Columns with column_category='SummaryColumn' are ALIAS columns that transitively depend on aggregates - use directly without wrapping. "
        "IMPORTANT: SummaryColumns are per-row values, not pre-totalled across the whole table. "
        "To aggregate across ALL rows (e.g. total count for the entire table), use the corresponding AggregateColumn with its merge_function (e.g. countMerge(`count()`)), NOT a SummaryColumn. "
        "Selecting a SummaryColumn without GROUP BY returns one value per row, not a single grand total. "
        "NEVER wrap a SummaryColumn in sum(), count(), avg() or any other aggregate - this causes ILLEGAL_AGGREGATION errors. "
        "Columns with column_category='Column' or column_category='AliasColumn' are dimensions - use directly and MUST appear in GROUP BY when mixed with aggregates. "
        "IMPORTANT: Dimension columns may have function-like names (e.g., 'toStartOfHour(col)') - these are LITERAL column names, use them exactly as-is with backticks. "
        "WRONG: SELECT toStartOfHour(col). RIGHT: SELECT `toStartOfHour(col)`. Also use in GROUP BY: GROUP BY `toStartOfHour(col)`. "
        "CRITICAL RULE: If your SELECT includes ANY dimension columns (column_category='Column' or 'AliasColumn') "
        "AND ANY aggregate columns (column_category='AggregateColumn' or 'SummaryColumn'), "
        "you MUST include 'GROUP BY <all dimension columns from SELECT>'. "
        "WITHOUT GROUP BY, the query will FAIL with 'NOT_AN_AGGREGATE' error. "
        "column_category='SummaryColumn' are NOT dimensions - do NOT include them in GROUP BY. "
        "Example: SELECT reqHost, cnt_all FROM table GROUP BY reqHost (reqHost has column_category='Column', cnt_all has column_category='SummaryColumn'). "
        "CRITICAL: You MUST use the EXACT merge_function value from each column with column_category='AggregateColumn'. "
        "DO NOT infer the merge function from the column name - always check the merge_function field. "
        "For example, if column `avgIf(col, condition)` has merge_function='avgIfMerge', "
        "you MUST use avgIfMerge(`avgIf(col, condition)`), NOT avgMerge(...)."
    )
```

- [ ] **Step 2: Add `column_analysis` import to `mcp_hydrolix/mcp_server.py`**

In the imports block, add this line directly after `from mcp_hydrolix.mcp_env import HydrolixConfig, get_config`:

```python
from mcp_hydrolix.column_analysis import (
    _enrich_column_metadata,
    result_to_table,
    summary_tips_for_columns,
)
```

- [ ] **Step 3: Remove `result_to_table` from `mcp_hydrolix/mcp_server.py`**

Delete this block (appears after `MetricsMiddleware`):

```python
def result_to_table(query_columns, result) -> List[Table]:
    sql_fields = Table.sql_fields()
    return [
        Table(**{k: v for k, v in zip(query_columns, row) if k in sql_fields}) for row in result
    ]
```

- [ ] **Step 4: Remove the column analysis functions from `mcp_hydrolix/mcp_server.py`**

Delete this entire block (the comment and six functions — stop before `_query_targets_summary_table`):

```python
# Summary Table Support - Helper Functions


def extract_function_from_type(column_type: str) -> Optional[str]:
    """
    Extract aggregate function name from AggregateFunction type.
    Examples:
      "AggregateFunction(count, String)" -> "count"
      "AggregateFunction(sumIf, Float64)" -> "sumIf"
      "AggregateFunction(quantile(0.5), DateTime)" -> "quantile(0.5)"
      "AggregateFunction(exponentialMovingAverage(0.5), UInt32)" -> "exponentialMovingAverage(0.5)"
      "SimpleAggregateFunction(sum, Int64)" -> "sum"
      "String" -> None
    """
    # Match everything from AggregateFunction( up to the comma that separates function from types
    # This captures function names with parameters like quantile(0.5) or quantile(0.5, 0.9)
    # Pattern: function_name or function_name(params) where params can contain commas
    match = re.match(r"^(?:Simple)?AggregateFunction\(([^,()]+(?:\([^)]*\))?)", column_type)
    if match:
        return match.group(1).strip()
    return None


def get_merge_function(base_function: str) -> str:
    """
    Generate -Merge function name from base function.
    For parameterized functions, parameters go AFTER "Merge":
      count -> countMerge
      countIf -> countIfMerge
      quantile(0.5) -> quantileMerge(0.5)
      exponentialMovingAverage(0.5) -> exponentialMovingAverageMerge(0.5)
    """
    # Check if function has parameters
    match = re.match(r"^(\w+)(\(.+\))$", base_function)
    if match:
        # Parameterized: quantile(0.5) -> quantileMerge(0.5)
        func_name = match.group(1)
        params = match.group(2)
        return f"{func_name}Merge{params}"
    else:
        # Non-parameterized: count -> countMerge
        return f"{base_function}Merge"


def detect_aggregate_aliases(alias_definitions: Dict[str, str]) -> Set[str]:
    """
    Parse ALIAS column expressions via sqlglot AST, build alias dependency graph,
    topologically sort, and return the set of alias names that are aggregate
    (directly contain AggFunc OR transitively depend on another aggregate alias).
    Unparseable expressions are treated as non-aggregate. Circular dependencies
    return an empty set as a safe fallback.
    """
    parsed: dict[str, sqlglot_exp.Expression] = {}
    for name, sql in alias_definitions.items():
        try:
            parsed[name] = sqlglot.parse_one(sql, dialect="clickhouse")
        except sqlglot_errors.SqlglotError:
            logger.warning(
                "detect_aggregate_aliases: could not parse ALIAS expression for %r, "
                "treating as non-aggregate (column classification may be incorrect)",
                name,
            )

    alias_names = set(alias_definitions)

    @dataclass
    class _AliasInfo:
        is_direct_aggregation: bool
        alias_dependencies: Set[str]

    def _is_agg_node(n: sqlglot_exp.Expression) -> bool:
        # sqlglot recognises simple -Merge combinators (countMerge, sumMerge, …) as
        # CombinedAggFunc (a subclass of AggFunc).  Compound combinators such as
        # countIfMerge (-If + -Merge) are unknown to sqlglot and fall back to Anonymous.
        # We catch both: the subclass check covers known functions; the name suffix
        # check covers any -Merge variant that sqlglot does not have in its registry.
        return isinstance(n, sqlglot_exp.AggFunc) or (
            isinstance(n, sqlglot_exp.Anonymous) and str(n.this).endswith("Merge")
        )

    alias_dependency_meta: Dict[str, _AliasInfo] = {}
    for name, expr in parsed.items():
        aggregators: List[sqlglot_exp.Expression] = []
        alias_dependencies: Set[str] = set()
        for node in expr.walk(prune=_is_agg_node):
            if _is_agg_node(node):
                aggregators.append(node)
            elif isinstance(node, sqlglot_exp.Column):
                if node.name in alias_names:
                    alias_dependencies.add(node.name)
        alias_dependencies |= {
            n.name
            for agg in aggregators
            for n in agg.walk()
            if isinstance(n, sqlglot_exp.Column) and n.name in alias_names
        }
        alias_dependency_meta[name] = _AliasInfo(
            is_direct_aggregation=len(aggregators) > 0,
            alias_dependencies=alias_dependencies,
        )

    try:
        order = list(
            TopologicalSorter(
                {name: m.alias_dependencies - {name} for name, m in alias_dependency_meta.items()}
            ).static_order()
        )
    except CycleError:
        logger.warning(
            "detect_aggregate_aliases: circular dependency detected among ALIAS columns %r; "
            "treating all as non-aggregate (column classification may be incorrect)",
            list(alias_dependency_meta),
        )
        return set()  # circular dependency — safe fallback, treat all as non-aggregate

    is_aggregation: Dict[str, bool] = {}
    for name in order:
        alias_meta = alias_dependency_meta[name]
        is_aggregation[name] = alias_meta.is_direct_aggregation or any(
            is_aggregation.get(d, False) for d in alias_meta.alias_dependencies
        )

    return {name for name, is_agg in is_aggregation.items() if is_agg}
```

Also delete `_enrich_column_metadata` (appears between `_query_targets_summary_table` and `_describe_columns`):

```python
def _enrich_column_metadata(rows: List[Dict[str, str]]) -> List[ColumnType]:
    """
    Classify DESCRIBE TABLE rows into typed column objects (Column, AliasColumn,
    AggregateColumn, SummaryColumn). ALIAS columns whose expressions transitively
    depend on aggregate functions are detected via AST parsing and classified as
    SummaryColumn; all other ALIAS columns become AliasColumn. Columns with
    AggregateFunction/SimpleAggregateFunction types become AggregateColumn.
    Everything else is a plain Column.
    """
    alias_columns: Dict[str, str] = {
        r["name"]: r["default_expression"]
        for r in rows
        if r.get("default_type") == "ALIAS" and r.get("default_expression")
    }
    aggregate_alias_names = detect_aggregate_aliases(alias_columns) if alias_columns else set()

    def classify_column(r: Dict[str, str]) -> ColumnType:
        name = r["name"]
        col_type = r.get("type", "")
        comment = r.get("comment") or None

        if r.get("default_type") != "ALIAS":
            if col_type.startswith(("AggregateFunction(", "SimpleAggregateFunction(")):
                base_fn = extract_function_from_type(col_type)
                merge_fn = get_merge_function(base_fn) if base_fn else f"{col_type}Merge"
                return AggregateColumn(name, col_type, base_fn or "", merge_fn, comment)
            return Column(name, col_type, comment)
        elif name in aggregate_alias_names:
            return SummaryColumn(name, col_type, alias_columns[name], comment)
        else:
            return AliasColumn(name, col_type, r.get("default_expression", ""), comment)

    return [classify_column(r) for r in rows]
```

Also delete `summary_tips_for_columns` (appears after `_describe_columns`):

```python
def summary_tips_for_columns(columns: list[ColumnType]) -> Optional[str]:
    """Build human-readable summary-table guidance from classified columns, or None if not a summary table."""
    aggregate_cols = [c for c in columns if isinstance(c, (AggregateColumn, SummaryColumn))]
    if len(aggregate_cols) == 0:
        # not a summary table
        return None
    dimension_cols = [c for c in columns if isinstance(c, (Column, AliasColumn))]
    return (
        f"This is a SUMMARY TABLE with {len(aggregate_cols)} aggregate column(s) and {len(dimension_cols)} dimension column(s). "
        "Columns with column_category='AggregateColumn' MUST be wrapped in their corresponding merge_function. "
        "Columns with column_category='SummaryColumn' are ALIAS columns that transitively depend on aggregates - use directly without wrapping. "
        "IMPORTANT: SummaryColumns are per-row values, not pre-totalled across the whole table. "
        "To aggregate across ALL rows (e.g. total count for the entire table), use the corresponding AggregateColumn with its merge_function (e.g. countMerge(`count()`)), NOT a SummaryColumn. "
        "Selecting a SummaryColumn without GROUP BY returns one value per row, not a single grand total. "
        "NEVER wrap a SummaryColumn in sum(), count(), avg() or any other aggregate - this causes ILLEGAL_AGGREGATION errors. "
        "Columns with column_category='Column' or column_category='AliasColumn' are dimensions - use directly and MUST appear in GROUP BY when mixed with aggregates. "
        "IMPORTANT: Dimension columns may have function-like names (e.g., 'toStartOfHour(col)') - these are LITERAL column names, use them exactly as-is with backticks. "
        "WRONG: SELECT toStartOfHour(col). RIGHT: SELECT `toStartOfHour(col)`. Also use in GROUP BY: GROUP BY `toStartOfHour(col)`. "
        "CRITICAL RULE: If your SELECT includes ANY dimension columns (column_category='Column' or 'AliasColumn') "
        "AND ANY aggregate columns (column_category='AggregateColumn' or 'SummaryColumn'), "
        "you MUST include 'GROUP BY <all dimension columns from SELECT>'. "
        "WITHOUT GROUP BY, the query will FAIL with 'NOT_AN_AGGREGATE' error. "
        "column_category='SummaryColumn' are NOT dimensions - do NOT include them in GROUP BY. "
        "Example: SELECT reqHost, cnt_all FROM table GROUP BY reqHost (reqHost has column_category='Column', cnt_all has column_category='SummaryColumn'). "
        "CRITICAL: You MUST use the EXACT merge_function value from each column with column_category='AggregateColumn'. "
        "DO NOT infer the merge function from the column name - always check the merge_function field. "
        "For example, if column `avgIf(col, condition)` has merge_function='avgIfMerge', "
        "you MUST use avgIfMerge(`avgIf(col, condition)`), NOT avgMerge(...)."
    )
```

- [ ] **Step 5: Run the unit tests**

```bash
uv run pytest tests/ -q --tb=short --ignore=tests/test_tool.py --ignore=tests/test_mcp_server.py
```

Expected: 132 passed

- [ ] **Step 6: Commit**

```bash
git add mcp_hydrolix/column_analysis.py mcp_hydrolix/mcp_server.py
git commit -m "refactor: extract column analysis logic into column_analysis.py"
```

---

### Task 3: Update test imports

**Files:**
- Modify: `tests/test_summary_tables.py`
- Modify: `tests/test_parameterized_queries.py`
- Modify: `tests/test_query_settings.py`

- [ ] **Step 1: Update `tests/test_summary_tables.py`**

Replace:

```python
from mcp_hydrolix.mcp_server import (
    AggregateColumn,
    AliasColumn,
    Column,
    SummaryColumn,
    detect_aggregate_aliases,
    _enrich_column_metadata,
    extract_function_from_type,
    get_merge_function,
)
```

With:

```python
from mcp_hydrolix.column_analysis import (
    _enrich_column_metadata,
    detect_aggregate_aliases,
    extract_function_from_type,
    get_merge_function,
)
from mcp_hydrolix.models import AggregateColumn, AliasColumn, Column, SummaryColumn
```

- [ ] **Step 2: Update `tests/test_parameterized_queries.py`**

Replace:

```python
from mcp_hydrolix.mcp_server import (
    HdxQueryResult,
    _parse_hydrolix_version,
    get_table_info,
    list_tables,
)
```

With:

```python
from mcp_hydrolix.models import HdxQueryResult
from mcp_hydrolix.mcp_server import (
    _parse_hydrolix_version,
    get_table_info,
    list_tables,
)
```

Also replace the inner import inside `_fake_table_result`:

```python
    from mcp_hydrolix.mcp_server import Table
```

With:

```python
    from mcp_hydrolix.models import Table
```

- [ ] **Step 3: Update `tests/test_query_settings.py`**

Replace:

```python
from mcp_hydrolix.mcp_server import HdxQueryResult, run_select_query
```

With:

```python
from mcp_hydrolix.models import HdxQueryResult
from mcp_hydrolix.mcp_server import run_select_query
```

- [ ] **Step 4: Run the full unit test suite**

```bash
uv run pytest tests/ -q --tb=short --ignore=tests/test_tool.py --ignore=tests/test_mcp_server.py
```

Expected: 132 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_summary_tables.py tests/test_parameterized_queries.py tests/test_query_settings.py
git commit -m "refactor: update test imports to use models and column_analysis modules"
```
