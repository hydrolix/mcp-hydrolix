"""Tests for ``mcp_hydrolix.mcp_env.HydrolixConfig`` configuration properties.

Focused on changes introduced for the gunicorn -> uvicorn migration:
  * the ``mcp_graceful_timeout`` property exists, defaults to ``mcp_timeout``,
    and can be overridden by ``HYDROLIX_MCP_GRACEFUL_TIMEOUT``
  * the worker-recycling knobs ``mcp_max_requests`` and ``mcp_max_requests_jitter``
    are preserved (now backed by ``MaxRequestsMiddleware`` instead of gunicorn)
"""

from __future__ import annotations

import os

import pytest

from mcp_hydrolix import mcp_env
from mcp_hydrolix.auth.credentials import ServiceAccountToken, UsernamePassword
from mcp_hydrolix.mcp_env import HydrolixConfig


@pytest.fixture(autouse=True)
def _isolate_hydrolix_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear every ``HYDROLIX_*`` env var so each test starts from a clean slate."""
    for key in list(os.environ):
        if key.startswith("HYDROLIX_"):
            monkeypatch.delenv(key, raising=False)
    # setattr so pytest restores these process-global sentinels on teardown.
    monkeypatch.setattr(mcp_env, "_external_deprecation_warned", False)
    monkeypatch.setattr(mcp_env, "_internal_deprecation_warned", False)


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> HydrolixConfig:
    """Return a fresh ``HydrolixConfig`` with the minimal required env vars set."""

    monkeypatch.setenv("HYDROLIX_URL", "https://example.invalid")
    return HydrolixConfig()


class TestGracefulTimeout:
    def test_default_matches_mcp_timeout(self, config: HydrolixConfig) -> None:
        assert config.mcp_graceful_timeout == config.mcp_timeout

    def test_default_follows_mcp_timeout_override(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HYDROLIX_MCP_REQUEST_TIMEOUT", "42")
        assert config.mcp_graceful_timeout == 42

    def test_explicit_override(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HYDROLIX_MCP_REQUEST_TIMEOUT", "42")
        monkeypatch.setenv("HYDROLIX_MCP_GRACEFUL_TIMEOUT", "7")
        assert config.mcp_graceful_timeout == 7


class TestMaxRequestsRecycling:
    def test_mcp_max_requests_default(self, config: HydrolixConfig) -> None:
        assert config.mcp_max_requests == 10000

    def test_mcp_max_requests_jitter_default(self, config: HydrolixConfig) -> None:
        assert config.mcp_max_requests_jitter == 1000

    def test_mcp_max_requests_override(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HYDROLIX_MCP_MAX_REQUESTS", "500")
        assert config.mcp_max_requests == 500

    def test_mcp_max_requests_jitter_override(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HYDROLIX_MCP_MAX_REQUESTS_JITTER", "50")
        assert config.mcp_max_requests_jitter == 50

    def test_mcp_max_requests_disabled_with_zero(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HYDROLIX_MCP_MAX_REQUESTS", "0")
        assert config.mcp_max_requests == 0


class TestExecuteQuerySettings:
    """The execute_query SETTINGS exposed as env vars (HDX-11673)."""

    def test_timerange_required_default(self, config: HydrolixConfig) -> None:
        assert config.query_timerange_required is True

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("false", False), ("FALSE", False), ("true", True), ("True", True)],
    )
    def test_timerange_required_override(
        self,
        config: HydrolixConfig,
        monkeypatch: pytest.MonkeyPatch,
        raw: str,
        expected: bool,
    ) -> None:
        monkeypatch.setenv("HYDROLIX_QUERY_TIMERANGE_REQUIRED", raw)
        assert config.query_timerange_required is expected

    def test_max_memory_usage_default(self, config: HydrolixConfig) -> None:
        assert config.query_max_memory_usage == 2 * 1024 * 1024 * 1024

    def test_max_memory_usage_override(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HYDROLIX_QUERY_MAX_MEMORY_USAGE", "1073741824")
        assert config.query_max_memory_usage == 1073741824

    def test_max_attempts_default(self, config: HydrolixConfig) -> None:
        assert config.query_max_attempts == 1

    def test_max_attempts_override(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HYDROLIX_QUERY_MAX_ATTEMPTS", "3")
        assert config.query_max_attempts == 3

    def test_max_result_rows_default(self, config: HydrolixConfig) -> None:
        assert config.query_max_result_rows == 100000

    def test_max_result_rows_override(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HYDROLIX_QUERY_MAX_RESULT_ROWS", "250")
        assert config.query_max_result_rows == 250

    @pytest.mark.parametrize(
        "var",
        [
            "HYDROLIX_QUERY_MAX_MEMORY_USAGE",
            "HYDROLIX_QUERY_MAX_ATTEMPTS",
            "HYDROLIX_QUERY_MAX_RESULT_ROWS",
        ],
    )
    @pytest.mark.parametrize("bad", ["0", "-1", "notanint"])
    def test_positive_int_validation_rejects_bad_values(
        self, monkeypatch: pytest.MonkeyPatch, var: str, bad: str
    ) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://example.invalid")
        monkeypatch.setenv(var, bad)
        with pytest.raises(ValueError, match=var):
            HydrolixConfig()


class TestQueryPool:
    """HYDROLIX_QUERY_POOL resolution.

    None when unset (cluster default), the literal value when set, and -- the
    edge case worth guarding -- None when MCPB injects a blank/whitespace value,
    so an empty pool name is never sent to the cluster.
    """

    def test_default_is_none(self, config: HydrolixConfig) -> None:
        assert config.query_pool is None

    def test_explicit_value(self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_QUERY_POOL", "high-capacity")
        assert config.query_pool == "high-capacity"

    @pytest.mark.parametrize("blank", ["", "   ", "\t\n"], ids=["empty", "spaces", "ws"])
    def test_blank_treated_as_unset(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch, blank: str
    ) -> None:
        monkeypatch.setenv("HYDROLIX_QUERY_POOL", blank)
        assert config.query_pool is None

    def test_surrounding_whitespace_stripped(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HYDROLIX_QUERY_POOL", "  analytics-pool  ")
        assert config.query_pool == "analytics-pool"


class TestQueryHeadPool:
    """HYDROLIX_QUERY_HEAD_POOL resolution and its effect on the connection's
    default database (the ?database= routing key).

    The property itself mirrors query_pool (None/value/blank/whitespace). The
    routing tests exercise get_client_config, where the head pool -- when set --
    drives the ``database`` slot.
    """

    def test_default_is_none(self, config: HydrolixConfig) -> None:
        assert config.query_head_pool is None

    def test_explicit_value(self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_QUERY_HEAD_POOL", "logs")
        assert config.query_head_pool == "logs"

    @pytest.mark.parametrize("blank", ["", "   ", "\t\n"], ids=["empty", "spaces", "ws"])
    def test_blank_treated_as_unset(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch, blank: str
    ) -> None:
        monkeypatch.setenv("HYDROLIX_QUERY_HEAD_POOL", blank)
        assert config.query_head_pool is None

    def test_surrounding_whitespace_stripped(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HYDROLIX_QUERY_HEAD_POOL", "  logs  ")
        assert config.query_head_pool == "logs"

    @staticmethod
    def _client_config(monkeypatch: pytest.MonkeyPatch) -> dict:
        """Build a token-authed config from the current env and return its client config.

        A credential must exist at construction time, so set HYDROLIX_TOKEN before
        constructing. query_head_pool is read lazily inside get_client_config,
        so env set here is honored.
        """
        monkeypatch.setenv("HYDROLIX_URL", "https://example.invalid")
        monkeypatch.setenv("HYDROLIX_TOKEN", _TEST_JWT)
        return HydrolixConfig().get_client_config(request_credential=None)

    def test_head_pool_sets_connection_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_QUERY_HEAD_POOL", "logs")
        assert self._client_config(monkeypatch)["database"] == "logs"

    def test_blank_head_pool_leaves_database_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A blank head pool (the MCPB empty-field case) is unset, so no routing key
        is sent and the connection carries no default database."""
        monkeypatch.setenv("HYDROLIX_QUERY_HEAD_POOL", "   ")
        assert "database" not in self._client_config(monkeypatch)

    def test_database_absent_when_head_pool_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert "database" not in self._client_config(monkeypatch)


