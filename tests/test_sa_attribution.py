"""Tests for the per-request service-account attribution middleware.

The middleware emits one structured log line per authenticated MCP request so
log aggregators can attribute queries back to a specific service account.
Creator-email attribution (per HDX-11151) is deferred until turbine grows a
``created_by`` field; see the module docstring for context.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from types import SimpleNamespace

import jwt

from mcp_hydrolix.auth import (
    AccessToken,
    HydrolixCredential,
    HydrolixCredentialChain,
    UsernamePassword,
)


def _make_jwt(claims: dict) -> str:
    return jwt.encode(claims, key="x" * 32, algorithm="HS256")


def _base_claims(**overrides):
    now = int(time.time())
    claims = {
        "iss": "https://test.invalid/config",
        "aud": "config-api",
        "sub": "sa-uuid-123",
        "iat": now - 10,
        "exp": now + 600,
        "jti": "token-uuid-456",
    }
    claims.update(overrides)
    return claims


def _sa_access_token(claims: dict | None = None):
    token = _make_jwt(claims or _base_claims())
    return HydrolixCredentialChain.ServiceAccountAccess(
        token=token,
        client_id=HydrolixCredentialChain.ServiceAccountAccess.FAKE_CLIENT_ID,
        scopes=[HydrolixCredentialChain.ServiceAccountAccess.FAKE_SCOPE],
        expires_at=None,
        resource=None,
        claims={},
        expected_issuer="https://test.invalid/config",
    )


def _ctx(method: str, tool_name: str | None = None):
    """Build a minimal stand-in for ``fastmcp.server.middleware.MiddlewareContext``.

    The middleware only reads ``.method`` and (for tools/call) ``.message.name``,
    so a SimpleNamespace duck-types it without pulling in the FastMCP wiring."""
    message = SimpleNamespace(name=tool_name) if tool_name else SimpleNamespace()
    return SimpleNamespace(method=method, message=message)


async def _ok(_ctx) -> str:
    return "downstream-result"


class TestSAAttributionMiddleware:
    """Per-request attribution logging."""

    def test_logs_service_account_id_for_authenticated_request(self, monkeypatch, caplog):
        from mcp_hydrolix import sa_attribution

        monkeypatch.setattr(sa_attribution, "get_access_token", lambda: _sa_access_token())

        mw = sa_attribution.SAAttributionMiddleware()
        with caplog.at_level(logging.INFO, logger="mcp_hydrolix.sa_attribution"):
            result = asyncio.run(mw.on_request(_ctx("tools/list"), _ok))

        assert result == "downstream-result"
        records = [r for r in caplog.records if r.name == "mcp_hydrolix.sa_attribution"]
        assert len(records) == 1
        rec = records[0]
        assert rec.service_account_id == "sa-uuid-123"

    def test_includes_tool_name_for_tool_calls(self, monkeypatch, caplog):
        from mcp_hydrolix import sa_attribution

        monkeypatch.setattr(sa_attribution, "get_access_token", lambda: _sa_access_token())

        mw = sa_attribution.SAAttributionMiddleware()
        with caplog.at_level(logging.INFO, logger="mcp_hydrolix.sa_attribution"):
            asyncio.run(mw.on_request(_ctx("tools/call", tool_name="run_select_query"), _ok))

        rec = next(r for r in caplog.records if r.name == "mcp_hydrolix.sa_attribution")
        assert rec.service_account_id == "sa-uuid-123"
        assert rec.tool_name == "run_select_query"

    def test_does_not_log_when_no_access_token_and_no_env_credential(self, monkeypatch, caplog):
        """No per-request token AND no env-configured default credential
        (raises ValueError from creds_with) — middleware skips silently."""
        from mcp_hydrolix import sa_attribution

        monkeypatch.setattr(sa_attribution, "get_access_token", lambda: None)

        class _NoCredsConfig:
            def creds_with(self, _request_credential):
                raise ValueError("no credentials")

        monkeypatch.setattr(sa_attribution, "get_config", lambda: _NoCredsConfig())

        mw = sa_attribution.SAAttributionMiddleware()
        with caplog.at_level(logging.INFO, logger="mcp_hydrolix.sa_attribution"):
            result = asyncio.run(mw.on_request(_ctx("tools/list"), _ok))

        assert result == "downstream-result"
        assert not any(r.name == "mcp_hydrolix.sa_attribution" for r in caplog.records)

    def test_falls_back_to_env_default_credential_for_stdio(self, monkeypatch, caplog):
        """For stdio transport (Claude Code's default), HYDROLIX_TOKEN becomes
        the env-configured default credential — it is NOT injected per-request
        and ``get_access_token()`` returns None. The middleware must fall back
        to the default credential via ``creds_with(None)`` so attribution still
        fires for stdio. This is the most common Claude Code setup."""
        from mcp_hydrolix import sa_attribution
        from mcp_hydrolix.auth.credentials import ServiceAccountToken

        monkeypatch.setattr(sa_attribution, "get_access_token", lambda: None)

        env_credential = ServiceAccountToken(
            _make_jwt(_base_claims()), expected_iss="https://test.invalid/config"
        )

        class _StdioConfig:
            def creds_with(self, request_credential):
                return request_credential if request_credential is not None else env_credential

        monkeypatch.setattr(sa_attribution, "get_config", lambda: _StdioConfig())

        mw = sa_attribution.SAAttributionMiddleware()
        with caplog.at_level(logging.INFO, logger="mcp_hydrolix.sa_attribution"):
            result = asyncio.run(mw.on_request(_ctx("tools/call", tool_name="list_databases"), _ok))

        assert result == "downstream-result"
        rec = next(r for r in caplog.records if r.name == "mcp_hydrolix.sa_attribution")
        assert rec.service_account_id == "sa-uuid-123"
        assert rec.tool_name == "list_databases"

    def test_skips_log_when_env_default_credential_is_username_password(self, monkeypatch, caplog):
        """If the server is started with HYDROLIX_USER/HYDROLIX_PASSWORD (no
        SA token), the env-default credential is a UsernamePassword. The
        middleware must skip cleanly via the isinstance guard — no log line,
        no DEBUG "logging failed" line, and call_next must still be invoked
        so the tool handler proceeds normally."""
        from mcp_hydrolix import sa_attribution

        monkeypatch.setattr(sa_attribution, "get_access_token", lambda: None)

        env_credential = UsernamePassword(username="bob", password="hunter2")

        class _UserPassConfig:
            def creds_with(self, request_credential):
                return request_credential if request_credential is not None else env_credential

        monkeypatch.setattr(sa_attribution, "get_config", lambda: _UserPassConfig())

        mw = sa_attribution.SAAttributionMiddleware()
        with caplog.at_level(logging.DEBUG, logger="mcp_hydrolix.sa_attribution"):
            result = asyncio.run(mw.on_request(_ctx("tools/call", tool_name="list_databases"), _ok))

        # call_next ran (request was not broken)
        assert result == "downstream-result"
        # Skip cleanly: no INFO (no SA to attribute) AND no DEBUG (no spurious
        # "logging failed" — UsernamePassword is a supported credential type).
        records = [r for r in caplog.records if r.name == "mcp_hydrolix.sa_attribution"]
        assert records == []

    def test_skips_log_when_credential_is_not_a_service_account_token(self, monkeypatch, caplog):
        """If a future ``AccessToken`` subclass yields a non-SA credential
        (e.g. UsernamePassword), the middleware must skip rather than crash on
        the missing ``service_account_id`` attribute. The broad except would
        also catch this, but the explicit guard makes the intent clear."""
        from mcp_hydrolix import sa_attribution

        class _NonSAAccess(AccessToken):
            def as_credential(self) -> HydrolixCredential:
                return UsernamePassword(username="u", password="p")

        non_sa_token = _NonSAAccess(
            token="opaque",
            client_id="fake-client",
            scopes=["fake-scope"],
            expires_at=None,
            resource=None,
            claims={},
        )
        monkeypatch.setattr(sa_attribution, "get_access_token", lambda: non_sa_token)

        mw = sa_attribution.SAAttributionMiddleware()
        with caplog.at_level(logging.DEBUG, logger="mcp_hydrolix.sa_attribution"):
            result = asyncio.run(mw.on_request(_ctx("tools/list"), _ok))

        assert result == "downstream-result"
        # Skip cleanly: no INFO (no attribution) AND no DEBUG (no spurious
        # "logging failed" — the credential simply wasn't an SA).
        records = [r for r in caplog.records if r.name == "mcp_hydrolix.sa_attribution"]
        assert records == []

    def test_logging_failure_does_not_break_the_request(self, monkeypatch, caplog):
        """A malformed JWT must not turn into a 500 — log path failures swallow,
        the request continues. This is a stopgap log; correctness of the request
        is more important than perfect attribution."""
        from mcp_hydrolix import sa_attribution

        # Build a "token" that will blow up at decode time inside as_credential().
        bad = HydrolixCredentialChain.ServiceAccountAccess(
            token="not-a-jwt",
            client_id=HydrolixCredentialChain.ServiceAccountAccess.FAKE_CLIENT_ID,
            scopes=[HydrolixCredentialChain.ServiceAccountAccess.FAKE_SCOPE],
            expires_at=None,
            resource=None,
            claims={},
            expected_issuer=None,
        )
        monkeypatch.setattr(sa_attribution, "get_access_token", lambda: bad)

        mw = sa_attribution.SAAttributionMiddleware()
        with caplog.at_level(logging.INFO, logger="mcp_hydrolix.sa_attribution"):
            result = asyncio.run(mw.on_request(_ctx("tools/list"), _ok))

        assert result == "downstream-result"
        # The attribution line should be absent, but downstream still ran.
        attribution_lines = [
            r
            for r in caplog.records
            if r.name == "mcp_hydrolix.sa_attribution" and getattr(r, "service_account_id", None)
        ]
        assert attribution_lines == []


class TestSAAttributionMiddlewareJsonOutput:
    """End-to-end: extras should round-trip through JsonFormatter as top-level
    JSON fields, matching the ticket's 'structured log output' requirement."""

    def test_structured_fields_round_trip_through_json_formatter(self, monkeypatch):
        import io

        from mcp_hydrolix import sa_attribution
        from mcp_hydrolix.log import JsonFormatter

        monkeypatch.setattr(sa_attribution, "get_access_token", lambda: _sa_access_token())

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        logger = logging.getLogger("mcp_hydrolix.sa_attribution")
        prev_level = logger.level
        try:
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            mw = sa_attribution.SAAttributionMiddleware()
            asyncio.run(mw.on_request(_ctx("tools/call", tool_name="list_databases"), _ok))
        finally:
            logger.removeHandler(handler)
            logger.setLevel(prev_level)

        lines = [ln for ln in stream.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["service_account_id"] == "sa-uuid-123"
        assert payload["tool_name"] == "list_databases"
        assert "jti" not in payload
        assert "mcp_method" not in payload
