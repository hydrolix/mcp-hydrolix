import asyncio
import json
import os
import time
import uuid
from typing import Any

import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp_clickhouse.mcp_server import create_clickhouse_client

from mcp_hydrolix.mcp_server import mcp


@pytest.fixture(scope="module")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def setup_test_database():
    """Set up test database and tables before running tests."""
    client = create_clickhouse_client()

    # Test database and table names
    test_db = "test_mcp_db"
    test_table = "test_table"
    test_table2 = "another_test_table"

    # Create test database
    client.command(f"CREATE DATABASE IF NOT EXISTS {test_db}")

    # Drop tables if they exist
    client.command(f"DROP TABLE IF EXISTS {test_db}.{test_table}")
    client.command(f"DROP TABLE IF EXISTS {test_db}.{test_table2}")

    # Create first test table with comments
    client.command(f"""
        CREATE TABLE {test_db}.{test_table} (
            id UInt32 COMMENT 'Primary identifier',
            name String COMMENT 'User name field',
            age UInt8 COMMENT 'User age',
            created_at DateTime DEFAULT now() COMMENT 'Record creation timestamp'
        ) ENGINE = MergeTree()
        ORDER BY id
        COMMENT 'Test table for MCP server testing'
    """)

    # Create second test table
    client.command(f"""
        CREATE TABLE {test_db}.{test_table2} (
            event_id UInt64,
            event_type String,
            timestamp DateTime
        ) ENGINE = MergeTree()
        ORDER BY (event_type, timestamp)
        COMMENT 'Event tracking table'
    """)

    # Insert test data
    client.command(f"""
        INSERT INTO {test_db}.{test_table} (id, name, age) VALUES
        (1, 'Alice', 30),
        (2, 'Bob', 25),
        (3, 'Charlie', 35),
        (4, 'Diana', 28)
    """)

    client.command(f"""
        INSERT INTO {test_db}.{test_table2} (event_id, event_type, timestamp) VALUES
        (1001, 'login', '2024-01-01 10:00:00'),
        (1002, 'logout', '2024-01-01 11:00:00'),
        (1003, 'login', '2024-01-01 12:00:00')
    """)

    yield test_db, test_table, test_table2

    # Cleanup after tests
    client.command(f"DROP DATABASE IF EXISTS {test_db}")


@pytest.fixture
def mcp_server():
    """Return the MCP server instance for testing."""
    return mcp


@pytest.mark.asyncio
async def test_list_databases(mcp_server, setup_test_database):
    """Test the list_databases tool."""
    test_db, _, _ = setup_test_database

    async with Client(mcp_server) as client:
        result = await client.call_tool("list_databases", {})

        databases = result.data
        assert len(result.data) >= 1
        assert test_db in databases
        assert "system" in databases  # System database should always exist


@pytest.mark.asyncio
async def test_list_tables_basic(mcp_server, setup_test_database):
    """Test the list_tables tool without filters."""
    test_db, test_table, test_table2 = setup_test_database

    async with Client(mcp_server) as client:
        result = await client.call_tool("list_tables", {"database": test_db})

        tables = result.data
        assert len(tables) >= 1

        # Should have exactly 2 tables
        assert len(tables) == 2

        # Get table names
        table_names = [table["name"] for table in tables]
        assert test_table in table_names
        assert test_table2 in table_names

        # Check table details
        for table in tables:
            assert table["database"] == test_db
            assert "columns" in table
            assert "total_rows" in table
            assert "engine" in table
            assert "comment" in table

            # Verify column information exists
            assert len(table["columns"]) > 0
            for column in table["columns"]:
                assert "name" in column
                assert "column_type" in column
                assert "comment" in column


@pytest.mark.asyncio
async def test_list_tables_with_like_filter(mcp_server, setup_test_database):
    """Test the list_tables tool with LIKE filter."""
    test_db, test_table, _ = setup_test_database

    async with Client(mcp_server) as client:
        # Test with LIKE filter
        result = await client.call_tool("list_tables", {"database": test_db, "like": "test_%"})

        tables_data = result.data

        # Handle both single dict and list of dicts
        if isinstance(tables_data, dict):
            tables = [tables_data]
        else:
            tables = tables_data

        assert len(tables) == 1
        assert tables[0]["name"] == test_table


