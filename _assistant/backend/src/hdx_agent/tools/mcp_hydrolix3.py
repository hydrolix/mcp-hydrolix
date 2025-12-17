"""
LangGraph integration for Hydrolix MCP Server tools.

This module provides:
- FastMCP client connection to the Hydrolix server
- LangGraph-compatible tool wrappers with server-defined metadata
- A pre-built agent graph for querying Hydrolix databases
"""

import json
from json import JSONEncoder
from typing import Any, Optional
from dataclasses import dataclass, field, asdict
from contextlib import asynccontextmanager

from fastmcp.exceptions import ToolError
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
        if base.endswith("/sse"):
            return base.rsplit("/sse", 1)[0] + "/mcp"
        return f"{base}/mcp" if not base.endswith("/mcp") else base


# =============================================================================
# Tool Metadata from Server
# =============================================================================


@dataclass
class MCPToolInfo:
    """
    Tool information including server-defined metadata.

    Captures the `meta` dict from @tool(meta={...}) on the FastMCP server.
    """

    name: str
    description: Optional[str] = None
    input_schema: Optional[dict] = None
    meta: dict[str, Any] = field(default_factory=dict)  # Server-defined metadata

    @classmethod
    def from_mcp_tool(cls, tool_def) -> "MCPToolInfo":
        """
        Create from an MCP tool definition.

        FastMCP stores custom meta in tool.annotations or tool.meta
        """
        # Extract custom metadata from annotations
        meta = {}
        if hasattr(tool_def, "annotations") and tool_def.annotations:
            # MCP protocol stores metadata in annotations
            meta = dict(tool_def.annotations)
        elif hasattr(tool_def, "meta") and tool_def.meta:
            # Direct meta attribute (FastMCP internal)
            meta = dict(tool_def.meta)

        return cls(
            name=tool_def.name,
            description=str(getattr(tool_def, "description", None))[:150],
            input_schema=getattr(tool_def, "inputSchema", None),
            meta=meta,
        )


# =============================================================================
# FastMCP Client Manager
# =============================================================================


class HydrolixMCPClient:
    """
    Manages the connection to the Hydrolix MCP server using FastMCP.
    Provides access to server-defined tool metadata.
    """

    def __init__(self, config: HydrolixMCPConfig):
        self.config = config
        self._tools_cache: Optional[dict[str, MCPToolInfo]] = None

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

    async def _ensure_tools_cached(self, client: Client) -> dict[str, MCPToolInfo]:
        """Fetch and cache tool definitions with metadata."""
        if self._tools_cache is None:
            tools = await client.list_tools()
            self._tools_cache = {t.name: MCPToolInfo.from_mcp_tool(t) for t in tools}
        return self._tools_cache

    async def get_tool_info(self, name: str) -> Optional[MCPToolInfo]:
        """Get full tool info including server-defined meta."""
        async with self.session() as client:
            cache = await self._ensure_tools_cached(client)
            return cache.get(name)

    async def get_tool_meta(self, name: str) -> dict[str, Any]:
        """Get just the server-defined meta dict for a tool."""
        info = await self.get_tool_info(name)
        return info.meta if info else {}

    async def list_tools_info(self) -> list[MCPToolInfo]:
        """List all tools with their full info and metadata."""
        async with self.session() as client:
            cache = await self._ensure_tools_cached(client)
            return list(cache.values())

    def _parse_content(self, result) -> Any:
        """Parse MCP result content."""
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

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool and return the result."""
        return await self.call_tool_with_info(name=name, arguments=arguments)
        # async with self.session() as client:
        #     result = await client.call_tool(name, arguments)
        #
        # if hasattr(result, "isError") and result.isError:
        #     raise ToolException(f"MCP tool error: {result.content}")
        #
        # return self._parse_content(result)

    async def call_tool_with_info(
        self, name: str, arguments: dict[str, Any]
    ) -> Any | dict[str, Any | MCPToolInfo]:
        """
        Call a tool and return both result and tool info.

        Returns:
            Tuple of (result_data, tool_info_with_meta)
        """
        async with self.session() as client:
            cache = await self._ensure_tools_cached(client)
            tool_info = cache.get(name, MCPToolInfo(name=name))

            try:
                result = await client.call_tool(name, arguments)
            except ToolError as e:
                return {"error": str(e), "tool_info": tool_info}

            if hasattr(result, "isError") and result.isError:
                return {"error": result.content, "tool_info": tool_info}
            # if hasattr(result, "isError") and result.isError:
            #     raise ToolException(f"MCP tool error: {result.content}")

            return {"content": self._parse_content(result), "tool_info": asdict(tool_info)}

    async def list_tools(self) -> list:
        """List raw MCP tool definitions."""
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
        _mcp_client = HydrolixMCPClient(HydrolixMCPConfig(server_url=config.mcp.url))
    return _mcp_client


# =============================================================================
# LangGraph Tool Definitions
# =============================================================================


def _validate_identifier(name: str, label: str) -> Optional[dict]:
    """Validate a database/table identifier."""
    if not name.replace("_", "").isalnum():
        return {"error": f"Invalid {label} name: {name}"}
    return None


@tool
async def list_databases() -> list[str]:
    """
    List all available Hydrolix databases.

    Returns a list of database names that can be queried.
    """
    client = _get_mcp_client()
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
    """
    client = _get_mcp_client()
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
    """
    if err := _validate_identifier(database, "database"):
        return err
    if err := _validate_identifier(table, "table"):
        return err

    try:
        client = _get_mcp_client()

        result = await client.call_tool(
            "run_select_query", {"query": f"DESCRIBE TABLE `{database}`.`{table}`"}
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
            "run_select_query", {"query": f"SELECT count() FROM `{database}`.`{table}`"}
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

    Args:
        query: The SELECT SQL query to execute

    Returns:
        Dictionary with 'columns' and 'rows'
    """
    sql_upper = query.strip().upper()
    if not sql_upper.startswith(("SELECT", "WITH")):
        return {"error": "Only SELECT queries are allowed."}

    client = _get_mcp_client()
    return await client.call_tool("run_select_query", {"query": query})


@tool
async def get_sample_data(database: str, table: str, limit: int = 5) -> dict[str, Any]:
    """
    Get sample rows from a table to understand its data.

    Args:
        database: Name of the database.
        table: Name of the table.
        limit: Number of sample rows (default 5, max 20).
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
# Tool Collection with Metadata Access
# =============================================================================


async def get_hydrolix_tools() -> list:
    """Get all Hydrolix tools including MCP server tools."""
    client = _get_mcp_client()
    mcp_tools = await client.list_tools()

    return [
        list_databases,
        list_tables,
        describe_table,
        run_select_query,
        get_sample_data,
    ]  # + mcp_tools


async def get_all_tools_info() -> list[MCPToolInfo]:
    """
    Get all MCP tools with their server-defined metadata.

    Example server definition:
        @mcp.tool(meta={"category": "query", "cost": "low"})
        def my_tool(...): ...

    Returns:
        List of MCPToolInfo with .meta containing the server's meta dict
    """
    client = _get_mcp_client()
    return await client.list_tools_info()


async def get_tool_meta(tool_name: str) -> dict[str, Any]:
    """
    Get the server-defined meta dict for a specific tool.

    Args:
        tool_name: Name of the MCP tool

    Returns:
        The meta dict defined with @tool(meta={...}) on the server
    """
    client = _get_mcp_client()
    return await client.get_tool_meta(tool_name)
