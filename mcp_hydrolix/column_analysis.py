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
