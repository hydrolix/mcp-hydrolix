import inspect
import ipaddress
import json
import logging
from datetime import date, datetime, time
from decimal import Decimal
from functools import wraps

import fastmcp.utilities.types
from fastmcp.tools.tool import ToolResult

logger = logging.getLogger(__name__)


class ExtendedEncoder(json.JSONEncoder):
    """Extends JSONEncoder to apply custom serialization of CH data types."""

    def default(self, obj):
        if isinstance(obj, ipaddress.IPv4Address):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.timestamp()
        if isinstance(obj, (date, time)):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode()
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def with_serializer(fn):
    """
    Decorator to apply custom serialization to CH query tool result.
    Should be applied as a first decorator of the tool function.

    :returns: sync/async wrapper of mcp tool function
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        """
        Sync wrapper of mcpt tool `fn` function.
        Function should return a dict or None.

        :returns: ToolResult object with text-serialized and structured content.
        """
        result = fn(*args, **kwargs)
        if not isinstance(result, dict):
            result = {"result": result}
        enc = json.dumps(result, cls=ExtendedEncoder)
        return ToolResult(content=enc, structured_content=json.loads(enc))

    @wraps(fn)
    async def async_wrapper(*args, **kwargs):
        """
        Async wrapper of mcp tool `fn` function.
        Function should return a dict or None.

        :returns: ToolResult object with text-serialized and structured content.
        """
        result = await fn(*args, **kwargs)
        if not isinstance(result, dict):
            result = {"result": result}
        enc = json.dumps(result, cls=ExtendedEncoder)
        return ToolResult(content=enc, structured_content=json.loads(enc))

    # TODO: remove next signature fix code when a new fastmcp released (https://github.com/jlowin/fastmcp/issues/2524)
    new_fn = fastmcp.utilities.types.create_function_without_params(fn, ["ctx"])
    sig = inspect.signature(new_fn)
    async_wrapper.__signature__ = sig
    wrapper.__signature__ = sig
    return async_wrapper if inspect.iscoroutinefunction(fn) else wrapper


def inject_limit(query: str, max_rows: int) -> str:
    """Rewrite query to enforce a row limit, taking the minimum of any existing LIMIT.

    Returns the rewritten SQL string. If the query cannot be parsed by sqlglot, logs a
    warning and returns the original query unchanged so the caller still executes something.
    """
    import sqlglot
    import sqlglot.errors as sqlglot_errors
    import sqlglot.expressions as exp

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
