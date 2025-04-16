import logging
from typing import Sequence
import concurrent.futures
import atexit

import clickhouse_connect
from clickhouse_connect.driver.binding import quote_identifier, format_query_value
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_hydrolix.mcp_env import config

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

deps = [
    "clickhouse-connect",
    "python-dotenv",
    "uvicorn",
    "pip-system-certs",
]

mcp = FastMCP(MCP_SERVER_NAME, dependencies=deps)


@mcp.tool()
def list_databases():
    """List available Hydrolix databases"""
    logger.info("Listing all databases")
    client = create_hydrolix_client()
    result = client.command("SHOW DATABASES")
    logger.info(f"Found {len(result) if isinstance(result, list) else 1} databases")
    return result


@mcp.tool()
def list_tables(database: str, like: str = None):
    """List available Hydrolix tables in a database"""
    logger.info(f"Listing tables in database '{database}'")
    client = create_hydrolix_client()
    query = f"SHOW TABLES FROM {quote_identifier(database)}"
    if like:
        query += f" LIKE {format_query_value(like)}"
    result = client.command(query)

    # Get all table comments in one query
    table_comments_query = (
        f"SELECT name, comment FROM system.tables WHERE database = {format_query_value(database)}"
    )
    table_comments_result = client.query(table_comments_query)
    table_comments = {row[0]: row[1] for row in table_comments_result.result_rows}

    # Get all column comments in one query
    column_comments_query = f"SELECT table, name, comment FROM system.columns WHERE database = {format_query_value(database)}"
    column_comments_result = client.query(column_comments_query)
    column_comments = {}
    for row in column_comments_result.result_rows:
        table, col_name, comment = row
        if table not in column_comments:
            column_comments[table] = {}
        column_comments[table][col_name] = comment

    def get_table_info(table):
        logger.info(f"Getting schema info for table {database}.{table}")
        schema_query = f"DESCRIBE TABLE {quote_identifier(database)}.{quote_identifier(table)}"
        schema_result = client.query(schema_query)

        columns = []
        column_names = schema_result.column_names
        for row in schema_result.result_rows:
            column_dict = {}
            for i, col_name in enumerate(column_names):
                column_dict[col_name] = row[i]
            # Add comment from our pre-fetched comments
            if table in column_comments and column_dict["name"] in column_comments[table]:
                column_dict["comment"] = column_comments[table][column_dict["name"]]
            else:
                column_dict["comment"] = None
            columns.append(column_dict)

        create_table_query = f"SHOW CREATE TABLE {database}.`{table}`"
        create_table_result = client.command(create_table_query)

        return {
            "database": database,
            "name": table,
            "comment": table_comments.get(table),
            "columns": columns,
            "create_table_query": create_table_result,
        }

    tables = []
    if isinstance(result, str):
        # Single table result
        for table in (t.strip() for t in result.split()):
            if table:
                tables.append(get_table_info(table))
    elif isinstance(result, Sequence):
        # Multiple table results
        for table in result:
            tables.append(get_table_info(table))

    logger.info(f"Found {len(tables)} tables")
    return tables


def execute_query(query: str):
    client = create_hydrolix_client()
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
        column_names = res.column_names
        rows = []
        for row in res.result_rows:
            row_dict = {}
            for i, col_name in enumerate(column_names):
                row_dict[col_name] = row[i]
            rows.append(row_dict)
        logger.info(f"Query returned {len(rows)} rows")
        return rows
    except Exception as err:
        logger.error(f"Error executing query: {err}")
        # Return a structured dictionary rather than a string to ensure proper serialization
        # by the MCP protocol. String responses for errors can cause BrokenResourceError.
        return {"error": str(err)}


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
        future = QUERY_EXECUTOR.submit(execute_query, query)
        try:
            result = future.result(timeout=SELECT_QUERY_TIMEOUT_SECS)
            # Check if we received an error structure from execute_query
            if isinstance(result, dict) and "error" in result:
                logger.warning(f"Query failed: {result['error']}")
                # MCP requires structured responses; string error messages can cause
                # serialization issues leading to BrokenResourceError
                return {"status": "error", "message": f"Query failed: {result['error']}"}
            return result
        except concurrent.futures.TimeoutError:
            logger.warning(f"Query timed out after {SELECT_QUERY_TIMEOUT_SECS} seconds: {query}")
            future.cancel()
            # Return a properly structured response for timeout errors
            return {
                "status": "error",
                "message": f"Query timed out after {SELECT_QUERY_TIMEOUT_SECS} seconds",
            }
    except Exception as e:
        logger.error(f"Unexpected error in run_select_query: {str(e)}")
        # Catch all other exceptions and return them in a structured format
        # to prevent MCP serialization failures
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}


def create_hydrolix_client():
    client_config = config.get_client_config()
    logger.info(
        f"Creating Hydrolix client connection to {client_config['host']}:{client_config['port']} "
        f"as {client_config['username']} "
        f"(secure={client_config['secure']}, verify={client_config['verify']}, "
        f"connect_timeout={client_config['connect_timeout']}s, "
        f"send_receive_timeout={client_config['send_receive_timeout']}s)"
    )

    try:
        client = clickhouse_connect.get_client(**client_config)
        # Test the connection
        version = client.server_version
        logger.info(f"Successfully connected to Hydrolix server version {version}")
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Hydrolix: {str(e)}")
        raise
