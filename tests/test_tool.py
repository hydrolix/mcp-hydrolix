import asyncio
import inspect
import unittest

from fastmcp.exceptions import ToolError

from mcp_hydrolix import create_hydrolix_client, list_databases, list_tables, run_select_query


class TestHydrolixTools(unittest.IsolatedAsyncioTestCase):
    test_db = "test_tool_db"
    test_table = "test_table"

    @classmethod
    def setUpClass(cls):
        asyncio.run(cls.asyncSetUpClass())

    @classmethod
    def tearDownClass(cls):
        asyncio.run(cls.asyncTearDownClass())

    @classmethod
    async def asyncSetUpClass(cls):
        """Set up the environment before tests."""
        cls.client = await create_hydrolix_client(None, None)

        # Prepare test database and table
        await cls.client.command(f"CREATE DATABASE IF NOT EXISTS {cls.test_db}")

        # Drop table if exists to ensure clean state
        await cls.client.command(f"DROP TABLE IF EXISTS {cls.test_db}.{cls.test_table}")

        # Create table with comments
        await cls.client.command(f"""
            CREATE TABLE {cls.test_db}.{cls.test_table} (
                id UInt32 COMMENT 'Primary identifier',
                name String COMMENT 'User name field'
            ) ENGINE = MergeTree()
            ORDER BY id
            COMMENT 'Test table for unit testing'
        """)
        await cls.client.command(f"""
            INSERT INTO {cls.test_db}.{cls.test_table} (id, name) VALUES (1, 'Alice'), (2, 'Bob')
        """)

    @classmethod
    async def asyncTearDownClass(cls):
        """Clean up the environment after tests."""
        await cls.client.command(f"DROP DATABASE IF EXISTS {cls.test_db}")

    async def test_list_databases(self):
        """Test listing databases."""
        result = await list_databases.fn()
        # Parse JSON response
        databases = result
        self.assertIn(self.test_db, databases)

    async def test_list_tables_without_like(self):
        """Test listing tables without a 'LIKE' filter."""
        result = await list_tables.fn(self.test_db)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        table = result[0]
        self.assertEqual(table.name, self.test_table)

    async def test_list_tables_with_like(self):
        """Test listing tables with a 'LIKE' filter."""
        result = await list_tables.fn(self.test_db, like=f"{self.test_table}%")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        table = result[0]
        self.assertEqual(table.name, self.test_table)

    async def test_run_select_query_success(self):
        """Test running a SELECT query successfully."""
        query = f"SELECT * FROM {self.test_db}.{self.test_table}"
        result = await inspect.unwrap(run_select_query.fn)(query)
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(result["rows"][0][0], 1)
        self.assertEqual(result["rows"][0][1], "Alice")

    async def test_run_select_query_failure(self):
        """Test running a SELECT query with an error."""
        query = f"SELECT * FROM {self.test_db}.non_existent_table"

        # Should raise ToolError
        with self.assertRaises(ToolError) as context:
            await run_select_query.fn(query)

        self.assertIn("Query execution failed", str(context.exception))

    async def test_table_and_column_comments(self):
        """Test that table and column comments are correctly retrieved."""
        result = await list_tables.fn(self.test_db)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

        table_info = result[0]
        # Verify table comment
        self.assertEqual(table_info.comment, "Test table for unit testing")

        # Get columns by name for easier testing
        columns = {col.name: col.__dict__ for col in table_info.columns}

        # Verify column comments
        self.assertEqual(columns["id"]["comment"], "Primary identifier")
        self.assertEqual(columns["name"]["comment"], "User name field")


if __name__ == "__main__":
    unittest.main()
