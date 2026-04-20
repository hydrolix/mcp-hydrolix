"""JWT verification behaviour through OAuthHydrolixAuthProvider.

These tests wire a static-public-key `JWTVerifier` into the provider so we
can exercise every verification branch without touching the network.
"""

import time

import pytest
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

from mcp_hydrolix.auth.oauth import (
    OAuthBearerToken,
    OAuthConfig,
    OAuthHydrolixAuthProvider,
)

ISSUER = "https://example.com/keycloak/realms/hydrolix-users"
AUDIENCE = ("mcp-hydrolix", "config-api")


@pytest.fixture
def keypair() -> RSAKeyPair:
    return RSAKeyPair.generate()


@pytest.fixture
def provider(keypair: RSAKeyPair) -> OAuthHydrolixAuthProvider:
    cfg = OAuthConfig(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_uri=None,
        required_scopes=(),
        resource_url="https://mcp.example.com/mcp",
    )
    verifier = JWTVerifier(
        public_key=keypair.public_key,
        issuer=ISSUER,
        audience=list(AUDIENCE),
        algorithm="RS256",
    )
    return OAuthHydrolixAuthProvider(cfg, verifier, "https://mcp.example.com/mcp")


async def test_happy_path_returns_access_token_that_yields_bearer_credential(keypair, provider):
    token = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience="mcp-hydrolix",
        scopes=["hydrolix:read"],
        additional_claims={"email": "alice@example.com"},
    )

    result = await provider.verify_token(token)

    assert result is not None
    credential = result.as_credential()
    assert isinstance(credential, OAuthBearerToken)
    assert credential.token == token
    assert credential.subject == "alice"
    assert credential.clickhouse_config_entries() == {"access_token": token}
    assert credential.claims["email"] == "alice@example.com"


async def test_expired_token_rejected(keypair, provider):
    token = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience="mcp-hydrolix",
        expires_in_seconds=-60,
    )
    assert await provider.verify_token(token) is None


async def test_wrong_issuer_rejected(keypair, provider):
    token = keypair.create_token(
        subject="alice",
        issuer="https://attacker.example.com/",
        audience="mcp-hydrolix",
    )
    assert await provider.verify_token(token) is None


async def test_audience_not_in_allowlist_rejected(keypair, provider):
    token = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience="some-other-api",
    )
    assert await provider.verify_token(token) is None


async def test_audience_matching_second_allowlist_entry_accepted(keypair, provider):
    token = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience="config-api",
    )
    assert await provider.verify_token(token) is not None


async def test_bad_signature_rejected(provider):
    other = RSAKeyPair.generate()
    token = other.create_token(
        subject="mallory",
        issuer=ISSUER,
        audience="mcp-hydrolix",
    )
    assert await provider.verify_token(token) is None


async def test_gibberish_rejected(provider):
    assert await provider.verify_token("not.a.jwt") is None
    assert await provider.verify_token("") is None


async def test_required_scopes_enforced(keypair):
    cfg = OAuthConfig(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_uri=None,
        required_scopes=("hydrolix:read",),
        resource_url="https://mcp.example.com/mcp",
    )
    verifier = JWTVerifier(
        public_key=keypair.public_key,
        issuer=ISSUER,
        audience=list(AUDIENCE),
        algorithm="RS256",
        required_scopes=list(cfg.required_scopes),
    )
    provider = OAuthHydrolixAuthProvider(cfg, verifier, "https://mcp.example.com/mcp")

    missing = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience="mcp-hydrolix",
        scopes=["other:scope"],
    )
    assert await provider.verify_token(missing) is None

    present = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience="mcp-hydrolix",
        scopes=["hydrolix:read", "other:scope"],
    )
    assert await provider.verify_token(present) is not None


async def test_expires_at_surfaces_from_exp_claim(keypair, provider):
    token = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience="mcp-hydrolix",
        expires_in_seconds=300,
    )
    result = await provider.verify_token(token)
    assert result is not None
    # exp should be in the future, within a few seconds of "now + 300".
    assert result.expires_at is not None
    assert abs(result.expires_at - (int(time.time()) + 300)) < 5
