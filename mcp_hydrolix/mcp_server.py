import asyncio
import base64
import logging
import re
import signal
import time
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from typing import (
    Any,
    Dict,
    Final,
    List,
    Optional,
    Set,
    cast,
)

import clickhouse_connect
import sqlglot
import sqlglot.errors as sqlglot_errors
import sqlglot.expressions as sqlglot_exp
from clickhouse_connect import common
from clickhouse_connect.driver import httputil
from clickhouse_connect.driver.binding import format_query_value
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.tools.tool import ToolResult
from fastmcp.server.middleware import Middleware, MiddlewareContext
from jwt import DecodeError
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from mcp_hydrolix import metrics
from mcp_hydrolix.auth import (
    AccessToken,
    HydrolixCredential,
    HydrolixCredentialChain,
    ServiceAccountToken,
    UsernamePassword,
)
from mcp_hydrolix.mcp_env import HydrolixConfig, get_config
from mcp_hydrolix.models import (
    AggregateColumn,
    AliasColumn,
    Column,
    ColumnType,
    HdxQueryResult,
    SummaryColumn,
    Table,
)
from mcp_hydrolix.utils import inject_limit, with_serializer


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
if hasattr(signal, "SIGQUIT"):
    signal.signal(signal.SIGQUIT, term)

# Cached per-process result of the /version preflight check.
# None = not yet checked; True/False = supported/not supported.
_parameterized_queries_supported: Optional[bool] = None
_parameterized_queries_lock = asyncio.Lock()


def _parse_hydrolix_version(version_str: str) -> Optional[tuple[int, int]]:
    """Parse a Hydrolix version string into a (major, minor) tuple.

    Accepts formats like "v5.12.0", "v5.12.0-2-gc1398c65", or "5.12.0".
    Returns None if the string cannot be parsed.
    """
    try:
        v = version_str.lstrip("v").split("-")[0]
        parts = v.split(".")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return None


async def _check_parameterized_query_support() -> bool:
    """Return True if this Hydrolix instance supports parameterized queries (>= v5.12).

    The result is cached for the lifetime of the process after the first successful check.
    On failure the function returns False without caching, so the next call will retry.
    """
    global _parameterized_queries_supported
    if _parameterized_queries_supported is not None:
        return _parameterized_queries_supported

    async with _parameterized_queries_lock:
        # Re-check after acquiring the lock — another coroutine may have set it while we waited.
        if _parameterized_queries_supported is not None:
            return _parameterized_queries_supported

        # Credential errors are configuration/auth problems and must not be swallowed.
        creds = HYDROLIX_CONFIG.creds_with(get_request_credential())
        if isinstance(creds, UsernamePassword):
            encoded = base64.b64encode(f"{creds.username}:{creds.password}".encode()).decode()
            headers = {"Authorization": f"Basic {encoded}"}
        else:
            headers = {"Authorization": f"Bearer {cast(ServiceAccountToken, creds).token}"}

        scheme = "https" if HYDROLIX_CONFIG.secure else "http"
        proxy = HYDROLIX_CONFIG.proxy_path or ""
        url = f"{scheme}://{HYDROLIX_CONFIG.host}:{HYDROLIX_CONFIG.port}{proxy}/version"

        try:
            response = await asyncio.to_thread(
                client_shared_pool.request, "GET", url, headers=headers
            )
        except Exception as e:
            logger.warning(
                f"Failed to reach Hydrolix /version endpoint: {e}. Falling back to interpolated queries.",
                exc_info=True,
            )
            return False

        if response.status != 200:
            logger.warning(
                f"Unexpected HTTP {response.status} from {url}. Falling back to interpolated queries."
            )
            return False

        version_str = response.data.decode("utf-8").strip()
        parsed = _parse_hydrolix_version(version_str)
        if parsed is None:
            logger.warning(
                f"Could not parse Hydrolix version {version_str!r}. Falling back to interpolated queries."
            )
            return False

        _parameterized_queries_supported = parsed >= (5, 12)
        logger.info(
            f"Hydrolix version {version_str!r}: parameterized queries "
            f"{'supported' if _parameterized_queries_supported else 'not supported'}"
        )

    return _parameterized_queries_supported


