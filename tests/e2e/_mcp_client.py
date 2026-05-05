"""Thin helpers around `fastmcp.Client` for the e2e suite.

The MCP protocol layer (initialize handshake, SSE framing, JSON-RPC envelopes)
is handled by `fastmcp.Client` itself — the same client the server is
implemented against, so client/server parity is by construction.

The `auth` parameter on `StreamableHttpTransport` (and on `Client`) accepts a
bare bearer-token string — fastmcp wraps it with `Authorization: Bearer ...`.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastmcp import Client
from fastmcp.client.client import CallToolResult
from fastmcp.client.transports import StreamableHttpTransport

PROTOCOL_VERSION = "2025-03-26"


def make_client(host: str, token: str, *, timeout: float = 30.0) -> Client:
    """Build a `fastmcp.Client` configured for the cluster's `/mcp` endpoint.

    Caller is responsible for the `async with` context-manager lifecycle.
    """
    url = f"https://{host.rstrip('/')}/mcp"
    transport = StreamableHttpTransport(url=url, auth=token)
    return Client(transport=transport, timeout=timeout)


def login_for_bearer_token(host: str, username: str, password: str, timeout: float = 15.0) -> str:
    url = f"https://{host.rstrip('/')}/config/v1/login"
    resp = httpx.post(
        url,
        json={"username": username, "password": password},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    token = (data.get("auth_token") or {}).get("access_token")
    if not token:
        raise RuntimeError(f"login response missing auth_token.access_token: keys={sorted(data)}")
    return token


def wait_for_endpoint_ready(
    host: str,
    *,
    timeout: float = 120.0,
    poll_interval: float = 2.0,
    success_streak: int = 3,
    probe_timeout: float = 5.0,
) -> None:
    """Poll `/mcp` until it serves a stable, non-infrastructure response.

    A k8s Deployment is reported Ready as soon as its readiness probe passes,
    which can happen well before the front-end LB has finished cutting traffic
    over from old pods or before the new pods' gunicorn workers have fully
    accepted load. During that window, the public `/mcp` endpoint returns 502
    or transient connection errors. Requiring a streak of consecutive non-5xx
    responses (401 is the expected healthy answer for an unauthed POST) avoids
    that race without coupling the test harness to LB internals.
    """
    deadline = time.monotonic() + timeout
    streak = 0
    last_signal = "no-attempts-yet"
    while time.monotonic() < deadline:
        try:
            status, _body = unauthed_initialize_status(host, timeout=probe_timeout)
            last_signal = f"HTTP {status}"
            if status < 500:
                streak += 1
                if streak >= success_streak:
                    return
            else:
                streak = 0
        except (httpx.HTTPError, OSError) as exc:
            last_signal = f"{type(exc).__name__}: {exc}"
            streak = 0
        time.sleep(poll_interval)
    raise TimeoutError(
        f"MCP endpoint at https://{host.rstrip('/')}/mcp did not stabilize within "
        f"{timeout}s (last_signal={last_signal!r}, streak={streak}/{success_streak})"
    )


def unauthed_initialize_status(host: str, timeout: float = 15.0) -> tuple[int, str]:
    """Direct httpx POST to `/mcp` without a bearer token.

    Returns `(status_code, response_text_prefix)`. Kept on raw httpx because the
    401 signal is clearer at the HTTP layer than as a wrapped fastmcp exception.
    """
    url = f"https://{host.rstrip('/')}/mcp"
    payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mcp-hydrolix-e2e-401-probe", "version": "0.1"},
        },
        "id": 1,
    }
    resp = httpx.post(
        url,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        timeout=timeout,
    )
    return resp.status_code, resp.text[:300]


def parsed_payload(result: CallToolResult) -> Any:
    """Return the canonical MCP-spec JSON payload from a CallToolResult.

    All four mcp-hydrolix tools return Pydantic-modeled responses, so
    `structured_content` is always populated. We avoid `result.data` because
    fastmcp's typed-data synthesis is unreliable when the server's output
    schema is permissive (e.g. `Table` uses `model_serializer(mode="wrap")`
    that strips None/empty fields, collapsing the JSON-Schema item shape to
    `additionalProperties: true` and causing the client to emit empty
    `Root()` dataclasses).
    """
    assert result.structured_content is not None, (
        f"expected structured_content on tool result; got {result!r}"
    )
    return result.structured_content