# A long-lived JWT (expires 2094) used to exercise ServiceAccountToken credential resolution.
# Signature verification is disabled in ServiceAccountToken.__init__, so only the structure
# and claims matter.
_TEST_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJzYS10ZXN0IiwiaXNzIjoiaHlkcm9saXgiLCJpYXQiOjE3Nzg2OTAwMzAsImV4cCI6MjA5NDA1MDAzMH0"
    ".6gNTaDM27jvFyrhPV--508_URToB2eql7c_SUVv_zog"
)


class TestCredentialResolution:
    """Verify that HydrolixConfig resolves HYDROLIX_TOKEN / HYDROLIX_USER / HYDROLIX_PASSWORD
    correctly, including when MCPB injects blank user_config fields as empty strings.
    """

    @pytest.fixture(autouse=True)
    def _base_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://example.invalid")
        monkeypatch.delenv("HYDROLIX_TOKEN", raising=False)
        monkeypatch.delenv("HYDROLIX_USER", raising=False)
        monkeypatch.delenv("HYDROLIX_PASSWORD", raising=False)

    def test_token_wins_when_user_password_blank(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_TOKEN", _TEST_JWT)
        monkeypatch.setenv("HYDROLIX_USER", "")
        monkeypatch.setenv("HYDROLIX_PASSWORD", "")
        cred = HydrolixConfig().creds_with(None)
        assert isinstance(cred, ServiceAccountToken)
        assert cred.token == _TEST_JWT

    @pytest.mark.parametrize("token", ["", None], ids=["blank-token", "unset-token"])
    def test_user_password_used_when_no_token(
        self, monkeypatch: pytest.MonkeyPatch, token: str | None
    ) -> None:
        if token is not None:
            monkeypatch.setenv("HYDROLIX_TOKEN", token)
        monkeypatch.setenv("HYDROLIX_USER", "alice")
        monkeypatch.setenv("HYDROLIX_PASSWORD", "hunter2")
        cred = HydrolixConfig().creds_with(None)
        assert isinstance(cred, UsernamePassword)
        assert cred.username == "alice"
        assert cred.password == "hunter2"

    @pytest.mark.parametrize(
        "user, password",
        [("alice", ""), ("", "hunter2"), ("", "")],
        ids=["blank-password", "blank-username", "both-blank"],
    )
    def test_partial_credentials_raise(
        self, monkeypatch: pytest.MonkeyPatch, user: str, password: str
    ) -> None:
        monkeypatch.setenv("HYDROLIX_USER", user)
        monkeypatch.setenv("HYDROLIX_PASSWORD", password)
        with pytest.raises(ValueError, match="No credentials available"):
            HydrolixConfig().creds_with(None)

    def test_no_credentials_when_all_unset(self) -> None:
        with pytest.raises(ValueError, match="No credentials available"):
            HydrolixConfig().creds_with(None)


class TestHydrolixUrlParsing:
    """HYDROLIX_URL parsing and validation at HydrolixConfig.__init__."""

    def test_valid_https_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://mycluster.hydrolix.live")
        c = HydrolixConfig()
        assert c._parsed_url is not None
        assert c._parsed_url.hostname == "mycluster.hydrolix.live"
        assert c._parsed_url.scheme == "https"

    def test_valid_http_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "http://dev-cluster.internal")
        c = HydrolixConfig()
        assert c._parsed_url is not None
        assert c._parsed_url.hostname == "dev-cluster.internal"
        assert c._parsed_url.scheme == "http"

    def test_ipv6_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://[::1]")
        c = HydrolixConfig()
        assert c._parsed_url is not None
        assert c._parsed_url.hostname == "::1"

    def test_userinfo_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://user:pass@mycluster.hydrolix.live")
        c = HydrolixConfig()
        assert c._parsed_url is not None
        assert c._parsed_url.hostname == "mycluster.hydrolix.live"

    def test_trailing_slash_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://mycluster.hydrolix.live/")
        HydrolixConfig()  # no raise

    def test_empty_path_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://mycluster.hydrolix.live")
        HydrolixConfig()

    def test_explicit_port_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # URL port is intentionally ignored for derivation.
        monkeypatch.setenv("HYDROLIX_URL", "https://mycluster.hydrolix.live:9443")
        c = HydrolixConfig()
        assert c.port == 443  # scheme-default, not 9443

    def test_missing_scheme_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "mycluster.hydrolix.live")
        with pytest.raises(ValueError):
            HydrolixConfig()

    def test_unsupported_scheme_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "ftp://mycluster.hydrolix.live")
        with pytest.raises(ValueError):
            HydrolixConfig()

    def test_no_hostname_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://")
        with pytest.raises(ValueError):
            HydrolixConfig()

    def test_empty_after_strip_treated_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "   ")
        monkeypatch.setenv("HYDROLIX_HOST", "fallback.invalid")
        c = HydrolixConfig()
        assert c._parsed_url is None
        assert c.host == "fallback.invalid"


