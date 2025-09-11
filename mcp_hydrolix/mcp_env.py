"""Environment configuration for the MCP Hydrolix server.

This module handles all environment variable configuration with sensible defaults
and type conversion.
"""

from dataclasses import dataclass
import os
from typing import Optional
from enum import Enum


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
    """

    def __init__(self):
        """Initialize the configuration from environment variables."""
        self._validate_required_vars()

    @property
    def host(self) -> str:
        """Get the Hydrolix host."""
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
    def service_account(self) -> bool:
        """Determine if service account is enabled

        Defaults to false.
        Can be overridden if HYDROLIX_TOKEN environment variable.
        """
        return "HYDROLIX_TOKEN" in os.environ

    @property
    def service_account_token(self) -> str:
        """Get the service account token

        Defaults to None.
        Can be overridden if HYDROLIX_TOKEN environment variable.
        """
        if "HYDROLIX_TOKEN" in os.environ:
            return os.environ["HYDROLIX_TOKEN"]
        return None

    @property
    def username(self) -> str:
        """Get the Hydrolix username."""
        if "HYDROLIX_USER" in os.environ:
            return os.environ["HYDROLIX_USER"]
        return None

    @property
    def password(self) -> str:
        """Get the Hydrolix password."""
        if "HYDROLIX_PASSWORD" in os.environ:
            return os.environ["HYDROLIX_PASSWORD"]
        return None

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
    def proxy_path(self) -> str:
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

    def get_client_config(self) -> dict:
        """Get the configuration dictionary for clickhouse_connect client.

        Returns:
            dict: Configuration ready to be passed to clickhouse_connect.get_client()
        """
        config = {
            "host": self.host,
            "port": self.port,
            "secure": True,
            "verify": self.verify,
            "connect_timeout": self.connect_timeout,
            "send_receive_timeout": self.send_receive_timeout,
            "client_name": "mcp_hydrolix",
        }

        # Add optional database if set
        if self.database:
            config["database"] = self.database

        if self.proxy_path:
            config["proxy_path"] = self.proxy_path

        if self.service_account:
            config["access_token"] = self.service_account_token
        else:
            config["username"] = self.username
            config["password"] = self.password

        return config

    def _validate_required_vars(self) -> None:
        """Validate that all required environment variables are set.

        Raises:
            ValueError: If any required environment variable is missing.
        """
        missing_vars = []
        if self.service_account:
            required_vars = ["HYDROLIX_HOST", "HYDROLIX_TOKEN"]
        else:
            required_vars = ["HYDROLIX_HOST", "HYDROLIX_USER", "HYDROLIX_PASSWORD"]
        for var in required_vars:
            if var not in os.environ:
                missing_vars.append(var)

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
