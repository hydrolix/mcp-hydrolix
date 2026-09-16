"""Per-query attribution in the existing Hydrolix query settings (HDX-12008, HDX-12410).

Scenario names mirror openspec/changes/gateway-hardening/specs/query-admin-comment.
"""

from __future__ import annotations

import importlib
import logging
import time
from importlib.metadata import PackageNotFoundError, version as _real_pkg_version
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

import mcp_hydrolix.mcp_server as mcp_server_module
from mcp_hydrolix import attribution
from mcp_hydrolix.attribution import (
    ADMIN_COMMENT_MAX_BYTES,
    PURPOSE_MAX_CHARS,
    build_admin_comment,
    gather_request_attribution,
    sanitize_purpose,
)
from mcp_hydrolix.auth import ServiceAccountToken
from mcp_hydrolix.mcp_env import HydrolixConfig

TRACE = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


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
                "app": "mcp-hydrolix/0.3.2",
                "transport": "stdio",
                "user": "9b2c0c5e-1f0a-4b4e-8a3e-2a1d2c3b4a5f",
                "agent": "claude-code/2.1.0",
                "model": "claude-opus-4-1",
                "session": "sess-1",
                "trace": TRACE,
            }
        )
        assert comment == (
            "app=mcp-hydrolix/0.3.2 transport=stdio user=9b2c0c5e-1f0a-4b4e-8a3e-2a1d2c3b4a5f "
            f"agent=claude-code/2.1.0 model=claude-opus-4-1 session=sess-1 trace={TRACE}"
        )

    def test_omits_empty_fields(self):
        comment = build_admin_comment(
            {"app": "mcp-hydrolix/0.3.2", "transport": "http", "user": None, "agent": ""}
        )
        assert comment == "app=mcp-hydrolix/0.3.2 transport=http"
        assert "user=" not in comment

    def test_sanitizes_values(self):
        comment = build_admin_comment(
            {"app": "mcp-hydrolix/0.3.2", "agent": "Claude Desktop/1.0 (beta)", "model": "x" * 80}
        )
        assert "agent=Claude_Desktop/1.0__beta_" in comment
        assert f"model={'x' * 64}" in comment
        assert "x" * 65 not in comment

    def test_caps_comment_at_budget(self, monkeypatch):
        # Seven 64-character values render to 499 bytes, so the real budget can only
        # bite on a future field; shrink it here to prove trailing fields drop first.
        fields = {key: "v" * 64 for key in ("app", "transport", "user", "agent", "model")}
        fields["session"] = "s" * 64
        fields["trace"] = "t" * 64
        full = build_admin_comment(fields)
        assert len(full.encode("utf-8")) == 499 <= ADMIN_COMMENT_MAX_BYTES

        monkeypatch.setattr(attribution, "ADMIN_COMMENT_MAX_BYTES", 400)
        capped = build_admin_comment(fields)
        assert len(capped.encode("utf-8")) <= 400
        assert capped.startswith("app=")
        assert "model=" in capped
        assert "session=" not in capped and "trace=" not in capped

    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_comment_built_per_request(self, mock_create_client):
        mock_ctx, mock_client = _mock_client_ctx()
        mock_create_client.return_value = mock_ctx
        credential = _bearer_credential("user-sub-42")
        with patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=credential):
            await mcp_server_module.execute_query("SELECT 1")
        settings = mock_client.query.call_args.kwargs["settings"]
        comment = settings["hdx_query_admin_comment"]
        assert comment.startswith("app=mcp-hydrolix/")
        assert " user=user-sub-42" in comment
        assert "User:" not in comment


class TestVersionResolution:
    def test_version_metadata_available(self):
        assert mcp_server_module._resolve_server_version() == _real_pkg_version("mcp-hydrolix")

    def test_version_metadata_unavailable(self, caplog):
        with patch(
            "mcp_hydrolix.mcp_server._pkg_version",
            side_effect=PackageNotFoundError("mcp-hydrolix"),
        ):
            with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
                result = mcp_server_module._resolve_server_version()
        assert result == "unknown"
        assert any("mcp-hydrolix" in record.getMessage() for record in caplog.records)


