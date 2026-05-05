from __future__ import annotations

import json

import pytest
from fastmcp import Client

from tests.e2e._mcp_client import parsed_payload, unauthed_initialize_status

EXPECTED_TOOLS = {"list_databases", "list_tables", "get_table_info", "run_select_query"}


def _first_database_name(payload: dict) -> str:
    # list_databases returns List[str]; fastmcp wraps non-object lists in
    # `{"result": [...]}` to satisfy MCP's object-typed outputSchema rule.
    return payload["result"][0]


def _first_table_name(payload: dict) -> str:
    # list_tables returns List[Table]; same wrapping convention as above.
    return payload["result"][0]["name"]


@pytest.mark.end_to_end
async def test_initialize_lists_expected_tools(mcp_client: Client) -> None:
    tools = await mcp_client.list_tools()
    names = {t.name for t in tools}
    assert EXPECTED_TOOLS <= names, (
        f"server is missing expected tools: {sorted(EXPECTED_TOOLS - names)}; got {sorted(names)}"
    )


@pytest.mark.end_to_end
async def test_list_databases_returns_at_least_one_entry(mcp_client: Client) -> None:
    result = await mcp_client.call_tool("list_databases", {})
    assert not result.is_error, f"list_databases reported is_error: {result!r}"
    payload = parsed_payload(result)
    assert payload, "list_databases returned an empty payload"
    assert _first_database_name(payload), "no database name in list_databases payload"


@pytest.mark.end_to_end
async def test_list_tables_for_first_database(mcp_client: Client) -> None:
    dbs = await mcp_client.call_tool("list_databases", {})
    assert not dbs.is_error, f"list_databases reported is_error: {dbs!r}"
    database = _first_database_name(parsed_payload(dbs))
    tables = await mcp_client.call_tool("list_tables", {"database": database})
    assert not tables.is_error, f"list_tables(database={database!r}) reported is_error: {tables!r}"
    payload = parsed_payload(tables)
    assert payload, f"list_tables({database!r}) returned an empty payload"


@pytest.mark.end_to_end
async def test_get_table_info_for_first_table(mcp_client: Client) -> None:
    dbs = await mcp_client.call_tool("list_databases", {})
    assert not dbs.is_error, f"list_databases reported is_error: {dbs!r}"
    database = _first_database_name(parsed_payload(dbs))
    tables = await mcp_client.call_tool("list_tables", {"database": database})
    assert not tables.is_error, f"list_tables(database={database!r}) reported is_error: {tables!r}"
    table = _first_table_name(parsed_payload(tables))
    info = await mcp_client.call_tool("get_table_info", {"database": database, "table": table})
    assert not info.is_error, f"get_table_info({database!r}, {table!r}) reported is_error: {info!r}"
    payload = parsed_payload(info)
    haystack = json.dumps(payload, default=str)
    assert "columns" in haystack.lower(), (
        f"expected 'columns' in get_table_info payload, got {haystack[:300]!r}"
    )


@pytest.mark.end_to_end
async def test_run_select_query_one(mcp_client: Client) -> None:
    result = await mcp_client.call_tool("run_select_query", {"query": "SELECT 1 AS smoke_test"})
    assert not result.is_error, f"run_select_query reported is_error: {result!r}"
    payload = parsed_payload(result)
    haystack = json.dumps(payload, default=str)
    assert "1" in haystack, f"expected '1' in run_select_query payload, got {haystack[:300]!r}"


@pytest.mark.end_to_end
def test_missing_auth_returns_401(mcp_ready) -> None:
    status, body_prefix = unauthed_initialize_status(mcp_ready.hydrolix_host)
    assert status == 401, f"expected HTTP 401 without bearer token, got {status}: {body_prefix!r}"
