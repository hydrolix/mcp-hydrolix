"""Environment configuration for the MCP Hydrolix server.

This module handles all environment variable configuration with sensible defaults
and type conversion.
"""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib.parse import ParseResult, urlparse

from mcp_hydrolix.auth.credentials import HydrolixCredential, ServiceAccountToken, UsernamePassword

logger = logging.getLogger("mcp-hydrolix")


# Mapping of deprecated env var names to their replacements.
# Transitional — will be REMOVED when the five deprecated aliases are dropped.
ALIAS_RENAMES: dict[str, str] = {
    "HYDROLIX_HOST": "HYDROLIX_HTTP_QUERY_HOST",
    "HYDROLIX_PORT": "HYDROLIX_HTTP_QUERY_PORT",
    "HYDROLIX_SECURE": "HYDROLIX_HTTP_QUERY_SECURE",
    "HYDROLIX_API_HOST": "HYDROLIX_VERSION_API_HOST",
    "HYDROLIX_API_PORT": "HYDROLIX_VERSION_API_PORT",
}
DEPRECATED_ALIASES: tuple[str, ...] = tuple(ALIAS_RENAMES.keys())


def _external_deprecation_message(aliases: list[str]) -> str:
    """Build the external-audience deprecation advisory for the given deprecated aliases."""
    return (
        f"Deprecated Hydrolix environment variable(s) detected: {', '.join(aliases)}. "
        "These will be removed in a future release. "
        "For typical external deployments, setting HYDROLIX_URL alone "
        "(e.g. HYDROLIX_URL=https://mycluster.hydrolix.live) is sufficient "
        "and replaces all of these variables."
    )


def _internal_deprecation_message(aliases: list[str]) -> str:
    """Build the internal-audience deprecation message (OLD -> NEW pairs) for the given aliases."""
    pairs = ", ".join(f"{old} -> {ALIAS_RENAMES[old]}" for old in aliases)
    return (
        f"Deprecated Hydrolix environment variable(s) detected: {pairs}. "
        "These will be removed in a future release; please migrate to the "
        "replacement variable names."
    )


# Process-level sentinels so we log each deprecation at most once.
_external_deprecation_warned: bool = False
_internal_deprecation_warned: bool = False


def _detect_deprecated_aliases() -> list[str]:
    """Return the deprecated alias env vars that are currently set, in canonical order."""
    return [name for name in DEPRECATED_ALIASES if name in os.environ]


def _classify_deprecation(aliases: list[str]) -> Optional[str]:
    """Classify deprecation audience based on HYDROLIX_NAME presence.

    Returns ``"external"``, ``"internal"``, or ``None`` if no aliases are set.
    """
    if not aliases:
        return None
    return "internal" if "HYDROLIX_NAME" in os.environ else "external"


