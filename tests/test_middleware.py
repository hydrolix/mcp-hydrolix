"""Unit tests for ASGI hardening middleware.

Covers three middlewares that sit in front of the MCP app when running under
uvicorn: request timeout (504), backpressure (503), and request body size limit
(413). Tests exercise the raw ASGI interface so they can run without binding a
socket.
"""

from __future__ import annotations

import asyncio
from typing import Any


async def _collect_response(middleware, scope: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Drive an ASGI middleware once and return (messages_sent, receive_calls).

    Uses a trivial ``receive`` that returns an empty body request.
    """

    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    await middleware(scope, receive, send)
    return sent, []


def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict[str, Any]:
    return {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": headers or [],
    }


# ---------------------------------------------------------------------------
# RequestTimeoutMiddleware
# ---------------------------------------------------------------------------


def test_request_timeout_middleware_passes_through_fast_responses():
    from mcp_hydrolix.middleware import RequestTimeoutMiddleware

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestTimeoutMiddleware(app, timeout=1.0)
    sent, _ = asyncio.run(_collect_response(middleware, _http_scope()))

    statuses = [m["status"] for m in sent if m["type"] == "http.response.start"]
    assert statuses == [200]


def test_request_timeout_middleware_returns_504_on_timeout():
    from mcp_hydrolix.middleware import RequestTimeoutMiddleware

    async def app(scope, receive, send):
        await asyncio.sleep(1.0)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestTimeoutMiddleware(app, timeout=0.01)
    sent, _ = asyncio.run(_collect_response(middleware, _http_scope()))

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1, "expected an http.response.start message"
    assert starts[0]["status"] == 504


def test_request_timeout_middleware_returns_504_on_timeout_after_headers():
    from mcp_hydrolix.middleware import RequestTimeoutMiddleware

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await asyncio.sleep(2.0)
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestTimeoutMiddleware(app, timeout=0.2)
    sent, _ = asyncio.run(_collect_response(middleware, _http_scope()))

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1, "expected an http.response.start message"
    assert starts[0]["status"] == 504


def test_request_timeout_middleware_ignores_non_http_scope():
    from mcp_hydrolix.middleware import RequestTimeoutMiddleware

    called = {"count": 0}

    async def app(scope, receive, send):
        called["count"] += 1

    middleware = RequestTimeoutMiddleware(app, timeout=0.01)

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(message):
        pass

    asyncio.run(middleware({"type": "lifespan"}, receive, send))
    assert called["count"] == 1
