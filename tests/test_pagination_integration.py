"""Integration tests for pagination functionality."""

import inspect

import pytest
import pytest_asyncio
from mcp_clickhouse.mcp_server import create_clickhouse_client

from mcp_hydrolix.mcp_server import list_tables, run_select_query

# Access underlying functions (MCP tools are wrapped)
list_tables_fn = list_tables.fn
# run_select_query has @with_serializer decorator, need to unwrap
run_select_query_fn = inspect.unwrap(run_select_query.fn)


@pytest_asyncio.fixture(scope="module")
async def setup_pagination_test_database():
    """Set up test database with many tables for pagination testing."""
    client = create_clickhouse_client()
    test_db = "test_pagination_db"

    # Create database
    client.command(f"DROP DATABASE IF EXISTS {test_db}")
    client.command(f"CREATE DATABASE {test_db}")

    # Create 125 tables for pagination testing (will be 3 pages of 50)
    table_count = 125
    for i in range(table_count):
        table_name = f"test_table_{i:03d}"
        client.command(f"""
            CREATE TABLE {test_db}.{table_name} (
                id UInt32,
                value String,
                timestamp DateTime
            ) ENGINE = MergeTree()
            ORDER BY id
        """)

    yield test_db, table_count

    # Cleanup
    client.command(f"DROP DATABASE IF EXISTS {test_db}")


@pytest_asyncio.fixture(scope="module")
async def setup_large_query_result():
    """Set up test table with many rows for query result pagination."""
    client = create_clickhouse_client()
    test_db = "test_query_pagination_db"
    test_table = "large_data"

    # Create database and table
    client.command(f"DROP DATABASE IF EXISTS {test_db}")
    client.command(f"CREATE DATABASE {test_db}")
    client.command(f"""
        CREATE TABLE {test_db}.{test_table} (
            id UInt32,
            value String,
            timestamp DateTime
        ) ENGINE = MergeTree()
        ORDER BY id
    """)

    # Insert 25,000 rows for pagination testing (will be 3 pages of 10,000)
    row_count = 25000
    client.command(f"""
        INSERT INTO {test_db}.{test_table}
        SELECT number, toString(number), now() + INTERVAL number SECOND
        FROM numbers({row_count})
    """)

    yield test_db, test_table, row_count

    # Cleanup
    client.command(f"DROP DATABASE IF EXISTS {test_db}")


