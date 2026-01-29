import json
import logging
import signal
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from typing import Any, Final, Optional, List, cast, TypedDict

import clickhouse_connect
from clickhouse_connect import common
from clickhouse_connect.driver import httputil
from clickhouse_connect.driver.binding import format_query_value
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from jwt import DecodeError
from pydantic import Field
from pydantic.dataclasses import dataclass
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from mcp_hydrolix.auth import (
    AccessToken,
    HydrolixCredential,
    HydrolixCredentialChain,
    ServiceAccountToken,
    UsernamePassword,
)
from mcp_hydrolix.mcp_env import HydrolixConfig, get_config
from mcp_hydrolix.utils import with_serializer


@dataclass
class Column:
    database: str
    table: str
    name: str
    column_type: str
    default_kind: Optional[str]
    default_expression: Optional[str]
    comment: Optional[str]


@dataclass
class Table:
    database: str
    name: str
    engine: str
    create_table_query: str
    dependencies_database: List[str]
    dependencies_table: List[str]
    engine_full: str
    sorting_key: str
    primary_key: str
    total_rows: Optional[int]
    total_bytes: Optional[int]
    total_bytes_uncompressed: Optional[int]
    parts: Optional[int]
    active_parts: Optional[int]
    total_marks: Optional[int]
    columns: Optional[List[Column]] = Field([])
    comment: Optional[str] = None


@dataclass
class HdxQueryResult(TypedDict):
    columns: List[str]
    rows: List[List[Any]]


MCP_SERVER_NAME = "mcp-hydrolix"
logger = logging.getLogger(MCP_SERVER_NAME)

load_dotenv()

HYDROLIX_CONFIG: Final[HydrolixConfig] = get_config()

mcp = FastMCP(
    name=MCP_SERVER_NAME,
    auth=HydrolixCredentialChain(None),
)


def get_request_credential() -> Optional[HydrolixCredential]:
    if (token := get_access_token()) is not None:
        if isinstance(token, AccessToken):
            try:
                return token.as_credential()
            except DecodeError:
                raise ValueError("The provided access token is invalid.")
        else:
            raise ValueError(
                "Found non-hydrolix access token on request -- this should be impossible!"
            )
    return None


async def create_hydrolix_client(pool_mgr, request_credential: Optional[HydrolixCredential]):
    """
    Create a client for operations against query-head. Note that this eagerly issues requests for initialization
    of properties like `server_version`, and so may throw exceptions.
    INV: clients returned by this method MUST NOT be reused across sessions, because they can close over per-session
    credentials.
    """
    creds = HYDROLIX_CONFIG.creds_with(request_credential)
    auth_info = (
        f"as {creds.username}"
        if isinstance(creds, UsernamePassword)
        else f"using service account {cast(ServiceAccountToken, creds).service_account_id}"
    )
    logger.info(
        f"Creating Hydrolix client connection to {HYDROLIX_CONFIG.host}:{HYDROLIX_CONFIG.port} "
        f"{auth_info} "
        f"(connect_timeout={HYDROLIX_CONFIG.connect_timeout}s, "
        f"send_receive_timeout={HYDROLIX_CONFIG.send_receive_timeout}s)"
    )

    try:
        client = await clickhouse_connect.get_async_client(
            pool_mgr=pool_mgr, **HYDROLIX_CONFIG.get_client_config(request_credential)
        )
        # Test the connection
        version = client.client.server_version
        logger.info(f"Successfully connected to Hydrolix compatible with ClickHouse {version}")
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Hydrolix: {str(e)}")
        raise


# allow custom hydrolix settings in CH client
common.set_setting("invalid_setting_action", "send")
common.set_setting("autogenerate_session_id", False)

pool_kwargs = {
    "maxsize": HYDROLIX_CONFIG.query_pool_size,
    "num_pools": 1,
    "verify": HYDROLIX_CONFIG.verify,
}

# When verify=True, use certifi CA bundle for SSL verification
# This ensures we trust modern CAs like Let's Encrypt
if HYDROLIX_CONFIG.verify:
    pool_kwargs["ca_cert"] = "certifi"
else:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

client_shared_pool = httputil.get_pool_manager(**pool_kwargs)


def term(*args, **kwargs):
    client_shared_pool.clear()


signal.signal(signal.SIGTERM, term)
signal.signal(signal.SIGINT, term)
signal.signal(signal.SIGQUIT, term)


async def execute_query(query: str) -> HdxQueryResult:
    try:
        async with await create_hydrolix_client(
            client_shared_pool, get_request_credential()
        ) as client:
            res = await client.query(
                query,
                settings={
                    "readonly": 1,
                    "hdx_query_max_execution_time": HYDROLIX_CONFIG.query_timeout_sec,
                    "hdx_query_max_attempts": 1,
                    "hdx_query_max_result_rows": 100_000,
                    "hdx_query_max_memory_usage": 2 * 1024 * 1024 * 1024,  # 2GiB
                    "hdx_query_admin_comment": f"User: {MCP_SERVER_NAME}",
                },
            )
            logger.info(f"Query returned {len(res.result_rows)} rows")
            return HdxQueryResult(columns=res.column_names, rows=res.result_rows)
    except Exception as err:
        logger.error(f"Error executing query: {err}")
        raise ToolError(f"Query execution failed: {str(err)}")