@pytest.mark.asyncio
async def test_list_tables_with_not_like_filter(mcp_server, setup_test_database):
    """Test the list_tables tool with NOT LIKE filter."""
    test_db, _, test_table2 = setup_test_database

    async with Client(mcp_server) as client:
        # Test with NOT LIKE filter
        result = await client.call_tool("list_tables", {"database": test_db, "not_like": "test_%"})

        tables_data = result.data

        # Handle both single dict and list of dicts
        if isinstance(tables_data, dict):
            tables = [tables_data]
        else:
            tables = tables_data

        assert len(tables) == 1
        assert tables[0]["name"] == test_table2


@pytest.mark.asyncio
async def test_run_select_query_success(mcp_server, setup_test_database):
    """Test running a successful SELECT query."""
    test_db, test_table, _ = setup_test_database

    async with Client(mcp_server) as client:
        query = f"SELECT id, name, age FROM {test_db}.{test_table} ORDER BY id"
        result = await client.call_tool("run_select_query", {"query": query})

        query_result = result.data

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


@pytest.mark.asyncio
async def test_run_select_query_with_aggregation(mcp_server, setup_test_database):
    """Test running a SELECT query with aggregation."""
    test_db, test_table, _ = setup_test_database

    async with Client(mcp_server) as client:
        query = f"SELECT COUNT(*) as count, AVG(age) as avg_age FROM {test_db}.{test_table}"
        result = await client.call_tool("run_select_query", {"query": query})

        query_result = result.data

        assert query_result["columns"] == ["count", "avg_age"]
        assert len(query_result["rows"]) == 1
        assert query_result["rows"][0][0] == 4  # count
        assert query_result["rows"][0][1] == 29.5  # average age


@pytest.mark.asyncio
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

        query_result = result.data
        assert query_result["rows"][0][0] == 3  # login, logout, purchase


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_run_select_query_syntax_error(mcp_server):
    """Test running a SELECT query with syntax error."""
    async with Client(mcp_server) as client:
        # Invalid SQL syntax
        query = "SELECT FROM WHERE"

        # Should raise ToolError
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool("run_select_query", {"query": query})

        assert "Query execution failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_table_metadata_details(mcp_server, setup_test_database):
    """Test that table metadata is correctly retrieved."""
    test_db, test_table, _ = setup_test_database

    async with Client(mcp_server) as client:
        result = await client.call_tool("list_tables", {"database": test_db})
        tables = result.data

        # Find our test table
        test_table_info = next(t for t in tables if t["name"] == test_table)

        # Check table comment
        assert test_table_info["comment"] == "Test table for MCP server testing"

        # Check engine info
        assert test_table_info["engine"] == "MergeTree"
        assert "MergeTree" in test_table_info["engine_full"]

        # Check row count
        assert test_table_info["total_rows"] == 4

        # Check columns and their comments
        columns_by_name = {col["name"]: col for col in test_table_info["columns"]}

        assert columns_by_name["id"]["comment"] == "Primary identifier"
        assert columns_by_name["id"]["column_type"] == "UInt32"

        assert columns_by_name["name"]["comment"] == "User name field"
        assert columns_by_name["name"]["column_type"] == "String"

        assert columns_by_name["age"]["comment"] == "User age"
        assert columns_by_name["age"]["column_type"] == "UInt8"

        assert columns_by_name["created_at"]["comment"] == "Record creation timestamp"
        assert columns_by_name["created_at"]["column_type"] == "DateTime"
        assert columns_by_name["created_at"]["default_expression"] == "now()"


@pytest.mark.asyncio
async def test_system_database_access(mcp_server):
    """Test that we can access system databases."""
    async with Client(mcp_server) as client:
        # List tables in system database
        result = await client.call_tool("list_tables", {"database": "system"})
        tables = result.data

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


@pytest.mark.asyncio
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

    mcp.add_middleware(InFlightCounterMiddleware())

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
        query_result = json.loads(result.content[0].text)
        assert "rows" in query_result
        assert len(query_result["rows"]) == 1


@pytest.mark.asyncio
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
        res = result.data["rows"]
        user = res[0][0]
        indata = list(filter(lambda x: x[0] == user, users))
        assert len(indata) == 1
        user_row = indata[0]
        for res_row in res:
            assert res_row == user_row