class TestExternalSufficiency:
    """HYDROLIX_URL alone is sufficient for all six derived properties."""

    def test_url_alone_resolves_all_six(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        c = HydrolixConfig()
        assert c.host == "cluster.example.com"
        assert c.port == 443
        assert c.secure is True
        assert c.version_api_host == "cluster.example.com"
        assert c.version_api_port == 443
        assert c.version_api_secure is True
        assert c.query_path == "/query"

    def test_url_alone_http_scheme(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "http://cluster.example.com")
        c = HydrolixConfig()
        assert c.port == 80
        assert c.secure is False
        assert c.version_api_port == 80
        assert c.version_api_secure is False

    def test_split_ports(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_PORT", "8088")
        monkeypatch.setenv("HYDROLIX_VERSION_API_PORT", "9090")
        c = HydrolixConfig()
        assert c.host == "cluster.example.com"
        assert c.port == 8088
        assert c.version_api_port == 9090
        assert c.version_api_secure is True


class TestHostPrecedence:
    def test_url_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        assert HydrolixConfig().host == "cluster.example.com"

    def test_alias_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "myhost.example.com")
        assert HydrolixConfig().host == "myhost.example.com"

    def test_new_var_wins_over_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_HOST", "turbine-query")
        monkeypatch.setenv("HYDROLIX_HOST", "myhost.example.com")
        assert HydrolixConfig().host == "turbine-query"

    def test_new_var_wins_over_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_HOST", "turbine-query")
        assert HydrolixConfig().host == "turbine-query"

    def test_alias_wins_over_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HOST", "override.example.com")
        assert HydrolixConfig().host == "override.example.com"


class TestPortPrecedence:
    def test_url_https_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        assert HydrolixConfig().port == 443

    def test_url_http_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "http://cluster.example.com")
        assert HydrolixConfig().port == 80

    def test_hard_default_no_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "myhost")
        assert HydrolixConfig().port == 8088

    def test_new_var_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_PORT", "8088")
        assert HydrolixConfig().port == 8088

    def test_alias_wins_over_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_PORT", "9000")
        assert HydrolixConfig().port == 9000

    def test_new_wins_over_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "myhost")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_PORT", "8088")
        monkeypatch.setenv("HYDROLIX_PORT", "9000")
        assert HydrolixConfig().port == 8088