async def execute_query(
    query: str, parameters: Optional[Dict[str, Any]] = None, extra_settings: Dict[str, Any] = {}
) -> HdxQueryResult:
    m = metrics.get_instance()
    start = time.perf_counter()
    status = "success"
    try:
        async with await create_hydrolix_client(
            client_shared_pool, get_request_credential()
        ) as client:
            settings: dict[str, Any] = {
                "readonly": 1,
                "hdx_query_max_execution_time": HYDROLIX_CONFIG.query_timeout_sec,
                "hdx_query_max_attempts": 1,
                "hdx_query_max_result_rows": 100_000,
                "hdx_query_max_memory_usage": 2 * 1024 * 1024 * 1024,  # 2GiB
                "hdx_query_admin_comment": f"User: {MCP_SERVER_NAME}",
            } | extra_settings
            res = await client.query(
                query,
                parameters=parameters,
                settings=settings,
            )
            logger.info(f"Query returned {len(res.result_rows)} rows")
            return HdxQueryResult(
                columns=list(res.column_names), rows=[list(row) for row in res.result_rows]
            )
    except Exception as err:
        logger.error(f"Error executing query: {err}")
        status = "error"
        raise ToolError(f"Query execution failed: {str(err)}")
    finally:
        if m is not None:
            m.queries_total.labels(status=status).inc()
            m.query_duration_seconds.observe(time.perf_counter() - start)


async def execute_cmd(query: str):
    m = metrics.get_instance()
    start = time.perf_counter()
    status = "success"
    try:
        async with await create_hydrolix_client(
            client_shared_pool, get_request_credential()
        ) as client:
            res = await client.command(query)
            logger.info("Command executed successfully.")
            return res
    except Exception as err:
        logger.error(f"Error executing command: {err}")
        status = "error"
        raise ToolError(f"Command execution failed: {str(err)}")
    finally:
        if m is not None:
            m.queries_total.labels(status=status).inc()
            m.query_duration_seconds.observe(time.perf_counter() - start)


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


if HYDROLIX_CONFIG.metrics_enabled:

    @mcp.custom_route("/metrics", methods=["GET"])
    async def metrics_endpoint(_request: Request) -> Response:
        data, content_type = metrics.generate_metrics()
        return Response(content=data, media_type=content_type)

    class MetricsMiddleware(Middleware):
        async def on_request(self, context: MiddlewareContext, call_next) -> Any:
            m = metrics.get_instance()
            if (
                m is None
            ):  # defensive — should not happen since middleware is only added when metrics are enabled
                return await call_next(context)
            if context.method != "tools/call":
                return await call_next(context)
            tool_name = context.message.name
            m.active_requests.inc()
            start = time.perf_counter()
            status = "success"
            try:
                result = await call_next(context)
                return result
            except Exception:
                status = "error"
                raise
            finally:
                m.tool_calls_total.labels(tool=tool_name, status=status).inc()
                m.tool_call_duration_seconds.labels(tool=tool_name).observe(
                    time.perf_counter() - start
                )
                m.active_requests.dec()

    mcp.add_middleware(MetricsMiddleware())


def result_to_table(query_columns, result) -> List[Table]:
    sql_fields = Table.sql_fields()
    return [
        Table(**{k: v for k, v in zip(query_columns, row) if k in sql_fields}) for row in result
    ]


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


