"""
LangGraph integration for Hydrolix MCP Server tools.

This module provides:
- FastMCP client connection to the Hydrolix server
- LangGraph-compatible tool wrappers
- A pre-built agent graph for querying Hydrolix databases
"""
import json
from typing import Any, Optional
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

from langchain_core.tools import tool, ToolException
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport, SSETransport

from hdx_agent.config import Config


# =============================================================================
# Configuration
# =============================================================================


class TransportType:
    """Supported MCP transport types."""
    SSE = "sse"
    HTTP = "http"


@dataclass
class HydrolixMCPConfig:
    """Configuration for connecting to the Hydrolix MCP server."""
    server_url: str
    transport: str = TransportType.HTTP
    timeout: float = 60.0
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def endpoint_url(self) -> str:
        """Get the appropriate endpoint URL based on transport type."""
        base = self.server_url.rstrip("/")
        if self.transport == TransportType.SSE:
            return f"{base}/sse" if not base.endswith("/sse") else base
        # HTTP streaming
        if base.endswith("/sse"):
            return base.rsplit("/sse", 1)[0] + "/mcp"
        return f"{base}/mcp" if not base.endswith("/mcp") else base


# =============================================================================
# FastMCP Client Manager
# =============================================================================


class HydrolixMCPClient:
    """
    Manages the connection to the Hydrolix MCP server using FastMCP.
    Supports both SSE and Streamable HTTP transports.
    """

    def __init__(self, config: HydrolixMCPConfig):
        self.config = config
        self._client: Optional[Client] = None

    def _create_transport(self):
        """Create the appropriate transport based on config."""
        url = self.config.endpoint_url
        headers = self.config.headers or None

        if self.config.transport == TransportType.SSE:
            return SSETransport(url, headers=headers, sse_read_timeout=self.config.timeout)
        return StreamableHttpTransport(url, headers=headers, sse_read_timeout=self.config.timeout)

    @asynccontextmanager
    async def session(self):
        """Context manager for MCP client sessions."""
        transport = self._create_transport()
        async with Client(transport) as client:
            yield client

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool and return the result."""
        async with self.session() as client:
            result = await client.call_tool(name, arguments)

        # Handle errors
        if hasattr(result, "isError") and result.isError:
            raise ToolException(f"MCP tool error: {result.content}")

        # Parse result content
        if isinstance(result, list) and result:
            content = result[0]
            if hasattr(content, "text"):
                try:
                    return json.loads(content.text)
                except json.JSONDecodeError:
                    return content.text
            return content

        if hasattr(result, "content") and result.content:
            content = result.content[0]
            if hasattr(content, "text"):
                try:
                    return json.loads(content.text)
                except json.JSONDecodeError:
                    return content.text

        return result

    async def list_tools(self) -> list:
        """List available tools from the MCP server."""
        async with self.session() as client:
            return await client.list_tools()


# =============================================================================
# Global Client Instance
# =============================================================================

_mcp_client: Optional[HydrolixMCPClient] = None


def _set_mcp_client(client: HydrolixMCPClient):
    """Set the global MCP client instance."""
    global _mcp_client
    _mcp_client = client


def _get_mcp_client() -> HydrolixMCPClient:
    """Get or create the global MCP client instance."""
    global _mcp_client
    if _mcp_client is None:
        config = Config()
        _mcp_client = HydrolixMCPClient(
            HydrolixMCPConfig(server_url=config.mcp.url)
        )
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
    client = _get_mcp_client()
    return await client.call_tool("list_databases", {})


@tool
async def list_tables(
        database: str,
        like: Optional[str] = None,
        not_like: Optional[str] = None
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
    client = _get_mcp_client()
    args = {"database": database}
    if like:
        args["like"] = like
    if not_like:
        args["not_like"] = not_like
    return await client.call_tool("list_tables", args)


def _validate_identifier(name: str, label: str) -> Optional[dict]:
    """Validate a database/table identifier."""
    if not name.replace("_", "").isalnum():
        return {"error": f"Invalid {label} name: {name}"}
    return None


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
    if err := _validate_identifier(database, "database"):
        return err
    if err := _validate_identifier(table, "table"):
        return err

    try:
        client = _get_mcp_client()

        result = await client.call_tool(
            "run_select_query",
            {"query": f"DESCRIBE TABLE `{database}`.`{table}`"}
        )

        columns = [
            {
                "name": row[0],
                "type": row[1],
                "default_type": row[2] if len(row) > 2 else None,
                "default_expression": row[3] if len(row) > 3 else None,
                "comment": row[4] if len(row) > 4 else None,
            }
            for row in result.get("rows", [])
        ]

        count_result = await client.call_tool(
            "run_select_query",
            {"query": f"SELECT count() FROM `{database}`.`{table}`"}
        )
        rows = count_result.get("rows", [])
        row_count = rows[0][0] if rows else 0

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
    if not sql_upper.startswith(("SELECT", "WITH")):
        return {
            "error": "Only SELECT queries are allowed for safety. "
                     "Use WITH...SELECT for CTEs."
        }

    client = _get_mcp_client()
    return await client.call_tool("run_select_query", {"query": query})


@tool
async def get_sample_data(
        database: str,
        table: str,
        limit: int = 5
) -> dict[str, Any]:
    """
    Get sample rows from a table to understand its data.

    Args:
        database: Name of the database.
        table: Name of the table.
        limit: Number of sample rows (default 5, max 20).

    Returns:
        Dictionary with sample data and column information.
    """
    if err := _validate_identifier(database, "database"):
        return err
    if err := _validate_identifier(table, "table"):
        return err

    try:
        client = _get_mcp_client()
        limit = min(max(1, limit), 20)

        query = f"SELECT * FROM `{database}`.`{table}` LIMIT {limit}"
        result = await client.call_tool("run_select_query", {"query": query})

        return {
            "database": database,
            "table": table,
            "columns": result.get("columns", []),
            "sample_rows": result.get("rows", []),
            "row_count": len(result.get("rows", [])),
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# Tool Collection
# =============================================================================


async def get_hydrolix_tools() -> list:
    """
    Get all Hydrolix tools including MCP server tools.

    Returns:
        List of LangGraph-compatible tools.
    """
    client = _get_mcp_client()
    mcp_tools = await client.list_tools()

    # Local tool wrappers + remote MCP tools
    return [
        list_tables,
        list_databases,
        run_select_query,
        describe_table,
        get_sample_data,
    ] #+ mcp_tools