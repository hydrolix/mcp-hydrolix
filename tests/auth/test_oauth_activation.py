"""Startup-time OIDC discovery + JWKS fetch, with fail-open-to-legacy-auth semantics."""

import httpx
import respx
from fastmcp.server.auth.providers.jwt import RSAKeyPair

from mcp_hydrolix.auth.oauth import (
    OAuthConfig,
    OAuthHydrolixAuthProvider,
    try_activate_oauth,
)

ISSUER = "https://example.com/keycloak/realms/hydrolix-users"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
JWKS_URI = f"{ISSUER}/protocol/openid-connect/certs"


def _config(
    jwks_uri: str | None = None,
    audience: tuple[str, ...] = ("mcp-hydrolix",),
) -> OAuthConfig:
    return OAuthConfig(
        issuer=ISSUER,
        audience=audience,
        jwks_uri=jwks_uri,
        required_scopes=(),
        resource_url=None,
    )


def _jwks_for(keypair: RSAKeyPair) -> dict:
    # FastMCP's JWTVerifier accepts PEM via public_key; for JWKS it needs a JWK dict.
    # We only care that the endpoint returns a plausible JWKS payload — the provider
    # uses the PEM-shaped `public_key` path here because we construct JWTVerifier
    # with a static key in activation tests (no JWKS fetch during unit tests).
    return {"keys": [{"kty": "RSA", "kid": "test", "use": "sig", "alg": "RS256"}]}


async def test_none_when_config_none():
    assert await try_activate_oauth(None) is None


@respx.mock(assert_all_mocked=True)
async def test_reachable_discovery_returns_provider(respx_mock, caplog):
    kp = RSAKeyPair.generate()
    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(
            200,
            json={"issuer": ISSUER, "jwks_uri": JWKS_URI},
        )
    )
    respx_mock.get(JWKS_URI).mock(return_value=httpx.Response(200, json=_jwks_for(kp)))

    provider = await try_activate_oauth(_config())

    assert isinstance(provider, OAuthHydrolixAuthProvider)
    # No startup warnings on the happy path.
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings == [], [r.message for r in warnings]


@respx.mock(assert_all_mocked=True)
async def test_discovery_503_returns_none_with_warning(respx_mock, caplog):
    respx_mock.get(DISCOVERY_URL).mock(return_value=httpx.Response(503))

    caplog.set_level("WARNING", logger="mcp-hydrolix")
    result = await try_activate_oauth(_config())

    assert result is None
    assert any(
        "OAuth configured but not activated" in r.message and "503" in r.message
        for r in caplog.records
    ), [r.message for r in caplog.records]


@respx.mock(assert_all_mocked=True)
async def test_discovery_network_error_returns_none_with_warning(respx_mock, caplog):
    respx_mock.get(DISCOVERY_URL).mock(side_effect=httpx.ConnectError("no route"))

    caplog.set_level("WARNING", logger="mcp-hydrolix")
    result = await try_activate_oauth(_config())

    assert result is None
    assert any("OAuth configured but not activated" in r.message for r in caplog.records)


@respx.mock(assert_all_mocked=True)
async def test_explicit_jwks_uri_skips_discovery(respx_mock, caplog):
    kp = RSAKeyPair.generate()
    respx_mock.get(JWKS_URI).mock(return_value=httpx.Response(200, json=_jwks_for(kp)))
    # No discovery call should happen when jwks_uri is explicit.

    result = await try_activate_oauth(_config(jwks_uri=JWKS_URI))

    assert isinstance(result, OAuthHydrolixAuthProvider)


@respx.mock(assert_all_mocked=True)
async def test_discovery_returns_malformed_json(respx_mock, caplog):
    respx_mock.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, content=b"not json"))

    caplog.set_level("WARNING", logger="mcp-hydrolix")
    result = await try_activate_oauth(_config())
    assert result is None
    assert any("OAuth configured but not activated" in r.message for r in caplog.records)


@respx.mock(assert_all_mocked=True)
async def test_discovery_missing_jwks_uri(respx_mock, caplog):
    respx_mock.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, json={"issuer": ISSUER}))

    caplog.set_level("WARNING", logger="mcp-hydrolix")
    result = await try_activate_oauth(_config())
    assert result is None
