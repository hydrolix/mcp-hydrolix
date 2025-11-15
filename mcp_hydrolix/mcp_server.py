import logging
import json
import time
from typing import Optional, List, Any, Final, cast, ClassVar
import concurrent.futures
import atexit

import clickhouse_connect
from clickhouse_connect.driver.binding import format_query_value
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from dataclasses import dataclass, field, asdict, is_dataclass

from fastmcp.server.auth import AuthProvider, AccessToken as FastMCPAccessToken
from fastmcp.server.dependencies import get_access_token
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware as McpAuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser as McpAuthenticatedUser, BearerAuthBackend
from mcp.server.auth.provider import TokenVerifier as McpTokenVerifier
from starlette.authentication import AuthenticationBackend, AuthCredentials, BaseUser
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request, HTTPConnection
from starlette.responses import PlainTextResponse
from starlette.types import Scope, Receive, Send, ASGIApp
from uvicorn._types import HTTPScope
from uvicorn.middleware.asgi2 import ASGI2Middleware

from mcp_hydrolix.mcp_env import get_config, HydrolixConfig, HydrolixCredential, ServiceAccountToken, UsernamePassword


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

QUERY_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=10)
atexit.register(lambda: QUERY_EXECUTOR.shutdown(wait=True))
SELECT_QUERY_TIMEOUT_SECS = 30

load_dotenv()


class ChainedAuthBackend(AuthenticationBackend):
    """
    Generic authentication backend that tries multiple backends in order. Returns the first successful
    authentication result. Only tries an auth method once all previous auth methods have failed.
    """

    def __init__(self, backends: List[AuthenticationBackend]):
        self.backends = backends

    async def authenticate(self, conn: HTTPConnection):
        # due to a very strange quirk of python syntax, this CANNOT be an anonymous async generator. The quirk is
        # that async generator expressions aren't allowed to have `await` in their if conditions (though async
        # generators have no such restriction on their if statements)
        async def successful_results():
            for backend in self.backends:
                if (result := await backend.authenticate(conn)) is not None:
                    yield result

        return await anext(successful_results(), None)


class GetParamAuthBackend(AuthenticationBackend):
    """
    Authentication backend that validates tokens from an HTTP GET parameter
    """

    def __init__(self, token_verifier: McpTokenVerifier, token_get_param: str):
        self.token_verifier = token_verifier
        self.token_get_param = token_get_param

    async def authenticate(self, conn: HTTPConnection):
        token = Request(conn.scope).query_params.get(self.token_get_param)

        if token is None:
            return None

        # Validate the token with the verifier
        auth_info = await self.token_verifier.verify_token(token)

        if not auth_info:
            return None

        if auth_info.expires_at and auth_info.expires_at < int(time.time()):
            return None

        return AuthCredentials(auth_info.scopes), McpAuthenticatedUser(auth_info)


class AccessToken(FastMCPAccessToken):
    def as_credential(self) -> HydrolixCredential: ...


class HydrolixCredentialChain(AuthProvider):
    """
    AuthProvider that authenticates with the following precedence:

    - MCP-standard oAuth (not implemented!)
    - Hydrolix service account via the "token" GET parameter
    - Hydrolix service account via the Bearer token
    """

    class ServiceAccountAccess(AccessToken):
        FAKE_CLIENT_ID: ClassVar[Final[str]] = "MCP_CLIENT_VIA_SERVICE_ACCOUNT"
        FAKE_SCOPE: ClassVar[Final[str]] = "MCP_SERVICE_ACCOUNT_SCOPE"

        def as_credential(self):
            ServiceAccountToken(self.token)

    def __init__(self, connection_settings: HydrolixConfig):
        super().__init__()
        self.connection_settings = connection_settings

    async def verify_token(self, token: str) -> AccessToken | None:
        """
        This is responsible for validating and authenticating the `token`.
        See ChainedAuthBackend for how the token is obtained in the first place.
        Authorization is performed by individual endpoints via `fastmcp.server.dependencies.get_access_token`
        """
        return HydrolixCredentialChain.ServiceAccountAccess(
            token=token,
            client_id=HydrolixCredentialChain.ServiceAccountAccess.FAKE_CLIENT_ID,
            scopes=[
                HydrolixCredentialChain.ServiceAccountAccess.FAKE_SCOPE],
            expires_at=None,
            resource=None,
            claims={}
        )

    def get_middleware(self) -> list:
        return [
            Middleware(
                AuthenticationMiddleware,
                backend=ChainedAuthBackend([
                    BearerAuthBackend(self),
                    GetParamAuthBackend(self, "token"),
                ]),
            ),
            Middleware(McpAuthContextMiddleware),
        ]


mcp = FastMCP(
    name=MCP_SERVER_NAME,
    dependencies=[
        "clickhouse-connect",
        "python-dotenv",
        "pip-system-certs",
    ],
    auth=HydrolixCredentialChain(get_config())
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
    if is_dataclass(obj):
        return json.dumps(asdict(obj), default=to_json)
    elif isinstance(obj, list):
        return [to_json(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: to_json(value) for key, value in obj.items()}
    return obj


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
    client_config = get_config()
    creds = client_config.creds_with(request_credential)
    logger.error(creds)
    auth_info = (
        f"as {creds.username}" if isinstance(creds, UsernamePassword)
        else f"using service account {creds.service_account_id}"
    )
    logger.info(
        f"Creating Hydrolix client connection to {client_config['host']}:{client_config['port']} "
        f"{auth_info} "
        f"(secure={client_config['secure']}, verify={client_config['verify']}, "
        f"connect_timeout={client_config['connect_timeout']}s, "
        f"send_receive_timeout={client_config['send_receive_timeout']}s)"
    )

    try:
        client = clickhouse_connect.get_client(**client_config.get_client_config(request_credential))
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
            raise ValueError("Found non-hydrolix access token on request -- this should be impossible!")
    return None
