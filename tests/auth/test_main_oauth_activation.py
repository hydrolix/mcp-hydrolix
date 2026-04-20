"""`main._maybe_activate_oauth()` swaps `mcp.auth` when OAuth is configured.

These tests cover the integration seam between `load_oauth_config` /
`try_activate_oauth` and the module-level `mcp` instance.
"""

import httpx
import pytest
import respx

from mcp_hydrolix.auth.oauth import OAuthHydrolixAuthProvider

ISSUER = "https://example.com/keycloak/realms/hydrolix-users"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
JWKS_URI = f"{ISSUER}/protocol/openid-connect/certs"


@pytest.fixture(autouse=True)
def _host_env(monkeypatch):
    monkeypatch.setenv("HYDROLIX_HOST", "hydrolix.example.com")
    for k in (
        "HYDROLIX_OAUTH_ISSUER",
        "HYDROLIX_OAUTH_AUDIENCE",
        "HYDROLIX_OAUTH_JWKS_URI",
        "HYDROLIX_OAUTH_REQUIRED_SCOPES",
        "HYDROLIX_OAUTH_RESOURCE_URL",
        "HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS",
    ):
        monkeypatch.delenv(k, raising=False)


def _jwks():
    return {"keys": [{"kty": "RSA", "kid": "test", "use": "sig", "alg": "RS256"}]}


def test_no_oauth_env_leaves_mcp_auth_unchanged(monkeypatch):
    from mcp_hydrolix import main as main_mod
    from mcp_hydrolix.auth import HydrolixCredentialChain

    before = main_mod.mcp.auth
    assert isinstance(before, HydrolixCredentialChain)
    main_mod._maybe_activate_oauth()
    assert main_mod.mcp.auth is before


@respx.mock(assert_all_mocked=True)
def test_oauth_env_swaps_mcp_auth_to_oauth_provider(respx_mock, monkeypatch):
    from mcp_hydrolix import main as main_mod
    from mcp_hydrolix.auth import HydrolixCredentialChain

    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(200, json={"issuer": ISSUER, "jwks_uri": JWKS_URI})
    )
    respx_mock.get(JWKS_URI).mock(return_value=httpx.Response(200, json=_jwks()))

    monkeypatch.setenv("HYDROLIX_OAUTH_ISSUER", ISSUER)
    monkeypatch.setenv("HYDROLIX_OAUTH_AUDIENCE", "mcp-hydrolix")
    monkeypatch.setenv("HYDROLIX_OAUTH_RESOURCE_URL", "https://mcp.example.com")

    original = main_mod.mcp.auth
    try:
        main_mod._maybe_activate_oauth()
        assert isinstance(main_mod.mcp.auth, OAuthHydrolixAuthProvider)
        assert not isinstance(main_mod.mcp.auth, HydrolixCredentialChain)
    finally:
        main_mod.mcp.auth = original


@respx.mock(assert_all_mocked=True)
def test_oauth_discovery_failure_leaves_mcp_auth_unchanged(respx_mock, monkeypatch, caplog):
    """Network error during discovery → legacy auth retained (fail-open)."""
    from mcp_hydrolix import main as main_mod
    from mcp_hydrolix.auth import HydrolixCredentialChain

    respx_mock.get(DISCOVERY_URL).mock(side_effect=httpx.ConnectError("no route"))

    monkeypatch.setenv("HYDROLIX_OAUTH_ISSUER", ISSUER)
    monkeypatch.setenv("HYDROLIX_OAUTH_AUDIENCE", "mcp-hydrolix")

    original = main_mod.mcp.auth
    caplog.set_level("WARNING", logger="mcp-hydrolix")
    main_mod._maybe_activate_oauth()
    try:
        assert main_mod.mcp.auth is original
        assert isinstance(main_mod.mcp.auth, HydrolixCredentialChain)
        assert any("OAuth configured but not activated" in r.message for r in caplog.records)
    finally:
        main_mod.mcp.auth = original


def test_oauth_config_error_propagates(monkeypatch):
    """Malformed env vars must surface immediately — operator needs to know."""
    from mcp_hydrolix import main as main_mod
    from mcp_hydrolix.auth.oauth import OAuthConfigError

    monkeypatch.setenv("HYDROLIX_OAUTH_ISSUER", ISSUER)
    # Missing audience — load_oauth_config raises.
    with pytest.raises(OAuthConfigError):
        main_mod._maybe_activate_oauth()
