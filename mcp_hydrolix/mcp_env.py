"""Environment configuration for the MCP Hydrolix server.

This module handles all environment variable configuration with sensible defaults
and type conversion.
"""

from dataclasses import dataclass
import os
from typing import Optional


@dataclass
class HydrolixConfig:
    """Configuration for Hydrolix connection settings.

    This class handles all environment variable configuration with sensible defaults
    and type conversion. It provides typed methods for accessing each configuration value.

    Required environment variables:
        HYDROLIX_HOST: The hostname of the Hydrolix server
        HYDROLIX_USER: The username for authentication
        HYDROLIX_PASSWORD: The password for authentication

    Optional environment variables (with defaults):
        HYDROLIX_PORT: The port number (default: 8088)
        HYDROLIX_VERIFY: Verify SSL certificates (default: true)
        HYDROLIX_CONNECT_TIMEOUT: Connection timeout in seconds (default: 30)
        HYDROLIX_SEND_RECEIVE_TIMEOUT: Send/receive timeout in seconds (default: 300)
        HYDROLIX_DATABASE: Default database to use (default: None)
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
    def username(self) -> str:
        """Get the Hydrolix username."""
        return os.environ["HYDROLIX_USER"]

    @property
    def password(self) -> str:
        """Get the Hydrolix password."""
        return os.environ["HYDROLIX_PASSWORD"]

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

    def get_client_config(self) -> dict:
        """Get the configuration dictionary for clickhouse_connect client.

        Returns:
            dict: Configuration ready to be passed to clickhouse_connect.get_client()
        """
        config = {
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "secure": True,
            "verify": self.verify,
            "connect_timeout": self.connect_timeout,
            "send_receive_timeout": self.send_receive_timeout,
            "client_name": "mcp_hydrolix",
        }

        # Add optional database if set
        if self.database:
            config["database"] = self.database

        return config

    def _validate_required_vars(self) -> None:
        """Validate that all required environment variables are set.

        Raises:
            ValueError: If any required environment variable is missing.
        """
        missing_vars = []
        for var in ["HYDROLIX_HOST", "HYDROLIX_USER", "HYDROLIX_PASSWORD"]:
            if var not in os.environ:
                missing_vars.append(var)

        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")


# Global instance for easy access
config = HydrolixConfig()
