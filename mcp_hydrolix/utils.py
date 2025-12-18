import inspect
import ipaddress
import json
from datetime import datetime, time, date
from decimal import Decimal
from functools import wraps

import fastmcp.utilities.types
from fastmcp.tools.tool import ToolResult


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
