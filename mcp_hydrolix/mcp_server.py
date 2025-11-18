import logging
import json
from typing import Final, Optional, List, Any, cast
import concurrent.futures
import atexit

import clickhouse_connect
from clickhouse_connect.driver.binding import format_query_value
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from dataclasses import dataclass, field, asdict, is_dataclass

from fastmcp.server.dependencies import get_access_token
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from .mcp_env import HydrolixConfig, get_config
from .auth import (
    HydrolixCredential,
    UsernamePassword,
    AccessToken,
    HydrolixCredentialChain,
    ServiceAccountToken,
)
from .logging_utils import AccessLogTokenRedactingFilter


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
    dependencies_database: str
    dependencies_table: str
    engine_full: str
    sorting_key: str
    primary_key: str
    total_rows: int
    total_bytes: int
    total_bytes_uncompressed: int
    parts: int
    active_parts: int
    total_marks: int
    comment: Optional[str] = None
    columns: List[Column] = field(default_factory=list)


MCP_SERVER_NAME = "mcp-hydrolix"

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(MCP_SERVER_NAME)

# Add token redaction filter to uvicorn access logs
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(AccessLogTokenRedactingFilter())

QUERY_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=10)
atexit.register(lambda: QUERY_EXECUTOR.shutdown(wait=True))
SELECT_QUERY_TIMEOUT_SECS = 30

load_dotenv()

HYDROLIX_CONFIG: Final[HydrolixConfig] = get_config()

mcp = FastMCP(
    name=MCP_SERVER_NAME,
    dependencies=[
        "clickhouse-connect",
        "python-dotenv",
        "pip-system-certs",
    ],
    auth=HydrolixCredentialChain(f"https://{HYDROLIX_CONFIG.host}/config"),
)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    """Health check endpoint for monitoring server status.

    Returns OK if the server is running and can connect to Hydrolix.
    """
    try:
        # Try to create a client connection to verify query-head connectivity
        client = create_hydrolix_client(get_request_credential())
        version = client.server_version
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
def list_databases():
    """List available Hydrolix databases"""
    logger.info("Listing all databases")
    client = create_hydrolix_client(get_request_credential())
    result = client.command("SHOW DATABASES")

    # Convert newline-separated string to list and trim whitespace
    if isinstance(result, str):
        databases = [db.strip() for db in result.strip().split("\n")]
    else:
        databases = [result]

    logger.info(f"Found {len(databases)} databases")
    return json.dumps(databases)


@mcp.tool()
def list_tables(database: str, like: Optional[str] = None, not_like: Optional[str] = None):
    """List available Hydrolix tables in a database, including schema, comment,
    row count, and column count."""
    logger.info(f"Listing tables in database '{database}'")
    client = create_hydrolix_client(get_request_credential())
    query = f"SELECT database, name, engine, create_table_query, dependencies_database, dependencies_table, engine_full, sorting_key, primary_key, total_rows, total_bytes, total_bytes_uncompressed, parts, active_parts, total_marks, comment FROM system.tables WHERE database = {format_query_value(database)}"
    if like:
        query += f" AND name LIKE {format_query_value(like)}"

    if not_like:
        query += f" AND name NOT LIKE {format_query_value(not_like)}"

    result = client.query(query)

    # Deserialize result as Table dataclass instances
    tables = result_to_table(result.column_names, result.result_rows)

    for table in tables:
        column_data_query = f"SELECT database, table, name, type AS column_type, default_kind, default_expression, comment FROM system.columns WHERE database = {format_query_value(database)} AND table = {format_query_value(table.name)}"
        column_data_query_result = client.query(column_data_query)
        table.columns = [
            c
            for c in result_to_column(
                column_data_query_result.column_names,
                column_data_query_result.result_rows,
            )
        ]

    logger.info(f"Found {len(tables)} tables")
    return [asdict(table) for table in tables]


def execute_query(query: str, request_credential: Optional[HydrolixCredential]):
    client = create_hydrolix_client(request_credential)
    try:
        res = client.query(
            query,
            settings={
                "readonly": 1,
                "hdx_query_max_execution_time": SELECT_QUERY_TIMEOUT_SECS,
                "hdx_query_max_attempts": 1,
                "hdx_query_max_result_rows": 100_000,
                "hdx_query_max_memory_usage": 2 * 1024 * 1024 * 1024,  # 2GiB
                "hdx_query_admin_comment": f"User: {MCP_SERVER_NAME}",
            },
        )
        logger.info(f"Query returned {len(res.result_rows)} rows")
        return {"columns": res.column_names, "rows": res.result_rows}
    except Exception as err:
        logger.error(f"Error executing query: {err}")
        raise ToolError(f"Query execution failed: {str(err)}")


@mcp.tool()
def run_select_query(query: str):
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
        future = QUERY_EXECUTOR.submit(execute_query, query, get_request_credential())
        try:
            result = future.result(timeout=SELECT_QUERY_TIMEOUT_SECS)
            # Check if we received an error structure from execute_query
            if isinstance(result, dict) and "error" in result:
                logger.warning(f"Query failed: {result['error']}")
                # MCP requires structured responses; string error messages can cause
                # serialization issues leading to BrokenResourceError
                return {
                    "status": "error",
                    "message": f"Query failed: {result['error']}",
                }
            return result
        except concurrent.futures.TimeoutError:
            logger.warning(f"Query timed out after {SELECT_QUERY_TIMEOUT_SECS} seconds: {query}")
            future.cancel()
            raise ToolError(f"Query timed out after {SELECT_QUERY_TIMEOUT_SECS} seconds")
    except ToolError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in run_select_query: {str(e)}")
        raise RuntimeError(f"Unexpected error during query execution: {str(e)}")


def create_hydrolix_client(request_credential: Optional[HydrolixCredential]):
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
        client = clickhouse_connect.get_client(
            **HYDROLIX_CONFIG.get_client_config(request_credential)
        )
        # Test the connection
        version = client.server_version
        logger.info(f"Successfully connected to Hydrolix compatible with ClickHouse {version}")
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Hydrolix: {str(e)}")
        raise


def get_request_credential() -> HydrolixCredential | None:
    if (token := get_access_token()) is not None:
        if isinstance(token, AccessToken):
            return cast(AccessToken, token).as_credential()
        else:
            raise ValueError(
                "Found non-hydrolix access token on request -- this should be impossible!"
            )
    return None
