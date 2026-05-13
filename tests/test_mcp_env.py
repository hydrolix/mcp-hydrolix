"""Tests for ``mcp_hydrolix.mcp_env.HydrolixConfig`` configuration properties.

Focused on changes introduced for the gunicorn -> uvicorn migration:
  * the ``mcp_graceful_timeout`` property exists, defaults to ``mcp_timeout``,
    and can be overridden by ``HYDROLIX_MCP_GRACEFUL_TIMEOUT``
  * the worker-recycling knobs ``mcp_max_requests`` and ``mcp_max_requests_jitter``
    are preserved (now backed by ``MaxRequestsMiddleware`` instead of gunicorn)
"""

from __future__ import annotations

import pytest

from mcp_hydrolix.auth.credentials import ServiceAccountToken, UsernamePassword
from mcp_hydrolix.mcp_env import HydrolixConfig


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> HydrolixConfig:
    """Return a fresh ``HydrolixConfig`` with the minimal required env vars set."""

    monkeypatch.setenv("HYDROLIX_HOST", "example.invalid")
    for key in (
        "HYDROLIX_MCP_REQUEST_TIMEOUT",
        "HYDROLIX_MCP_GRACEFUL_TIMEOUT",
        "HYDROLIX_MCP_MAX_REQUESTS",
        "HYDROLIX_MCP_MAX_REQUESTS_JITTER",
    ):
        monkeypatch.delenv(key, raising=False)
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

    def _make_config(self, monkeypatch: pytest.MonkeyPatch) -> HydrolixConfig:
        """Return a fresh HydrolixConfig with only HYDROLIX_HOST set by default."""
        monkeypatch.setenv("HYDROLIX_HOST", "example.invalid")
        monkeypatch.delenv("HYDROLIX_TOKEN", raising=False)
        monkeypatch.delenv("HYDROLIX_USER", raising=False)
        monkeypatch.delenv("HYDROLIX_PASSWORD", raising=False)
        return HydrolixConfig()

    def test_token_set_blank_user_password_uses_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HYDROLIX_TOKEN set, user/password both blank -> ServiceAccountToken wins."""
        monkeypatch.setenv("HYDROLIX_HOST", "example.invalid")
        monkeypatch.setenv("HYDROLIX_TOKEN", _TEST_JWT)
        monkeypatch.setenv("HYDROLIX_USER", "")
        monkeypatch.setenv("HYDROLIX_PASSWORD", "")
        cfg = HydrolixConfig()
        cred = cfg.creds_with(None)
        assert isinstance(cred, ServiceAccountToken)
        assert cred.token == _TEST_JWT

    def test_blank_token_with_user_password_uses_user_password(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HYDROLIX_TOKEN blank, user/password both set -> UsernamePassword."""
        monkeypatch.setenv("HYDROLIX_HOST", "example.invalid")
        monkeypatch.setenv("HYDROLIX_TOKEN", "")
        monkeypatch.setenv("HYDROLIX_USER", "alice")
        monkeypatch.setenv("HYDROLIX_PASSWORD", "hunter2")
        cfg = HydrolixConfig()
        cred = cfg.creds_with(None)
        assert isinstance(cred, UsernamePassword)
        assert cred.username == "alice"
        assert cred.password == "hunter2"

    def test_unset_token_with_user_password_uses_user_password(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HYDROLIX_TOKEN unset, user/password both set -> UsernamePassword."""
        monkeypatch.setenv("HYDROLIX_HOST", "example.invalid")
        monkeypatch.delenv("HYDROLIX_TOKEN", raising=False)
        monkeypatch.setenv("HYDROLIX_USER", "alice")
        monkeypatch.setenv("HYDROLIX_PASSWORD", "hunter2")
        cfg = HydrolixConfig()
        cred = cfg.creds_with(None)
        assert isinstance(cred, UsernamePassword)
        assert cred.username == "alice"
        assert cred.password == "hunter2"

    def test_blank_password_raises_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HYDROLIX_TOKEN unset, user set but password blank -> no credentials."""
        monkeypatch.setenv("HYDROLIX_HOST", "example.invalid")
        monkeypatch.delenv("HYDROLIX_TOKEN", raising=False)
        monkeypatch.setenv("HYDROLIX_USER", "alice")
        monkeypatch.setenv("HYDROLIX_PASSWORD", "")
        cfg = HydrolixConfig()
        with pytest.raises(ValueError, match="No credentials available"):
            cfg.creds_with(None)

    def test_blank_username_raises_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HYDROLIX_TOKEN unset, user blank but password set -> no credentials."""
        monkeypatch.setenv("HYDROLIX_HOST", "example.invalid")
        monkeypatch.delenv("HYDROLIX_TOKEN", raising=False)
        monkeypatch.setenv("HYDROLIX_USER", "")
        monkeypatch.setenv("HYDROLIX_PASSWORD", "hunter2")
        cfg = HydrolixConfig()
        with pytest.raises(ValueError, match="No credentials available"):
            cfg.creds_with(None)

    def test_all_blank_raises_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All credential env vars blank -> no credentials."""
        monkeypatch.setenv("HYDROLIX_HOST", "example.invalid")
        monkeypatch.setenv("HYDROLIX_TOKEN", "")
        monkeypatch.setenv("HYDROLIX_USER", "")
        monkeypatch.setenv("HYDROLIX_PASSWORD", "")
        cfg = HydrolixConfig()
        with pytest.raises(ValueError, match="No credentials available"):
            cfg.creds_with(None)

    def test_all_unset_raises_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All credential env vars unset -> no credentials."""
        cfg = self._make_config(monkeypatch)
        with pytest.raises(ValueError, match="No credentials available"):
            cfg.creds_with(None)
