"""The ?token= query parameter stays on by default and can be turned off (HDX-12410).

Some MCP clients cannot send an Authorization header, so the query-parameter form
is the only way for them to present a service-account token. Deployments where
every client sends the header, for example behind a gateway, turn it off.
"""

from __future__ import annotations

import logging

from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend

from mcp_hydrolix.auth import GetParamAuthBackend, HydrolixCredentialChain
from mcp_hydrolix.mcp_env import HydrolixConfig


def test_query_parameter_backend_on_by_default(monkeypatch):
    monkeypatch.delenv("HYDROLIX_ALLOW_TOKEN_QUERY_PARAM", raising=False)
    assert HydrolixConfig().allow_token_query_param is True
    backends = HydrolixCredentialChain(None).backends()
    assert [type(b) for b in backends] == [BearerAuthBackend, GetParamAuthBackend]


def test_query_parameter_backend_removed_when_disabled(monkeypatch):
    monkeypatch.setenv("HYDROLIX_ALLOW_TOKEN_QUERY_PARAM", "false")
    assert HydrolixConfig().allow_token_query_param is False
    backends = HydrolixCredentialChain(None, allow_token_query_param=False).backends()
    assert [type(b) for b in backends] == [BearerAuthBackend]


def test_only_an_explicit_false_disables(monkeypatch):
    monkeypatch.setenv("HYDROLIX_ALLOW_TOKEN_QUERY_PARAM", "off")
    assert HydrolixConfig().allow_token_query_param is True


def test_disabling_logs_at_startup(monkeypatch, caplog):
    monkeypatch.setenv("HYDROLIX_ALLOW_TOKEN_QUERY_PARAM", "false")
    with caplog.at_level(logging.INFO, logger="mcp-hydrolix"):
        HydrolixConfig()
    assert any("HYDROLIX_ALLOW_TOKEN_QUERY_PARAM" in r.getMessage() for r in caplog.records)


def test_bearer_backend_always_first(monkeypatch):
    for enabled in (True, False):
        backends = HydrolixCredentialChain(None, allow_token_query_param=enabled).backends()
        assert type(backends[0]) is BearerAuthBackend
