"""Tests for query settings applied by run_select_query.

Verifies that:
- hdx_query_timerange_required is always True on the final query
- hdx_query_max_timerange_sec is set to the configured max_raw_timerange only when the query
  targets no SummaryColumns
- Neither setting leaks into non-final queries (execute_query base settings)
- hdx_query_admin_comment composition (User/version/transport) and execute_cmd exclusion
"""

import importlib
import inspect
import logging
from importlib.metadata import PackageNotFoundError, version as _real_pkg_version
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import mcp_hydrolix.mcp_server as mcp_server_module
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


class TestStripConflictingSettingsIntegration:
    """execute_query must strip inline SETTINGS that collide with the transport-level
    guardrail settings dict, so our values win de facto (HDX-11717)."""

    @staticmethod
    def _mock_client():
        mock_client = AsyncMock()
        mock_query_result = AsyncMock()
        mock_query_result.column_names = ["id"]
        mock_query_result.result_rows = [[1]]
        mock_client.query.return_value = mock_query_result

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        return mock_client, mock_ctx

    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_conflicting_inline_setting_stripped_from_query(self, mock_create_client):
        from mcp_hydrolix.mcp_server import execute_query

        mock_client, mock_ctx = self._mock_client()
        mock_create_client.return_value = mock_ctx

        # readonly is a guardrail key; an inline override must be removed.
        await execute_query("SELECT id FROM db.t SETTINGS readonly=0, max_threads=4")

        sent_query = mock_client.query.call_args[0][0]
        assert "readonly" not in sent_query.lower()
        # Non-conflicting inline settings are preserved.
        assert "max_threads" in sent_query.lower()
        # And the guardrail value we send still wins on the transport side.
        assert mock_client.query.call_args.kwargs["settings"]["readonly"] == 1

    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_parameterized_query_passes_through_unchanged(self, mock_create_client):
        """Regression: queries without a SETTINGS clause (e.g. the internal parameterized
        metadata queries) must reach the client byte-for-byte. They previously bypassed
        sqlglot entirely; the guardrail strip must not round-trip them through sqlglot,
        which would inject a space into ClickHouse placeholders ({db:Identifier} ->
        {db: Identifier}) and break server-side parameter substitution."""
        from mcp_hydrolix.mcp_server import execute_query

        mock_client, mock_ctx = self._mock_client()
        mock_create_client.return_value = mock_ctx

        query = "DESCRIBE TABLE {db:Identifier}.{table:Identifier}"
        await execute_query(query, parameters={"db": "mydb", "table": "mytable"})

        assert mock_client.query.call_args[0][0] == query

    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    async def test_extra_settings_key_is_also_protected(self, mock_create_client):
        """Guardrail keys supplied via extra_settings (not just the base dict) must be
        stripped too. run_select_query adds hdx_query_timerange_required=True as a
        guardrail; an inline SETTINGS hdx_query_timerange_required=0 must be removed so
        the transport value wins (verified live against the cluster)."""
        from mcp_hydrolix.mcp_server import execute_query

        mock_client, mock_ctx = self._mock_client()
        mock_create_client.return_value = mock_ctx

        await execute_query(
            "SELECT id FROM db.t SETTINGS hdx_query_timerange_required=0, max_threads=4",
            extra_settings={"hdx_query_timerange_required": True},
        )

        sent_query = mock_client.query.call_args[0][0]
        # The inline override is stripped...
        assert "hdx_query_timerange_required" not in sent_query.lower()
        # ...the non-conflicting setting is preserved...
        assert "max_threads" in sent_query.lower()
        # ...and the guardrail value we send still wins on the transport side.
        assert (
            mock_client.query.call_args.kwargs["settings"]["hdx_query_timerange_required"] is True
        )


@pytest.fixture
def reload_server_after_test():
    """Reload mcp_server after the test to restore the real HDX_ADMIN_COMMENT."""
    yield
    importlib.reload(mcp_server_module)


def _reload_server_with(monkeypatch, transport, pkg_version_mock):
    """Reload mcp_server with the given transport env and a patched importlib.metadata.version.

    Patching `importlib.metadata.version` (the source `version` callable, before the
    `from importlib.metadata import version as _pkg_version` re-binding fires) is the
    only way to stub the import-time value of `_pkg_version` inside the reloaded module.
    """
    monkeypatch.setenv("HYDROLIX_MCP_SERVER_TRANSPORT", transport)
    with patch("importlib.metadata.version", pkg_version_mock):
        return importlib.reload(mcp_server_module)


def test_renders_composed_comment(monkeypatch, reload_server_after_test):
    """Scenario: Renders Composed Comment."""
    module = _reload_server_with(
        monkeypatch,
        transport="stdio",
        pkg_version_mock=MagicMock(return_value="0.3.2"),
    )
    assert module.HDX_ADMIN_COMMENT == "User: mcp-hydrolix version: 0.3.2 transport: stdio"


def test_version_metadata_available():
    """Scenario: Version Metadata Available."""
    assert mcp_server_module._resolve_server_version() == _real_pkg_version("mcp-hydrolix")


def test_version_metadata_unavailable(caplog):
    """Scenario: Version Metadata Unavailable."""
    with patch(
        "mcp_hydrolix.mcp_server._pkg_version",
        side_effect=PackageNotFoundError("mcp-hydrolix"),
    ):
        with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
            result = mcp_server_module._resolve_server_version()
    assert result == "unknown"
    assert any("mcp-hydrolix" in record.getMessage() for record in caplog.records)


def test_transport_reflects_config(monkeypatch, reload_server_after_test):
    """Scenario: Transport Reflects Config."""
    module = _reload_server_with(
        monkeypatch,
        transport="sse",
        pkg_version_mock=MagicMock(return_value="0.3.2"),
    )
    assert "transport: sse" in module.HDX_ADMIN_COMMENT


async def test_execute_cmd_omits_admin_comment():
    """Scenario: execute_cmd Omits Admin Comment."""
    mock_client = AsyncMock()
    mock_client.command.return_value = "ok"

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("mcp_hydrolix.mcp_server.create_hydrolix_client", return_value=mock_ctx):
        await mcp_server_module.execute_cmd("SHOW DATABASES")

    mock_client.command.assert_awaited_once()
    _, kwargs = mock_client.command.call_args
    settings = kwargs.get("settings", {})
    assert "hdx_query_admin_comment" not in settings