async def execute_cmd(query: str):
    try:
        async with await create_hydrolix_client(
            client_shared_pool, get_request_credential()
        ) as client:
            res = await client.command(query)
            logger.info("Command returned executed.")
            return res
    except Exception as err:
        logger.error(f"Error executing command: {err}")
        raise ToolError(f"Command execution failed: {str(err)}")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    """Health check endpoint for monitoring server status.

    Returns OK if the server is running and can connect to Hydrolix.
    """
    try:
        # Try to create a client connection to verify query-head connectivity
        async with await create_hydrolix_client(
            client_shared_pool, get_request_credential()
        ) as client:
            version = client.client.server_version
        return PlainTextResponse(f"OK - Connected to Hydrolix compatible with ClickHouse {version}")
    except Exception as e:
        # Return 503 Service Unavailable if we can't connect to Hydrolix
        return PlainTextResponse(f"ERROR - Cannot connect to Hydrolix: {str(e)}", status_code=503)


def result_to_table(query_columns, result) -> List[Table]:
    return [Table(**dict(zip(query_columns, row))) for row in result]


def result_to_column(query_columns, result) -> List[Column]:
    return [Column(**dict(zip(query_columns, row))) for row in result]


def to_json(obj: Any) -> str:
    # This function technically returns different types:
    # - str for dataclasses (the primary use case)
    # - list/dict/Any for recursive processing during serialization
    # Type checking is suppressed for non-str returns as they're only used internally by json.dumps
    if is_dataclass(obj):
        return json.dumps(asdict(obj), default=to_json)
    elif isinstance(obj, list):
        return [to_json(item) for item in obj]  # type: ignore[return-value]
    elif isinstance(obj, dict):
        return {key: to_json(value) for key, value in obj.items()}  # type: ignore[return-value]
    return obj  # type: ignore[return-value]


@mcp.tool()
async def list_databases() -> List[str]:
    """List available Hydrolix databases"""
    logger.info("Listing all databases")
    result = await execute_cmd("SHOW DATABASES")

    # Convert newline-separated string to list and trim whitespace
    if isinstance(result, str):
        databases = [db.strip() for db in result.strip().split("\n")]
    else:
        databases = [result]

    logger.info(f"Found {len(databases)} databases")
    return databases


@mcp.tool()
async def list_tables(
    database: str, like: Optional[str] = None, not_like: Optional[str] = None
) -> List[Table]:
    """List available Hydrolix tables in a database, including schema, comment,
    row count, and column count."""
    logger.info(f"Listing tables in database '{database}'")
    query = f"""
        SELECT database, name, engine, create_table_query, dependencies_database,
            dependencies_table, engine_full, sorting_key, primary_key, total_rows, total_bytes,
            total_bytes_uncompressed, parts, active_parts, total_marks, comment
        FROM system.tables WHERE database = {format_query_value(database)}"""
    if like:
        query += f" AND name LIKE {format_query_value(like)}"

    if not_like:
        query += f" AND name NOT LIKE {format_query_value(not_like)}"

    result = await execute_query(query)

    # Deserialize result as Table dataclass instances
    tables = result_to_table(result["columns"], result["rows"])

    for table in tables:
        column_data_query = f"""
            SELECT database, table, name, type AS column_type, default_kind, default_expression, comment
            FROM system.columns
            WHERE database = {format_query_value(database)} AND table = {format_query_value(table.name)}"""
        column_data_query_result = await execute_query(column_data_query)
        table.columns = [
            c
            for c in result_to_column(
                column_data_query_result["columns"],
                column_data_query_result["rows"],
            )
        ]

    logger.info(f"Found {len(tables)} tables")
    return tables


@mcp.tool()
@with_serializer
async def run_select_query(query: str) -> dict[str, tuple | Sequence[str | Sequence[Any]]]:
    """Run a SELECT query in a Hydrolix time-series database using the Clickhouse SQL dialect.
    Queries run using this tool will timeout after 30 seconds.

    The primary key on tables queried this way is always a timestamp. Queries should include either
    a LIMIT clause or a filter based on the primary key as a performance guard to ensure they return
    in a reasonable amount of time. Queries should select specific fields and avoid the use of
    SELECT * to avoid performance issues. The performance guard used for the query should be clearly
    communicated with the user, and the user should be informed that the query may take a long time
    to run if the performance guard is not used. When choosing a performance guard, the user's
    preference should be requested and used if available. When using aggregations, the performance
    guard should take form of a primary key filter, or else the LIMIT should be applied in a
    subquery before applying the aggregations.

    When matching columns based on substrings, prefix or suffix matches should be used instead of
    full-text search whenever possible. When searching for substrings, the syntax `column LIKE
    '%suffix'` or `column LIKE 'prefix%'` should be used.

    Example query. Purpose: get logs from the `application.logs` table. Primary key: `timestamp`.
    Performance guard: 10 minute recency filter.

    `SELECT message, timestamp FROM application.logs WHERE timestamp > now() - INTERVAL 10 MINUTES`

    Example query. Purpose: get the median humidity from the `weather.measurements` table. Primary
    key: `date`. Performance guard: 1000 row limit, applied before aggregation.

     `SELECT median(humidity) FROM (SELECT humidity FROM weather.measurements LIMIT 1000)`

    Example query. Purpose: get the lowest temperature from the `weather.measurements` table over
    the last 10 years. Primary key: `date`. Performance guard: date range filter.

    `SELECT min(temperature) FROM weather.measurements WHERE date > now() - INTERVAL 10 YEARS`

    Example query. Purpose: get the app name with the most log messages from the `application.logs`
    table in the window between new year and valentine's day of 2024. Primary key: `timestamp`.
    Performance guard: date range filter.
     `SELECT app, count(*) FROM application.logs WHERE timestamp > '2024-01-01' AND timestamp < '2024-02-14' GROUP BY app ORDER BY count(*) DESC LIMIT 1`
    """
    logger.info(f"Executing SELECT query: {query}")
    try:
        result = await execute_query(query=query)
        return result
    except Exception as e:
        logger.error(f"Unexpected error in run_select_query: {str(e)}")
        raise ToolError(f"Unexpected error during query execution: {str(e)}")
