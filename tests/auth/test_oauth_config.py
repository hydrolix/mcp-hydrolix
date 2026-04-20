"""Env-var parsing and validation for OAuthConfig."""

import pytest

from mcp_hydrolix.auth.oauth import (
    OAuthConfig,
    OAuthConfigError,
    load_oauth_config,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip every HYDROLIX_OAUTH_* var so tests start from a known baseline."""
    for key in [
        "HYDROLIX_OAUTH_ISSUER",
        "HYDROLIX_OAUTH_AUDIENCE",
        "HYDROLIX_OAUTH_JWKS_URI",
        "HYDROLIX_OAUTH_REQUIRED_SCOPES",
        "HYDROLIX_OAUTH_RESOURCE_URL",
        "HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_returns_none_when_issuer_unset():
    assert load_oauth_config() is None


def test_missing_audience_raises(monkeypatch):
    monkeypatch.setenv(
        "HYDROLIX_OAUTH_ISSUER",
        "https://example.com/keycloak/realms/hydrolix-users",
    )
    with pytest.raises(OAuthConfigError, match="HYDROLIX_OAUTH_AUDIENCE"):
        load_oauth_config()


def test_audience_comma_list_parsed_and_stripped(monkeypatch):
    monkeypatch.setenv(
        "HYDROLIX_OAUTH_ISSUER",
        "https://example.com/keycloak/realms/hydrolix-users",
    )
    monkeypatch.setenv("HYDROLIX_OAUTH_AUDIENCE", "mcp-hydrolix, config-api ,other")
    cfg = load_oauth_config()
    assert cfg is not None
    assert cfg.audience == ("mcp-hydrolix", "config-api", "other")


def test_required_scopes_comma_list_parsed(monkeypatch):
    monkeypatch.setenv(
        "HYDROLIX_OAUTH_ISSUER",
        "https://example.com/keycloak/realms/hydrolix-users",
    )
    monkeypatch.setenv("HYDROLIX_OAUTH_AUDIENCE", "mcp-hydrolix")
    monkeypatch.setenv("HYDROLIX_OAUTH_REQUIRED_SCOPES", "hydrolix:read, hydrolix:write")
    cfg = load_oauth_config()
    assert cfg is not None
    assert cfg.required_scopes == ("hydrolix:read", "hydrolix:write")


def test_jwks_uri_default_derived_from_issuer(monkeypatch):
    monkeypatch.setenv(
        "HYDROLIX_OAUTH_ISSUER",
        "https://example.com/keycloak/realms/hydrolix-users",
    )
    monkeypatch.setenv("HYDROLIX_OAUTH_AUDIENCE", "mcp-hydrolix")
    cfg = load_oauth_config()
    assert cfg is not None
    assert cfg.jwks_uri is None  # deferred to discovery if unset
    assert cfg.discovery_url == (
        "https://example.com/keycloak/realms/hydrolix-users/.well-known/openid-configuration"
    )


def test_http_jwks_rejected_without_insecure_flag(monkeypatch):
    monkeypatch.setenv(
        "HYDROLIX_OAUTH_ISSUER",
        "https://example.com/keycloak/realms/hydrolix-users",
    )
    monkeypatch.setenv("HYDROLIX_OAUTH_AUDIENCE", "mcp-hydrolix")
    monkeypatch.setenv(
        "HYDROLIX_OAUTH_JWKS_URI",
        "http://keycloak:8080/keycloak/realms/hydrolix-users/protocol/openid-connect/certs",
    )
    with pytest.raises(OAuthConfigError, match="HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS"):
        load_oauth_config()


def test_http_jwks_accepted_with_insecure_flag(monkeypatch):
    monkeypatch.setenv(
        "HYDROLIX_OAUTH_ISSUER",
        "https://example.com/keycloak/realms/hydrolix-users",
    )
    monkeypatch.setenv("HYDROLIX_OAUTH_AUDIENCE", "mcp-hydrolix")
    jwks = "http://keycloak:8080/keycloak/realms/hydrolix-users/protocol/openid-connect/certs"
    monkeypatch.setenv("HYDROLIX_OAUTH_JWKS_URI", jwks)
    monkeypatch.setenv("HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS", "true")
    cfg = load_oauth_config()
    assert cfg is not None
    assert cfg.jwks_uri == jwks


def test_is_frozen():
    cfg = OAuthConfig(
        issuer="https://example.com/keycloak/realms/hydrolix-users",
        audience=("mcp-hydrolix",),
        jwks_uri=None,
        required_scopes=(),
        resource_url=None,
    )
    with pytest.raises((AttributeError, Exception)):
        cfg.issuer = "other"  # type: ignore[misc]


def test_blank_audience_value_rejected(monkeypatch):
    monkeypatch.setenv(
        "HYDROLIX_OAUTH_ISSUER",
        "https://example.com/keycloak/realms/hydrolix-users",
    )
    monkeypatch.setenv("HYDROLIX_OAUTH_AUDIENCE", " , ")
    with pytest.raises(OAuthConfigError, match="HYDROLIX_OAUTH_AUDIENCE"):
        load_oauth_config()
