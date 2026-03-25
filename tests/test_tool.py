import inspect

import pytest
from fastmcp.exceptions import ToolError

from mcp_hydrolix import (
    get_table_info,
    list_databases,
    list_tables,
    run_select_query,
)


class TestHydrolixTools:
    async def test_list_databases(self, setup_tool_test_database):
        """Test listing databases."""
        test_db, _ = setup_tool_test_database
        result = await list_databases()
        assert test_db in result

    async def test_list_tables_without_like(self, setup_tool_test_database):
        """Test listing tables without a 'LIKE' filter."""
        test_db, test_table = setup_tool_test_database
        result = await list_tables(test_db)
        assert isinstance(result, list)
        assert len(result) == 1
        table = result[0]
        assert table.name == test_table

    async def test_list_tables_with_like(self, setup_tool_test_database):
        """Test listing tables with a 'LIKE' filter."""
        test_db, test_table = setup_tool_test_database
        result = await list_tables(test_db, like=f"{test_table}%")
        assert isinstance(result, list)
        assert len(result) == 1
        table = result[0]
        assert table.name == test_table

    async def test_run_select_query_success(self, setup_tool_test_database):
        """Test running a SELECT query successfully."""
        test_db, test_table = setup_tool_test_database
        query = f"SELECT * FROM {test_db}.{test_table}"
        result = await inspect.unwrap(run_select_query)(query)
        assert isinstance(result, dict)
        assert len(result["rows"]) == 2
        assert result["rows"][0][0] == 1
        assert result["rows"][0][1] == "Alice"

    async def test_run_select_query_failure(self, setup_tool_test_database):
        """Test running a SELECT query with an error."""
        test_db, _ = setup_tool_test_database
        query = f"SELECT * FROM {test_db}.non_existent_table"

        with pytest.raises(ToolError) as exc_info:
            await run_select_query(query)

        assert "Query execution failed" in str(exc_info.value)

    async def test_column_comments(self, setup_tool_test_database):
        """Test that column comments are correctly retrieved.

        Updated: Now uses get_table_info() instead of list_tables()
        since list_tables() no longer returns column metadata.
        """
        test_db, test_table = setup_tool_test_database

        # First verify the table exists
        tables = await list_tables(test_db)
        assert isinstance(tables, list)
        assert len(tables) == 1
        assert tables[0].name == test_table

        # Now get detailed table info including columns
        table_info = await get_table_info(test_db, test_table)

        # Get columns by name for easier testing
        columns = {col.name: col.__dict__ for col in table_info.columns}

        # Verify column comments
        assert columns["id"]["comment"] == "Primary identifier"
        assert columns["name"]["comment"] == "User name field"
