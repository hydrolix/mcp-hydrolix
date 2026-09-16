"""Result caps a caller can only lower (HDX-12410).

Scenario names mirror openspec/changes/result-limits/specs/result-limits.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from mcp_hydrolix.mcp_env import HydrolixConfig


async def _settings_sent_by_execute_query() -> dict:
    from mcp_hydrolix.mcp_server import execute_query

    mock_client = AsyncMock()
    mock_result = AsyncMock()
    mock_result.column_names = ["id"]
    mock_result.result_rows = [[1]]
    mock_client.query.return_value = mock_result
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
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
        with pytest.raises(ValueError, match="HYDROLIX_QUERY_MAX_RESULT_BYTES"):
            HydrolixConfig()


class TestCallerLowerableCellCap:
    def test_default_cell_cap_is_positive(self, monkeypatch):
        monkeypatch.delenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT", raising=False)
        assert HydrolixConfig().max_result_cells_limit == 200_000

    def test_zero_max_cells_is_capped_by_default(self, monkeypatch):
        from mcp_hydrolix.mcp_server import _resolve_cell_limit

        monkeypatch.delenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT", raising=False)
        cell_limit, capped = _resolve_cell_limit(0)
        assert cell_limit == 200_000
        assert capped is True

    def test_caller_can_lower_below_cap(self, monkeypatch):
        from mcp_hydrolix.mcp_server import _resolve_cell_limit

        monkeypatch.delenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT", raising=False)
        cell_limit, capped = _resolve_cell_limit(500)
        assert cell_limit == 500
        assert capped is False

    def test_explicit_zero_limit_disables_cap(self, monkeypatch):
        from mcp_hydrolix.mcp_server import _resolve_cell_limit

        monkeypatch.setenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT", "0")
        cell_limit, capped = _resolve_cell_limit(0)
        assert cell_limit == 0
        assert capped is False

    def test_zero_limit_warns_on_http(self, monkeypatch, caplog):
        monkeypatch.setenv("HYDROLIX_MCP_SERVER_TRANSPORT", "http")
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.test")
        monkeypatch.setenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT", "0")
        with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
            HydrolixConfig()
        assert any("HYDROLIX_MAX_RESULT_CELLS_LIMIT" in r.getMessage() for r in caplog.records)

    def test_positive_limit_does_not_warn(self, monkeypatch, caplog):
        monkeypatch.setenv("HYDROLIX_MCP_SERVER_TRANSPORT", "http")
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.test")
        monkeypatch.delenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT", raising=False)
        with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
            HydrolixConfig()
        assert not any("HYDROLIX_MAX_RESULT_CELLS_LIMIT" in r.getMessage() for r in caplog.records)
