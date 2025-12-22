import logging.config as lconfig

from fastmcp.server.http import StarletteWithLifespan
from gunicorn.app.base import BaseApplication

from .log import setup_logging
from .mcp_env import TransportType, get_config
from .mcp_server import mcp


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
                "worker_class": "uvicorn.workers.UvicornWorker",
                "worker_connections": config.mcp_worker_connections,
                "max_requests": config.mcp_max_requests,
                "max_requests_jitter": config.mcp_max_requests_jitter,
                "keepalive": config.mcp_keepalive,
                "logconfig_dict": log_dict_config,
            }
            CoreApplication(
                mcp.http_app(path="/mcp", stateless_http=True, transport=transport), options
            ).run()
    else:
        # For stdio transport, no host or port is needed
        mcp.run(transport=transport)


if __name__ == "__main__":
    main()
