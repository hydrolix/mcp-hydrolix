"""The request half of the attribution is resolved once per MCP request (HDX-12008).

Scenario names mirror openspec/changes/admin-comment-attribution.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mcp_hydrolix import request_attribution
from mcp_hydrolix.attribution import RequestAttribution
from mcp_hydrolix.request_attribution import (
    RequestAttributionMiddleware,
    attribution_for,
    current_attribution,
)

TRACE = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


def _ctx(*, transport="stdio", session_id="sid", client_name=None, client_version=None):
    client_info = SimpleNamespace(name=client_name, version=client_version) if client_name else None
    return SimpleNamespace(
        transport=transport,
        session_id=session_id,
        session=SimpleNamespace(client_params=SimpleNamespace(clientInfo=client_info)),
    )


def _context(*, meta=None, ctx=None):
    message = SimpleNamespace(meta=SimpleNamespace(model_extra=meta) if meta is not None else None)
    return SimpleNamespace(method="tools/call", message=message, fastmcp_context=ctx)


@pytest.fixture(autouse=True)
def no_http_request(monkeypatch):
    monkeypatch.setattr(request_attribution, "get_http_headers", lambda: {})


class TestAgentAttributionSources:
    def test_headers_take_precedence(self, monkeypatch):
        monkeypatch.setattr(
            request_attribution,
            "get_http_headers",
            lambda: {"x-hdx-agent": "gateway-seen/1.0", "x-hdx-model": "m1", "traceparent": TRACE},
        )
        got = attribution_for(
            _context(
                meta={"io.hydrolix/agent": "meta/9"},
                ctx=_ctx(transport="streamable-http", client_name="init", client_version="2"),
            )
        )
        assert got.agent == "gateway-seen/1.0"
        assert got.model == "m1"
        assert got.trace == TRACE

    def test_prefixed_meta_keys_then_bare(self):
        got = attribution_for(
            _context(
                meta={"io.hydrolix/agent": "ns/9", "agent": "bare/1", "model": "bare-model"},
                ctx=_ctx(transport="streamable-http"),
            )
        )
        assert got.agent == "ns/9"
        assert got.model == "bare-model"

    def test_client_info_fallback_and_stdio_session(self):
        got = attribution_for(
            _context(
                meta={},
                ctx=_ctx(transport="stdio", client_name="claude-code", client_version="2.1.0"),
            )
        )
        assert got.agent == "claude-code/2.1.0"
        assert got.session == "sid"

    def test_sse_keeps_the_session(self):
        assert attribution_for(_context(ctx=_ctx(transport="sse"))).session == "sid"

    def test_stateless_http_has_no_session(self):
        assert attribution_for(_context(ctx=_ctx(transport="streamable-http"))).session is None

    def test_no_context_yields_empty_attribution(self):
        assert attribution_for(_context(ctx=None)) == RequestAttribution()

    def test_sub_is_never_resolved_here(self):
        got = attribution_for(_context(ctx=_ctx(client_name="c", client_version="1")))
        assert got.sub is None

    def test_session_fields_failing_do_not_fail_attribution(self, monkeypatch):
        monkeypatch.setattr(
            request_attribution, "get_http_headers", lambda: {"x-hdx-agent": "gw/1"}
        )

        class Broken:
            @property
            def transport(self):
                raise RuntimeError("no session")

            @property
            def session(self):
                raise RuntimeError("no session")

        got = attribution_for(_context(ctx=Broken()))
        assert got.agent == "gw/1"
        assert got.session is None


class TestResolvedOncePerRequest:
    async def test_middleware_sets_and_resets_the_context(self, monkeypatch):
        monkeypatch.setattr(
            request_attribution, "get_http_headers", lambda: {"x-hdx-agent": "gw/1"}
        )
        seen = {}

        async def call_next(_context):
            seen["agent"] = current_attribution().agent
            return "ok"

        result = await RequestAttributionMiddleware().on_request(_context(ctx=None), call_next)
        assert result == "ok"
        assert seen["agent"] == "gw/1"
        assert current_attribution() == RequestAttribution()

    async def test_context_is_reset_when_the_request_fails(self, monkeypatch):
        monkeypatch.setattr(
            request_attribution, "get_http_headers", lambda: {"x-hdx-agent": "gw/1"}
        )

        async def call_next(_context):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await RequestAttributionMiddleware().on_request(_context(ctx=None), call_next)
        assert current_attribution() == RequestAttribution()
