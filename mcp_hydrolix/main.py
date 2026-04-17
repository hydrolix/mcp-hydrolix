import atexit
import logging.config as lconfig
import os
import shutil
import tempfile

import uvicorn
from prometheus_client import multiprocess as prom_multiprocess

from . import metrics
from .log import setup_logging
from .mcp_env import TransportType, get_config
from .mcp_server import mcp


def _mark_worker_dead() -> None:
    """atexit handler for Prometheus multiprocess mode."""
    prom_multiprocess.mark_process_dead(os.getpid())


def main():
    config = get_config()

    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        # Wipe on startup — clears stale files from any previous run
        shutil.rmtree(os.environ["PROMETHEUS_MULTIPROC_DIR"], ignore_errors=True)

    if config.metrics_enabled and config.mcp_workers > 1:
        if "PROMETHEUS_MULTIPROC_DIR" not in os.environ:
            # Local multi-worker: create a temp dir and clean it up on exit
            tmpdir = tempfile.mkdtemp(prefix="prom_mcp_")
            os.environ["PROMETHEUS_MULTIPROC_DIR"] = tmpdir
            atexit.register(lambda: shutil.rmtree(tmpdir, ignore_errors=True))
        os.makedirs(os.environ["PROMETHEUS_MULTIPROC_DIR"], exist_ok=True)

    if config.metrics_enabled:
        metrics.enable()
        if config.mcp_workers > 1:
            atexit.register(_mark_worker_dead)

    transport = config.mcp_server_transport

    # For HTTP and SSE transports, we need to specify host and port
    http_transports = [TransportType.HTTP.value, TransportType.SSE.value]
    if transport in http_transports:
        # Use the configured bind host (defaults to 127.0.0.1, can be set to 0.0.0.0)
        # and bind port (defaults to 8000).
        # Uvicorn requires an import string (not an app instance) to support
        # workers > 1, since each child process re-imports the factory.
        log_dict_config = setup_logging(None, "INFO", "json")
        lconfig.dictConfig(log_dict_config)
        uvicorn.run(
            "mcp_hydrolix.webapp:create_app",
            factory=True,
            host=config.mcp_bind_host,
            port=config.mcp_bind_port,
            workers=config.mcp_workers,
            timeout_keep_alive=config.mcp_keepalive,
            limit_concurrency=config.mcp_worker_connections,
            limit_max_requests=(
                config.mcp_max_requests
                if config.mcp_workers > 1 and config.mcp_max_requests > 0
                else None
            ),
            limit_max_requests_jitter=config.mcp_max_requests_jitter,
            log_config=log_dict_config,
            access_log=False,
            server_header=False,
            timeout_graceful_shutdown=config.mcp_graceful_timeout,
        )
    else:
        # For stdio transport, no host or port is needed
        log_dict_config = setup_logging(None, "INFO", "json")
        if log_dict_config:
            lconfig.dictConfig(log_dict_config)
        mcp.run(transport=transport)


if __name__ == "__main__":
    main()