class TestListTablesPagination:
    """Tests for list_tables pagination."""

    @pytest.mark.asyncio
    async def test_list_tables_first_page(self, setup_pagination_test_database):
        """Test getting first page of tables."""
        test_db, total_tables = setup_pagination_test_database

        result = await list_tables_fn(database=test_db)

        assert "tables" in result
        assert "nextCursor" in result
        assert "pageSize" in result
        assert "totalRetrieved" in result

        # Should return first page (50 tables)
        assert len(result["tables"]) == 50
        assert result["pageSize"] == 50
        assert result["totalRetrieved"] == 50
        assert result["nextCursor"] is not None  # More pages exist

    @pytest.mark.asyncio
    async def test_list_tables_pagination_complete(self, setup_pagination_test_database):
        """Test paginating through all tables."""
        test_db, total_tables = setup_pagination_test_database

        all_tables = []
        cursor = None
        page_count = 0

        while True:
            result = await list_tables_fn(database=test_db, cursor=cursor)

            all_tables.extend([t.name for t in result["tables"]])
            page_count += 1

            cursor = result.get("nextCursor")
            if not cursor:
                break

        # Should have retrieved all tables
        assert len(all_tables) == total_tables
        assert page_count == 3  # 125 tables / 50 per page = 3 pages

        # All table names should be unique
        assert len(set(all_tables)) == total_tables

        # Verify tables are named correctly
        for i in range(total_tables):
            expected_name = f"test_table_{i:03d}"
            assert expected_name in all_tables

    @pytest.mark.asyncio
    async def test_list_tables_last_page_partial(self, setup_pagination_test_database):
        """Test that last page contains remaining tables (not full page)."""
        test_db, total_tables = setup_pagination_test_database

        # Navigate to last page
        cursor = None
        pages = []

        while True:
            result = await list_tables_fn(database=test_db, cursor=cursor)
            pages.append(result)
            cursor = result.get("nextCursor")
            if not cursor:
                break

        # Last page should have 25 tables (125 % 50 = 25)
        last_page = pages[-1]
        assert last_page["pageSize"] == 25
        assert last_page["nextCursor"] is None
        assert last_page["totalRetrieved"] == total_tables

    @pytest.mark.asyncio
    async def test_list_tables_with_like_filter(self, setup_pagination_test_database):
        """Test pagination with LIKE filter."""
        test_db, _ = setup_pagination_test_database

        # Filter for tables 010-019 (10 tables)
        result = await list_tables_fn(database=test_db, like="test_table_01%")

        assert len(result["tables"]) == 10
        assert result["nextCursor"] is None  # All results fit in one page
        assert all("_01" in t.name for t in result["tables"])

    @pytest.mark.asyncio
    async def test_list_tables_invalid_cursor(self, setup_pagination_test_database):
        """Test invalid cursor returns error."""
        test_db, _ = setup_pagination_test_database

        with pytest.raises(Exception, match="Invalid cursor"):
            await list_tables_fn(database=test_db, cursor="invalid_cursor_data")

    @pytest.mark.asyncio
    async def test_list_tables_cursor_parameter_mismatch(self, setup_pagination_test_database):
        """Test cursor from different parameters is rejected."""
        test_db, _ = setup_pagination_test_database

        # Get cursor with LIKE filter
        result1 = await list_tables_fn(database=test_db, like="test_table_0%")
        cursor = result1["nextCursor"]

        if cursor:  # Only test if cursor was generated
            # Try to use cursor without LIKE filter (parameter mismatch)
            with pytest.raises(Exception, match="Cursor parameter mismatch|Invalid cursor"):
                await list_tables_fn(database=test_db, cursor=cursor)

    @pytest.mark.asyncio
    async def test_list_tables_each_table_has_columns(self, setup_pagination_test_database):
        """Test that tables include column metadata."""
        test_db, _ = setup_pagination_test_database

        result = await list_tables_fn(database=test_db)

        # Each table should have columns populated
        for table in result["tables"]:
            assert table.columns is not None
            assert len(table.columns) > 0
            # Should have at least id, value, timestamp columns
            assert len(table.columns) >= 3


