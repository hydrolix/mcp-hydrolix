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
    ServiceAccountToken,
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


def _sa_credential(claims: dict | None = None) -> ServiceAccountToken:
    """Build a real ServiceAccountToken for tests. The JWT decoder skips
    signature verification, so the key/algo used by ``_make_jwt`` is fine."""
    return ServiceAccountToken(
        _make_jwt(claims or _base_claims()),
        expected_iss="https://test.invalid/config",
    )


class _PassthroughConfig:
    """Stand-in for HydrolixConfig.creds_with: returns the per-request
    credential when present, else the env-supplied default (if any), else
    raises ValueError (matching the real ``creds_with`` contract)."""

    def __init__(self, env_default=None):
        self._env_default = env_default

    def creds_with(self, request_credential):
        if request_credential is not None:
            return request_credential
        if self._env_default is not None:
            return self._env_default
        raise ValueError("no credentials")


def _ctx(method: str, tool_name: str | None = None):
    """Build a minimal stand-in for ``fastmcp.server.middleware.MiddlewareContext``.

    The middleware only reads ``.method`` and (for tools/call) ``.message.name``,
    so a SimpleNamespace duck-types it without pulling in the FastMCP wiring."""
    message = SimpleNamespace(name=tool_name) if tool_name else SimpleNamespace()
    return SimpleNamespace(method=method, message=message)


async def _ok(_ctx) -> str:
    return "downstream-result"


