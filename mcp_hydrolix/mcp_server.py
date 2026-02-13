import logging
import re
import signal
from typing import Any, Final, List, Optional, TypedDict, cast

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
    """Column with enriched metadata: column_category, base_function, merge_function."""

    database: str
    table: str
    name: str
    column_type: str
    default_kind: Optional[str]
    default_expression: Optional[str]
    comment: Optional[str]
    column_category: Optional[str] = None  # 'aggregate', 'alias_aggregate', 'dimension'
    base_function: Optional[str] = None
    merge_function: Optional[str] = None


@dataclass
class Table:
    """Table with summary table detection (is_summary_table=True if has aggregate columns)."""

    database: str
    name: str
    engine: str
    sorting_key: str
    primary_key: str
    total_rows: Optional[int]
    total_bytes: Optional[int]
    total_bytes_uncompressed: Optional[int]
    parts: Optional[int]
    active_parts: Optional[int]
    columns: Optional[List[Column]] = Field(default_factory=list)
    is_summary_table: bool = False
    summary_table_info: Optional[str] = None


class HdxQueryResult(TypedDict):
    columns: List[str]
    rows: List[List[Any]]


class PaginatedTableList(TypedDict):
    """Response format for paginated list_tables results."""

    tables: List[Table]
    nextCursor: Optional[str]
    pageSize: int
    totalRetrieved: int


class PaginatedQueryResult(TypedDict):
    """Response format for paginated run_select_query results."""

    columns: List[str]
    rows: List[List[Any]]
    nextCursor: Optional[str]
    pageSize: int
    totalRetrieved: int
    hasMore: bool


@dataclass
class TableClassification:
    """Result of table column classification."""

    is_summary_table: bool
    aggregate_columns: List[Column]
    dimension_columns: List[Column]


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

