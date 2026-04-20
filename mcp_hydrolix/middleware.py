"""ASGI middleware for production hardening."""

import asyncio
import logging

from starlette.responses import PlainTextResponse

logger = logging.getLogger(__name__)


class RequestTimeoutMiddleware:
    """Aborts HTTP requests that exceed `timeout` seconds and returns 504.

    Fills a gap in uvicorn: it has no per-request handler timeout. Its
    `timeout_keep_alive` (default 5s) only governs idle Keep-Alive connections
    *between* requests, and `timeout_graceful_shutdown` only applies during
    server shutdown. Neither bounds how long an individual handler may run, so a
    hung tool call or downstream ClickHouse query will pin a worker's event loop
    indefinitely.
    See https://www.uvicorn.org/settings/#timeouts.

    This parallels the role gunicorn's worker `--timeout` (default 30s) played
    previously: "Workers silent for more than this many seconds are killed and
    restarted." Gunicorn's mechanism is a watchdog -- the arbiter `SIGKILL`s
    the worker and the client gets a reset connection with no HTTP status.
    See https://docs.gunicorn.org/en/stable/settings.html#timeout.

    This middleware is a bit more gentle: it kills ONLY the offending request, and
    does so by sending a `504 Gateway Timeout` to the client if possible, leaving other
    requests in progress.

    If the timeout fires *after* the wrapped app has already emitted
    `http.response.start`, we cannot rewrite the status line -- ASGI forbids a
    second start message. In that case we log a warning and return; the
    underlying server truncates the response, which HTTP/1.1 (RFC 9112) and
    HTTP/2 both define as a client-detectable (legal) incomplete response.
    """

    def __init__(self, app, timeout: float = 120.0):
        self.app = app
        self.timeout = timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_wrapper(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await asyncio.wait_for(self.app(scope, receive, send_wrapper), timeout=self.timeout)
        except asyncio.TimeoutError:
            if not started:
                await PlainTextResponse("Gateway Timeout", status_code=504)(scope, receive, send)
            else:
                logger.warning(
                    "Request timeout after response started: %s %s",
                    scope.get("method"),
                    scope.get("path"),
                )
