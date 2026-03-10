import inspect
import ipaddress
import json
import logging
from datetime import date, datetime, time
from decimal import Decimal
from functools import wraps
from typing import Any

import fastmcp.utilities.types
from fastmcp.tools.tool import ToolResult
from toon_format import encode as toon_encode

logger = logging.getLogger(__name__)


def _normalize_value(val: Any) -> Any:
    """Convert a CH-specific type to a TOON/JSON-safe primitive."""
    if isinstance(val, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        return str(val)
    if isinstance(val, datetime):
        return val.timestamp()
    if isinstance(val, (date, time)):
        return val.isoformat()
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    if isinstance(val, Decimal):
        return str(val)
    return val


def _serialize_query_result(result: dict) -> tuple[str, dict]:
    """
    Serialize a HdxQueryResult to TOON format for LLM consumption.

    Normalizes CH-specific types (datetime, Decimal, IPv4/6Address, bytes) directly,
    converts the columnar structure to a list of records, then encodes as TOON.
    Falls back to JSON if TOON encoding fails.

    :returns: (encoded_string, structured_dict) tuple
    """
    columns = result["columns"]
    records = [dict(zip(columns, (_normalize_value(v) for v in row))) for row in result["rows"]]
    structured = {"columns": columns, "rows": [list(record.values()) for record in records]}
    try:
        return toon_encode(records), structured
    except Exception as exc:
        logger.warning("TOON encoding failed, falling back to JSON: %s", exc)
        return json.dumps(records), structured


def with_serializer(fn):
    """
    Decorator to serialize HdxQueryResult to TOON for LLM consumption.

    Must be the innermost decorator (directly above the function definition,
    below @mcp.tool()).

    :returns: sync/async wrapper of mcp tool function
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        result = fn(*args, **kwargs)
        toon_str, structured = _serialize_query_result(result)
        return ToolResult(content=toon_str, structured_content=structured)

    @wraps(fn)
    async def async_wrapper(*args, **kwargs):
        result = await fn(*args, **kwargs)
        toon_str, structured = _serialize_query_result(result)
        return ToolResult(content=toon_str, structured_content=structured)

    # TODO: remove next signature fix code when a new fastmcp released (https://github.com/jlowin/fastmcp/issues/2524)
    new_fn = fastmcp.utilities.types.create_function_without_params(fn, ["ctx"])
    sig = inspect.signature(new_fn)
    async_wrapper.__signature__ = sig
    wrapper.__signature__ = sig
    return async_wrapper if inspect.iscoroutinefunction(fn) else wrapper
