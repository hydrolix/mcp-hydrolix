"""Per-query attribution in hdx_query_admin_comment (HDX-12008).

The static prefix ``User: <dist> version: <v> transport: <t>`` is the pseudo
user-agent every Hydrolix connector writes; the request fields follow it as
further ``key: value`` tokens. Scenario names mirror
openspec/changes/admin-comment-attribution.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import jwt

import mcp_hydrolix.mcp_server as mcp_server_module
from mcp_hydrolix import attribution
from mcp_hydrolix.attribution import (
    ADMIN_COMMENT_MAX_BYTES,
    build_admin_comment,
    gather_request_attribution,
)
from mcp_hydrolix.auth import ServiceAccountToken, UsernamePassword

TRACE = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
STATIC = {"User": "mcp-hydrolix", "version": "0.3.6", "transport": "http"}
STATIC_TEXT = "User: mcp-hydrolix version: 0.3.6 transport: http"


def _bearer_credential(sub: str) -> ServiceAccountToken:
    now = int(time.time())
    token = jwt.encode(
        {"iss": "https://test.invalid", "sub": sub, "iat": now - 5, "exp": now + 300},
        key="x" * 32,
        algorithm="HS256",
    )
    return ServiceAccountToken(token, None)


def _mock_client_ctx():
    mock_client = AsyncMock()
    mock_result = AsyncMock()
    mock_result.column_names = ["id"]
    mock_result.result_rows = [[1]]
    mock_client.query.return_value = mock_result
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_client


class TestQueryCommentComposition:
    def test_renders_composed_comment(self):
        comment = build_admin_comment(
            {
                "User": "mcp-hydrolix",
                "version": "0.3.2",
                "transport": "stdio",
                "sub": "9b2c0c5e-1f0a-4b4e-8a3e-2a1d2c3b4a5f",
                "agent": "claude-code/2.1.0",
                "model": "claude-opus-4-1",
                "session": "sess-1",
                "trace": TRACE,
            }
        )
        assert comment == (
            "User: mcp-hydrolix version: 0.3.2 transport: stdio "
            "sub: 9b2c0c5e-1f0a-4b4e-8a3e-2a1d2c3b4a5f agent: claude-code/2.1.0 "
            f"model: claude-opus-4-1 session: sess-1 trace: {TRACE}"
        )

    def test_static_prefix_unchanged(self):
        assert build_admin_comment(STATIC) == STATIC_TEXT

    def test_omits_empty_fields(self):
        comment = build_admin_comment({**STATIC, "sub": None, "agent": "", "trace": "  "})
        assert comment == STATIC_TEXT
        assert "sub:" not in comment

    def test_sanitizes_values(self):
        comment = build_admin_comment(
            {**STATIC, "agent": "Claude Desktop/1.0 (beta)", "model": "x" * 80, "session": "a:b"}
        )
        assert "agent: Claude_Desktop/1.0__beta_" in comment
        assert f"model: {'x' * 64}" in comment
        assert "x" * 65 not in comment
        assert "session: a_b" in comment

    def test_static_identity_survives_budget(self, monkeypatch):
        fields = {**STATIC, **{key: "v" * 64 for key in attribution.REQUEST_FIELDS}}
        full = build_admin_comment(fields)
        assert len(full.encode("utf-8")) <= ADMIN_COMMENT_MAX_BYTES

        monkeypatch.setattr(attribution, "ADMIN_COMMENT_MAX_BYTES", 120)
        capped = build_admin_comment(fields)
        assert capped.startswith(STATIC_TEXT + " sub: ")
        assert len(capped.encode("utf-8")) <= 120
        assert "agent:" not in capped

        monkeypatch.setattr(attribution, "ADMIN_COMMENT_MAX_BYTES", 10)
        assert build_admin_comment(fields) == STATIC_TEXT

    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_comment_built_per_request(self, mock_create_client):
        mock_ctx, mock_client = _mock_client_ctx()
        mock_create_client.return_value = mock_ctx
        credential = _bearer_credential("user-sub-42")
        with patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=credential):
            await mcp_server_module.execute_query("SELECT 1")
        comment = mock_client.query.call_args.kwargs["settings"]["hdx_query_admin_comment"]
        assert comment.startswith("User: mcp-hydrolix version: ")
        assert " sub: user-sub-42" in comment

    def test_module_constant_keeps_legacy_shape(self):
        assert mcp_server_module.HDX_ADMIN_COMMENT.startswith("User: mcp-hydrolix version: ")
        assert " transport: " in mcp_server_module.HDX_ADMIN_COMMENT
        assert "sub:" not in mcp_server_module.HDX_ADMIN_COMMENT


def _fake_context(*, meta_extra=None, client_name=None, client_version=None, session_id="sid"):
    meta = SimpleNamespace(model_extra=meta_extra or {}) if meta_extra is not None else None
    client_info = SimpleNamespace(name=client_name, version=client_version) if client_name else None
    return SimpleNamespace(
        request_context=SimpleNamespace(meta=meta),
        session=SimpleNamespace(client_params=SimpleNamespace(clientInfo=client_info)),
        session_id=session_id,
    )


class TestAgentAttributionSources:
    def test_headers_take_precedence(self, monkeypatch):
        monkeypatch.setattr(
            attribution,
            "get_http_headers",
            lambda include=None: {
                "X-Hdx-Agent": "gateway-seen/1.0",
                "x-hdx-model": "m1",
                "traceparent": TRACE,
                "mcp-session-id": "http-session",
            },
        )
        monkeypatch.setattr(
            attribution,
            "get_context",
            lambda: _fake_context(
                meta_extra={"agent": "meta/9"}, client_name="init", client_version="2"
            ),
        )
        got = gather_request_attribution(
            _bearer_credential("u1"), transport="http", use_session_id=True
        )
        assert got.sub == "u1"
        assert got.agent == "gateway-seen/1.0"
        assert got.model == "m1"
        assert got.trace == TRACE
        assert got.session == "http-session"

    def test_meta_fallback(self, monkeypatch):
        monkeypatch.setattr(attribution, "get_http_headers", lambda include=None: {})
        monkeypatch.setattr(
            attribution,
            "get_context",
            lambda: _fake_context(
                meta_extra={"agent": "meta-agent/9", "model": "meta-model"},
                client_name="init",
                client_version="2",
            ),
        )
        got = gather_request_attribution(None, transport="http", use_session_id=True)
        assert got.sub is None
        assert got.agent == "meta-agent/9"
        assert got.model == "meta-model"
        assert got.session is None

    def test_client_info_fallback(self, monkeypatch):
        monkeypatch.setattr(attribution, "get_http_headers", lambda include=None: {})
        monkeypatch.setattr(
            attribution,
            "get_context",
            lambda: _fake_context(client_name="claude-code", client_version="2.1.0"),
        )
        got = gather_request_attribution(None, transport="stdio", use_session_id=True)
        assert got.agent == "claude-code/2.1.0"
        assert got.session == "sid"

    def test_sub_from_basic_credential(self, monkeypatch):
        monkeypatch.setattr(attribution, "get_http_headers", lambda include=None: {})
        monkeypatch.setattr(attribution, "get_context", lambda: _fake_context())
        got = gather_request_attribution(
            UsernamePassword(username="alice", password="x"), transport="http", use_session_id=True
        )
        assert got.sub == "alice"

    def test_attribution_never_raises(self, monkeypatch):
        def boom(*_args, **_kwargs):
            raise RuntimeError("no request")

        monkeypatch.setattr(attribution, "get_http_headers", boom)
        monkeypatch.setattr(attribution, "get_context", boom)
        got = gather_request_attribution(
            _bearer_credential("u2"), transport="http", use_session_id=True
        )
        assert got.sub == "u2"
        assert got.agent is None and got.trace is None
