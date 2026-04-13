import atexit
import logging.config as lconfig
import os
import shutil
import tempfile

from fastmcp.server.http import StarletteWithLifespan
from gunicorn.app.base import BaseApplication
from prometheus_client import multiprocess as prom_multiprocess

from . import metrics
from .log import setup_logging
from .mcp_env import TransportType, get_config
from .mcp_server import mcp


def _child_exit(_server, worker) -> None:
    prom_multiprocess.mark_process_dead(worker.pid)


class CoreApplication(BaseApplication):
    """Gunicorn Core Application"""

    def __init__(self, app: StarletteWithLifespan, options: dict = None) -> None:
        """Initialize the core application."""
        self.options = options or {}
        self.app = app
        super().__init__()

    def load_config(self) -> None:
        """Load the options specific to this application."""
        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self) -> BaseApplication:
        """Load the application."""
        return self.app


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

    transport = config.mcp_server_transport

    # For HTTP and SSE transports, we need to specify host and port
    http_transports = [TransportType.HTTP.value, TransportType.SSE.value]
    if transport in http_transports:
        # Use the configured bind host (defaults to 127.0.0.1, can be set to 0.0.0.0)
        # and bind port (defaults to 8000)
        workers = config.mcp_workers
        if workers == 1:
            log_dict_config = setup_logging(None, "INFO", "json")
            lconfig.dictConfig(log_dict_config)
            mcp.run(
                transport=transport,
                host=config.mcp_bind_host,
                port=config.mcp_bind_port,
                uvicorn_config={"log_config": log_dict_config},
                stateless_http=True,
            )
        else:
            log_dict_config = setup_logging(None, "INFO", "json")
            lconfig.dictConfig(log_dict_config)

            options = {
                "bind": f"{config.mcp_bind_host}:{config.mcp_bind_port}",
                "timeout": config.mcp_timeout,
                "workers": config.mcp_workers,
                "worker_class": "uvicorn_worker.UvicornWorker",
                "worker_connections": config.mcp_worker_connections,
                "max_requests": config.mcp_max_requests,
                "max_requests_jitter": config.mcp_max_requests_jitter,
                "keepalive": config.mcp_keepalive,
                "worker_tmp_dir": "/dev/shm",
                "logconfig_dict": log_dict_config,
            }

            if config.metrics_enabled:
                options["child_exit"] = _child_exit

            CoreApplication(
                mcp.http_app(path="/mcp", stateless_http=True, transport=transport), options
            ).run()
    else:
        # For stdio transport, no host or port is needed
        log_dict_config = setup_logging(None, "INFO", "json")
        if log_dict_config:
            lconfig.dictConfig(log_dict_config)
        mcp.run(transport=transport)


if __name__ == "__main__":
    main()