class TestServiceAccountAttributionMiddleware:
    """Per-request attribution logging."""

    def test_logs_service_account_id_for_authenticated_request(self, monkeypatch, caplog):
        from mcp_hydrolix import sa_attribution

        monkeypatch.setattr(sa_attribution, "get_request_credential", _sa_credential)
        monkeypatch.setattr(sa_attribution, "get_config", _PassthroughConfig)

        mw = sa_attribution.ServiceAccountAttributionMiddleware()
        with caplog.at_level(logging.INFO, logger="mcp_hydrolix.sa_attribution"):
            result = asyncio.run(mw.on_request(_ctx("tools/list"), _ok))

        assert result == "downstream-result"
        records = [r for r in caplog.records if r.name == "mcp_hydrolix.sa_attribution"]
        assert len(records) == 1
        rec = records[0]
        assert rec.service_account_id == "sa-uuid-123"

    def test_includes_tool_name_for_tool_calls(self, monkeypatch, caplog):
        from mcp_hydrolix import sa_attribution

        monkeypatch.setattr(sa_attribution, "get_request_credential", _sa_credential)
        monkeypatch.setattr(sa_attribution, "get_config", _PassthroughConfig)

        mw = sa_attribution.ServiceAccountAttributionMiddleware()
        with caplog.at_level(logging.INFO, logger="mcp_hydrolix.sa_attribution"):
            asyncio.run(mw.on_request(_ctx("tools/call", tool_name="run_select_query"), _ok))

        rec = next(r for r in caplog.records if r.name == "mcp_hydrolix.sa_attribution")
        assert rec.service_account_id == "sa-uuid-123"
        assert rec.tool_name == "run_select_query"

    def test_does_not_log_when_no_request_credential_and_no_env_credential(
        self, monkeypatch, caplog
    ):
        """No per-request credential AND no env-configured default credential
        (``creds_with(None)`` raises ValueError) — middleware skips silently."""
        from mcp_hydrolix import sa_attribution

        monkeypatch.setattr(sa_attribution, "get_request_credential", lambda: None)
        monkeypatch.setattr(sa_attribution, "get_config", lambda: _PassthroughConfig())

        mw = sa_attribution.ServiceAccountAttributionMiddleware()
        with caplog.at_level(logging.INFO, logger="mcp_hydrolix.sa_attribution"):
            result = asyncio.run(mw.on_request(_ctx("tools/list"), _ok))

        assert result == "downstream-result"
        assert not any(r.name == "mcp_hydrolix.sa_attribution" for r in caplog.records)

    def test_falls_back_to_env_default_credential_for_stdio(self, monkeypatch, caplog):
        """For stdio transport (Claude Code's default), HYDROLIX_TOKEN becomes
        the env-configured default credential — there is NO per-request auth
        context, so ``get_request_credential()`` returns None. The middleware
        must fall back to the default credential via ``creds_with(None)`` so
        attribution still fires for stdio. This is the most common Claude
        Code setup."""
        from mcp_hydrolix import sa_attribution

        monkeypatch.setattr(sa_attribution, "get_request_credential", lambda: None)
        monkeypatch.setattr(
            sa_attribution, "get_config", lambda: _PassthroughConfig(env_default=_sa_credential())
        )

        mw = sa_attribution.ServiceAccountAttributionMiddleware()
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

        env_credential = UsernamePassword(username="bob", password="hunter2")
        monkeypatch.setattr(sa_attribution, "get_request_credential", lambda: None)
        monkeypatch.setattr(
            sa_attribution, "get_config", lambda: _PassthroughConfig(env_default=env_credential)
        )

        mw = sa_attribution.ServiceAccountAttributionMiddleware()
        with caplog.at_level(logging.DEBUG, logger="mcp_hydrolix.sa_attribution"):
            result = asyncio.run(mw.on_request(_ctx("tools/call", tool_name="list_databases"), _ok))

        # call_next ran (request was not broken)
        assert result == "downstream-result"
        # Skip cleanly: no INFO (no SA to attribute) AND no DEBUG (no spurious
        # "logging failed" — UsernamePassword is a supported credential type).
        records = [r for r in caplog.records if r.name == "mcp_hydrolix.sa_attribution"]
        assert records == []

    def test_skips_log_when_request_credential_is_not_a_service_account_token(
        self, monkeypatch, caplog
    ):
        """If a non-SA credential is somehow on the request (e.g. a future
        AccessToken subtype yielding UsernamePassword), the middleware must
        skip cleanly via the isinstance guard — no crash on the missing
        ``service_account_id`` attribute."""
        from mcp_hydrolix import sa_attribution

        non_sa_credential = UsernamePassword(username="u", password="p")
        monkeypatch.setattr(sa_attribution, "get_request_credential", lambda: non_sa_credential)
        monkeypatch.setattr(sa_attribution, "get_config", _PassthroughConfig)

        mw = sa_attribution.ServiceAccountAttributionMiddleware()
        with caplog.at_level(logging.DEBUG, logger="mcp_hydrolix.sa_attribution"):
            result = asyncio.run(mw.on_request(_ctx("tools/list"), _ok))

        assert result == "downstream-result"
        # Skip cleanly: no INFO (no attribution) AND no DEBUG (no spurious
        # "logging failed" — the credential simply wasn't an SA).
        records = [r for r in caplog.records if r.name == "mcp_hydrolix.sa_attribution"]
        assert records == []

    def test_invalid_request_token_does_not_break_the_request(self, monkeypatch, caplog):
        """If ``get_request_credential`` raises ValueError (e.g. malformed
        per-request JWT), middleware must skip the log line cleanly and still
        call call_next so the request proceeds. ``creds_with`` is the layer
        that raises in the merged code path, but the same outcome must hold
        when get_request_credential itself raises."""
        from mcp_hydrolix import sa_attribution

        def _raises():
            raise ValueError("The provided access token is invalid.")

        monkeypatch.setattr(sa_attribution, "get_request_credential", _raises)
        monkeypatch.setattr(sa_attribution, "get_config", _PassthroughConfig)

        mw = sa_attribution.ServiceAccountAttributionMiddleware()
        with caplog.at_level(logging.INFO, logger="mcp_hydrolix.sa_attribution"):
            result = asyncio.run(mw.on_request(_ctx("tools/list"), _ok))

        assert result == "downstream-result"
        attribution_lines = [
            r
            for r in caplog.records
            if r.name == "mcp_hydrolix.sa_attribution" and getattr(r, "service_account_id", None)
        ]
        assert attribution_lines == []


class TestServiceAccountAttributionMiddlewareJsonOutput:
    """End-to-end: extras should round-trip through JsonFormatter as top-level
    JSON fields, matching the ticket's 'structured log output' requirement."""

    def test_structured_fields_round_trip_through_json_formatter(self, monkeypatch):
        import io

        from mcp_hydrolix import sa_attribution
        from mcp_hydrolix.log import JsonFormatter

        monkeypatch.setattr(sa_attribution, "get_request_credential", _sa_credential)
        monkeypatch.setattr(sa_attribution, "get_config", _PassthroughConfig)

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        logger = logging.getLogger("mcp_hydrolix.sa_attribution")
        prev_level = logger.level
        try:
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            mw = sa_attribution.ServiceAccountAttributionMiddleware()
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
