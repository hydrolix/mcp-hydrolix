"""The caller's purpose rides every user query as hdx_query_comment (HDX-12008)."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

import mcp_hydrolix.mcp_server as mcp_server_module
from mcp_hydrolix.models import HdxQueryResult
from mcp_hydrolix.utils import PURPOSE_MAX_CHARS, sanitize_purpose


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


class TestSanitizePurpose:
    def test_collapses_whitespace(self):
        assert sanitize_purpose("  top errors\nlast hour ") == "top errors last hour"

    def test_truncates_to_budget(self):
        assert len(sanitize_purpose("p" * 1000)) == PURPOSE_MAX_CHARS

    def test_empty_is_none(self):
        assert sanitize_purpose(None) is None
        assert sanitize_purpose("   ") is None


class TestQueryPurposeComment:
    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_purpose_sets_query_comment(self, mock_create_client):
        mock_ctx, mock_client = _mock_client_ctx()
        mock_create_client.return_value = mock_ctx
        await mcp_server_module.execute_query("SELECT 1", comment="  top errors\nlast hour ")
        settings = mock_client.query.call_args.kwargs["settings"]
        assert settings["hdx_query_comment"] == "top errors last hour"

    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_no_purpose_no_comment(self, mock_create_client):
        mock_ctx, mock_client = _mock_client_ctx()
        mock_create_client.return_value = mock_ctx
        await mcp_server_module.execute_query("SELECT 1")
        assert "hdx_query_comment" not in mock_client.query.call_args.kwargs["settings"]

    @patch(
        "mcp_hydrolix.mcp_server._query_targets_summary_table",
        new_callable=AsyncMock,
        return_value=False,
    )
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=HdxQueryResult(columns=["a"], rows=[[1]]),
    )
    async def test_run_select_query_forwards_purpose(self, mock_execute, _summary):
        await inspect.unwrap(mcp_server_module.run_select_query)(
            "SELECT a FROM db.t WHERE ts > now() - INTERVAL 1 HOUR", purpose="why"
        )
        assert mock_execute.call_args.kwargs["comment"] == "why"