def detect_aggregate_aliases(alias_definitions: Dict[str, str]) -> Set[str]:
    """
    Parse ALIAS column expressions via sqlglot AST, build alias dependency graph,
    topologically sort, and return the set of alias names that are aggregate
    (directly contain AggFunc OR transitively depend on another aggregate alias).
    Unparseable expressions are treated as non-aggregate. Circular dependencies
    return an empty set as a safe fallback.
    """
    parsed: dict[str, sqlglot_exp.Expression] = {}
    for name, sql in alias_definitions.items():
        try:
            parsed[name] = sqlglot.parse_one(sql, dialect="clickhouse")
        except sqlglot_errors.SqlglotError:
            logger.warning(
                "detect_aggregate_aliases: could not parse ALIAS expression for %r, "
                "treating as non-aggregate (column classification may be incorrect)",
                name,
            )

    alias_names = set(alias_definitions)

    @dataclass
    class _AliasInfo:
        is_direct_aggregation: bool
        alias_dependencies: Set[str]

    def _is_agg_node(n: sqlglot_exp.Expression) -> bool:
        # sqlglot recognises simple -Merge combinators (countMerge, sumMerge, …) as
        # CombinedAggFunc (a subclass of AggFunc).  Compound combinators such as
        # countIfMerge (-If + -Merge) are unknown to sqlglot and fall back to Anonymous.
        # We catch both: the subclass check covers known functions; the name suffix
        # check covers any -Merge variant that sqlglot does not have in its registry.
        return isinstance(n, sqlglot_exp.AggFunc) or (
            isinstance(n, sqlglot_exp.Anonymous) and str(n.this).endswith("Merge")
        )

    alias_dependency_meta: Dict[str, _AliasInfo] = {}
    for name, expr in parsed.items():
        aggregators: List[sqlglot_exp.Expression] = []
        alias_dependencies: Set[str] = set()
        for node in expr.walk(prune=_is_agg_node):
            if _is_agg_node(node):
                aggregators.append(node)
            elif isinstance(node, sqlglot_exp.Column):
                if node.name in alias_names:
                    alias_dependencies.add(node.name)
        alias_dependencies |= {
            n.name
            for agg in aggregators
            for n in agg.walk()
            if isinstance(n, sqlglot_exp.Column) and n.name in alias_names
        }
        alias_dependency_meta[name] = _AliasInfo(
            is_direct_aggregation=len(aggregators) > 0,
            alias_dependencies=alias_dependencies,
        )

    try:
        order = list(
            TopologicalSorter(
                {name: m.alias_dependencies - {name} for name, m in alias_dependency_meta.items()}
            ).static_order()
        )
    except CycleError:
        logger.warning(
            "detect_aggregate_aliases: circular dependency detected among ALIAS columns %r; "
            "treating all as non-aggregate (column classification may be incorrect)",
            list(alias_dependency_meta),
        )
        return set()  # circular dependency — safe fallback, treat all as non-aggregate

    is_aggregation: Dict[str, bool] = {}
    for name in order:
        alias_meta = alias_dependency_meta[name]
        is_aggregation[name] = alias_meta.is_direct_aggregation or any(
            is_aggregation.get(d, False) for d in alias_meta.alias_dependencies
        )

    return {name for name, is_agg in is_aggregation.items() if is_agg}


async def _query_targets_summary_table(query: str) -> bool:
    """Return True if any table referenced in the query is a summary table.

    Fetches column metadata via DESCRIBE TABLE for each referenced table and
    checks for SummaryColumn instances.
    """
    try:
        parsed = sqlglot.parse_one(query, dialect="clickhouse")
    except sqlglot_errors.SqlglotError:
        return False
    for table_node in parsed.find_all(sqlglot_exp.Table):
        if not table_node.db or not table_node.name:
            continue
        try:
            columns = await _describe_columns(table_node.db, table_node.name)
            if any(isinstance(c, SummaryColumn) for c in columns):
                return True
        except Exception:
            continue
    return False