class TestSecurePrecedence:
    def test_url_https(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        assert HydrolixConfig().secure is True

    def test_url_http(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "http://cluster.example.com")
        assert HydrolixConfig().secure is False

    def test_hard_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "myhost")
        assert HydrolixConfig().secure is True

    def test_new_var_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_SECURE", "false")
        assert HydrolixConfig().secure is False

    def test_alias_wins_over_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_SECURE", "false")
        assert HydrolixConfig().secure is False


class TestQueryPath:
    def test_default_is_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        assert HydrolixConfig().query_path == "/query"

    def test_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_PATH", "/custom/query")
        assert HydrolixConfig().query_path == "/custom/query"

    def test_override_to_root(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_PATH", "/")
        assert HydrolixConfig().query_path == "/"

    def test_override_to_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Empty string is an explicit override (falls back to the default only
        # when the var is unset), letting root-path targets opt out of "/query".
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_PATH", "")
        assert HydrolixConfig().query_path == ""

    def test_included_in_client_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_USER", "u")
        monkeypatch.setenv("HYDROLIX_PASSWORD", "p")
        cfg = HydrolixConfig().get_client_config(None)
        assert cfg["proxy_path"] == "/query"

    def test_client_config_reflects_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_USER", "u")
        monkeypatch.setenv("HYDROLIX_PASSWORD", "p")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_PATH", "/query-head")
        cfg = HydrolixConfig().get_client_config(None)
        assert cfg["proxy_path"] == "/query-head"

    def test_deprecated_alias_honored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A pre-#133 config using HYDROLIX_PROXY_PATH still works.
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_PROXY_PATH", "/legacy")
        assert HydrolixConfig().query_path == "/legacy"

    def test_new_var_wins_over_deprecated_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_PATH", "/query")
        monkeypatch.setenv("HYDROLIX_PROXY_PATH", "/legacy")
        assert HydrolixConfig().query_path == "/query"

    def test_deprecated_alias_empty_is_honored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Empty string is an explicit value for the alias too (root path).
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_PROXY_PATH", "")
        assert HydrolixConfig().query_path == ""


class TestVersionApiHostAndPort:
    def test_inherits_from_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        c = HydrolixConfig()
        assert c.version_api_host == "cluster.example.com"
        assert c.version_api_port == 443

    def test_falls_back_to_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "myhost")
        c = HydrolixConfig()
        assert c.version_api_host == "myhost"

    def test_new_var_host_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_VERSION_API_HOST", "version")
        assert HydrolixConfig().version_api_host == "version"

    def test_alias_host_wins_over_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_API_HOST", "version")
        assert HydrolixConfig().version_api_host == "version"

    def test_new_var_port_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_VERSION_API_PORT", "23925")
        assert HydrolixConfig().version_api_port == 23925

    def test_alias_port_wins_over_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_API_PORT", "23925")
        assert HydrolixConfig().version_api_port == 23925


class TestVersionApiSecure:
    def test_inherits_url_https(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        assert HydrolixConfig().version_api_secure is True

    def test_inherits_http_query_secure_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_SECURE", "false")
        assert HydrolixConfig().version_api_secure is False

    def test_explicit_diverges_from_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_SECURE", "false")
        monkeypatch.setenv("HYDROLIX_VERSION_API_SECURE", "true")
        c = HydrolixConfig()
        assert c.secure is False
        assert c.version_api_secure is True

    def test_inherits_via_deprecated_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "host")
        monkeypatch.setenv("HYDROLIX_SECURE", "false")
        assert HydrolixConfig().version_api_secure is False


class TestBackwardsCompatibility:
    def test_host_alone_preserves_pre_change_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "myhost.example.com")
        c = HydrolixConfig()
        assert c.host == "myhost.example.com"
        assert c.port == 8088
        assert c.secure is True
        assert c.version_api_host == "myhost.example.com"
        assert c.version_api_port == 443
        assert c.version_api_secure is True


