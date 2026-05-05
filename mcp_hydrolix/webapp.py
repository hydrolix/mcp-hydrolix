"""ASGI entrypoint for the MCP Hydrolix HTTP server.

Exposes a ``create_app`` factory that uvicorn imports via the
``"mcp_hydrolix.webapp:create_app"`` import string with ``factory=True``.
Keeping the wrapped ASGI app behind an import string is what lets
``uvicorn.run(..., workers=N)`` work — uvicorn's multi-worker supervisor
requires a re-importable callable so each child process can rebuild the app.
"""

from .mcp_env import get_config
from .mcp_server import mcp
from .middleware import RequestTimeoutMiddleware


def create_app():
    """Build the wrapped ASGI app. Invoked once per uvicorn worker."""
    config = get_config()
    app = mcp.http_app(
        path="/mcp",
        stateless_http=True,
        transport=config.mcp_server_transport,
    )
    app = RequestTimeoutMiddleware(app, timeout=config.mcp_timeout)
    return app