def _enrich_column_metadata(rows: List[Dict[str, str]]) -> List[ColumnType]:
    """
    Classify DESCRIBE TABLE rows into typed column objects (Column, AliasColumn,
    AggregateColumn, SummaryColumn). ALIAS columns whose expressions transitively
    depend on aggregate functions are detected via AST parsing and classified as
    SummaryColumn; all other ALIAS columns become AliasColumn. Columns with
    AggregateFunction/SimpleAggregateFunction types become AggregateColumn.
    Everything else is a plain Column.
    """
    alias_columns: Dict[str, str] = {
        r["name"]: r["default_expression"]
        for r in rows
        if r.get("default_type") == "ALIAS" and r.get("default_expression")
    }
    aggregate_alias_names = detect_aggregate_aliases(alias_columns) if alias_columns else set()

    def classify_column(r: Dict[str, str]) -> ColumnType:
        name = r["name"]
        col_type = r.get("type", "")
        comment = r.get("comment") or None

        if r.get("default_type") != "ALIAS":
            if col_type.startswith(("AggregateFunction(", "SimpleAggregateFunction(")):
                base_fn = extract_function_from_type(col_type)
                merge_fn = get_merge_function(base_fn) if base_fn else f"{col_type}Merge"
                return AggregateColumn(name, col_type, base_fn or "", merge_fn, comment)
            return Column(name, col_type, comment)
        elif name in aggregate_alias_names:
            return SummaryColumn(name, col_type, alias_columns[name], comment)
        else:
            return AliasColumn(name, col_type, r.get("default_expression", ""), comment)

    return [classify_column(r) for r in rows]


async def _describe_columns(database: str, table_name: str) -> list[ColumnType]:
    """Fetch and classify columns for a table via DESCRIBE TABLE.

    Uses DESCRIBE TABLE to get full AggregateFunction types.
    """
    result = await execute_query(f"DESCRIBE TABLE `{database}`.`{table_name}`")
    col_names = result["columns"]
    rows = [dict(zip(col_names, row)) for row in result["rows"]]
    return _enrich_column_metadata(rows)


def summary_tips_for_columns(columns: list[ColumnType]) -> Optional[str]:
    """Build human-readable summary-table guidance from classified columns, or None if not a summary table."""
    aggregate_cols = [c for c in columns if isinstance(c, (AggregateColumn, SummaryColumn))]
    if len(aggregate_cols) == 0:
        # not a summary table
        return None
    dimension_cols = [c for c in columns if isinstance(c, (Column, AliasColumn))]
    return (
        f"This is a SUMMARY TABLE with {len(aggregate_cols)} aggregate column(s) and {len(dimension_cols)} dimension column(s). "
        "Columns with column_category='AggregateColumn' MUST be wrapped in their corresponding merge_function. "
        "Columns with column_category='SummaryColumn' are ALIAS columns that transitively depend on aggregates - use directly without wrapping. "
        "IMPORTANT: SummaryColumns are per-row values, not pre-totalled across the whole table. "
        "To aggregate across ALL rows (e.g. total count for the entire table), use the corresponding AggregateColumn with its merge_function (e.g. countMerge(`count()`)), NOT a SummaryColumn. "
        "Selecting a SummaryColumn without GROUP BY returns one value per row, not a single grand total. "
        "NEVER wrap a SummaryColumn in sum(), count(), avg() or any other aggregate - this causes ILLEGAL_AGGREGATION errors. "
        "Columns with column_category='Column' or column_category='AliasColumn' are dimensions - use directly and MUST appear in GROUP BY when mixed with aggregates. "
        "IMPORTANT: Dimension columns may have function-like names (e.g., 'toStartOfHour(col)') - these are LITERAL column names, use them exactly as-is with backticks. "
        "WRONG: SELECT toStartOfHour(col). RIGHT: SELECT `toStartOfHour(col)`. Also use in GROUP BY: GROUP BY `toStartOfHour(col)`. "
        "CRITICAL RULE: If your SELECT includes ANY dimension columns (column_category='Column' or 'AliasColumn') "
        "AND ANY aggregate columns (column_category='AggregateColumn' or 'SummaryColumn'), "
        "you MUST include 'GROUP BY <all dimension columns from SELECT>'. "
        "WITHOUT GROUP BY, the query will FAIL with 'NOT_AN_AGGREGATE' error. "
        "column_category='SummaryColumn' are NOT dimensions - do NOT include them in GROUP BY. "
        "Example: SELECT reqHost, cnt_all FROM table GROUP BY reqHost (reqHost has column_category='Column', cnt_all has column_category='SummaryColumn'). "
        "CRITICAL: You MUST use the EXACT merge_function value from each column with column_category='AggregateColumn'. "
        "DO NOT infer the merge function from the column name - always check the merge_function field. "
        "For example, if column `avgIf(col, condition)` has merge_function='avgIfMerge', "
        "you MUST use avgIfMerge(`avgIf(col, condition)`), NOT avgMerge(...)."
    )


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
    - columns: List of column objects, each with a column_category field:
      - column_category='Column': plain dimension column
      - column_category='AliasColumn': non-aggregate ALIAS column, has default_expr
      - column_category='AggregateColumn': AggregateFunction/SimpleAggregateFunction type, has base_function and merge_function
      - column_category='SummaryColumn': ALIAS column that transitively depends on aggregates, has default_expr
    - summary_table_info: Human-readable description for summary tables
    - total_rows, total_bytes: Table statistics

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
    sql_fields_for_table: List[str] = Table.sql_fields()
    if await _check_parameterized_query_support():
        query = f"""
        SELECT {", ".join(sql_fields_for_table)}
        FROM system.tables
        WHERE database = {{db:String}} AND name = {{table:String}}"""
        query_params: Optional[Dict[str, Any]] = {"db": database, "table": table}
    else:
        query = f"""
        SELECT {", ".join(sql_fields_for_table)}
        FROM system.tables
        WHERE database = {format_query_value(database)} AND name = {format_query_value(table)}"""
        query_params = None

    result = await execute_query(query, parameters=query_params)

    if not result["rows"]:
        raise ToolError(f"Table {database}.{table} not found")

    params_from_metadata_table = {
        k: v for k, v in zip(result["columns"], result["rows"][0]) if k in sql_fields_for_table
    }
    columns = await _describe_columns(database, table)
    usage_guide = summary_tips_for_columns(columns)
    return Table(
        **params_from_metadata_table,
        columns=columns,
        is_summary_table=any(isinstance(c, SummaryColumn) for c in columns),
        summary_table_info=usage_guide,
    )


