"""
LangGraph integration for Hydrolix MCP Server tools.

This module provides:
- MCP client connection to the Hydrolix server
- LangGraph-compatible tool wrappers
- A pre-built agent graph for querying Hydrolix databases
"""
import asyncio
import json
from typing import Any, Optional
from dataclasses import dataclass

from langchain_core.tools import tool, ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from hdx_agent.config import Config


# =============================================================================
# Configuration
# =============================================================================


class TransportType:
    """Supported MCP transport types."""

    SSE = "sse"
    HTTP = "http"  # Streamable HTTP


@dataclass
class HydrolixMCPConfig:
    """Configuration for connecting to the Hydrolix MCP server."""

    server_url: str
    transport: str = TransportType.HTTP  # Default to HTTP streaming
    timeout: float = 60.0

    # HTTP-specific options
    http_headers: dict | None = None

    @property
    def sse_url(self) -> str:
        """Get SSE endpoint URL (typically /sse)."""
        base = self.server_url.rstrip("/")
        if not base.endswith("/sse"):
            return f"{base}/sse"
        return base

    @property
    def http_url(self) -> str:
        """Get HTTP streaming endpoint URL (typically /mcp)."""
        base = self.server_url.rstrip("/")
        if base.endswith("/sse"):
            return base.rsplit("/sse", 1)[0] + "/mcp"
        if not base.endswith("/mcp"):
            return f"{base}/mcp"
        return base


# =============================================================================
# MCP Client Manager
# =============================================================================


class HydrolixMCPClient:
    """
    Manages the connection to the Hydrolix MCP server.
    Supports both SSE and Streamable HTTP transports.
    Provides async context manager for session lifecycle.
    """

    def __init__(self, config: HydrolixMCPConfig):
        self.config = config
        self._client: Optional[MultiServerMCPClient] = None

    async def __aenter__(self) -> "HydrolixMCPClient":
        """Establish connection to MCP server using configured transport."""

        if self.config.transport == TransportType.HTTP:
            # Use Streamable HTTP transport
            url = self.config.http_url
        else:
            url = self.config.sse_url

        self._client = MultiServerMCPClient(
            {
                "hdx": {
                    "transport": self.config.transport,
                    "url": url,
                    # "headers": {
                    #     "Authorization": "Bearer YOUR_TOKEN",
                    #     "X-Custom-Header": "custom-value"
                    # },
                }
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up MCP connection."""
        pass

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool and return the result."""
        async with self._client.session("hdx") as session:
            result = await session.call_tool(name, arguments)

        if result.isError:
            raise ToolException(f"MCP tool error: {result.content}")

        # Parse the result content
        if result.content and len(result.content) > 0:
            content = result.content[0]
            if hasattr(content, "text"):
                try:
                    return json.loads(content.text)
                except json.JSONDecodeError:
                    return content.text
        return result.content

    async def list_tools(self):
        async with self._client.session("hdx") as session:
            return await load_mcp_tools(session)


# =============================================================================
# Global client instance (for tool functions)
# =============================================================================

_mcp_client: Optional[HydrolixMCPClient] = None


def _set_mcp_client(client: HydrolixMCPClient):
    """Set the global MCP client instance for tools to use."""
    global _mcp_client
    _mcp_client = client


async def _get_mcp_client() -> HydrolixMCPClient:
    """Get the global MCP client instance."""
    if _mcp_client is None:
        config = Config()
        client = await HydrolixMCPClient(HydrolixMCPConfig(server_url=config.mcp.url)).__aenter__()
        _set_mcp_client(client)
    return _mcp_client

# =============================================================================
# LangGraph Tool Definitions
# =============================================================================


@tool
async def list_databases() -> list[str]:
    """
    List all available Hydrolix databases.

    Returns a list of database names that can be queried.
    Use this to discover what data is available before running queries.
    """
    client = await _get_mcp_client()
    return await client.call_tool("list_databases", {})


@tool
async def list_tables(
    database: str, like: Optional[str] = None, not_like: Optional[str] = None
) -> list[dict]:
    """
    List available tables in a Hydrolix database with their schemas.

    Args:
        database: The name of the database to list tables from
        like: Optional pattern to filter table names (SQL LIKE syntax)
        not_like: Optional pattern to exclude table names (SQL LIKE syntax)

    Returns:
        List of tables with schema information including:
        - name, engine, columns, row counts, sorting/primary keys
    """
    client = await _get_mcp_client()
    args = {"database": database}
    if like:
        args["like"] = like
    if not_like:
        args["not_like"] = not_like
    return await client.call_tool("list_tables", args)


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
        client = await _get_mcp_client()
        if not database.replace("_", "").isalnum():
            return {"error": f"Invalid database name: {database}"}
        if not table.replace("_", "").isalnum():
            return {"error": f"Invalid table name: {table}"}

        result = client.call_tool("run_select_query", {"query": f"DESCRIBE TABLE `{database}`.`{table}`"})
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

        count_result = client.call_tool("run_select_query", {"query": "SELECT count() FROM `{database}`.`{table}`"})
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
async def run_select_query(query: str) -> dict[str, Any]:
    """
    Run a SELECT query against Hydrolix using ClickHouse SQL dialect.

    IMPORTANT: Queries timeout after 30 seconds. Always include performance guards:
    - Use LIMIT clauses for unbounded queries
    - Filter on the primary key (usually a timestamp) for time-series data
    - Select specific columns instead of SELECT *
    - For aggregations, apply LIMIT in a subquery before aggregating

    Args:
        query: The SELECT SQL query to execute

    Returns:
        Dictionary with 'columns' (list of column names) and 'rows' (list of row data)

    Examples:
        # Get recent logs with time filter
        "SELECT message, timestamp FROM app.logs WHERE timestamp > now() - INTERVAL 10 MINUTES"

        # Aggregate with subquery limit
        "SELECT median(value) FROM (SELECT value FROM metrics.data LIMIT 1000)"

        # Date range filter
        "SELECT min(temp) FROM weather.readings WHERE date > now() - INTERVAL 1 YEAR"
    """

    sql_upper = query.strip().upper()
    if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
        return {
            "error": "Only SELECT queries are allowed for safety. "
                     "Use WITH...SELECT for CTEs."
        }

    client = await _get_mcp_client()
    result = await client.call_tool("run_select_query", {"query": query})
    return result


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
        client = await _get_mcp_client()
        if not database.replace("_", "").isalnum():
            return {"error": f"Invalid database name: {database}"}
        if not table.replace("_", "").isalnum():
            return {"error": f"Invalid table name: {table}"}

        limit = min(max(1, limit), 20)
        query = f"SELECT * FROM `{database}`.`{table}` LIMIT {limit}"
        result = await client.call_tool("run_select_query", {"query": query})

        return {
            "database": database,
            "table": table,
            "columns": result.column_names,
            "sample_rows": result.result_rows,
            "row_count": len(result.result_rows),
        }
    except Exception as e:
        return {"error": str(e)}

async def get_hydrolix_tools():
    client = await _get_mcp_client()
    tools = await client.list_tools()
    return [describe_table, get_sample_data] + tools