pool_kwargs: dict[str, Any] = {
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
            logger.info("Command executed successfully.")
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


# system.tables query fields for fetching table metadata
SYSTEM_TABLES_FIELDS = """database, name, engine, sorting_key, primary_key, total_rows, total_bytes,
    total_bytes_uncompressed, parts, active_parts"""


# Summary Table Support - Helper Functions


def extract_function_from_type(column_type: str) -> Optional[str]:
    """
    Extract aggregate function name from AggregateFunction type.
    Examples:
      "AggregateFunction(count, String)" -> "count"
      "AggregateFunction(sumIf, Float64)" -> "sumIf"
      "AggregateFunction(quantile(0.5), DateTime)" -> "quantile(0.5)"
      "AggregateFunction(exponentialMovingAverage(0.5), UInt32)" -> "exponentialMovingAverage(0.5)"
      "SimpleAggregateFunction(sum, Int64)" -> "sum"
      "String" -> None
    """
    # Match everything from AggregateFunction( up to the comma that separates function from types
    # This captures function names with parameters like quantile(0.5) or quantile(0.5, 0.9)
    # Pattern: function_name or function_name(params) where params can contain commas
    match = re.match(r"^(?:Simple)?AggregateFunction\(([^,()]+(?:\([^)]*\))?)", column_type)
    if match:
        return match.group(1).strip()
    return None


def get_merge_function(base_function: str) -> str:
    """
    Generate -Merge function name from base function.
    For parameterized functions, parameters go AFTER "Merge":
      count -> countMerge
      countIf -> countIfMerge
      quantile(0.5) -> quantileMerge(0.5)
      exponentialMovingAverage(0.5) -> exponentialMovingAverageMerge(0.5)
    """
    # Check if function has parameters
    match = re.match(r"^(\w+)(\(.+\))$", base_function)
    if match:
        # Parameterized: quantile(0.5) -> quantileMerge(0.5)
        func_name = match.group(1)
        params = match.group(2)
        return f"{func_name}Merge{params}"
    else:
        # Non-parameterized: count -> countMerge
        return f"{base_function}Merge"


def classify_table_columns(columns: List[Column]) -> TableClassification:
    """
    Classify columns and determine if table is a summary table (has any aggregate columns).
    Requires columns to be enriched first via enrich_column_metadata().
    """
    aggregate_columns = []
    dimension_columns = []

    for column in columns:
        if column.column_category in ("aggregate", "alias_aggregate"):
            aggregate_columns.append(column)
        else:
            dimension_columns.append(column)

    return TableClassification(
        is_summary_table=len(aggregate_columns) > 0,
        aggregate_columns=aggregate_columns,
        dimension_columns=dimension_columns,
    )


def enrich_column_metadata(column: Column) -> Column:
    """
    Classify column as aggregate, alias_aggregate, or dimension and populate metadata.
    Sets column_category, base_function, and merge_function fields.

    Detection strategy:
    1. Check column_type for AggregateFunction/SimpleAggregateFunction (primary method)
    2. Check if ALIAS wrapping a -Merge function (for user-friendly shortcuts)
    3. Everything else is a dimension

    Note: In real ClickHouse summary tables, aggregate columns ALWAYS have
    AggregateFunction or SimpleAggregateFunction types.
    """

    type_func = extract_function_from_type(column.column_type)
    if type_func:
        column.column_category = "aggregate"
        column.base_function = type_func
        column.merge_function = get_merge_function(type_func)
    elif (
        column.default_kind == "ALIAS"
        and column.default_expression
        and "Merge(" in column.default_expression
    ):
        column.column_category = "alias_aggregate"
        column.base_function = None
        column.merge_function = None
    # Everything else is a dimension
    else:
        column.column_category = "dimension"

    return column


async def _populate_table_metadata(database: str, table: Table) -> None:
    """Fetch and populate table with column metadata from Hydrolix.

    Args:
        database: Database name
        table: Table object to enrich with column metadata
    """
    # Use DESCRIBE TABLE instead of system.columns to get full AggregateFunction types
    # system.columns returns simplified types (like "String") but DESCRIBE returns full types
    # ("AggregateFunction(count, Nullable(String))")
    # Use backticks for identifiers, not format_query_value which adds quotes for VALUES
    column_data_query = f"DESCRIBE TABLE `{database}`.`{table.name}`"
    column_data_query_result = await execute_query(column_data_query)

    # DESCRIBE TABLE returns: name, type, default_type, default_expression, comment, ...
    # Transform results to Column objects, mapping DESCRIBE TABLE fields to Column dataclass fields
    column_names = column_data_query_result["columns"]
    columns = [
        Column(
            database=database,
            table=table.name,
            name=row_dict.get("name", ""),
            column_type=row_dict.get("type", ""),
            default_kind=row_dict.get("default_type", ""),
            default_expression=row_dict.get("default_expression", ""),
            comment=row_dict.get("comment", ""),
        )
        for row_dict in (dict(zip(column_names, row)) for row in column_data_query_result["rows"])
    ]

    # Summary Table Support: Enrich column metadata
    # For each column, detect if it's an aggregate, alias_aggregate, or dimension
    # and populate column_category, base_function, and merge_function fields.
    enriched_columns = [enrich_column_metadata(col) for col in columns]

    # Classify table based on enriched column metadata
    # A table is a summary table if it has ANY aggregate columns
    classification = classify_table_columns(enriched_columns)
    is_summary_table = classification.is_summary_table

    # Add human-readable usage guidance for LLMs querying summary tables
    summary_table_info = None
    if is_summary_table:
        num_agg = len(classification.aggregate_columns)
        num_dim = len(classification.dimension_columns)
        summary_table_info = (
            f"This is a SUMMARY TABLE with {num_agg} aggregate column(s) and {num_dim} dimension column(s). "
            "Aggregate columns (column_category='aggregate') MUST be wrapped in their corresponding -Merge functions. "
            "ALIAS aggregate columns (column_category='alias_aggregate') are pre-wrapped aggregates - use directly without -Merge. "
            "Dimension columns (column_category='dimension') can be SELECTed directly and MUST appear in GROUP BY when mixed with aggregates. "
            "IMPORTANT: Dimension columns may have function-like names (e.g., 'toStartOfHour(col)') - these are LITERAL column names, use them exactly as-is with backticks. "
            "WRONG: SELECT toStartOfHour(col). RIGHT: SELECT `toStartOfHour(col)`. Also use in GROUP BY: GROUP BY `toStartOfHour(col)`. "
            "CRITICAL RULE: If your SELECT includes ANY dimension columns (column_category='dimension') "
            "AND ANY aggregate columns (column_category='aggregate' or 'alias_aggregate'), "
            "you MUST include 'GROUP BY <all dimension columns from SELECT>'. "
            "WITHOUT GROUP BY, the query will FAIL with 'NOT_AN_AGGREGATE' error. "
            "IMPORTANT: ALIAS aggregates (column_category='alias_aggregate') are NOT dimensions - do NOT include them in GROUP BY. "
            "Example: SELECT reqHost, cnt_all FROM table GROUP BY reqHost (reqHost=dimension, cnt_all=alias_aggregate). "
            "CRITICAL: You MUST use the EXACT merge_function value from each aggregate column's metadata. "
            "DO NOT infer the merge function from the column name - always check the merge_function field. "
            "For example, if column `avgIf(col, condition)` has merge_function='avgIfMerge', "
            "you MUST use avgIfMerge(`avgIf(col, condition)`), NOT avgMerge(...)."
        )

    # Populate table object with metadata
    table.columns = enriched_columns
    table.is_summary_table = is_summary_table
    table.summary_table_info = summary_table_info


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
async def get_table_info(database: str, table: str) -> Table:
    """Get detailed metadata for a specific table including columns and summary table detection.

    REQUIRED USAGE: Call this tool BEFORE querying ANY table to check if it's a summary
    table and get column metadata. This is mandatory to avoid query errors.

    This tool provides:
    - is_summary_table: Boolean indicating if table has pre-aggregated data
    - columns: List of columns with metadata:
      - column_category: 'aggregate', 'alias_aggregate', or 'dimension'
      - merge_function: Exact -Merge function name for aggregate columns (e.g., "countMerge")
      - column_type: ClickHouse data type
      - default_expression: For ALIAS columns, shows the underlying expression
    - summary_table_info: Human-readable description for summary tables
    - row_count, total_bytes: Table statistics

    WORKFLOW for querying tables:
    1. Call get_table_info('database', 'table_name')
    2. Check is_summary_table field
    3. If is_summary_table=True:
       - Read column_category and merge_function for each column
       - Use merge_function to wrap aggregate columns in queries
       - Example: SELECT countMerge(`count(vendor_id)`) FROM table
    4. If is_summary_table=False:
       - Use standard SQL (SELECT count(*), sum(col), etc.)
    5. Execute query with run_select_query

    For summary tables, aggregate columns MUST be wrapped with their corresponding -Merge functions
    from the merge_function field. Querying without checking this metadata first will cause errors.
    """
    # Fetch table metadata (row counts, sizes, etc.)
    query = f"""
        SELECT {SYSTEM_TABLES_FIELDS}
        FROM system.tables
        WHERE database = {format_query_value(database)} AND name = {format_query_value(table)}"""

    result = await execute_query(query)

    if not result["rows"]:
        raise ToolError(f"Table {database}.{table} not found")

    # Create Table object from first (and only) row
    tables = result_to_table(result["columns"], result["rows"])
    table_obj = tables[0]

    # Populate table with column metadata
    await _populate_table_metadata(database, table_obj)

    return table_obj


@mcp.tool()
async def list_tables(
    database: str,
    like: Optional[str] = None,
    not_like: Optional[str] = None,
    cursor: Optional[str] = None,
    paginate: bool = True,
) -> "List[Table] | PaginatedTableList":
    """List all tables in a database with pagination support.

    Use this tool to:
    - Discover what tables exist in a database
    - Filter tables by name pattern (like/not_like)
    - Get overview of table metadata (engine, row counts, etc.)
    - Identify which tables are summary tables (is_summary_table field)
    - Get complete column metadata including merge_function for aggregates

    Returns complete table information including columns and summary table detection
    (same metadata as get_table_info but for all tables in the database).

    NOTE: If you already know which specific table you want to query, use
    get_table_info(database, table) instead - it's faster and returns metadata
    for just that one table.

    BEFORE querying any table from the results, check is_summary_table and column
    metadata to build correct queries.

    Pagination:
        This tool supports cursor-based pagination for large result sets.

        When paginate=True (default):
        - Results are returned in pages (default: 50 tables per page)
        - Response includes:
          - tables: List of Table objects for current page
          - nextCursor: Opaque cursor string (None if no more pages)
          - pageSize: Number of tables in this page
          - totalRetrieved: Total tables retrieved so far (including this page)
        - To get next page, pass nextCursor to cursor parameter
        - Loop until nextCursor is None to fetch all tables

        When paginate=False:
        - Returns all tables in single response (legacy behavior)
        - Returns List[Table] directly

        Example pagination workflow:
            # Get first page
            result = await list_tables('my_database')
            tables = result['tables']

            # Get subsequent pages if more exist
            while result['nextCursor']:
                result = await list_tables('my_database', cursor=result['nextCursor'])
                tables.extend(result['tables'])
    """
    logger.info(f"Listing tables in database '{database}' (paginate={paginate}, cursor={cursor})")

    # Import pagination utilities
    from mcp_hydrolix.pagination import decode_cursor, encode_cursor, validate_cursor_params

    # Decode cursor to get offset
    offset = 0
    if cursor:
        try:
            cursor_data = decode_cursor(cursor)
            validate_cursor_params(
                cursor_data, {"database": database, "like": like, "not_like": not_like}
            )
            offset = cursor_data.get("offset", 0)
        except Exception as e:
            raise ToolError(f"Invalid cursor: {str(e)}")

    # Build base query
    query = f"""
        SELECT {SYSTEM_TABLES_FIELDS}
        FROM system.tables WHERE database = {format_query_value(database)}"""

    if like:
        query += f" AND name LIKE {format_query_value(like)}"

    if not_like:
        query += f" AND name NOT LIKE {format_query_value(not_like)}"

    # Add pagination if enabled
    if paginate and HYDROLIX_CONFIG.enable_pagination:
        page_size = HYDROLIX_CONFIG.list_tables_page_size
        # Fetch one extra to detect if more pages exist
        query += f" LIMIT {page_size + 1} OFFSET {offset}"

    result = await execute_query(query)
    tables = result_to_table(result["columns"], result["rows"])

    # Check if more pages exist (only when paginating)
    has_more = False
    if paginate and HYDROLIX_CONFIG.enable_pagination:
        page_size = HYDROLIX_CONFIG.list_tables_page_size
        has_more = len(tables) > page_size
        if has_more:
            tables = tables[:page_size]  # Trim extra row

    # Populate column metadata only for tables in this page
    for table in tables:
        await _populate_table_metadata(database, table)

    logger.info(f"Found {len(tables)} tables (offset={offset}, hasMore={has_more})")

    # Return format depends on paginate parameter
    if not paginate or not HYDROLIX_CONFIG.enable_pagination:
        # Legacy behavior: return list directly
        return tables

    # Generate next cursor if more data exists
    next_cursor = None
    if has_more:
        next_cursor_data = {
            "type": "table_list",
            "offset": offset + page_size,
            "params": {"database": database, "like": like, "not_like": not_like},
        }
        next_cursor = encode_cursor(next_cursor_data)

    return PaginatedTableList(
        tables=tables,
        nextCursor=next_cursor,
        pageSize=len(tables),
        totalRetrieved=offset + len(tables),
    )


def _add_pagination_to_query(query: str, limit: int, offset: int) -> str:
    """Add LIMIT and OFFSET to a SQL query.

    If the query already contains LIMIT or OFFSET clauses, wraps it in a subquery
    to apply pagination at the outer level.

    Args:
        query: SQL query string
        limit: Maximum number of rows to return
        offset: Number of rows to skip

    Returns:
        Modified query with LIMIT and OFFSET applied
    """
    query = query.strip().rstrip(";")

    # If query already has LIMIT/OFFSET, wrap in subquery
    if "LIMIT" in query.upper() or "OFFSET" in query.upper():
        return f"SELECT * FROM ({query}) AS paginated_subquery LIMIT {limit} OFFSET {offset}"

    # Simple case: append LIMIT/OFFSET
    return f"{query} LIMIT {limit} OFFSET {offset}"


@mcp.tool()
@with_serializer
async def run_select_query(
    query: str, cursor: Optional[str] = None, paginate: bool = True
) -> dict[str, Any]:
    """Run a SELECT query in a Hydrolix time-series database using the Clickhouse SQL dialect with pagination support.
    Queries run using this tool will timeout after 30 seconds.

    MANDATORY PRE-QUERY CHECK - DO THIS FIRST BEFORE EVERY QUERY:

    BEFORE running ANY query on a table, you MUST call get_table_info(database, table_name)
    to check if it's a summary table and get column metadata.

    WHY: Summary tables require special -Merge functions for aggregate columns. Querying
    without checking metadata first will cause:
    - "Nested aggregate function" errors (if you use sum/count/avg instead of -Merge)
    - "Cannot read AggregateFunction" errors (if you SELECT aggregate columns directly)
    - Wrong results (if you treat aggregate columns as regular values)

    REQUIRED WORKFLOW (follow this order every time):

    1. FIRST: Call get_table_info('database', 'table_name')
       - Check is_summary_table field
       - Read column metadata (column_category, merge_function for each column)

    2. THEN: Build query based on metadata
       - If is_summary_table=False: use standard SQL (count, sum, avg, etc.)
       - If is_summary_table=True: follow summary table rules below

    Do NOT skip step 1. Do NOT assume a table is regular/summary without checking.

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

    SUMMARY TABLE RULES (only apply if is_summary_table=True from get_table_info):

    Summary tables contain pre-computed aggregations stored in aggregate function state columns.
    These tables are identified by having columns with aggregate function names like count(...),
    sum(...), avg(...), countIf(...), sumIf(...), etc.

    CRITICAL RULES for querying summary tables:

    1. Raw aggregate columns (column_category='aggregate') CANNOT be SELECTed directly
       - They store binary AggregateFunction states, not readable values
       - Direct SELECT will cause deserialization errors
       - MUST be wrapped in their -Merge function from get_table_info:
         - count(vendor_id) → countMerge(`count(vendor_id)`)
         - sum(bytes_out) → sumMerge(`sum(bytes_out)`)
         - avg(latitude) → avgMerge(`avg(latitude)`)
         - countIf(condition) → countIfMerge(`countIf(condition)`)
       - ALWAYS check column.merge_function in get_table_info to get the exact function name
       - Use backticks around column names with special characters

    2. Do NOT use standard aggregate functions (sum/count/avg) on summary table columns
       - WRONG: SELECT sum(count_column) FROM summary_table
         (causes "nested aggregate function" error)
       - RIGHT: SELECT countMerge(`count_column`) FROM summary_table
         (uses the merge function from column metadata)

    3. ALIAS aggregate columns (column_category='alias_aggregate') use directly:
       - These are pre-defined shortcuts that already wrap -Merge functions
       - Example: cnt_all (which is defined as ALIAS countMerge(`count()`))
       - SELECT cnt_all directly, NO additional wrapping needed
       - These make queries simpler and more readable

    4. Dimension columns (column_category='dimension') - use as-is with backticks:
       - Reference them exactly as listed in column metadata
       - Many have function-like names (e.g., `toStartOfMinute(primary_datetime)`)
       - These are LITERAL column names, not expressions to compute
       - WRONG: SELECT toStartOfMinute(primary_datetime) (tries to call function on non-existent base column)
       - RIGHT: SELECT `toStartOfMinute(primary_datetime)` (selects the actual dimension column)
       - Always use backticks for columns with special characters
       - Can be used in SELECT, WHERE, GROUP BY, ORDER BY
       - For time dimensions in WHERE clauses:
         * Use simple date format: '2022-06-01' (preferred)
         * Use full timestamp: '2022-06-01 00:00:00' (with seconds)
         * Do NOT use partial time: '2022-06-01 00:00' (causes parse errors)
         * Use >= and < for ranges: WHERE col >= '2022-06-01' AND col < '2022-06-02'

    5. CRITICAL: When mixing dimensions and aggregates in SELECT, you MUST use GROUP BY:
       - SELECT only aggregates → no GROUP BY needed (aggregates entire table)
         Example: SELECT count_vendor_id FROM table
       - SELECT dimensions + aggregates → MUST GROUP BY all dimension columns
         Example: SELECT pickup_dt, count_vendor_id FROM table GROUP BY pickup_dt
       - Forgetting GROUP BY causes error: "Column X is not under aggregate function and not in GROUP BY"

    6. NEVER use SELECT * on summary tables (will cause deserialization errors)

    7. Aggregate columns can ONLY appear in SELECT:
       - Raw aggregates: wrapped with -Merge (see column.merge_function)
       - Alias aggregates: used directly
       - NEVER in GROUP BY (use dimension columns only)

    Summary table query patterns (after calling get_table_info first):

    Pattern 1: Aggregate entire table
    -- First: get_table_info('database', 'summary_table')
    -- Read column.merge_function for count(column_name) = "countMerge"
    SELECT countMerge(`count(column_name)`) as total FROM database.summary_table

    Pattern 2: Aggregate with grouping by dimension
    -- First: get_table_info('database', 'summary_table')
    -- Read merge_function for each aggregate column
    SELECT time_bucket_column,
           countMerge(`count(column_name)`) as total,
           avgMerge(`avg(other_column)`) as avg_value
    FROM database.summary_table
    GROUP BY time_bucket_column

    Pattern 2b: Grouping with time range filter
    -- First: get_table_info('database', 'summary_table')
    SELECT `toStartOfMinute(datetime_field)` as time_bucket,
           countMerge(`count(column)`) as total
    FROM database.summary_table
    WHERE `toStartOfMinute(datetime_field)` >= '2022-06-01'
      AND `toStartOfMinute(datetime_field)` < '2022-06-02'
    GROUP BY `toStartOfMinute(datetime_field)`
    ORDER BY time_bucket DESC

    Pattern 3: Multiple aggregates (no dimensions, no GROUP BY)
    -- First: get_table_info('database', 'summary_table')
    SELECT countMerge(`count(column_name)`) as count_result,
           sumMerge(`sum(other_column)`) as sum_result
    FROM database.summary_table

    Pattern 4: Using ALIAS aggregate columns (no dimensions, no GROUP BY)
    -- First: get_table_info('database', 'summary_table')
    -- Check which columns have column_category='alias_aggregate'
    SELECT cnt_all, sum_bytes, avg_value FROM database.summary_table
    -- No -Merge needed, these are pre-defined aliases

    Pattern 5: ALIAS aggregates with dimensions (requires GROUP BY)
    -- First: get_table_info('database', 'summary_table')
    SELECT time_dimension,
           cnt_all,
           avg_value
    FROM database.summary_table
    GROUP BY time_dimension
    -- MUST include GROUP BY when mixing dimensions and aggregates

    Pattern 6: Using dimensions with function-like names (common pattern)
    -- First: get_table_info('database', 'summary_table')
    -- See dimension column named: toStartOfMinute(primary_datetime)
    -- WRONG: SELECT toStartOfMinute(primary_datetime) ... (tries to call function)
    -- RIGHT: Use the literal column name with backticks
    SELECT `toStartOfMinute(primary_datetime)` as time_bucket,
           countMerge(`count()`) as cnt,
           maxMerge(`max(value)`) as max_val
    FROM database.summary_table
    GROUP BY `toStartOfMinute(primary_datetime)`
    ORDER BY time_bucket DESC
    LIMIT 10

    Regular table examples (non-summary):

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

    Pagination:
        This tool supports cursor-based pagination for large result sets.

        When paginate=True (default):
        - Results are returned in pages (default: 10,000 rows per page)
        - Response includes:
          - columns: List of column names
          - rows: List of row data for current page
          - nextCursor: Opaque cursor string (None if no more pages)
          - pageSize: Number of rows in this page
          - totalRetrieved: Total rows retrieved so far (including this page)
          - hasMore: Boolean indicating if more pages exist
        - To get next page, pass nextCursor to cursor parameter with same query
        - Loop until nextCursor is None to fetch all results

        When paginate=False:
        - Returns all results in single response (legacy behavior)
        - Returns HdxQueryResult dict with columns and rows only

        Example pagination workflow:
            # Get first page
            result = await run_select_query('SELECT * FROM table ORDER BY id')
            rows = result['rows']

            # Get subsequent pages if more exist
            while result['nextCursor']:
                result = await run_select_query(
                    'SELECT * FROM table ORDER BY id',
                    cursor=result['nextCursor']
                )
                rows.extend(result['rows'])

        IMPORTANT: When using pagination, always include ORDER BY in your query
        to ensure consistent ordering across pages.
    """
    logger.info(f"Executing SELECT query: {query} (paginate={paginate}, cursor={cursor})")

    # Import pagination utilities
    from mcp_hydrolix.pagination import decode_cursor, encode_cursor, hash_query

    # Decode cursor to get offset and validate query
    offset = 0
    if cursor:
        try:
            cursor_data = decode_cursor(cursor)
            # Validate query hasn't changed
            expected_hash = hash_query(query)
            if cursor_data.get("query_hash") != expected_hash:
                raise ValueError("Query has changed since cursor was generated")
            offset = cursor_data.get("offset", 0)
        except Exception as e:
            raise ToolError(f"Invalid cursor: {str(e)}")

    # Apply pagination if enabled
    paginated_query = query
    if paginate and HYDROLIX_CONFIG.enable_pagination:
        page_size = HYDROLIX_CONFIG.query_result_page_size
        # Fetch one extra row to detect if more pages exist
        paginated_query = _add_pagination_to_query(query, page_size + 1, offset)

    try:
        result = await execute_query(query=paginated_query)

        # Check if we're in pagination mode
        if not paginate or not HYDROLIX_CONFIG.enable_pagination:
            # Legacy behavior: return HdxQueryResult directly
            return result

        # Pagination mode: return PaginatedQueryResult
        page_size = HYDROLIX_CONFIG.query_result_page_size
        rows = result["rows"]
        columns = result["columns"]

        # Check if more pages exist
        has_more = len(rows) > page_size
        if has_more:
            rows = rows[:page_size]  # Trim extra row

        # Generate next cursor if more data exists
        next_cursor = None
        if has_more:
            next_cursor_data = {
                "type": "query_result",
                "offset": offset + page_size,
                "query_hash": hash_query(query),
            }
            next_cursor = encode_cursor(next_cursor_data)

        return PaginatedQueryResult(
            columns=columns,
            rows=rows,
            nextCursor=next_cursor,
            pageSize=len(rows),
            totalRetrieved=offset + len(rows),
            hasMore=has_more,
        )

    except Exception as e:
        logger.error(f"Unexpected error in run_select_query: {str(e)}")
        raise ToolError(f"Unexpected error during query execution: {str(e)}")