@mcp.tool()
async def list_tables(
    database: str, like: Optional[str] = None, not_like: Optional[str] = None
) -> List[Table]:
    """List all tables in a database for exploration and discovery.

    Use this tool to:
    - Discover what tables exist in a database
    - Filter tables by name pattern (like/not_like)
    - Get basic table metadata (name, engine, row counts, sizes, primary keys)

    Returns basic table information WITHOUT column details for performance.
    Tables are returned with empty columns lists and is_summary_table not set.

    IMPORTANT: Always call get_table_info(database, table) before querying a specific table.
    Column metadata (types, categories, merge functions) is required to build correct queries,
    especially for summary tables which need special -Merge function syntax.
    list_tables() is intentionally lightweight to avoid loading schema for all tables at once.
    """
    logger.info(f"Listing tables in database '{database}'")
    if await _check_parameterized_query_support():
        query = f"""
        SELECT {", ".join(Table.sql_fields())}
        FROM system.tables WHERE database = {{db:String}}"""
        query_params: Optional[Dict[str, Any]] = {"db": database}
        if like:
            query += " AND name LIKE {like:String}"
            query_params["like"] = like
        if not_like:
            query += " AND name NOT LIKE {not_like:String}"
            query_params["not_like"] = not_like
    else:
        query = f"""
        SELECT {", ".join(Table.sql_fields())}
        FROM system.tables WHERE database = {format_query_value(database)}"""
        query_params = None
        if like:
            query += f" AND name LIKE {format_query_value(like)}"
        if not_like:
            query += f" AND name NOT LIKE {format_query_value(not_like)}"

    result = await execute_query(query, parameters=query_params)

    # Deserialize result as Table dataclass instances (without column metadata)
    tables = result_to_table(result["columns"], result["rows"])

    # DO NOT populate columns here - this makes list_tables() fast and token-efficient
    # LLM will call get_table_info() for specific tables when needed
    # This optimization reduces token usage by 90%+ for typical workflows

    logger.info(
        f"Found {len(tables)} tables (columns not populated - use get_table_info for schema)"
    )
    return tables


