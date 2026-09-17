"""Resolve the request half of the attribution once per MCP request (HDX-12008).

This is the transport adapter for ``mcp_hydrolix.attribution``. It reads the
HTTP headers, the request's MCP ``_meta``, the session's ``initialize`` client
info and the session id inside the middleware, the one place where "this is
the request's ``_meta``" is unambiguous, and stores the result in a context
variable that ``execute_query`` reads for every query the request issues. One
tool call can issue several queries (a DESCRIBE per referenced table plus the
statement), so this runs once per request, not once per query.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Final, Optional

from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware, MiddlewareContext

from mcp_hydrolix.attribution import RequestAttribution, resolve_request_attribution

logger = logging.getLogger(__name__)

# Transports whose session object lives for the whole client connection, so the
# session id names one agent run. FastMCP generates it server-side there; the
# client never sees it. On stateless streamable HTTP FastMCP would mint a fresh
# UUID per request (pure log cardinality) unless the client sends
# Mcp-Session-Id, so the field is omitted and trace is the join key instead.
SESSION_TRANSPORTS: Final[frozenset[str]] = frozenset({"stdio", "sse"})

_CURRENT: ContextVar[RequestAttribution] = ContextVar(
    "mcp_hydrolix_request_attribution", default=RequestAttribution()
)


def current_attribution() -> RequestAttribution:
    """The attribution resolved for the current MCP request; empty outside one."""
    return _CURRENT.get()


def _client_info(ctx: Any) -> Optional[str]:
    """``<name>/<version>`` from the session's ``initialize`` params, when the transport kept them."""
    info = getattr(getattr(ctx.session, "client_params", None), "clientInfo", None)
    name = getattr(info, "name", None)
    if not name:
        return None
    version = getattr(info, "version", None)
    return f"{name}/{version}" if version else str(name)


def attribution_for(context: MiddlewareContext) -> RequestAttribution:
    """Extract the request inputs from FastMCP and resolve them; never raises."""
    # Lowercased, empty outside an HTTP request, and it never raises.
    headers = get_http_headers()
    meta = getattr(getattr(context, "message", None), "meta", None)
    meta_extra = getattr(meta, "model_extra", None) or {}
    client_info = session_id = None
    ctx = getattr(context, "fastmcp_context", None)
    if ctx is not None:
        try:
            client_info = _client_info(ctx)
            if ctx.transport in SESSION_TRANSPORTS:
                session_id = ctx.session_id
        except Exception:
            logger.debug("attribution: session fields unavailable", exc_info=True)
    return resolve_request_attribution(headers, meta_extra, client_info, session_id)


class RequestAttributionMiddleware(Middleware):
    """Resolve the request's attribution once and expose it to the queries it runs."""

    async def on_request(self, context: MiddlewareContext, call_next):
        token = _CURRENT.set(attribution_for(context))
        try:
            return await call_next(context)
        finally:
            _CURRENT.reset(token)
