import logging
import os

logger = logging.getLogger(__name__)


def inject_truststore() -> None:
    # Inject before importing mcp_server, which creates client_shared_pool at
    # module level. Only the exact string "1" disables injection (matches
    # mcp-clickhouse). Any failure logs a warning rather than crashing startup.
    if os.getenv("MCP_HYDROLIX_TRUSTSTORE_DISABLE", None) != "1":
        try:
            import truststore

            truststore.inject_into_ssl()
        except Exception as exc:
            logger.warning("truststore injection failed, falling back to default SSL: %s", exc)


inject_truststore()

from .mcp_server import (  # noqa: E402
    create_hydrolix_client,
    get_table_info,
    list_databases,
    list_tables,
    run_select_query,
)

__all__ = [
    "list_databases",
    "list_tables",
    "run_select_query",
    "create_hydrolix_client",
    "get_table_info",
]
