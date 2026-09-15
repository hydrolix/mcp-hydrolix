"""Per-request credentials on the gateway path (HDX-12410).

No request may run as the deployment's service account once
HYDROLIX_REQUIRE_REQUEST_CREDENTIAL is on, and a token in the URL is opt-in.
Scenario names mirror openspec/changes/gateway-hardening/specs/request-credentials.
"""

from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastmcp.exceptions import ToolError
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend

from mcp_hydrolix.auth import (
    GetParamAuthBackend,
    HydrolixCredentialChain,
    ServiceAccountToken,
)
from mcp_hydrolix.mcp_env import HydrolixConfig, MissingRequestCredentialError


def _bearer_credential(sub: str = "user-sub-1") -> ServiceAccountToken:
    now = int(time.time())
    token = jwt.encode(
        {"iss": "https://test.invalid", "sub": sub, "iat": now - 5, "exp": now + 300},
        key="x" * 32,
        algorithm="HS256",
    )
    return ServiceAccountToken(token, None)


@pytest.fixture
def http_required(monkeypatch):
    monkeypatch.setenv("HYDROLIX_MCP_SERVER_TRANSPORT", "http")
    monkeypatch.setenv("HYDROLIX_REQUIRE_REQUEST_CREDENTIAL", "true")
    monkeypatch.setenv("HYDROLIX_TOKEN", _bearer_credential("service-account").token)


class TestRequestCredentialRequiredMode:
    def test_missing_request_credential_is_refused(self, http_required):
        with pytest.raises(MissingRequestCredentialError, match="per-request credential"):
            HydrolixConfig().creds_with(None)

    def test_request_credential_still_honoured(self, http_required):
        credential = _bearer_credential()
        assert HydrolixConfig().creds_with(credential) is credential

    def test_required_mode_rejects_stdio_transport(self, monkeypatch):
        monkeypatch.setenv("HYDROLIX_MCP_SERVER_TRANSPORT", "stdio")
        monkeypatch.setenv("HYDROLIX_REQUIRE_REQUEST_CREDENTIAL", "true")
        with pytest.raises(ValueError, match="http or sse"):
            HydrolixConfig()

    def test_default_mode_keeps_environment_fallback(self, monkeypatch):
        monkeypatch.delenv("HYDROLIX_REQUIRE_REQUEST_CREDENTIAL", raising=False)
        monkeypatch.setenv("HYDROLIX_TOKEN", _bearer_credential("service-account").token)
        credential = HydrolixConfig().creds_with(None)
        assert isinstance(credential, ServiceAccountToken)
        assert credential.service_account_id == "service-account"

    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    async def test_query_without_credential_fails_closed(self, _no_cred, http_required):
        from mcp_hydrolix.mcp_server import execute_query

        with pytest.raises(ToolError, match="per-request credential"):
            await execute_query("SELECT 1")

    @patch("mcp_hydrolix.mcp_server.create_hydrolix_client")
    @patch("mcp_hydrolix.mcp_server.get_request_credential", return_value=None)
    async def test_readiness_probe_passes_mounted_credential(
        self, _no_cred, mock_create_client, http_required
    ):
        from mcp_hydrolix import mcp_server

        mounted = _bearer_credential("readonly-sa")
        mock_client = AsyncMock()
        mock_client.client.server_version = "24.1"
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_create_client.return_value = mock_ctx

        with patch.object(mcp_server, "_load_k8s_service_credential", return_value=mounted):
            response = await mcp_server.readiness_check(AsyncMock())

        assert response.status_code == 200
        _, passed = mock_create_client.call_args.args
        assert passed is mounted


class TestTokenQueryParameterOptIn:
    def test_query_parameter_backend_off_by_default(self, monkeypatch):
        monkeypatch.delenv("HYDROLIX_ALLOW_TOKEN_QUERY_PARAM", raising=False)
        assert HydrolixConfig().allow_token_query_param is False
        backends = HydrolixCredentialChain(None).backends()
        assert [type(b) for b in backends] == [BearerAuthBackend]

    def test_query_parameter_backend_enabled_by_env(self, monkeypatch):
        monkeypatch.setenv("HYDROLIX_ALLOW_TOKEN_QUERY_PARAM", "true")
        assert HydrolixConfig().allow_token_query_param is True
        backends = HydrolixCredentialChain(None, allow_token_query_param=True).backends()
        assert [type(b) for b in backends] == [BearerAuthBackend, GetParamAuthBackend]

    def test_enabling_query_parameter_logs_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("HYDROLIX_ALLOW_TOKEN_QUERY_PARAM", "true")
        with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
            HydrolixConfig()
        assert any("HYDROLIX_ALLOW_TOKEN_QUERY_PARAM" in r.getMessage() for r in caplog.records)
