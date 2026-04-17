"""Tests for ``mcp_hydrolix.mcp_env.HydrolixConfig`` configuration properties.

Focused on changes introduced for the gunicorn -> uvicorn migration:
  * the ``mcp_graceful_timeout`` property exists, defaults to ``mcp_timeout``,
    and can be overridden by ``HYDROLIX_MCP_GRACEFUL_TIMEOUT``
  * the worker-recycling knobs ``mcp_max_requests`` and ``mcp_max_requests_jitter``
    are preserved (now backed by ``MaxRequestsMiddleware`` instead of gunicorn)
"""

from __future__ import annotations

import pytest

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
