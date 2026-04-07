"""Tests for query settings applied by run_select_query.

Verifies that:
- hdx_query_timerange_required is always True on the final query
- hdx_query_max_timerange_sec is set to the configured max_raw_timerange only when the query
  targets no SummaryColumns
- Neither setting leaks into non-final queries (execute_query base settings)
"""

import inspect
from unittest.mock import AsyncMock, patch

import pytest

from mcp_hydrolix.mcp_env import get_config
from mcp_hydrolix.models import HdxQueryResult
from mcp_hydrolix.mcp_server import run_select_query


def _fake_result() -> HdxQueryResult:
    return HdxQueryResult(columns=["id"], rows=[[1]])


class TestQuerySettings:
    """Verify extra_settings passed to execute_query by run_select_query."""

    @patch(
        "mcp_hydrolix.mcp_server._query_targets_summary_table",
        new_callable=AsyncMock,
        return_value=False,
    )
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=_fake_result(),
    )
    async def test_non_summary_table_includes_max_timerange(
        self, mock_execute, mock_targets_summary
    ):
        """When the query does NOT target a summary table,
        extra_settings must contain hdx_query_max_timerange_sec matching config."""
        query = "SELECT id FROM db.plain_table WHERE ts > now() - INTERVAL 1 HOUR"
        await inspect.unwrap(run_select_query)(query)

        mock_execute.assert_awaited_once()
        _, kwargs = mock_execute.call_args
        extra = kwargs["extra_settings"]
        assert extra["hdx_query_max_timerange_sec"] == get_config().max_raw_timerange

    @patch(
        "mcp_hydrolix.mcp_server._query_targets_summary_table",
        new_callable=AsyncMock,
        return_value=True,
    )
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=_fake_result(),
    )
    async def test_summary_table_omits_max_timerange(self, mock_execute, mock_targets_summary):
        """When the query targets a summary table,
        hdx_query_max_timerange_sec must NOT be present."""
        query = "SELECT cnt_all FROM db.summary_table WHERE ts > now() - INTERVAL 1 DAY"
        await inspect.unwrap(run_select_query)(query)

        mock_execute.assert_awaited_once()
        _, kwargs = mock_execute.call_args
        extra = kwargs["extra_settings"]
        assert "hdx_query_max_timerange_sec" not in extra

    @patch(
        "mcp_hydrolix.mcp_server._query_targets_summary_table",
        new_callable=AsyncMock,
    )
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=_fake_result(),
    )
    @pytest.mark.parametrize("is_summary", [True, False])
    async def test_timerange_required_always_true(
        self, mock_execute, mock_targets_summary, is_summary
    ):
        """hdx_query_timerange_required must always be True,
        regardless of summary table status."""
        mock_targets_summary.return_value = is_summary

        await inspect.unwrap(run_select_query)(
            "SELECT x FROM db.t WHERE ts > now() - INTERVAL 1 HOUR"
        )

        _, kwargs = mock_execute.call_args
        extra = kwargs["extra_settings"]
        assert extra.get("hdx_query_timerange_required") is True

    @patch(
        "mcp_hydrolix.mcp_server._query_targets_summary_table",
        new_callable=AsyncMock,
        return_value=False,
    )
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=_fake_result(),
    )
    async def test_non_summary_settings_exact_keys(self, mock_execute, mock_targets_summary):
        """For non-summary queries, extra_settings should contain exactly
        hdx_query_timerange_required and hdx_query_max_timerange_sec."""
        await inspect.unwrap(run_select_query)(
            "SELECT id FROM db.t WHERE ts > now() - INTERVAL 1 HOUR"
        )

        _, kwargs = mock_execute.call_args
        extra = kwargs["extra_settings"]
        assert set(extra.keys()) == {
            "hdx_query_timerange_required",
            "hdx_query_max_timerange_sec",
        }

    @patch(
        "mcp_hydrolix.mcp_server._query_targets_summary_table",
        new_callable=AsyncMock,
        return_value=True,
    )
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=_fake_result(),
    )
    async def test_summary_settings_exact_keys(self, mock_execute, mock_targets_summary):
        """For summary queries, extra_settings should contain only
        hdx_query_timerange_required."""

        await inspect.unwrap(run_select_query)(
            "SELECT cnt_all FROM db.t WHERE ts > now() - INTERVAL 1 DAY"
        )

        _, kwargs = mock_execute.call_args
        extra = kwargs["extra_settings"]
        assert set(extra.keys()) == {"hdx_query_timerange_required"}

    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_base_settings_exclude_timerange_keys(self, mock_create_client):
        """execute_query base settings must not include hdx_query_timerange_required
        or hdx_query_max_timerange_sec when no extra_settings are provided."""
        from mcp_hydrolix.mcp_server import execute_query

        mock_client = AsyncMock()
        mock_query_result = AsyncMock()
        mock_query_result.column_names = ["id"]
        mock_query_result.result_rows = [[1]]
        mock_client.query.return_value = mock_query_result

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_create_client.return_value = mock_ctx

        await execute_query("SELECT 1")

        mock_client.query.assert_awaited_once()
        _, kwargs = mock_client.query.call_args
        settings = kwargs["settings"]
        assert "hdx_query_timerange_required" not in settings
        assert "hdx_query_max_timerange_sec" not in settings
