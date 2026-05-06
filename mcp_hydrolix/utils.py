import ipaddress
import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, List

import sqlglot
import sqlglot.errors as sqlglot_errors
import sqlglot.expressions as exp

logger = logging.getLogger(__name__)


def coerce_cell(v: Any) -> Any:
    """Coerce ClickHouse-specific Python types in a result cell to JSON-friendly
    equivalents.

    `null` values pass through unchanged — `None` in a query result is data
    (the user's SELECT may legitimately return SQL NULLs) and must be preserved.
    """
    if isinstance(v, ipaddress.IPv4Address):
        return str(v)
    if isinstance(v, datetime):
        return v.timestamp()
    if isinstance(v, (date, time)):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.decode()
    if isinstance(v, Decimal):
        return str(v)
    return v


def coerce_rows(rows: List[List[Any]]) -> List[List[Any]]:
    """Apply `coerce_cell` to every cell in a 2D result set."""
    return [[coerce_cell(c) for c in row] for row in rows]


def inject_limit(query: str, max_rows: int) -> str:
    """Rewrite query to enforce a row limit, taking the minimum of any existing LIMIT.

    Returns the rewritten SQL string. If the query cannot be parsed by sqlglot, logs a
    warning and returns the original query unchanged so the caller still executes something.
    """
    try:
        ast = sqlglot.parse_one(query, dialect="clickhouse")
    except sqlglot_errors.SqlglotError:
        logger.warning(
            "inject_limit: could not parse query with sqlglot; LIMIT will not be injected. "
            "Result set may be larger than max_rows=%d.",
            max_rows,
        )
        return query

    existing = ast.args.get("limit")
    if existing:
        try:
            current = int(existing.args["expression"].this)
            existing.set("expression", exp.Literal.number(min(current, max_rows)))
        except (TypeError, ValueError, AttributeError):
            logger.warning(
                "inject_limit: existing LIMIT is a non-literal expression; "
                "leaving it unchanged. Result set may exceed max_rows=%d.",
                max_rows,
            )
    else:
        ast.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
    return ast.sql(dialect="clickhouse")