class TestRunSelectQueryPagination:
    """Tests for run_select_query pagination."""

    @pytest.mark.asyncio
    async def test_query_result_first_page(self, setup_large_query_result):
        """Test getting first page of query results."""
        test_db, test_table, _ = setup_large_query_result
        query = f"SELECT id, value FROM {test_db}.{test_table} ORDER BY id"

        result = await run_select_query_fn(query)

        assert "columns" in result
        assert "rows" in result
        assert "nextCursor" in result
        assert "pageSize" in result
        assert "totalRetrieved" in result
        assert "hasMore" in result

        # Should return first page (10,000 rows)
        assert len(result["rows"]) == 10000
        assert result["pageSize"] == 10000
        assert result["totalRetrieved"] == 10000
        assert result["hasMore"] is True
        assert result["nextCursor"] is not None

    @pytest.mark.asyncio
    async def test_query_result_pagination_complete(self, setup_large_query_result):
        """Test paginating through all query results."""
        test_db, test_table, total_rows = setup_large_query_result
        query = f"SELECT id FROM {test_db}.{test_table} ORDER BY id"

        all_rows = []
        cursor = None
        page_count = 0

        while True:
            result = await run_select_query_fn(query, cursor=cursor)

            all_rows.extend(result["rows"])
            page_count += 1

            cursor = result.get("nextCursor")
            if not cursor:
                break

        # Should have retrieved all rows
        assert len(all_rows) == total_rows
        assert page_count == 3  # 25,000 rows / 10,000 per page = 3 pages

        # Verify ordering is maintained
        assert all_rows[0][0] == 0
        assert all_rows[-1][0] == total_rows - 1

    @pytest.mark.asyncio
    async def test_query_result_last_page_partial(self, setup_large_query_result):
        """Test that last page contains remaining rows."""
        test_db, test_table, total_rows = setup_large_query_result
        query = f"SELECT id FROM {test_db}.{test_table} ORDER BY id"

        # Navigate to last page
        cursor = None
        pages = []

        while True:
            result = await run_select_query_fn(query, cursor=cursor)
            pages.append(result)
            cursor = result.get("nextCursor")
            if not cursor:
                break

        # Last page should have 5,000 rows (25,000 % 10,000 = 5,000)
        last_page = pages[-1]
        assert last_page["pageSize"] == 5000
        assert last_page["hasMore"] is False
        assert last_page["nextCursor"] is None
        assert last_page["totalRetrieved"] == total_rows

    @pytest.mark.asyncio
    async def test_query_result_invalid_cursor(self, setup_large_query_result):
        """Test invalid cursor returns error."""
        test_db, test_table, _ = setup_large_query_result
        query = f"SELECT id FROM {test_db}.{test_table}"

        with pytest.raises(Exception, match="Invalid cursor"):
            await run_select_query_fn(query, cursor="invalid_cursor_data")

    @pytest.mark.asyncio
    async def test_query_result_cursor_query_mismatch(self, setup_large_query_result):
        """Test cursor from different query is rejected."""
        test_db, test_table, _ = setup_large_query_result

        # Get cursor from first query
        query1 = f"SELECT id FROM {test_db}.{test_table} ORDER BY id"
        result1 = await run_select_query_fn(query1)
        cursor = result1["nextCursor"]

        # Try to use cursor with different query
        query2 = f"SELECT value FROM {test_db}.{test_table} ORDER BY id"
        with pytest.raises(Exception, match="Query has changed|Invalid cursor"):
            await run_select_query_fn(query2, cursor=cursor)

    @pytest.mark.asyncio
    async def test_query_with_existing_limit(self, setup_large_query_result):
        """Test pagination wraps queries that already have LIMIT."""
        test_db, test_table, _ = setup_large_query_result

        # Query with existing LIMIT should be wrapped in subquery
        query = f"SELECT id FROM {test_db}.{test_table} ORDER BY id LIMIT 15000"

        result = await run_select_query_fn(query)

        # Should still paginate to 10,000 rows per page
        assert len(result["rows"]) == 10000
        assert result["hasMore"] is True

    @pytest.mark.asyncio
    async def test_query_maintains_column_names(self, setup_large_query_result):
        """Test that column names are preserved through pagination."""
        test_db, test_table, _ = setup_large_query_result
        query = f"SELECT id, value AS my_value, timestamp FROM {test_db}.{test_table} ORDER BY id"

        result = await run_select_query_fn(query)

        assert list(result["columns"]) == ["id", "my_value", "timestamp"]

    @pytest.mark.asyncio
    async def test_query_empty_result_set(self, setup_large_query_result):
        """Test query with no results."""
        test_db, test_table, _ = setup_large_query_result
        query = f"SELECT id FROM {test_db}.{test_table} WHERE id > 999999"

        result = await run_select_query_fn(query)

        assert len(result["rows"]) == 0
        assert result["pageSize"] == 0
        assert result["hasMore"] is False
        assert result["nextCursor"] is None


class TestPaginationEdgeCases:
    """Tests for pagination edge cases."""

    @pytest.mark.asyncio
    async def test_single_page_result_no_cursor(self, setup_pagination_test_database):
        """Test that single-page results don't include nextCursor."""
        test_db, _ = setup_pagination_test_database

        # Filter to get only 10 tables (less than page size of 50)
        result = await list_tables_fn(database=test_db, like="test_table_00%")

        assert len(result["tables"]) == 10
        assert result["nextCursor"] is None
        assert result["totalRetrieved"] == 10

    @pytest.mark.asyncio
    async def test_cursor_data_structure(self, setup_pagination_test_database):
        """Test cursor contains expected fields."""
        test_db, _ = setup_pagination_test_database

        result = await list_tables_fn(database=test_db)
        cursor = result.get("nextCursor")

        if cursor:
            from mcp_hydrolix.pagination import decode_cursor

            cursor_data = decode_cursor(cursor)

            assert "type" in cursor_data
            assert cursor_data["type"] == "table_list"
            assert "offset" in cursor_data
            assert cursor_data["offset"] == 50  # Second page starts at 50
            assert "params" in cursor_data
            assert cursor_data["params"]["database"] == test_db

    @pytest.mark.asyncio
    async def test_query_cursor_includes_hash(self, setup_large_query_result):
        """Test query result cursor includes query hash."""
        test_db, test_table, _ = setup_large_query_result
        query = f"SELECT id FROM {test_db}.{test_table}"

        result = await run_select_query_fn(query)
        cursor = result.get("nextCursor")

        if cursor:
            from mcp_hydrolix.pagination import decode_cursor, hash_query

            cursor_data = decode_cursor(cursor)

            assert "query_hash" in cursor_data
            assert cursor_data["query_hash"] == hash_query(query)
