import pytest
import pytest_asyncio
from mcp_clickhouse.mcp_server import create_clickhouse_client

from mcp_hydrolix.mcp_server import mcp
from mcp_hydrolix import create_hydrolix_client


@pytest.fixture(scope="session")
def mcp_server():
    """Return the MCP server instance for testing."""
    return mcp


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def setup_test_database():
    """Set up test database and tables before running tests."""
    client = create_clickhouse_client()

    test_db = "test_mcp_db"
    test_table = "test_table"
    test_table2 = "another_test_table"

    client.command(f"CREATE DATABASE IF NOT EXISTS {test_db}")

    client.command(f"DROP TABLE IF EXISTS {test_db}.{test_table}")
    client.command(f"DROP TABLE IF EXISTS {test_db}.{test_table2}")

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

    client.command(f"""
        CREATE TABLE {test_db}.{test_table2} (
            event_id UInt64,
            event_type String,
            timestamp DateTime
        ) ENGINE = MergeTree()
        ORDER BY (event_type, timestamp)
        COMMENT 'Event tracking table'
    """)

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

    client.command(f"DROP DATABASE IF EXISTS {test_db}")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def setup_tool_test_database():
    """Set up test database for tool-level tests."""
    test_db = "test_tool_db"
    test_table = "test_table"

    client = await create_hydrolix_client(None, None)

    await client.command(f"CREATE DATABASE IF NOT EXISTS {test_db}")
    await client.command(f"DROP TABLE IF EXISTS {test_db}.{test_table}")

    await client.command(f"""
        CREATE TABLE {test_db}.{test_table} (
            id UInt32 COMMENT 'Primary identifier',
            name String COMMENT 'User name field'
        ) ENGINE = MergeTree()
        ORDER BY id
        COMMENT 'Test table for unit testing'
    """)
    await client.command(f"""
        INSERT INTO {test_db}.{test_table} (id, name) VALUES (1, 'Alice'), (2, 'Bob')
    """)

    yield test_db, test_table

    await client.command(f"DROP DATABASE IF EXISTS {test_db}")
