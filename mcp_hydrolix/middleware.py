"""ASGI middleware for production hardening."""

import asyncio

from starlette.responses import PlainTextResponse


class RequestTimeoutMiddleware:
    """Aborts HTTP requests that exceed ``timeout`` seconds and returns 504."""

    def __init__(self, app, timeout: float = 120.0):
        self.app = app
        self.timeout = timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await asyncio.wait_for(self.app(scope, receive, send), timeout=self.timeout)
        except asyncio.TimeoutError:
            await PlainTextResponse("Gateway Timeout", status_code=504)(scope, receive, send)


class BackpressureMiddleware:
    """Returns 503 with Retry-After before uvicorn's ``limit_concurrency`` drops connections silently."""

    def __init__(self, app, limit: int = 100, threshold: float = 0.9):
        self.app = app
        self._soft_limit = int(limit * threshold)
        self._active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self._active >= self._soft_limit:
            await PlainTextResponse(
                "Service Unavailable",
                status_code=503,
                headers={"retry-after": "1"},
            )(scope, receive, send)
            return

        self._active += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self._active -= 1


class RequestBodySizeLimitMiddleware:
    """Rejects HTTP requests whose Content-Length exceeds a configured limit."""

    def __init__(self, app, max_bytes: int = 1_048_576):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    await PlainTextResponse("Request Entity Too Large", status_code=413)(
                        scope, receive, send
                    )
                    return
            except ValueError:
                pass

        await self.app(scope, receive, send)