def _resolve_cell_limit(max_cells: Optional[int]) -> tuple[int, bool]:
    """Validate max_cells and resolve the effective cell limit and operator-cap flag."""
    if max_cells is not None and max_cells < 0:
        raise ToolError("max_cells must be 0 (to disable truncation) or a positive integer.")

    cell_limit = max_cells if max_cells is not None else HYDROLIX_CONFIG.max_result_cells

    upper_limit = HYDROLIX_CONFIG.max_result_cells_limit
    capped_by_operator = False
    if upper_limit > 0 and (cell_limit == 0 or cell_limit > upper_limit):
        cell_limit = upper_limit
        capped_by_operator = True

    return cell_limit, capped_by_operator


def _build_truncation_response(
    columns: list,
    rows: list,
    cell_limit: int,
    capped_by_operator: bool,
) -> dict:
    """Build the truncated response dict, logging the truncation event.

    Precondition: len(columns) > 0 (caller already guards this).
    """
    num_rows = len(rows)
    num_cols = len(columns)
    max_rows = cell_limit // num_cols
    total_cells = num_rows * num_cols

    logger.info(
        f"Truncating result from {num_rows} to {max_rows} rows "
        f"(cell limit: {cell_limit}, columns: {num_cols})"
    )

    if capped_by_operator:
        retrieve_more = (
            f"This limit is enforced by the server (max_cells capped at {cell_limit:,}). "
            f"Contact your administrator to adjust HYDROLIX_MAX_RESULT_CELLS_LIMIT, "
            f"or refine your query with LIMIT, WHERE filters, or GROUP BY."
        )
    else:
        retrieve_more = (
            "Consider refining your query with LIMIT, WHERE filters, or GROUP BY. "
            "To retrieve more data, call run_select_query with a larger max_cells value "
            "(e.g. max_cells=200000), or set max_cells=0 to disable truncation entirely."
        )

    return {
        "columns": columns,
        "rows": rows[:max_rows],
        "truncated": True,
        "row_count": max_rows,
        "total_row_count": num_rows,
        "message": (
            f"Result truncated: showing {max_rows:,} of {num_rows:,} fetched rows "
            f"({num_cols} columns). "
            f"Exceeded the cell limit of {cell_limit:,} "
            f"({total_cells:,} cells in full result). "
            + (
                "Note: total_row_count reflects rows fetched from the server "
                "(capped at 100,000) — the actual table may contain more rows. "
                if num_rows >= 100_000
                else ""
            )
            + retrieve_more
        ),
    }