class TestInClusterShapes:
    """Sanity checks for the two o6r-emitted env-var shapes."""

    def test_post_migration_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_HOST", "turbine-query")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_PORT", "8088")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_SECURE", "false")
        monkeypatch.setenv("HYDROLIX_VERSION_API_HOST", "version")
        monkeypatch.setenv("HYDROLIX_VERSION_API_PORT", "23925")
        c = HydrolixConfig()
        assert c.host == "turbine-query"
        assert c.port == 8088
        assert c.secure is False
        assert c.version_api_host == "version"
        assert c.version_api_port == 23925
        assert c.version_api_secure is False

    def test_transition_shape_with_aliases(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HOST", "turbine-query")
        monkeypatch.setenv("HYDROLIX_PORT", "8088")
        monkeypatch.setenv("HYDROLIX_SECURE", "false")
        monkeypatch.setenv("HYDROLIX_API_HOST", "version")
        monkeypatch.setenv("HYDROLIX_API_PORT", "23925")
        c = HydrolixConfig()
        assert c.host == "turbine-query"
        assert c.port == 8088
        assert c.secure is False
        assert c.version_api_host == "version"
        assert c.version_api_port == 23925
        assert c.version_api_secure is False


class TestConnectionTargetValidation:
    def test_no_connection_target_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(ValueError, match="HYDROLIX_URL") as exc_info:
            HydrolixConfig()
        # Never recommend the deprecated HYDROLIX_HOST in the guidance.
        assert "HYDROLIX_HOST" not in str(exc_info.value)

    def test_only_http_query_host_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # HTTP_QUERY_HOST is an override, never a standalone connection target.
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_HOST", "turbine-query")
        with pytest.raises(ValueError):
            HydrolixConfig()

    def test_url_required_for_http_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_MCP_SERVER_TRANSPORT", "http")
        monkeypatch.setenv("HYDROLIX_HOST", "myhost")
        with pytest.raises(ValueError, match="HYDROLIX_URL"):
            HydrolixConfig()

    def test_url_required_for_sse_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_MCP_SERVER_TRANSPORT", "sse")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_HOST", "myhost")
        with pytest.raises(ValueError, match="HYDROLIX_URL"):
            HydrolixConfig()

    def test_stdio_transport_accepts_host_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_MCP_SERVER_TRANSPORT", "stdio")
        monkeypatch.setenv("HYDROLIX_HOST", "myhost")
        HydrolixConfig()  # no raise


