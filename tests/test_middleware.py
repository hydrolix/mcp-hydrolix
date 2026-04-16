"""Unit tests for ASGI hardening middleware.

Covers three middlewares that sit in front of the MCP app when running under
uvicorn: request timeout (504), backpressure (503), and request body size limit
(413). Tests exercise the raw ASGI interface so they can run without binding a
socket.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest


pytestmark = pytest.mark.xfail(
    reason="HDX-10675: awaiting implementation",
    strict=True,
)


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
    assert starts, "expected an http.response.start message"
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


# ---------------------------------------------------------------------------
# BackpressureMiddleware
# ---------------------------------------------------------------------------


def test_backpressure_middleware_allows_requests_under_threshold():
    from mcp_hydrolix.middleware import BackpressureMiddleware

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = BackpressureMiddleware(app, limit=10, threshold=0.9)
    sent, _ = asyncio.run(_collect_response(middleware, _http_scope()))

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert starts and starts[0]["status"] == 200


def test_backpressure_middleware_returns_503_with_retry_after_when_saturated():
    from mcp_hydrolix.middleware import BackpressureMiddleware

    # limit=10, threshold=0.9 -> soft_limit=9
    saturated_started = asyncio.Event()
    release = asyncio.Event()

    async def slow_app(scope, receive, send):
        saturated_started.set()
        await release.wait()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = BackpressureMiddleware(slow_app, limit=10, threshold=0.9)

    async def drive():
        # Fill up to the soft limit with in-flight requests.
        tasks = []
        for _ in range(9):
            tasks.append(asyncio.create_task(_collect_response(middleware, _http_scope())))
        # Give them a tick to enter the app.
        await asyncio.sleep(0)
        await saturated_started.wait()

        # This one should be rejected with 503.
        rejected, _ = await _collect_response(middleware, _http_scope())

        release.set()
        await asyncio.gather(*tasks)
        return rejected

    sent = asyncio.run(drive())
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert starts and starts[0]["status"] == 503
    header_map = {k: v for k, v in starts[0]["headers"]}
    assert header_map.get(b"retry-after") == b"1"


def test_backpressure_middleware_decrements_active_count_after_completion():
    from mcp_hydrolix.middleware import BackpressureMiddleware

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = BackpressureMiddleware(app, limit=10, threshold=0.9)
    # Drive 20 requests serially; none should be rejected because each completes
    # before the next starts.
    for _ in range(20):
        sent, _ = asyncio.run(_collect_response(middleware, _http_scope()))
        starts = [m for m in sent if m["type"] == "http.response.start"]
        assert starts and starts[0]["status"] == 200


# ---------------------------------------------------------------------------
# RequestBodySizeLimitMiddleware
# ---------------------------------------------------------------------------


def test_request_body_size_limit_allows_small_bodies():
    from mcp_hydrolix.middleware import RequestBodySizeLimitMiddleware

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestBodySizeLimitMiddleware(app, max_bytes=1024)
    scope = _http_scope([(b"content-length", b"512")])
    sent, _ = asyncio.run(_collect_response(middleware, scope))

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert starts and starts[0]["status"] == 200


def test_request_body_size_limit_rejects_oversized_content_length():
    from mcp_hydrolix.middleware import RequestBodySizeLimitMiddleware

    async def app(scope, receive, send):
        raise AssertionError("inner app should not be called when content length exceeds limit")

    middleware = RequestBodySizeLimitMiddleware(app, max_bytes=1024)
    scope = _http_scope([(b"content-length", b"2048")])
    sent, _ = asyncio.run(_collect_response(middleware, scope))

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert starts and starts[0]["status"] == 413


def test_request_body_size_limit_ignores_invalid_content_length():
    from mcp_hydrolix.middleware import RequestBodySizeLimitMiddleware

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestBodySizeLimitMiddleware(app, max_bytes=1024)
    scope = _http_scope([(b"content-length", b"not-a-number")])
    sent, _ = asyncio.run(_collect_response(middleware, scope))

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert starts and starts[0]["status"] == 200


def test_request_body_size_limit_allows_missing_content_length():
    from mcp_hydrolix.middleware import RequestBodySizeLimitMiddleware

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestBodySizeLimitMiddleware(app, max_bytes=1024)
    sent, _ = asyncio.run(_collect_response(middleware, _http_scope()))

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert starts and starts[0]["status"] == 200
