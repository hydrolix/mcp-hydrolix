"""Tests for the version-gated *internal* deprecation log emitted from the
``/version`` probe path.

The probe path lives in ``mcp_server._check_parameterized_query_support``; the
helper ``_maybe_emit_internal_deprecation_log`` fires an ERROR log exactly once
when the cluster reports version >= 6.1 and the operator's deployment is
classified as "internal" (HYDROLIX_NAME set, deprecated aliases present).
"""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock, patch

import pytest

import mcp_hydrolix.mcp_server as server
from mcp_hydrolix import mcp_env


@pytest.fixture(autouse=True)
def _reset_probe_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset module state that the probe path mutates between tests."""
    for key in list(os.environ):
        if key.startswith("HYDROLIX_"):
            monkeypatch.delenv(key, raising=False)
    # setattr (not bare assignment) so pytest restores these process-global
    # values on teardown, keeping state from leaking between tests.
    monkeypatch.setattr(server, "_parameterized_queries_supported", None)
    monkeypatch.setattr(mcp_env, "_external_deprecation_warned", False)
    monkeypatch.setattr(mcp_env, "_internal_deprecation_warned", False)


def _resp(body: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.data = body.encode("utf-8")
    resp.status = status
    return resp


def _apply_internal_cfg(mock_config: MagicMock) -> None:
    mock_config.creds_with.return_value = MagicMock(token="tok")
    mock_config.version_api_secure = False
    mock_config.version_api_host = "version"
    mock_config.version_api_port = 23925
    mock_config.deprecation_audience = "internal"
    mock_config.deprecated_aliases = ["HYDROLIX_HOST", "HYDROLIX_API_PORT"]


def _apply_external_cfg(mock_config: MagicMock) -> None:
    mock_config.creds_with.return_value = MagicMock(token="tok")
    mock_config.version_api_secure = True
    mock_config.version_api_host = "cluster.example.com"
    mock_config.version_api_port = 443
    mock_config.deprecation_audience = "external"
    mock_config.deprecated_aliases = ["HYDROLIX_HOST"]


def _apply_no_deprecation_cfg(mock_config: MagicMock) -> None:
    mock_config.creds_with.return_value = MagicMock(token="tok")
    mock_config.version_api_secure = True
    mock_config.version_api_host = "cluster.example.com"
    mock_config.version_api_port = 443
    mock_config.deprecation_audience = None
    mock_config.deprecated_aliases = []


def _error_records(caplog: pytest.LogCaptureFixture) -> list:
    return [
        r for r in caplog.records if r.levelno == logging.ERROR and "Deprecated" in r.getMessage()
    ]


class TestInternalAudienceFiresLog:
    @patch("mcp_hydrolix.mcp_server.HYDROLIX_CONFIG")
    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_v6_1_0_fires_once(
        self,
        mock_to_thread,
        mock_cred,
        mock_config,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _apply_internal_cfg(mock_config)
        mock_to_thread.return_value = _resp("v6.1.0")

        with caplog.at_level(logging.ERROR, logger="mcp-hydrolix"):
            await server._check_parameterized_query_support()

        errors = _error_records(caplog)
        assert len(errors) == 1
        msg = errors[0].getMessage()
        assert "HYDROLIX_HOST -> HYDROLIX_HTTP_QUERY_HOST" in msg
        assert "HYDROLIX_API_PORT -> HYDROLIX_VERSION_API_PORT" in msg

    @pytest.mark.parametrize("version_str", ["v6.2.0", "v7.0.0", "v6.1.0-5-gabcdef12"])
    @patch("mcp_hydrolix.mcp_server.HYDROLIX_CONFIG")
    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_versions_at_or_above_6_1(
        self,
        mock_to_thread,
        mock_cred,
        mock_config,
        version_str: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _apply_internal_cfg(mock_config)
        mock_to_thread.return_value = _resp(version_str)

        with caplog.at_level(logging.ERROR, logger="mcp-hydrolix"):
            await server._check_parameterized_query_support()

        assert len(_error_records(caplog)) == 1


class TestInternalBelowVersionGate:
    @pytest.mark.parametrize("version_str", ["v6.0.9", "v5.12.0", "v5.0.0"])
    @patch("mcp_hydrolix.mcp_server.HYDROLIX_CONFIG")
    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_no_log_below_6_1(
        self,
        mock_to_thread,
        mock_cred,
        mock_config,
        version_str: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _apply_internal_cfg(mock_config)
        mock_to_thread.return_value = _resp(version_str)

        with caplog.at_level(logging.ERROR, logger="mcp-hydrolix"):
            await server._check_parameterized_query_support()

        assert _error_records(caplog) == []


class TestInternalProbeFailureModes:
    @patch("mcp_hydrolix.mcp_server.HYDROLIX_CONFIG")
    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_http_exception_then_recovery_fires_log(
        self,
        mock_to_thread,
        mock_cred,
        mock_config,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _apply_internal_cfg(mock_config)
        # First call: probe raises -> no log.
        mock_to_thread.side_effect = Exception("connection refused")
        with caplog.at_level(logging.ERROR, logger="mcp-hydrolix"):
            await server._check_parameterized_query_support()
        assert _error_records(caplog) == []

        # Second call: probe succeeds with 6.1.0 -> log fires.
        mock_to_thread.side_effect = None
        mock_to_thread.return_value = _resp("v6.1.0")
        with caplog.at_level(logging.ERROR, logger="mcp-hydrolix"):
            await server._check_parameterized_query_support()
        assert len(_error_records(caplog)) == 1

    @patch("mcp_hydrolix.mcp_server.HYDROLIX_CONFIG")
    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_non_200_response_no_log(
        self,
        mock_to_thread,
        mock_cred,
        mock_config,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _apply_internal_cfg(mock_config)
        mock_to_thread.return_value = _resp("Internal Server Error", status=500)

        with caplog.at_level(logging.ERROR, logger="mcp-hydrolix"):
            await server._check_parameterized_query_support()

        assert _error_records(caplog) == []

    @patch("mcp_hydrolix.mcp_server.HYDROLIX_CONFIG")
    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_unparseable_body_no_log(
        self,
        mock_to_thread,
        mock_cred,
        mock_config,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _apply_internal_cfg(mock_config)
        mock_to_thread.return_value = _resp("garbage")

        with caplog.at_level(logging.ERROR, logger="mcp-hydrolix"):
            await server._check_parameterized_query_support()

        assert _error_records(caplog) == []


class TestNonInternalAudiences:
    @patch("mcp_hydrolix.mcp_server.HYDROLIX_CONFIG")
    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_external_audience_no_log(
        self,
        mock_to_thread,
        mock_cred,
        mock_config,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _apply_external_cfg(mock_config)
        mock_to_thread.return_value = _resp("v6.1.0")

        with caplog.at_level(logging.ERROR, logger="mcp-hydrolix"):
            await server._check_parameterized_query_support()

        assert _error_records(caplog) == []

    @patch("mcp_hydrolix.mcp_server.HYDROLIX_CONFIG")
    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    @patch("mcp_hydrolix.mcp_server.asyncio.to_thread")
    async def test_no_deprecation_no_log(
        self,
        mock_to_thread,
        mock_cred,
        mock_config,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _apply_no_deprecation_cfg(mock_config)
        mock_to_thread.return_value = _resp("v6.1.0")

        with caplog.at_level(logging.ERROR, logger="mcp-hydrolix"):
            await server._check_parameterized_query_support()

        assert _error_records(caplog) == []
