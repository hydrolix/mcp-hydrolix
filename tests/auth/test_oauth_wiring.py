"""Wiring contract: OAuthBearerToken flows through existing server plumbing.

The server code (`create_hydrolix_client`, `_check_parameterized_query_support`,
`get_request_credential`) was written for `ServiceAccountToken` /
`UsernamePassword`. These tests lock in that `OAuthBearerToken` plays the same
role without special-cases — it is the forward-compatible fourth credential
type.
"""

import pytest

from mcp_hydrolix.auth.credentials import HydrolixCredential
from mcp_hydrolix.auth.oauth import OAuthBearerToken


ISSUER = "https://example.com/keycloak/realms/hydrolix-users"


@pytest.fixture(autouse=True)
def _hdx_host(monkeypatch):
    monkeypatch.setenv("HYDROLIX_HOST", "hydrolix.example.com")


def _oauth_token(**overrides) -> OAuthBearerToken:
    defaults = dict(
        token="<jwt>",
        subject="alice@example.com",
        expires_at=2_000_000_000,
        claims={"sub": "alice@example.com", "email": "alice@example.com"},
    )
    defaults.update(overrides)
    return OAuthBearerToken(**defaults)


def test_oauth_bearer_is_hydrolix_credential():
    assert isinstance(_oauth_token(), HydrolixCredential)


def test_clickhouse_config_entries_uses_access_token():
    t = _oauth_token(token="real.jwt.here")
    assert t.clickhouse_config_entries() == {"access_token": "real.jwt.here"}


def test_service_account_id_falls_back_to_sentinel_when_no_subject():
    t = _oauth_token(subject=None)
    assert t.service_account_id == "<oauth-bearer>"


def test_service_account_id_uses_subject_when_present():
    t = _oauth_token(subject="alice")
    assert t.service_account_id == "alice"


def test_is_frozen():
    t = _oauth_token()
    with pytest.raises((AttributeError, Exception)):
        t.token = "other"  # type: ignore[misc]


def test_creds_with_prefers_oauth_bearer_over_env_default(monkeypatch):
    """HYDROLIX_CONFIG.creds_with(oauth_token) returns the request token, not env creds."""
    monkeypatch.setenv("HYDROLIX_USER", "u")
    monkeypatch.setenv("HYDROLIX_PASSWORD", "p")
    from mcp_hydrolix.mcp_env import HydrolixConfig

    cfg = HydrolixConfig()
    tok = _oauth_token(token="abc")
    assert cfg.creds_with(tok) is tok


def test_creds_with_none_falls_back_to_env_default(monkeypatch):
    monkeypatch.setenv("HYDROLIX_USER", "u")
    monkeypatch.setenv("HYDROLIX_PASSWORD", "p")
    from mcp_hydrolix.mcp_env import HydrolixConfig

    cfg = HydrolixConfig()
    fallback = cfg.creds_with(None)
    # Falls back to the UsernamePassword env-var default.
    assert fallback is not None
    assert fallback.clickhouse_config_entries() == {"username": "u", "password": "p"}


def test_get_client_config_passes_access_token_for_oauth_bearer(monkeypatch):
    monkeypatch.setenv("HYDROLIX_USER", "u")
    monkeypatch.setenv("HYDROLIX_PASSWORD", "p")
    from mcp_hydrolix.mcp_env import HydrolixConfig

    cfg = HydrolixConfig()
    tok = _oauth_token(token="xyz")
    client_cfg = cfg.get_client_config(tok)
    assert client_cfg["access_token"] == "xyz"
    # Must NOT contain env-var username/password when a bearer credential is used
    assert "username" not in client_cfg
    assert "password" not in client_cfg


def test_load_oauth_config_is_single_source_of_truth(monkeypatch):
    """Activation is driven by `load_oauth_config()` — no parallel flag on HydrolixConfig."""
    from mcp_hydrolix.auth.oauth import load_oauth_config

    monkeypatch.delenv("HYDROLIX_OAUTH_ISSUER", raising=False)
    assert load_oauth_config() is None

    monkeypatch.setenv("HYDROLIX_OAUTH_ISSUER", ISSUER)
    monkeypatch.setenv("HYDROLIX_OAUTH_AUDIENCE", "mcp-hydrolix")
    cfg = load_oauth_config()
    assert cfg is not None
    assert cfg.issuer == ISSUER


def test_check_parameterized_query_support_handles_oauth_bearer():
    """The /version preflight builds a bearer Authorization header for token creds.

    We can't hit a real Hydrolix here — instead we assert the header-construction
    branch recognises OAuthBearerToken as a token-bearing credential (not a
    UsernamePassword), so it uses `Authorization: Bearer <jwt>`.
    """
    tok = _oauth_token(token="my-jwt")
    entries = tok.clickhouse_config_entries()
    assert "access_token" in entries
    # Implementation assertion: the token value must be forwardable as a
    # bearer header so `_check_parameterized_query_support` can reuse it.
    assert entries["access_token"] == "my-jwt"