@mcp.tool()
@with_serializer
async def run_select_query(
    query: str,
    max_cells: Optional[int] = None,
) -> ToolResult:
    """Run a SELECT query in a Hydrolix time-series database using the Clickhouse SQL dialect.
    Queries run using this tool will timeout after 30 seconds.

    RESULT TRUNCATION:

    Query results are automatically truncated when the total cell count (rows * columns)
    exceeds the configured limit.

    Response shape:
        - Always present: columns, rows, truncated (bool), row_count
        - Only when truncated=true: total_row_count, message
        Note: total_row_count is the number of rows fetched from the server, which is
        capped at 100,000. The actual table may contain more rows than this value suggests.

    Note: if the cell limit is smaller than the number of columns, row_count will be 0 —
    in that case you must either refine the query (fewer columns, stricter filters) or
    increase max_cells.

    MANDATORY PRE-QUERY CHECK:

    Before running ANY query, call get_table_info(database, table_name) if you haven't already.
    Check is_summary_table and read column metadata (column_category, merge_function per column).
    If is_summary_table=True: follow summary_table_info from get_table_info response and rules below.
    If is_summary_table=False: use standard SQL (count, sum, avg, etc.).

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

    SUMMARY TABLE RULES (if is_summary_table=True):

    Use column_category from get_table_info to determine column usage — do NOT infer from names.

    1. column_category='AggregateColumn': MUST be wrapped in its merge_function
       - Stores binary AggregateFunction state — direct SELECT causes deserialization errors
       - Use exact merge_function from column metadata (do NOT infer from column name)
       - count(vendor_id) → countMerge(`count(vendor_id)`), countIf(c) → countIfMerge(`countIf(c)`)
       - Always use backticks for column names with special characters

    2. column_category='SummaryColumn': select directly, no wrapping
       - ALIAS that wraps -Merge internally — NEVER wrap in sum()/count()/avg() (ILLEGAL_AGGREGATION)
       - Per-row value — for grand totals use the corresponding AggregateColumn + merge_function

    3. column_category='Column'/'AliasColumn': dimension columns, use as-is
       - Many have function-like names (e.g., `toStartOfMinute(dt)`) — LITERAL names, not expressions
       - WRONG: SELECT toStartOfMinute(dt)  RIGHT: SELECT `toStartOfMinute(dt)`
       - For time filters: use '2022-06-01' or '2022-06-01 00:00:00' — NOT partial '2022-06-01 00:00'
       - Use >= and < for ranges: WHERE col >= '2022-06-01' AND col < '2022-06-02'

    4. GROUP BY: required when SELECT mixes dimension columns with aggregates
       - Only Column/AliasColumn go in GROUP BY — never AggregateColumn or SummaryColumn

    5. NEVER use SELECT * on summary tables (causes deserialization errors)

    Summary table query patterns (after calling get_table_info first):

    Pattern 1: Aggregate entire table
    -- First: get_table_info('database', 'summary_table')
    -- Read column.merge_function for count(column_name) = "countMerge"
    SELECT countMerge(`count(column_name)`) as total FROM database.summary_table

    Pattern 2: Aggregate with grouping by dimension and optional time range filter
    -- First: get_table_info('database', 'summary_table')
    -- Read merge_function for each aggregate column
    SELECT `toStartOfMinute(datetime_field)` as time_bucket,
           countMerge(`count(column_name)`) as total,
           avgMerge(`avg(other_column)`) as avg_value
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

    Pattern 4: Using column_category='SummaryColumn'
    -- First: get_table_info('database', 'summary_table')
    -- SummaryColumns are per-row values — use with GROUP BY to break down by dimension
    SELECT cdn, cnt_all, sum_bytes FROM database.summary_table GROUP BY cdn
    -- No -Merge needed, these are pre-defined aliases
    -- For a grand total across all rows, use AggregateColumn + merge_function instead:
    SELECT countMerge(`count()`) AS grand_total FROM database.summary_table

    Pattern 5: Using dimensions with function-like names (common pattern)
    -- First: get_table_info('database', 'summary_table')
    -- Dimension column named: toStartOfMinute(primary_datetime) — LITERAL name, not an expression
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
    """
    cell_limit, capped_by_operator = _resolve_cell_limit(max_cells)

    # Rewrite the query to add a server-side LIMIT before hitting the DB, so we don't
    # materialise more rows than needed. inject_limit takes the min of any existing LIMIT
    # and our budget. We pass cell_limit as a loose upper bound on rows — the exact
    # column count is only known after execution, so we can't be precise here;
    # post-fetch cell-based truncation below handles the final slice.
    effective_query = inject_limit(query, cell_limit) if cell_limit > 0 else query

    logger.info(f"Executing SELECT query: {effective_query}")
    try:
        extra_settings: dict[str, Any] = {"hdx_query_timerange_required": True}
        if not await _query_targets_summary_table(query):
            extra_settings["hdx_query_max_timerange_sec"] = get_config().max_raw_timerange
        result = await execute_query(query=effective_query, extra_settings=extra_settings)
    except ToolError:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in run_select_query: {str(e)}")
        raise ToolError(f"Unexpected error during query execution: {str(e)}")

    columns, rows = result["columns"], result["rows"]
    num_rows, num_cols = len(rows), len(columns)

    if cell_limit > 0 and num_cols > 0 and num_rows * num_cols > cell_limit:
        return _build_truncation_response(columns, rows, cell_limit, capped_by_operator)

    return {"columns": columns, "rows": rows, "truncated": False, "row_count": num_rows}
