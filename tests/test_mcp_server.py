import asyncio
import json
import os
import time
import uuid
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp_clickhouse.mcp_server import create_clickhouse_client


def _assert_structured_matches_content(result, tool_name: str):
    """Assert that structured_content and content[0].text agree."""
    assert result.content, f"{tool_name}: content is empty"
    text_parsed = json.loads(result.content[0].text)
    structured_content = result.structured_content
    if isinstance(text_parsed, list):
        # fastmcp requires dict-type structured content. Lists get wrapped as {result": list}
        # while content text contains the unwrapped list
        assert isinstance(structured_content, dict)
        assert "result" in structured_content
        structured_content = structured_content["result"]
    assert text_parsed == structured_content, (
        f"{tool_name}: structured_content does not match parsed content text"
    )


async def test_list_databases_structured_matches_content(mcp_server, setup_test_database):
    """Verify structured and unstructured responses match for list_databases."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("list_databases", {})
        _assert_structured_matches_content(result, "list_databases")


async def test_list_tables_structured_matches_content(mcp_server, setup_test_database):
    """Verify structured and unstructured responses match for list_tables."""
    test_db, _, _ = setup_test_database
    async with Client(mcp_server) as client:
        result = await client.call_tool("list_tables", {"database": test_db})
        _assert_structured_matches_content(result, "list_tables")


async def test_get_table_info_structured_matches_content(mcp_server, setup_test_database):
    """Verify structured and unstructured responses match for get_table_info."""
    test_db, test_table, _ = setup_test_database
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "get_table_info", {"database": test_db, "table": test_table}
        )
        _assert_structured_matches_content(result, "get_table_info")


async def test_run_select_query_structured_matches_content(mcp_server, setup_test_database):
    """Verify structured and unstructured responses match for run_select_query."""
    test_db, test_table, _ = setup_test_database
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "run_select_query",
            {"query": f"SELECT id, name FROM {test_db}.{test_table} ORDER BY id"},
        )
        _assert_structured_matches_content(result, "run_select_query")


async def test_list_databases(mcp_server, setup_test_database):
    """Test the list_databases tool."""
    test_db, _, _ = setup_test_database

    async with Client(mcp_server) as client:
        result = await client.call_tool("list_databases", {})

        databases = result.structured_content["result"]
        assert len(databases) >= 1
        assert test_db in databases
        assert "system" in databases  # System database should always exist


async def test_list_tables_basic(mcp_server, setup_test_database):
    """Test the list_tables tool without filters.

    Updated: list_tables() now returns only basic table info without columns.
    """
    test_db, test_table, test_table2 = setup_test_database

    async with Client(mcp_server) as client:
        result = await client.call_tool("list_tables", {"database": test_db})

        tables = result.structured_content["result"]
        assert len(tables) >= 1

        # Should have exactly 2 tables
        assert len(tables) == 2

        # Get table names
        table_names = [table["name"] for table in tables]
        assert test_table in table_names
        assert test_table2 in table_names

        # Check basic table details (without columns)
        for table in tables:
            assert table["database"] == test_db
            assert "total_rows" in table
            assert "engine" in table
            assert "name" in table
            assert "primary_key" in table

            # Columns should be empty or None (not populated by list_tables)
            assert table.get("columns") is None or len(table.get("columns", [])) == 0


async def test_list_tables_with_like_filter(mcp_server, setup_test_database):
    """Test the list_tables tool with LIKE filter."""
    test_db, test_table, _ = setup_test_database

    async with Client(mcp_server) as client:
        # Test with LIKE filter
        result = await client.call_tool("list_tables", {"database": test_db, "like": "test_%"})

        tables = result.structured_content["result"]

        assert len(tables) == 1
        assert tables[0]["name"] == test_table


async def test_list_tables_with_not_like_filter(mcp_server, setup_test_database):
    """Test the list_tables tool with NOT LIKE filter."""
    test_db, _, test_table2 = setup_test_database

    async with Client(mcp_server) as client:
        # Test with NOT LIKE filter
        result = await client.call_tool("list_tables", {"database": test_db, "not_like": "test_%"})

        tables = result.structured_content["result"]

        assert len(tables) == 1
        assert tables[0]["name"] == test_table2


async def test_run_select_query_success(mcp_server, setup_test_database):
    """Test running a successful SELECT query."""
    test_db, test_table, _ = setup_test_database

    async with Client(mcp_server) as client:
        query = f"SELECT id, name, age FROM {test_db}.{test_table} ORDER BY id"
        result = await client.call_tool("run_select_query", {"query": query})

        query_result = result.structured_content

        # Check structure
        assert "columns" in query_result
        assert "rows" in query_result

        # Check columns
        assert query_result["columns"] == ["id", "name", "age"]

        # Check rows
        assert len(query_result["rows"]) == 4
        assert query_result["rows"][0] == [1, "Alice", 30]
        assert query_result["rows"][1] == [2, "Bob", 25]
        assert query_result["rows"][2] == [3, "Charlie", 35]
        assert query_result["rows"][3] == [4, "Diana", 28]


async def test_run_select_query_with_aggregation(mcp_server, setup_test_database):
    """Test running a SELECT query with aggregation."""
    test_db, test_table, _ = setup_test_database

    async with Client(mcp_server) as client:
        query = f"SELECT COUNT(*) as count, AVG(age) as avg_age FROM {test_db}.{test_table}"
        result = await client.call_tool("run_select_query", {"query": query})

        query_result = result.structured_content

        assert query_result["columns"] == ["count", "avg_age"]
        assert len(query_result["rows"]) == 1
        assert query_result["rows"][0][0] == 4  # count
        assert query_result["rows"][0][1] == 29.5  # average age


async def test_run_select_query_with_join(mcp_server, setup_test_database):
    """Test running a SELECT query with JOIN."""
    test_db, test_table, test_table2 = setup_test_database

    async with Client(mcp_server) as client:
        # Insert related data for join
        client_direct = create_clickhouse_client()
        client_direct.command(f"""
            INSERT INTO {test_db}.{test_table2} (event_id, event_type, timestamp) VALUES
            (2001, 'purchase', '2024-01-01 14:00:00')
        """)

        query = f"""
        SELECT
            COUNT(DISTINCT event_type) as event_types_count
        FROM {test_db}.{test_table2}
        """
        result = await client.call_tool("run_select_query", {"query": query})

        query_result = result.structured_content
        assert query_result["rows"][0][0] == 3  # login, logout, purchase


async def test_run_select_query_error(mcp_server, setup_test_database):
    """Test running a SELECT query that results in an error."""
    test_db, _, _ = setup_test_database

    async with Client(mcp_server) as client:
        # Query non-existent table
        query = f"SELECT * FROM {test_db}.non_existent_table"

        # Should raise ToolError
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool("run_select_query", {"query": query})

        assert "Query execution failed" in str(exc_info.value)


async def test_run_select_query_syntax_error(mcp_server):
    """Test running a SELECT query with syntax error."""
    async with Client(mcp_server) as client:
        # Invalid SQL syntax
        query = "SELECT FROM WHERE"

        # Should raise ToolError
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool("run_select_query", {"query": query})

        assert "Query execution failed" in str(exc_info.value)


async def test_table_metadata_details(mcp_server, setup_test_database):
    """Test that table metadata is correctly retrieved."""
    test_db, test_table, _ = setup_test_database

    async with Client(mcp_server) as client:
        # First, list tables to discover available tables
        result = await client.call_tool("list_tables", {"database": test_db})
        tables = result.structured_content["result"]

        # Verify our test table exists in the list
        test_table_exists = any(t["name"] == test_table for t in tables)
        assert test_table_exists, f"Test table {test_table} not found in list_tables result"

        # Now use get_table_info to get detailed metadata including columns
        result = await client.call_tool(
            "get_table_info", {"database": test_db, "table": test_table}
        )
        # Use structured_content (raw JSON) to reliably access column fields
        # result.data goes through fastmcp's schema reconstruction which produces
        # opaque Root objects for anyOf union types
        test_table_info = result.structured_content

        # Check engine info
        assert test_table_info["engine"] == "MergeTree"

        # Check row count
        assert test_table_info["total_rows"] == 4

        # Columns are plain dicts from @field_serializer with column_category injected
        columns_by_name = {col["name"]: col for col in test_table_info["columns"]}

        assert columns_by_name["id"]["comment"] == "Primary identifier"
        assert columns_by_name["id"]["type"] == "UInt32"
        assert columns_by_name["id"]["column_category"] == "Column"

        assert columns_by_name["name"]["comment"] == "User name field"
        assert columns_by_name["name"]["type"] == "String"
        assert columns_by_name["name"]["column_category"] == "Column"

        assert columns_by_name["age"]["comment"] == "User age"
        assert columns_by_name["age"]["type"] == "UInt8"
        assert columns_by_name["age"]["column_category"] == "Column"

        assert columns_by_name["created_at"]["comment"] == "Record creation timestamp"
        assert columns_by_name["created_at"]["type"] == "DateTime"
        # DEFAULT columns are classified as plain Column — default_expression not exposed
        assert columns_by_name["created_at"]["column_category"] == "Column"


async def test_system_database_access(mcp_server):
    """Test that we can access system databases."""
    async with Client(mcp_server) as client:
        # List tables in system database
        result = await client.call_tool("list_tables", {"database": "system"})
        tables = result.structured_content["result"]

        # System database should have many tables
        assert len(tables) > 10

        # Check for some common system tables
        table_names = [t["name"] for t in tables]
        assert "tables" in table_names
        assert "columns" in table_names
        assert "databases" in table_names


class ServerMetrics:
    inflight_requests = 0
    queries = {}


class InFlightCounterMiddleware(Middleware):
    async def on_request(self, context: MiddlewareContext, call_next):
        # Increment counter before processing
        try:
            if context.message.name == "run_select_query":
                ServerMetrics.queries[context.message.arguments["query"]] = {"start": time.time()}
                # ServerMetrics.queries.append(context.message.arguments["query"])
                ServerMetrics.inflight_requests += 1
        except Exception:
            pass
        try:
            # Process the request
            return await call_next(context)
        finally:
            try:
                if context.message.name == "run_select_query":
                    ServerMetrics.queries[context.message.arguments["query"]]["end"] = time.time()
                    # Decrement counter after processing (even if it fails)
                    # ServerMetrics.inflight_requests -= 1
            except Exception:
                pass


async def test_concurrent_queries(monkeypatch, mcp_server, setup_test_database):
    """Test running multiple queries concurrently."""

    from clickhouse_connect.driver import AsyncClient

    instance = AsyncClient
    original_method = AsyncClient.query

    async def wrapper_proxy(self, query: str, settings: dict[str, Any]):
        settings["readonly"] = 0
        # Call the original method
        return await original_method(self, query, settings)

    # Patch the instance method at runtime
    monkeypatch.setattr(instance, "query", wrapper_proxy)

    test_db, test_table, test_table2 = setup_test_database

    mcp_server.add_middleware(InFlightCounterMiddleware())

    # limit mcp client request time
    os.environ["HYDROLIX_SEND_RECEIVE_TIMEOUT"] = "10"

    # limit mcp server waiting for query finish
    os.environ["HYDROLIX_QUERY_TIMEOUT_SECS"] = "10"

    ServerMetrics.inflight_requests = 0
    async with Client(mcp_server) as client:
        lq = "SELECT * FROM loop  (numbers(3)) LIMIT 7000000000000 SETTINGS max_execution_time=9"
        lq_f = asyncio.gather(*[client.call_tool("run_select_query", {"query": lq})])

        # Run multiple queries concurrently
        queries = [
            f"SELECT COUNT(*) FROM {test_db}.{test_table}",
            f"SELECT COUNT(*) FROM {test_db}.{test_table2}",
            f"SELECT MAX(id) FROM {test_db}.{test_table}",
            f"SELECT MIN(event_id) FROM {test_db}.{test_table2}",
        ]

        # Execute all queries concurrently
        results = asyncio.gather(
            *[client.call_tool("run_select_query", {"query": query}) for query in queries]
        )

        # let mcp server handle requests
        await asyncio.sleep(20)

    # Check that other queries were submitted to mcp server
    assert lq_f.done() and isinstance(lq_f.exception(), ToolError)
    assert ServerMetrics.inflight_requests > 1, (
        "By now at least one another query should have been invoked."
    )

    # count queries started after long blocking query finished.
    lq_end = ServerMetrics.queries[lq]["end"]
    blocked_count = sum(
        [1 for q, q_time in ServerMetrics.queries.items() if q != lq and q_time["start"] > lq_end]
    )
    assert blocked_count < len(queries), "All queries were blocked by long running query."

    # all queries were invoked
    for query in queries:
        assert query in ServerMetrics.queries

    # Check each result
    assert results.done()
    for result in results.result():
        query_result = result.structured_content
        assert "rows" in query_result
        assert len(query_result["rows"]) == 1


async def test_concurrent_queries_isolation(monkeypatch, mcp_server, setup_test_database):
    """Test running multiple queries concurrently."""
    from clickhouse_connect.driver import AsyncClient

    instance = AsyncClient
    original_method = AsyncClient.query

    async def wrapper_proxy(self, query: str, settings: dict[str, Any]):
        settings["readonly"] = 0
        # Call the original method
        return await original_method(self, query, settings)

    # Patch the instance method at runtime
    monkeypatch.setattr(instance, "query", wrapper_proxy)

    users = [[f"user_{i}", f"pass_{i}", uuid.uuid4().hex] for i in range(50)]

    async def _call_tool(user, password, guid):
        async with Client(mcp_server) as client:
            return await client.call_tool(
                "run_select_query",
                {
                    "query": f"select '{user}', '{password}', '{guid}' from loop(numbers(3)) LIMIT 50"
                },
            )

    results = await asyncio.gather(
        *[_call_tool(user, password, guid) for user, password, guid in users for _ in range(10)]
    )

    for result in results:
        res = result.structured_content["rows"]
        user = res[0][0]
        indata = list(filter(lambda x: x[0] == user, users))
        assert len(indata) == 1
        user_row = indata[0]
        for res_row in res:
            assert res_row == user_row