@pytest.fixture
def reload_server_after_test():
    yield
    importlib.reload(mcp_server_module)


class TestTransportResolution:
    def test_transport_reflects_config(self, monkeypatch, reload_server_after_test):
        monkeypatch.setenv("HYDROLIX_MCP_SERVER_TRANSPORT", "sse")
        with patch("importlib.metadata.version", MagicMock(return_value="0.3.2")):
            module = importlib.reload(mcp_server_module)
        assert module.HDX_ADMIN_COMMENT == "app=mcp-hydrolix/0.3.2 transport=sse"


class TestQueryPurposeComment:
    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_purpose_sets_query_comment(self, mock_create_client):
        mock_ctx, mock_client = _mock_client_ctx()
        mock_create_client.return_value = mock_ctx
        await mcp_server_module.execute_query("SELECT 1", comment="  top errors\nlast hour ")
        settings = mock_client.query.call_args.kwargs["settings"]
        assert settings["hdx_query_comment"] == "top errors last hour"

    def test_purpose_truncated_to_budget(self):
        assert len(sanitize_purpose("p" * 1000)) == PURPOSE_MAX_CHARS

    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_no_purpose_no_comment(self, mock_create_client):
        mock_ctx, mock_client = _mock_client_ctx()
        mock_create_client.return_value = mock_ctx
        await mcp_server_module.execute_query("SELECT 1")
        assert "hdx_query_comment" not in mock_client.query.call_args.kwargs["settings"]


class TestQueryLabel:
    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_label_sent_as_transport_setting_when_configured(
        self, mock_create_client, monkeypatch
    ):
        monkeypatch.setenv("HYDROLIX_QUERY_LABEL", "mcp")
        mock_ctx, mock_client = _mock_client_ctx()
        mock_create_client.return_value = mock_ctx
        await mcp_server_module.execute_query("SELECT 1 FROM db.t LIMIT 5")
        assert mock_client.query.call_args.kwargs["settings"]["hdx_query_label"] == "mcp"
        # Never inline: an inline SETTINGS clause is refused under readonly=1
        # (ClickHouse code 164, verified against the integration stack).
        assert mock_client.query.call_args.args[0] == "SELECT 1 FROM db.t LIMIT 5"

    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_label_absent_by_default(self, mock_create_client, monkeypatch):
        monkeypatch.delenv("HYDROLIX_QUERY_LABEL", raising=False)
        mock_ctx, mock_client = _mock_client_ctx()
        mock_create_client.return_value = mock_ctx
        await mcp_server_module.execute_query("SELECT 1")
        assert "hdx_query_label" not in mock_client.query.call_args.kwargs["settings"]

    def test_label_rejects_unsafe_value(self, monkeypatch):
        monkeypatch.setenv("HYDROLIX_QUERY_LABEL", "mcp'; DROP")
        with pytest.raises(ValueError, match="HYDROLIX_QUERY_LABEL"):
            HydrolixConfig()


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
        assert got.user == "u1"
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
        assert got.user is None
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

    def test_user_from_basic_credential(self, monkeypatch):
        from mcp_hydrolix.auth import UsernamePassword

        monkeypatch.setattr(attribution, "get_http_headers", lambda include=None: {})
        monkeypatch.setattr(attribution, "get_context", lambda: _fake_context())
        got = gather_request_attribution(
            UsernamePassword(username="alice", password="x"), transport="http", use_session_id=True
        )
        assert got.user == "alice"

    def test_attribution_never_raises(self, monkeypatch):
        def boom(*_args, **_kwargs):
            raise RuntimeError("no request")

        monkeypatch.setattr(attribution, "get_http_headers", boom)
        monkeypatch.setattr(attribution, "get_context", boom)
        got = gather_request_attribution(
            _bearer_credential("u2"), transport="http", use_session_id=True
        )
        assert got.user == "u2"
        assert got.agent is None and got.trace is None
