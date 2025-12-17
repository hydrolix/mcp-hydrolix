"""Environment configuration for the MCP Hydrolix server.

This module handles all environment variable configuration with sensible defaults
and type conversion.
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from mcp_hydrolix.auth.credentials import HydrolixCredential, ServiceAccountToken, UsernamePassword


class TransportType(str, Enum):
    """Supported MCP server transport types."""

    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"

    @classmethod
    def values(cls) -> list[str]:
        """Get all valid transport values."""
        return [transport.value for transport in cls]


@dataclass
class HydrolixConfig:
    """Configuration for Hydrolix connection settings.

    This class handles all environment variable configuration with sensible defaults
    and type conversion. It provides typed methods for accessing each configuration value.

    Required environment variables:
        HYDROLIX_HOST: The hostname of the Hydrolix server

    Optional environment variables (with defaults):
        HYDROLIX_TOKEN: Service account token to the Hydrolix Server (this or user+password is required)
        HYDROLIX_USER: The username for authentication (this or token is required)
        HYDROLIX_PASSWORD: The password for authentication (this or token is required)
        HYDROLIX_PORT: The port number (default: 8088)
        HYDROLIX_VERIFY: Verify SSL certificates (default: true)
        HYDROLIX_CONNECT_TIMEOUT: Connection timeout in seconds (default: 30)
        HYDROLIX_SEND_RECEIVE_TIMEOUT: Send/receive timeout in seconds (default: 300)
        HYDROLIX_DATABASE: Default database to use (default: None)
        HYDROLIX_PROXY_PATH: Path to be added to the host URL. For instance, for servers behind an HTTP proxy (default: None)
        HYDROLIX_MCP_SERVER_TRANSPORT: MCP server transport method - "stdio", "http", or "sse" (default: stdio)
        HYDROLIX_MCP_BIND_HOST: Host to bind the MCP server to when using HTTP or SSE transport (default: 127.0.0.1)
        HYDROLIX_MCP_BIND_PORT: Port to bind the MCP server to when using HTTP or SSE transport (default: 8000)
        HYDROLIX_QUERIES_POOL_SIZE 100
        HYDROLIX_MCP_REQUEST_TIMEOUT 120
        HYDROLIX_MCP_WORKERS 3
        HYDROLIX_MCP_WORKER_CONNECTIONS 200
        HYDROLIX_MCP_MAX_REQUESTS 10000
        HYDROLIX_MCP_MAX_REQUESTS_JITTER 1000
        HYDROLIX_MCP_MAX_KEEPALIVE 10
    """

    def __init__(self) -> None:
        """Initialize the configuration from environment variables."""
        self._validate_required_vars()
        # Credential to use for clickhouse connections when no per-request credential is provided
        self._default_credential: Optional[HydrolixCredential] = None

        # Set the default credential to the service account from the environment, if available
        if (global_service_account := os.environ.get("HYDROLIX_TOKEN")) is not None:
            self._default_credential = ServiceAccountToken(
                global_service_account, f"https://{self.host}/config"
            )
        elif (global_username := os.environ.get("HYDROLIX_USER")) is not None and (
            global_password := os.environ.get("HYDROLIX_PASSWORD")
        ) is not None:
            # No global service account available. Set the default credential to the username/password
            # from the environment, if available
            self._default_credential = UsernamePassword(global_username, global_password)

    def creds_with(self, request_credential: Optional[HydrolixCredential]) -> HydrolixCredential:
        if request_credential is not None:
            return request_credential
        elif self._default_credential is not None:
            return self._default_credential
        else:
            raise ValueError(
                "No credentials available for Hydrolix connection. "
                "Please provide credentials either through HYDROLIX_TOKEN or "
                "HYDROLIX_USER/HYDROLIX_PASSWORD environment variables, "
                "or pass credentials explicitly via the creds parameter."
            )

    @property
    def host(self) -> str:
        """Get the Hydrolix host. Called during __init__"""
        return os.environ["HYDROLIX_HOST"]

    @property
    def port(self) -> int:
        """Get the Hydrolix port.

        Defaults to 8088.
        Can be overridden by HYDROLIX_PORT environment variable.
        """
        if "HYDROLIX_PORT" in os.environ:
            return int(os.environ["HYDROLIX_PORT"])
        return 8088

    @property
    def database(self) -> Optional[str]:
        """Get the default database name if set."""
        return os.getenv("HYDROLIX_DATABASE")

    @property
    def verify(self) -> bool:
        """Get whether SSL certificate verification is enabled.

        Default: True
        """
        return os.getenv("HYDROLIX_VERIFY", "true").lower() == "true"

    @property
    def secure(self) -> bool:
        """Get whether use secured connection.

        Default: True
        """
        return os.getenv("HYDROLIX_SECURE", "true").lower() == "true"

    @property
    def connect_timeout(self) -> int:
        """Get the connection timeout in seconds.

        Default: 30
        """
        return int(os.getenv("HYDROLIX_CONNECT_TIMEOUT", "30"))

    @property
    def send_receive_timeout(self) -> int:
        """Get the send/receive timeout in seconds.

        Default: 300 (Hydrolix default)
        """
        return int(os.getenv("HYDROLIX_SEND_RECEIVE_TIMEOUT", "300"))

    @property
    def query_pool_size(self) -> int:
        """Get the send/receive timeout in seconds.

        Default: 300 (Hydrolix default)
        """
        return int(os.getenv("HYDROLIX_QUERIES_POOL_SIZE", 100))

    @property
    def query_timeout_sec(self) -> int:
        """Get the send/receive timeout in seconds.

        Default: 300 (Hydrolix default)
        """
        return int(os.getenv("HYDROLIX_QUERY_TIMEOUT_SECS", 30))

    @property
    def proxy_path(self) -> Optional[str]:
        return os.getenv("HYDROLIX_PROXY_PATH")

    @property
    def mcp_server_transport(self) -> str:
        """Get the MCP server transport method.

        Valid options: "stdio", "http", "sse"
        Default: "stdio"
        """
        transport = os.getenv("HYDROLIX_MCP_SERVER_TRANSPORT", TransportType.STDIO.value).lower()

        # Validate transport type
        if transport not in TransportType.values():
            valid_options = ", ".join(f'"{t}"' for t in TransportType.values())
            raise ValueError(f"Invalid transport '{transport}'. Valid options: {valid_options}")
        return transport

    @property
    def mcp_bind_host(self) -> str:
        """Get the host to bind the MCP server to.

        Only used when transport is "http" or "sse".
        Default: "127.0.0.1"
        """
        return os.getenv("HYDROLIX_MCP_BIND_HOST", "127.0.0.1")

    @property
    def mcp_bind_port(self) -> int:
        """Get the port to bind the MCP server to.

        Only used when transport is "http" or "sse".
        Default: 8000
        """
        return int(os.getenv("HYDROLIX_MCP_BIND_PORT", "8000"))

    @property
    def mcp_timeout(self) -> int:
        """Get the request timeout secunds.

        Only used when transport is "http" or "sse".
        Default: 120
        """
        return int(os.getenv("HYDROLIX_MCP_REQUEST_TIMEOUT", 120))

    @property
    def mcp_workers(self) -> int:
        """Get the number of worker processes.

        Only used when transport is "http" or "sse".
        Default: 1
        """
        return int(os.getenv("HYDROLIX_MCP_WORKERS", 1))

    @property
    def mcp_worker_connections(self) -> int:
        """Get the max number of concurrent requests per worker.

        Only used when transport is "http" or "sse".
        Default: 200
        """
        return int(os.getenv("HYDROLIX_MCP_WORKER_CONNECTIONS", 100))

    @property
    def mcp_max_requests_jitter(self) -> int:
        """Get the random parameter to randomize time process is reloaded after max_requests.

        Only used when transport is "http" or "sse".
        Default: 10000
        """
        return int(os.getenv("HYDROLIX_MCP_MAX_REQUESTS_JITTER", 1000))

    @property
    def mcp_max_requests(self) -> int:
        """Get the max number of requests handled by worker before it is restarted.

        Only used when transport is "http" or "sse".
        Default: 1000
        """
        return int(os.getenv("HYDROLIX_MCP_MAX_REQUESTS", 10000))

    @property
    def mcp_keepalive(self) -> int:
        """Get a seconds of idle keepalive connections are kept alive.

        Only used when transport is "http" or "sse".
        Default: 10
        """
        return int(os.getenv("HYDROLIX_MCP_MAX_KEEPALIVE", 10))

    def get_client_config(self, request_credential: Optional[HydrolixCredential]) -> dict:
        """
        Get the configuration dictionary for clickhouse_connect client.

        Args:
            request_credential: Optional credentials to use for this request. If not provided,
                   falls back to the default credential for this HydrolixConfig

        Returns:
            dict: Configuration ready to be passed to clickhouse_connect.get_client()

        Raises:
            ValueError: If no credentials could be inferred for the request (either from
                       the startup environment or provided in the request)
        """
        config = {
            "host": self.host,
            "port": self.port,
            "secure": self.secure,
            "verify": self.verify,
            "connect_timeout": self.connect_timeout,
            "send_receive_timeout": self.send_receive_timeout,
            "executor_threads": self.query_pool_size,
            "client_name": "mcp_hydrolix",
        }

        # Add optional database if set
        if self.database:
            config["database"] = self.database

        if self.proxy_path:
            config["proxy_path"] = self.proxy_path

        # Add credentials
        config |= self.creds_with(request_credential).clickhouse_config_entries()

        return config

    def _validate_required_vars(self) -> None:
        """Validate that all required environment variables are set. Called during __init__.

        Raises:
            ValueError: If any required environment variable is missing.
        """
        missing_vars = []
        required_vars = ["HYDROLIX_HOST"]
        for var in required_vars:
            if var not in os.environ:
                missing_vars.append(var)

        # HYDROLIX_USER and HYDROLIX_PASSWORD must either be both present or both absent
        if ("HYDROLIX_USER" in os.environ) != ("HYDROLIX_PASSWORD" in os.environ):
            raise ValueError(
                "User/password authentication is only partially configured: set both HYDROLIX_USER and HYDROLIX_PASSWORD"
            )

        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")


# Global instance placeholder for the singleton pattern
_CONFIG_INSTANCE = None


def get_config():
    """
    Gets the singleton instance of HydrolixConfig.
    Instantiates it on the first call.
    """
    global _CONFIG_INSTANCE
    if _CONFIG_INSTANCE is None:
        # Instantiate the config object here, ensuring load_dotenv() has likely run
        _CONFIG_INSTANCE = HydrolixConfig()
    return _CONFIG_INSTANCE
