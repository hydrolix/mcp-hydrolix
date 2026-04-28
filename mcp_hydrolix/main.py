import atexit
import logging.config as lconfig
import multiprocessing
import os
import shutil
import tempfile

import uvicorn

from . import mcp_env
from .log import setup_logging
from .mcp_env import TransportType

# NOTE: do NOT import ``.mcp_server`` at module scope. It transitively imports
# ``.metrics``, whose module-level code reads ``PROMETHEUS_MULTIPROC_DIR`` to
# decide between live and no-op collectors and to register the bypass warning.
# ``main()`` must be allowed to set that env var *before* metrics.py is first
# imported; otherwise the supervisor process trips its own "launcher bypassed"
# warning on every legitimate multi-worker startup. The stdio branch imports
# ``mcp`` lazily below.


def _prepare_prometheus_multiproc_dir():
    """Wipe and recreate ``PROMETHEUS_MULTIPROC_DIR`` when workers will share it."""
    # Module-qualified so tests can monkeypatch mcp_env.get_config.
    config = mcp_env.get_config()
    if (not config.metrics_enabled) or config.mcp_workers == 1:
        return config

    if "PROMETHEUS_MULTIPROC_DIR" not in os.environ:
        # Use a temporary directory for the prometheus multiproc dir if none was explicitly set
        tmpdir = tempfile.mkdtemp(prefix="prom_mcp_")
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = tmpdir
        atexit.register(lambda: shutil.rmtree(tmpdir, ignore_errors=True))

    # "The PROMETHEUS_MULTIPROC_DIR environment variable must be set to a directory that
    # the client library can use for metrics. This directory must be wiped between process/Gunicorn
    # runs (before startup is recommended)." ~ https://prometheus.github.io/client_python/multiprocess/
    shutil.rmtree(os.environ["PROMETHEUS_MULTIPROC_DIR"], ignore_errors=True)
    os.makedirs(os.environ["PROMETHEUS_MULTIPROC_DIR"], exist_ok=True)
    return config


def main():
    # Force spawn universally: workers get a fresh interpreter, so no
    # supervisor state (prometheus collectors, open fds, cached config,
    # RNG state, etc.) can leak to them via fork inheritance. This is the
    # primary correctness guarantee; the PID guard in metrics.py is the
    # structural backstop.
    multiprocessing.set_start_method("spawn", force=True)

    config = _prepare_prometheus_multiproc_dir()

    transport = config.mcp_server_transport

    # For HTTP and SSE transports, we need to specify host and port
    http_transports = [TransportType.HTTP.value, TransportType.SSE.value]
    if transport in http_transports:
        log_dict_config = setup_logging(None, "INFO", "json")
        lconfig.dictConfig(log_dict_config)
        # Uvicorn requires an import string (not an app instance) to support
        # workers > 1, since each child process re-imports the factory.
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
            timeout_worker_healthcheck=config.mcp_worker_healthcheck_timeout,
        )
    else:
        log_dict_config = setup_logging(None, "INFO", "json")
        if log_dict_config:
            lconfig.dictConfig(log_dict_config)
        # Lazy import — see module docstring for why this must not be hoisted.
        from .mcp_server import mcp

        mcp.run(transport=transport)


if __name__ == "__main__":
    main()
