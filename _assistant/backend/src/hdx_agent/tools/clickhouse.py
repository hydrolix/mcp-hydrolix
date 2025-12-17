"""ClickHouse MCP tool bindings."""

from typing import Any
from langchain_core.tools import tool
import clickhouse_connect
from hdx_agent.config import get_settings


def get_client():
    """Get ClickHouse client instance."""
    settings = get_settings()
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
    )


@tool
async def list_databases() -> dict[str, Any]:
    """
    List all available databases in ClickHouse.

    Returns:
        Dictionary with 'databases' key containing list of database names.
    """
    try:
        client = get_client()
        result = client.query("SHOW DATABASES")
        databases = [row[0] for row in result.result_rows]
        return {
            "databases": databases,
            "count": len(databases),
        }
    except Exception as e:
        return {"error": str(e)}


@tool
async def list_tables(database: str) -> dict[str, Any]:
    """
    List all tables in the specified database.

    Args:
        database: Name of the database to list tables from.

    Returns:
        Dictionary with 'tables' key containing list of table names.
    """
    try:
        client = get_client()
        if not database.replace("_", "").isalnum():
            return {"error": f"Invalid database name: {database}"}

        result = client.query(f"SHOW TABLES FROM `{database}`")
        tables = [row[0] for row in result.result_rows]
        return {
            "database": database,
            "tables": tables,
            "count": len(tables),
        }
    except Exception as e:
        return {"error": str(e)}


@tool
async def describe_table(database: str, table: str) -> dict[str, Any]:
    """
    Get detailed schema information for a table.

    Args:
        database: Name of the database containing the table.
        table: Name of the table to describe.

    Returns:
        Dictionary with column information including names, types, and metadata.
    """
    try:
        client = get_client()
        if not database.replace("_", "").isalnum():
            return {"error": f"Invalid database name: {database}"}
        if not table.replace("_", "").isalnum():
            return {"error": f"Invalid table name: {table}"}

        result = client.query(f"DESCRIBE TABLE `{database}`.`{table}`")
        columns = [
            {
                "name": row[0],
                "type": row[1],
                "default_type": row[2] if len(row) > 2 else None,
                "default_expression": row[3] if len(row) > 3 else None,
                "comment": row[4] if len(row) > 4 else None,
            }
            for row in result.result_rows
        ]

        count_result = client.query(
            f"SELECT count() FROM `{database}`.`{table}`"
        )
        row_count = count_result.result_rows[0][0] if count_result.result_rows else 0

        return {
            "database": database,
            "table": table,
            "columns": columns,
            "column_count": len(columns),
            "approximate_row_count": row_count,
        }
    except Exception as e:
        return {"error": str(e)}


@tool
async def run_query(sql: str) -> dict[str, Any]:
    """
    Execute a ClickHouse SQL query and return results.

    Args:
        sql: The SQL query to execute. Must be a SELECT query for safety.

    Returns:
        Dictionary with columns, rows, and metadata. Limited to 100 rows.
    """
    try:
        client = get_client()

        sql_upper = sql.strip().upper()
        if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
            return {
                "error": "Only SELECT queries are allowed for safety. "
                         "Use WITH...SELECT for CTEs."
            }

        result = client.query(sql)

        max_rows = 100
        rows = result.result_rows[:max_rows]
        truncated = len(result.result_rows) > max_rows

        return {
            "columns": result.column_names,
            "rows": rows,
            "row_count": len(rows),
            "total_rows": result.row_count,
            "truncated": truncated,
            "sql": sql,
        }
    except Exception as e:
        return {
            "error": str(e),
            "sql": sql,
        }


@tool
async def get_sample_data(database: str, table: str, limit: int = 5) -> dict[str, Any]:
    """
    Get sample rows from a table to understand its data.

    Args:
        database: Name of the database.
        table: Name of the table.
        limit: Number of sample rows (default 5, max 20).

    Returns:
        Dictionary with sample data and column information.
    """
    try:
        client = get_client()
        if not database.replace("_", "").isalnum():
            return {"error": f"Invalid database name: {database}"}
        if not table.replace("_", "").isalnum():
            return {"error": f"Invalid table name: {table}"}

        limit = min(max(1, limit), 20)

        result = client.query(
            f"SELECT * FROM `{database}`.`{table}` LIMIT {limit}"
        )

        return {
            "database": database,
            "table": table,
            "columns": result.column_names,
            "sample_rows": result.result_rows,
            "row_count": len(result.result_rows),
        }
    except Exception as e:
        return {"error": str(e)}


clickhouse_tools = [
    list_databases,
    list_tables,
    describe_table,
    run_query,
    get_sample_data,
]
