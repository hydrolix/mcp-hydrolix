import inspect
from datetime import datetime, time
from decimal import Decimal
from functools import wraps
from typing import Protocol

import fastmcp.utilities.types
from fastmcp.tools.tool import ToolResult
from fastmcp import Context
import json
import ipaddress


class ContextToolCallable(Protocol):
    def __call__(self, ctx: Context, *args, **kwargs): ...


class ExtendedEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ipaddress.IPv4Address):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.time()
        if isinstance(obj, time):
            return obj.hour * 3600 + obj.minute * 60 + obj.second + obj.microsecond / 1_000_000
        if isinstance(obj, bytes):
            return obj.decode()
        if isinstance(obj, Decimal):
            return str(obj)
        return json.JSONEncoder.default(self, obj)


def with_serializer(fn):
    """Decorator to apply custom serialization to tool output."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        result = fn(*args, **kwargs)
        enc = json.dumps(result, cls=ExtendedEncoder)
        return ToolResult(content=enc, structured_content=json.loads(enc))

    @wraps(fn)
    async def async_wrapper(*args, **kwargs):
        result = await fn(*args, **kwargs)
        enc = json.dumps(result, cls=ExtendedEncoder)
        return ToolResult(content=enc, structured_content=json.loads(enc))

    new_fn = fastmcp.utilities.types.create_function_without_params(fn, ["ctx"])
    sig = inspect.signature(new_fn)
    async_wrapper.__signature__ = sig
    wrapper.__signature__ = sig
    return async_wrapper if inspect.iscoroutinefunction(fn) else wrapper
