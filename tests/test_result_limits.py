"""Result caps: a byte cap on every query, and a cell cap a caller can only lower (HDX-12410).

Scenario names mirror openspec/changes/result-limits/specs/result-limits.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastmcp.exceptions import ToolError

from mcp_hydrolix.mcp_env import HydrolixConfig


def _client_ctx(query_side_effect=None) -> tuple[AsyncMock, AsyncMock]:
    mock_client = AsyncMock()
    mock_result = AsyncMock()
    mock_result.column_names = ["id"]
    mock_result.result_rows = [[1]]
    if query_side_effect is not None:
        mock_client.query.side_effect = query_side_effect
    else:
        mock_client.query.return_value = mock_result
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_client


async def _settings_sent_by_execute_query() -> dict:
    from mcp_hydrolix.mcp_server import execute_query

    mock_ctx, mock_client = _client_ctx()
    with patch("mcp_hydrolix.mcp_server.create_hydrolix_client", return_value=mock_ctx):
        await execute_query("SELECT 1")
    return mock_client.query.call_args.kwargs["settings"]


class TestResultByteCap:
    async def test_byte_cap_sent_with_every_query(self, monkeypatch):
        monkeypatch.delenv("HYDROLIX_QUERY_MAX_RESULT_BYTES", raising=False)
        settings = await _settings_sent_by_execute_query()
        assert settings["hdx_query_max_result_bytes"] == 64 * 1024 * 1024

    async def test_byte_cap_override_from_env(self, monkeypatch):
        monkeypatch.setenv("HYDROLIX_QUERY_MAX_RESULT_BYTES", "4194304")
        settings = await _settings_sent_by_execute_query()
        assert settings["hdx_query_max_result_bytes"] == 4194304

    @pytest.mark.parametrize("raw", ["9999", "0", "-1", "lots"])
    def test_byte_cap_below_floor_rejected(self, monkeypatch, raw):
        monkeypatch.setenv("HYDROLIX_QUERY_MAX_RESULT_BYTES", raw)
        with pytest.raises(ValueError, match="QUERY_MAX_RESULT_BYTES"):
            HydrolixConfig()


class TestCancelledResultCarriesARemedy:
    async def test_result_limit_error_gets_a_remedy(self):
        from mcp_hydrolix.mcp_server import execute_query

        mock_ctx, _ = _client_ctx(
            Exception(
                "Code: 396. DB::Exception: Limit for result exceeded, max bytes: 9.77 KiB, "
                "current bytes: 818.03 KiB. (TOO_MANY_ROWS_OR_BYTES)"
            )
        )
        with patch("mcp_hydrolix.mcp_server.create_hydrolix_client", return_value=mock_ctx):
            with pytest.raises(ToolError, match="narrow the time range"):
                await execute_query("SELECT 1")

    async def test_other_errors_are_passed_through_unchanged(self):
        from mcp_hydrolix.mcp_server import execute_query

        mock_ctx, _ = _client_ctx(Exception("Code: 62. DB::Exception: Syntax error"))
        with patch("mcp_hydrolix.mcp_server.create_hydrolix_client", return_value=mock_ctx):
            with pytest.raises(ToolError) as info:
                await execute_query("SELECT 1")
        assert "narrow the time range" not in str(info.value)
        assert "Syntax error" in str(info.value)


class TestCallerLowerableCellCap:
    def test_default_cell_cap_is_unlimited(self, monkeypatch):
        monkeypatch.delenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT", raising=False)
        assert HydrolixConfig().max_result_cells_limit == 0

    def test_zero_max_cells_is_uncapped_by_default(self, monkeypatch):
        from mcp_hydrolix.mcp_server import _resolve_cell_limit

        monkeypatch.delenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT", raising=False)
        cell_limit, capped = _resolve_cell_limit(0)
        assert cell_limit == 0
        assert capped is False

    def test_zero_max_cells_is_capped_when_operator_sets_limit(self, monkeypatch):
        from mcp_hydrolix.mcp_server import _resolve_cell_limit

        monkeypatch.setenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT", "200000")
        cell_limit, capped = _resolve_cell_limit(0)
        assert cell_limit == 200_000
        assert capped is True

    def test_caller_can_lower_below_cap(self, monkeypatch):
        from mcp_hydrolix.mcp_server import _resolve_cell_limit

        monkeypatch.setenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT", "200000")
        cell_limit, capped = _resolve_cell_limit(500)
        assert cell_limit == 500
        assert capped is False

    def test_caller_cannot_exceed_cap(self, monkeypatch):
        from mcp_hydrolix.mcp_server import _resolve_cell_limit

        monkeypatch.setenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT", "200000")
        cell_limit, capped = _resolve_cell_limit(5_000_000)
        assert cell_limit == 200_000
        assert capped is True
