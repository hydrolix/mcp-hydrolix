"""Per-query attribution in hdx_query_admin_comment (HDX-12008).

The static prefix ``User: <dist> version: <v> transport: <t>`` is the pseudo
user-agent every Hydrolix connector writes; the request fields follow it as
further ``key: value`` tokens. Scenario names mirror
openspec/changes/admin-comment-attribution.
"""

from __future__ import annotations

import time
from dataclasses import fields
from unittest.mock import AsyncMock, patch

import jwt

import mcp_hydrolix.mcp_server as mcp_server_module
from mcp_hydrolix import attribution
from mcp_hydrolix.attribution import (
    ADMIN_COMMENT_MAX_BYTES,
    AGENT_FIELDS,
    REQUEST_FIELDS,
    RequestAttribution,
    build_admin_comment,
    render_admin_comment,
)
from mcp_hydrolix.auth import ServiceAccountToken, UsernamePassword
from mcp_hydrolix.middlewares import request_attribution

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
        comment = render_admin_comment(
            "User: mcp-hydrolix version: 0.3.2 transport: stdio",
            "9b2c0c5e-1f0a-4b4e-8a3e-2a1d2c3b4a5f",
            RequestAttribution(
                agent="claude-code/2.1.0",
                model="claude-opus-4-1",
                session="sess-1",
                trace=TRACE,
            ),
        )
        assert comment == (
            "User: mcp-hydrolix version: 0.3.2 transport: stdio "
            "sub: 9b2c0c5e-1f0a-4b4e-8a3e-2a1d2c3b4a5f agent: claude-code/2.1.0 "
            f"session: sess-1 trace: {TRACE} model: claude-opus-4-1"
        )

    def test_static_prefix_unchanged(self):
        assert build_admin_comment(STATIC) == STATIC_TEXT
        assert render_admin_comment(STATIC_TEXT, "", RequestAttribution()) == STATIC_TEXT

    def test_omits_empty_fields(self):
        comment = render_admin_comment(STATIC_TEXT, "", RequestAttribution(agent="", trace="  "))
        assert comment == STATIC_TEXT

    def test_sanitizes_values(self):
        comment = render_admin_comment(
            STATIC_TEXT,
            "svc acct",
            RequestAttribution(agent="Claude Desktop/1.0 (beta)", model="x" * 80, session="a:b"),
        )
        assert "sub: svc_acct" in comment
        assert "agent: Claude_Desktop/1.0__beta_" in comment
        assert f"model: {'x' * 64}" in comment
        assert "x" * 65 not in comment
        assert "session: a_b" in comment

    def test_budget_drops_model_before_join_keys(self, monkeypatch):
        sub = "v" * 64
        full = RequestAttribution(**{key: "v" * 64 for key in AGENT_FIELDS})
        assert len(render_admin_comment(STATIC_TEXT, sub, full).encode()) <= ADMIN_COMMENT_MAX_BYTES

        monkeypatch.setattr(attribution, "ADMIN_COMMENT_MAX_BYTES", 400)
        capped = render_admin_comment(STATIC_TEXT, sub, full)
        assert len(capped.encode("utf-8")) <= 400
        assert "model:" not in capped
        assert "sub: " in capped and "session: " in capped and "trace: " in capped

        monkeypatch.setattr(attribution, "ADMIN_COMMENT_MAX_BYTES", 10)
        assert render_admin_comment(STATIC_TEXT, sub, full) == STATIC_TEXT

    def test_fields_match_vocabulary(self):
        assert tuple(f.name for f in fields(RequestAttribution)) == AGENT_FIELDS
        assert REQUEST_FIELDS == ("sub",) + AGENT_FIELDS
        assert not hasattr(RequestAttribution(), "sub")

    def test_module_constant_keeps_legacy_shape(self):
        assert mcp_server_module.HDX_ADMIN_COMMENT.startswith("User: mcp-hydrolix version: ")
        assert " transport: " in mcp_server_module.HDX_ADMIN_COMMENT
        assert "sub:" not in mcp_server_module.HDX_ADMIN_COMMENT


class TestCommentBuiltPerRequest:
    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_sub_and_agent_from_request(self, mock_create_client):
        mock_ctx, mock_client = _mock_client_ctx()
        mock_create_client.return_value = mock_ctx
        credential = _bearer_credential("user-sub-42")
        token = request_attribution._CURRENT.set(
            RequestAttribution(agent="claude-code/2.1.0", trace=TRACE)
        )
        try:
            with patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=credential):
                await mcp_server_module.execute_query("SELECT 1")
        finally:
            request_attribution._CURRENT.reset(token)
        comment = mock_client.query.call_args.kwargs["settings"]["hdx_query_admin_comment"]
        assert comment.startswith("User: mcp-hydrolix version: ")
        assert f" sub: user-sub-42 agent: claude-code/2.1.0 trace: {TRACE}" in comment

    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_client_authenticates_with_the_attributed_credential(self, mock_create_client):
        mock_ctx, _ = _mock_client_ctx()
        mock_create_client.return_value = mock_ctx
        credential = _bearer_credential("user-sub-43")
        with patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=credential):
            await mcp_server_module.execute_query("SELECT 1")
        assert mock_create_client.call_args.args[1] is credential

    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_sub_from_basic_credential(self, mock_create_client):
        mock_ctx, mock_client = _mock_client_ctx()
        mock_create_client.return_value = mock_ctx
        with patch(
            "mcp_hydrolix.mcp_server.get_request_credential",
            return_value=UsernamePassword(username="alice", password="x"),
        ):
            await mcp_server_module.execute_query("SELECT 1")
        comment = mock_client.query.call_args.kwargs["settings"]["hdx_query_admin_comment"]
        assert comment.endswith(" sub: alice")


class TestCredentialSubject:
    def test_service_account_subject_is_the_sub_claim(self):
        assert _bearer_credential("u1").subject == "u1"

    def test_basic_credential_subject_is_the_username(self):
        assert UsernamePassword(username="alice", password="x").subject == "alice"
