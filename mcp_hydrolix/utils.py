import inspect
import ipaddress
import json
import logging
from datetime import date, datetime, time
from decimal import Decimal
from functools import wraps

import fastmcp.utilities.types
from fastmcp.tools.tool import ToolResult
from toon_format import encode as toon_encode

logger = logging.getLogger(__name__)


class ExtendedEncoder(json.JSONEncoder):
    """Extends JSONEncoder to apply custom serialization of CH data types."""

    def default(self, obj):
        if isinstance(obj, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.timestamp()
        if isinstance(obj, (date, time)):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def _serialize_query_result(result: dict) -> tuple[str, dict]:
    """
    Serialize a HdxQueryResult to TOON format for LLM consumption.

    Normalizes CH-specific types (datetime, Decimal, IPv4/6Address, bytes) via
    ExtendedEncoder, converts the columnar structure to a list of records, then
    encodes as TOON. Falls back to JSON if TOON encoding fails.

    :returns: (encoded_string, structured_dict) tuple
    """
    normalized: dict = json.loads(json.dumps(result, cls=ExtendedEncoder))

    records = [dict(zip(normalized["columns"], row)) for row in normalized["rows"]]
    try:
        return toon_encode(records), normalized
    except Exception as exc:
        logger.warning("TOON encoding failed, falling back to JSON: %s", exc)
        return json.dumps(records), normalized


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