def _parse_hydrolix_url() -> Optional[ParseResult]:
    """Parse the ``HYDROLIX_URL`` env var, returning ``None`` if unset/empty.

    Raises ``ValueError`` for a non-empty value with a missing/unsupported scheme
    or missing hostname.
    """
    raw = os.environ.get("HYDROLIX_URL")
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    parsed = urlparse(stripped)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid HYDROLIX_URL={raw!r}: scheme must be 'http' or 'https'.")
    if not parsed.hostname:
        raise ValueError(f"Invalid HYDROLIX_URL={raw!r}: missing hostname.")
    return parsed


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

    Connection target (one of these MUST be set; for ``http``/``sse`` transports
    ``HYDROLIX_URL`` specifically is required):
        HYDROLIX_URL: Canonical public URL of the Hydrolix cluster
            (e.g. ``https://mycluster.hydrolix.live``). For typical external
            deployments this single variable is sufficient to derive ``host``,
            ``port``, ``secure``, ``version_api_host``, ``version_api_port``,
            and ``version_api_secure``.
        HYDROLIX_HOST (deprecated alias): Hostname of the Hydrolix HTTP query
            endpoint. Accepted as a connection target only for stdio transport.

    Endpoint overrides (ClickHouse HTTP query endpoint):
        HYDROLIX_HTTP_QUERY_HOST: Override the query hostname
            (precedence: this > HYDROLIX_HOST > URL hostname).
        HYDROLIX_HTTP_QUERY_PORT: Override the query port
            (precedence: this > HYDROLIX_PORT > URL scheme default > 8088).
        HYDROLIX_HTTP_QUERY_SECURE: Override the query TLS flag
            (precedence: this > HYDROLIX_SECURE > URL scheme == "https" > True).

    Endpoint overrides (REST ``/version`` probe):
        HYDROLIX_VERSION_API_HOST: Override the version-api hostname
            (precedence: this > HYDROLIX_API_HOST > URL hostname > resolved host).
        HYDROLIX_VERSION_API_PORT: Override the version-api port
            (precedence: this > HYDROLIX_API_PORT > URL scheme default >
            443 if secure else 80).
        HYDROLIX_VERSION_API_SECURE: Override the version-api TLS flag
            (precedence: this > resolved ``secure``).

    Deprecated environment variables (still honored during the transition window):
        HYDROLIX_HOST, HYDROLIX_PORT, HYDROLIX_SECURE,
        HYDROLIX_API_HOST, HYDROLIX_API_PORT

    Optional environment variables (with defaults):
        HYDROLIX_TOKEN: Service account token to the Hydrolix Server (this or user+password is required)
        HYDROLIX_USER: The username for authentication (this or token is required)
        HYDROLIX_PASSWORD: The password for authentication (this or token is required)
        HYDROLIX_PORT (deprecated): The port number (default: 8088). Prefer HYDROLIX_HTTP_QUERY_PORT.
        HYDROLIX_VERIFY: Verify SSL certificates (default: true)
        HYDROLIX_CONNECT_TIMEOUT: Connection timeout in seconds (default: 30)
        HYDROLIX_SEND_RECEIVE_TIMEOUT: Send/receive timeout in seconds (default: 300)
        HYDROLIX_DATABASE: Default database to use (default: None)
        HYDROLIX_MCP_SERVER_TRANSPORT: MCP server transport method - "stdio", "http", or "sse" (default: stdio)
        HYDROLIX_MCP_BIND_HOST: Host to bind the MCP server to when using HTTP or SSE transport (default: 127.0.0.1)
        HYDROLIX_MCP_BIND_PORT: Port to bind the MCP server to when using HTTP or SSE transport (default: 8000)
        HYDROLIX_QUERIES_POOL_SIZE 100
        HYDROLIX_MCP_REQUEST_TIMEOUT 120
        HYDROLIX_MCP_WORKERS 1
        HYDROLIX_MCP_WORKER_CONNECTIONS 200
        HYDROLIX_MCP_MAX_REQUESTS 10000
        HYDROLIX_MCP_MAX_REQUESTS_JITTER 1000
        HYDROLIX_MCP_MAX_KEEPALIVE 10
        HYDROLIX_MAX_RESULT_CELLS: Maximum number of cells (rows × columns) to return in a
            query result before truncating (default: 50000)
        HYDROLIX_MAX_RESULT_CELLS_LIMIT: Hard upper bound on max_cells that callers may request.
            0 means no limit is enforced (default: 0). Set this in multi-tenant HTTP/SSE
            deployments to prevent a single session from materialising very large result sets.
        HYDROLIX_MAX_RAW_TIMERANGE: Max timerange in seconds for non-summary queries (default: 21600 = 6 hours)
    """

    def __init__(self) -> None:
        """Initialize the configuration from environment variables."""
        # Parse HYDROLIX_URL eagerly so validation errors surface at construction time.
        self._parsed_url: Optional[ParseResult] = _parse_hydrolix_url()
        self._validate_required_vars()

        # Snapshot deprecation state once so the LLM-visible notice and the
        # version-gated internal probe log agree on what was seen at startup.
        self._deprecated_aliases: list[str] = _detect_deprecated_aliases()
        self._deprecation_audience: Optional[str] = _classify_deprecation(self._deprecated_aliases)
        # Format the external advisory once; both the startup log and the
        # deprecation_notice property read this cached value.
        self._deprecation_notice: Optional[str] = (
            _external_deprecation_message(self._deprecated_aliases)
            if self._deprecation_audience == "external"
            else None
        )

        global _external_deprecation_warned
        if self._deprecation_notice is not None and not _external_deprecation_warned:
            logger.warning(self._deprecation_notice)
            _external_deprecation_warned = True

        # Credential to use for clickhouse connections when no per-request credential is provided
        self._default_credential: Optional[HydrolixCredential] = None

        # Set the default credential to the service account from the environment, if available.
        # Both token and username are stripped and checked for non-empty so that
        # MCPB hosts injecting blank user_config fields (as empty strings) do not produce
        # bogus credentials.
        if global_service_account := os.getenv("HYDROLIX_TOKEN", "").strip():
            self._default_credential = ServiceAccountToken(global_service_account, None)
        else:
            if (global_username := os.getenv("HYDROLIX_USER", "").strip()) and (
                global_password := os.getenv("HYDROLIX_PASSWORD", "")
            ):
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
        """Get the Hydrolix HTTP query host.

        Precedence: HYDROLIX_HTTP_QUERY_HOST > HYDROLIX_HOST (deprecated) > URL hostname.
        """
        if value := os.getenv("HYDROLIX_HTTP_QUERY_HOST"):
            return value
        if value := os.getenv("HYDROLIX_HOST"):
            return value
        if self._parsed_url is not None and self._parsed_url.hostname:
            return self._parsed_url.hostname
        # Unreachable: _validate_required_vars guarantees a connection target.
        raise ValueError("No Hydrolix host configured (set HYDROLIX_URL).")

    @property
    def port(self) -> int:
        """Get the Hydrolix HTTP query port.

        Precedence: HYDROLIX_HTTP_QUERY_PORT > HYDROLIX_PORT (deprecated) >
        URL-derived (443 https / 80 http) > hard default 8088.
        """
        if raw := os.getenv("HYDROLIX_HTTP_QUERY_PORT"):
            return int(raw)
        if raw := os.getenv("HYDROLIX_PORT"):
            return int(raw)
        if self._parsed_url is not None:
            return 443 if self._parsed_url.scheme == "https" else 80
        return 8088

    @property
    def secure(self) -> bool:
        """Get whether to use a secured (TLS) connection for the HTTP query endpoint.

        Precedence: HYDROLIX_HTTP_QUERY_SECURE > HYDROLIX_SECURE (deprecated) >
        URL scheme == "https" > hard default True.
        """
        if (raw := os.getenv("HYDROLIX_HTTP_QUERY_SECURE")) is not None:
            return raw.lower() == "true"
        if (raw := os.getenv("HYDROLIX_SECURE")) is not None:
            return raw.lower() == "true"
        if self._parsed_url is not None:
            return self._parsed_url.scheme == "https"
        return True

    @property
    def version_api_host(self) -> str:
        """Get the hostname of the Hydrolix REST ``/version`` probe endpoint.

        Precedence: HYDROLIX_VERSION_API_HOST > HYDROLIX_API_HOST (deprecated) >
        URL hostname > resolved ``host``.
        """
        if value := os.getenv("HYDROLIX_VERSION_API_HOST"):
            return value
        if value := os.getenv("HYDROLIX_API_HOST"):
            return value
        if self._parsed_url is not None and self._parsed_url.hostname:
            return self._parsed_url.hostname
        return self.host

    @property
    def version_api_port(self) -> int:
        """Get the port of the Hydrolix REST ``/version`` probe endpoint.

        Precedence: HYDROLIX_VERSION_API_PORT > HYDROLIX_API_PORT (deprecated) >
        URL-derived (443/80 by scheme) > ``443`` if secure else ``80``.
        """
        if raw := os.getenv("HYDROLIX_VERSION_API_PORT"):
            return int(raw)
        if raw := os.getenv("HYDROLIX_API_PORT"):
            return int(raw)
        if self._parsed_url is not None:
            return 443 if self._parsed_url.scheme == "https" else 80
        return 443 if self.secure else 80

    @property
    def version_api_secure(self) -> bool:
        """Get whether to use TLS for the ``/version`` probe endpoint.

        Precedence: HYDROLIX_VERSION_API_SECURE > resolved ``secure``.
        Note: this inherits from the *resolved* ``secure`` value (which already
        respects HYDROLIX_HTTP_QUERY_SECURE / HYDROLIX_SECURE / URL scheme), not
        the URL scheme directly.
        """
        if (raw := os.getenv("HYDROLIX_VERSION_API_SECURE")) is not None:
            return raw.lower() == "true"
        return self.secure

    @property
    def deprecated_aliases(self) -> list[str]:
        """Deprecated alias env var names that were set at construction time."""
        return list(self._deprecated_aliases)

    @property
    def deprecation_audience(self) -> Optional[str]:
        """``"external"``, ``"internal"``, or ``None`` -- determined at construction time."""
        return self._deprecation_audience

    @property
    def deprecation_notice(self) -> Optional[str]:
        """LLM-visible deprecation advisory string, or ``None``.

        Returns a non-empty message only for the ``"external"`` audience. Internal
        operators are notified via the version-gated probe log, not via the MCP
        ``instructions`` channel.
        """
        return self._deprecation_notice

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
    def query_pool_size(self) -> int:
        """Get the query executor thread pool size.

        Default: 100
        """
        return int(os.getenv("HYDROLIX_QUERIES_POOL_SIZE", 100))

    @property
    def query_timeout_sec(self) -> int:
        """Get the per-query execution timeout in seconds.

        Default: 30
        """
        return int(os.getenv("HYDROLIX_QUERY_TIMEOUT_SECS", 30))

    @property
    def max_result_cells(self) -> int:
        """Get the default cell budget (rows × columns) for query result truncation.

        Configured via HYDROLIX_MAX_RESULT_CELLS (default: 50000).
        """
        return int(os.getenv("HYDROLIX_MAX_RESULT_CELLS", "50000"))

    @property
    def max_result_cells_limit(self) -> int:
        """Get the hard upper bound on the max_cells value callers may request.

        When > 0, any per-call max_cells value above this limit is capped to this
        value, preventing callers from requesting unbounded result sets.

        Configured via HYDROLIX_MAX_RESULT_CELLS_LIMIT (default: 0, no cap enforced).
        Set to a positive integer to enforce a cap in multi-tenant HTTP/SSE deployments.
        """
        return int(os.getenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT", "0"))

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
        """Get the request timeout seconds.

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
        Default: 100
        """
        return int(os.getenv("HYDROLIX_MCP_WORKER_CONNECTIONS", 100))

    @property
    def max_raw_timerange(self) -> int:
        """Get the max timerange in seconds for non-summary queries.

        Default: 21600 (6 hours)
        """
        return int(os.getenv("HYDROLIX_MAX_RAW_TIMERANGE", "21600"))

    @property
    def mcp_graceful_timeout(self) -> int:
        """Get the seconds to wait for in-flight requests during shutdown.

        Only used when transport is "http" or "sse".
        Default: same as mcp_timeout
        """
        return int(os.getenv("HYDROLIX_MCP_GRACEFUL_TIMEOUT", self.mcp_timeout))

    @property
    def mcp_max_requests(self) -> int:
        """Max HTTP requests a worker serves before being gracefully recycled.

        Wired into uvicorn's ``limit_max_requests`` setting
        (https://www.uvicorn.org/settings/#resource-limits), which parallels
        gunicorn's ``max_requests``. Only effective when transport is "http"
        or "sse" AND mcp_workers > 1 — single-worker mode has no supervisor
        to respawn the process, so ``main.py`` passes ``None`` to uvicorn in
        that case.

        Set to 0 to disable. Default: 10000.
        """
        return int(os.getenv("HYDROLIX_MCP_MAX_REQUESTS", 10000))

    @property
    def mcp_max_requests_jitter(self) -> int:
        """Random jitter added to ``mcp_max_requests`` per worker.

        Wired into uvicorn's ``limit_max_requests_jitter`` setting, which
        parallels gunicorn's ``max_requests_jitter``. Prevents all workers
        from recycling simultaneously (thundering herd). Default: 1000.
        """
        return int(os.getenv("HYDROLIX_MCP_MAX_REQUESTS_JITTER", 1000))

    @property
    def mcp_keepalive(self) -> int:
        """Get a seconds of idle keepalive connections are kept alive.

        Only used when transport is "http" or "sse".
        Default: 10
        """
        return int(os.getenv("HYDROLIX_MCP_MAX_KEEPALIVE", 10))

    @property
    def mcp_worker_healthcheck_timeout(self) -> int:
        """Seconds the supervisor waits for a worker ping response before killing it.

        Wired into uvicorn's ``timeout_worker_healthcheck`` setting. The default
        of 5s is too tight for cold-start module imports under CPU pressure; 15s
        gives workers headroom without masking genuinely hung processes.

        Default: 15
        """
        return int(os.getenv("HYDROLIX_MCP_WORKER_HEALTHCHECK_TIMEOUT", 15))

    @property
    def metrics_enabled(self) -> bool:
        """Get whether Prometheus metrics are enabled.

        Default: False
        """
        return os.getenv("HYDROLIX_METRICS_ENABLED", "false").lower() == "true"

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
            # clickhouse-connect's default tz_mode ("naive_utc") is broken
            # for zoneless DateTime columns: it strips tzinfo when the server
            # is UTC, and silently falls back to the *client's* local timezone
            # when it can't detect the server's. "aware" forces every
            # datetime to carry explicit tzinfo (column tz if set, else the
            # server's), eliminating the ambiguity and matching the behavior of
            # the `clickhouse client` CLI
            "tz_mode": "aware",
        }

        # Add optional database if set
        if self.database:
            config["database"] = self.database

        # Add credentials
        config |= self.creds_with(request_credential).clickhouse_config_entries()

        return config

    def _validate_required_vars(self) -> None:
        """Validate that all required environment variables are set. Called during __init__.

        Raises:
            ValueError: If any required environment variable is missing.
        """
        # HYDROLIX_USER and HYDROLIX_PASSWORD must either be both present or both absent
        if ("HYDROLIX_USER" in os.environ) != ("HYDROLIX_PASSWORD" in os.environ):
            raise ValueError(
                "User/password authentication is only partially configured: set both HYDROLIX_USER and HYDROLIX_PASSWORD"
            )

        # http/sse transports surface the cluster URL in OAuth metadata, so
        # HYDROLIX_URL specifically (not HYDROLIX_HOST) is required for those.
        transport = os.getenv("HYDROLIX_MCP_SERVER_TRANSPORT", TransportType.STDIO.value).lower()
        if transport in (TransportType.HTTP.value, TransportType.SSE.value):
            if self._parsed_url is None:
                raise ValueError(
                    "HYDROLIX_URL is required when HYDROLIX_MCP_SERVER_TRANSPORT is "
                    f"{transport!r}. Set HYDROLIX_URL=https://<your-cluster-host>."
                )
        else:
            # All other transports: a connection target is required. The deprecated
            # HYDROLIX_HOST is still honored as a target, but we never recommend it --
            # the error points operators only at HYDROLIX_URL. HYDROLIX_HTTP_QUERY_HOST
            # is an override on top of the connection target and is never sufficient alone.
            if self._parsed_url is None and "HYDROLIX_HOST" not in os.environ:
                raise ValueError(
                    "Missing Hydrolix connection target: set HYDROLIX_URL "
                    "(e.g. https://mycluster.hydrolix.live)."
                )

        # Validate HYDROLIX_MAX_RESULT_CELLS: must be a positive integer if set.
        raw_cells = os.getenv("HYDROLIX_MAX_RESULT_CELLS")
        if raw_cells is not None:
            try:
                val = int(raw_cells)
                if val <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError(
                    f"Invalid HYDROLIX_MAX_RESULT_CELLS={raw_cells!r}: "
                    "must be a positive integer (e.g. 50000)."
                )

        # Validate HYDROLIX_MAX_RESULT_CELLS_LIMIT: must be a non-negative integer if set.
        raw_limit = os.getenv("HYDROLIX_MAX_RESULT_CELLS_LIMIT")
        if raw_limit is not None:
            try:
                val = int(raw_limit)
                if val < 0:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError(
                    f"Invalid HYDROLIX_MAX_RESULT_CELLS_LIMIT={raw_limit!r}: "
                    "must be a non-negative integer (0 means no cap)."
                )


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