class TestProxyPoolKwargs:
    """``proxy_pool_kwargs()`` resolves the outbound proxy for the shared urllib3 pool.

    Because mcp-hydrolix passes clickhouse-connect a pre-built ``pool_mgr``,
    clickhouse-connect's own env-proxy detection is skipped and urllib3 does not
    read proxy env vars. This method is the explicit, HYDROLIX-namespaced hook
    that lets a proxy-bound deployment route the connection. It feeds a single
    proxy into ``get_pool_manager`` (which raises ``ProgrammingError`` if both
    ``http_proxy`` and ``https_proxy`` are passed), so at most one key is emitted.
    """

    def test_no_proxy_returns_empty(self, config: HydrolixConfig) -> None:
        # Default: no proxy configured -> empty kwargs -> plain PoolManager (direct).
        assert config.proxy_pool_kwargs() == {}

    def test_https_proxy(self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HTTPS_PROXY", "http://proxy.corp:8080")
        assert config.proxy_pool_kwargs() == {"https_proxy": "http://proxy.corp:8080"}

    def test_http_proxy(self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HTTP_PROXY", "http://proxy.corp:8080")
        assert config.proxy_pool_kwargs() == {"http_proxy": "http://proxy.corp:8080"}

    def test_https_wins_when_both_set(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Both set: emit only https_proxy -- never both, which would make
        # clickhouse-connect's get_pool_manager raise ProgrammingError.
        monkeypatch.setenv("HYDROLIX_HTTPS_PROXY", "http://secure.corp:8080")
        monkeypatch.setenv("HYDROLIX_HTTP_PROXY", "http://plain.corp:8080")
        assert config.proxy_pool_kwargs() == {"https_proxy": "http://secure.corp:8080"}

    def test_blank_https_proxy_is_unset(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # MCPB hosts inject empty user_config fields as blank strings.
        monkeypatch.setenv("HYDROLIX_HTTPS_PROXY", "   ")
        assert config.proxy_pool_kwargs() == {}

    def test_blank_https_falls_through_to_http(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HYDROLIX_HTTPS_PROXY", "")
        monkeypatch.setenv("HYDROLIX_HTTP_PROXY", "http://plain.corp:8080")
        assert config.proxy_pool_kwargs() == {"http_proxy": "http://plain.corp:8080"}

    @pytest.mark.parametrize(
        "bad",
        ["proxy.corp:8080", "proxy.corp", "ftp://proxy.corp:8080", "http://"],
        ids=["no-scheme", "host-only", "bad-scheme", "no-host"],
    )
    def test_malformed_proxy_url_raises(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch, bad: str
    ) -> None:
        # Validated like HYDROLIX_URL: scheme (http/https) + host required.
        monkeypatch.setenv("HYDROLIX_HTTPS_PROXY", bad)
        with pytest.raises(ValueError, match="HYDROLIX_HTTPS_PROXY"):
            config.proxy_pool_kwargs()


class TestProxyPoolWiring:
    """End-to-end: the shared pool actually becomes a ProxyManager when configured.

    These build the pool from ``mcp_server.client_pool_kwargs(config)`` -- the
    exact dict ``mcp_server`` feeds to ``get_pool_manager`` -- so the proxy spread
    cannot silently drop out of the real connection path without failing here.
    Pins the contract with clickhouse-connect: ProxyManager when a proxy is set,
    plain PoolManager when it is not.
    """

    def _build_pool(self, config: HydrolixConfig):
        from clickhouse_connect.driver import httputil

        from mcp_hydrolix.mcp_server import client_pool_kwargs

        return httputil.get_pool_manager(**client_pool_kwargs(config))

    def test_no_proxy_builds_plain_pool_manager(self, config: HydrolixConfig) -> None:
        from urllib3.poolmanager import PoolManager, ProxyManager

        pool = self._build_pool(config)
        assert isinstance(pool, PoolManager)
        assert not isinstance(pool, ProxyManager)

    def test_https_proxy_builds_proxy_manager(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from urllib3.poolmanager import ProxyManager

        monkeypatch.setenv("HYDROLIX_HTTPS_PROXY", "http://proxy.corp:8080")
        pool = self._build_pool(config)
        assert isinstance(pool, ProxyManager)

    def test_http_proxy_builds_proxy_manager(
        self, config: HydrolixConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from urllib3.poolmanager import ProxyManager

        monkeypatch.setenv("HYDROLIX_HTTP_PROXY", "http://proxy.corp:8080")
        pool = self._build_pool(config)
        assert isinstance(pool, ProxyManager)
