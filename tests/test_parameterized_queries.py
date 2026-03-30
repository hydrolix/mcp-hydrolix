"""Tests for parameterized query support detection and usage.

Covers:
- Version string parsing
- /version preflight check (supported, not supported, error)
- list_tables and get_table_info passing parameters when supported
- list_tables and get_table_info using interpolation when not supported
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch


import mcp_hydrolix.mcp_server as server
from mcp_hydrolix.mcp_server import (
    HdxQueryResult,
    _parse_hydrolix_version,
    get_table_info,
    list_tables,
)


def _fake_result(columns=None, rows=None) -> HdxQueryResult:
    return HdxQueryResult(columns=columns or ["database", "name"], rows=rows or [])


def _fake_table_result() -> HdxQueryResult:
    """Minimal result matching Table.sql_fields() column order."""
    from mcp_hydrolix.mcp_server import Table

    fields = Table.sql_fields()
    row = ["mydb", "mytable", "MergeTree", "ts", "ts", None, None, None, None, None]
    return HdxQueryResult(columns=fields, rows=[row[: len(fields)]])


# ---------------------------------------------------------------------------
# _parse_hydrolix_version
# ---------------------------------------------------------------------------


class TestParseHydrolixVersion:
    def test_plain_version(self):
        assert _parse_hydrolix_version("v5.12.0") == (5, 12)

    def test_version_with_git_suffix(self):
        assert _parse_hydrolix_version("v5.9.5-2-gc1398c65") == (5, 9)

    def test_version_without_v_prefix(self):
        assert _parse_hydrolix_version("5.12.0") == (5, 12)

    def test_major_minor_only(self):
        assert _parse_hydrolix_version("v6.0") == (6, 0)

    def test_unparseable_returns_none(self):
        assert _parse_hydrolix_version("not-a-version") is None

    def test_empty_string_returns_none(self):
        assert _parse_hydrolix_version("") is None


# ---------------------------------------------------------------------------
# _check_parameterized_query_support
# ---------------------------------------------------------------------------


def _make_urllib3_response(body: str, status: int = 200):
    resp = MagicMock()
    resp.data = body.encode("utf-8")
    resp.status = status
    return resp


class TestCheckParameterizedQuerySupport:
    def setup_method(self):
        # Reset the module-level cache before each test
        server._parameterized_queries_supported = None

    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_supported_version(self, mock_to_thread, mock_cred):
        mock_to_thread.return_value = _make_urllib3_response("v5.12.0")
        result = await server._check_parameterized_query_support()
        assert result is True
        assert server._parameterized_queries_supported is True

    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_old_version_not_supported(self, mock_to_thread, mock_cred):
        mock_to_thread.return_value = _make_urllib3_response("v5.9.5-2-gc1398c65")
        result = await server._check_parameterized_query_support()
        assert result is False
        assert server._parameterized_queries_supported is False

    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_one_minor_below_threshold_not_supported(self, mock_to_thread, mock_cred):
        mock_to_thread.return_value = _make_urllib3_response("v5.11.9")
        assert await server._check_parameterized_query_support() is False

    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_newer_major_version_supported(self, mock_to_thread, mock_cred):
        mock_to_thread.return_value = _make_urllib3_response("v6.0.0")
        assert await server._check_parameterized_query_support() is True

    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread", side_effect=Exception("connection refused"))
    async def test_network_error_falls_back_to_false(self, mock_to_thread, mock_cred):
        result = await server._check_parameterized_query_support()
        assert result is False
        # Cache is not written on error so the next call will retry
        assert server._parameterized_queries_supported is None

    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_result_is_cached(self, mock_to_thread, mock_cred):
        mock_to_thread.return_value = _make_urllib3_response("v5.12.0")
        await server._check_parameterized_query_support()
        await server._check_parameterized_query_support()
        # Should only hit the network once
        mock_to_thread.assert_called_once()

    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_unparseable_version_falls_back_to_false(self, mock_to_thread, mock_cred):
        mock_to_thread.return_value = _make_urllib3_response("unknown")
        result = await server._check_parameterized_query_support()
        assert result is False


# ---------------------------------------------------------------------------
# list_tables — query construction
# ---------------------------------------------------------------------------


class TestListTablesQueryConstruction:
    def setup_method(self):
        server._parameterized_queries_supported = None

    @patch(
        "mcp_hydrolix.mcp_server._check_parameterized_query_support",
        new_callable=AsyncMock,
        return_value=True,
    )
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=_fake_result(),
    )
    async def test_uses_parameterized_query_when_supported(self, mock_execute, mock_check):
        await inspect.unwrap(list_tables)("mydb")

        mock_execute.assert_awaited_once()
        _, kwargs = mock_execute.call_args
        assert kwargs["parameters"] == {"db": "mydb"}
        assert "{db:String}" in mock_execute.call_args[0][0]

    @patch(
        "mcp_hydrolix.mcp_server._check_parameterized_query_support",
        new_callable=AsyncMock,
        return_value=False,
    )
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=_fake_result(),
    )
    async def test_uses_interpolation_when_not_supported(self, mock_execute, mock_check):
        await inspect.unwrap(list_tables)("mydb")

        mock_execute.assert_awaited_once()
        _, kwargs = mock_execute.call_args
        assert kwargs.get("parameters") is None
        assert "'mydb'" in mock_execute.call_args[0][0]

    @patch(
        "mcp_hydrolix.mcp_server._check_parameterized_query_support",
        new_callable=AsyncMock,
        return_value=True,
    )
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=_fake_result(),
    )
    async def test_like_filter_included_in_params(self, mock_execute, mock_check):
        await inspect.unwrap(list_tables)("mydb", like="events%")

        _, kwargs = mock_execute.call_args
        assert kwargs["parameters"] == {"db": "mydb", "like": "events%"}
        assert "{like:String}" in mock_execute.call_args[0][0]

    @patch(
        "mcp_hydrolix.mcp_server._check_parameterized_query_support",
        new_callable=AsyncMock,
        return_value=True,
    )
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=_fake_result(),
    )
    async def test_not_like_filter_included_in_params(self, mock_execute, mock_check):
        await inspect.unwrap(list_tables)("mydb", not_like="tmp%")

        _, kwargs = mock_execute.call_args
        assert kwargs["parameters"] == {"db": "mydb", "not_like": "tmp%"}
        assert "{not_like:String}" in mock_execute.call_args[0][0]


# ---------------------------------------------------------------------------
# get_table_info — query construction
# ---------------------------------------------------------------------------


class TestGetTableInfoQueryConstruction:
    def setup_method(self):
        server._parameterized_queries_supported = None

    @patch(
        "mcp_hydrolix.mcp_server._check_parameterized_query_support",
        new_callable=AsyncMock,
        return_value=True,
    )
    @patch("mcp_hydrolix.mcp_server._describe_columns", new_callable=AsyncMock, return_value=[])
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=_fake_table_result(),
    )
    async def test_uses_parameterized_query_when_supported(
        self, mock_execute, mock_describe, mock_check
    ):
        await inspect.unwrap(get_table_info)("mydb", "mytable")

        # execute_query is called twice: once for table metadata, once inside _describe_columns
        # but _describe_columns is mocked, so only one call here
        mock_execute.assert_awaited_once()
        _, kwargs = mock_execute.call_args
        assert kwargs["parameters"] == {"db": "mydb", "table": "mytable"}
        assert "{db:String}" in mock_execute.call_args[0][0]
        assert "{table:String}" in mock_execute.call_args[0][0]

    @patch(
        "mcp_hydrolix.mcp_server._check_parameterized_query_support",
        new_callable=AsyncMock,
        return_value=False,
    )
    @patch("mcp_hydrolix.mcp_server._describe_columns", new_callable=AsyncMock, return_value=[])
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=_fake_table_result(),
    )
    async def test_uses_interpolation_when_not_supported(
        self, mock_execute, mock_describe, mock_check
    ):
        await inspect.unwrap(get_table_info)("mydb", "mytable")

        mock_execute.assert_awaited_once()
        _, kwargs = mock_execute.call_args
        assert kwargs.get("parameters") is None
        assert "'mydb'" in mock_execute.call_args[0][0]
        assert "'mytable'" in mock_execute.call_args[0][0]
