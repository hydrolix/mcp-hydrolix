"""End-to-end activation: Keycloak discovery → JWKS fetch → HTTP bearer flow.

Exercises the full pipeline a production operator would hit:

1. `try_activate_oauth` fetches OIDC discovery.
2. It validates the JWKS endpoint responds with a live RSA JWK.
3. The resulting `OAuthHydrolixAuthProvider` is plugged into a FastMCP app.
4. ASGI requests with valid / invalid tokens hit the real verifier and get
   the expected 401 / authenticated outcomes.

The other test files cover each stage in isolation; this one pins that the
seams between them still line up.
"""

import contextlib
import json

import httpx
import respx
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import RSAKeyPair
from httpx import ASGITransport
from jwt.algorithms import RSAAlgorithm

from mcp_hydrolix.auth.oauth import (
    OAuthConfig,
    OAuthHydrolixAuthProvider,
    try_activate_oauth,
)

ISSUER = "https://example.com/keycloak/realms/hydrolix-users"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
JWKS_URI = f"{ISSUER}/protocol/openid-connect/certs"
BASE_URL = "https://mcp.example.com"
MCP_PATH = "/mcp"


def _real_jwks_for(kp: RSAKeyPair) -> dict:
    """Serialise an RSA public key into a Keycloak-shaped JWKS payload."""
    pub = load_pem_public_key(kp.public_key.encode())
    jwk = json.loads(RSAAlgorithm.to_jwk(pub))
    jwk["kid"] = "test-key-1"
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return {"keys": [jwk]}


@contextlib.asynccontextmanager
async def _lifespan_client(app):
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            yield client


@respx.mock(assert_all_mocked=True)
async def test_full_activation_then_verified_http_flow(respx_mock):
    kp = RSAKeyPair.generate()
    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(200, json={"issuer": ISSUER, "jwks_uri": JWKS_URI})
    )
    # JWKS gets hit at least twice: once by try_activate_oauth for validation,
    # and once lazily by the verifier on first token verification.
    respx_mock.get(JWKS_URI).mock(return_value=httpx.Response(200, json=_real_jwks_for(kp)))

    cfg = OAuthConfig(
        issuer=ISSUER,
        audience=("mcp-hydrolix",),
        jwks_uri=None,  # force discovery path
        required_scopes=("hydrolix:read",),
        resource_url=BASE_URL,
    )
    provider = await try_activate_oauth(cfg, base_url=BASE_URL)
    assert isinstance(provider, OAuthHydrolixAuthProvider)

    mcp = FastMCP(name="e2e", auth=provider)
    app = mcp.http_app(transport="http", path=MCP_PATH)

    async with _lifespan_client(app) as client:
        # 1. Metadata endpoint is served.
        meta = await client.get("/.well-known/oauth-protected-resource/mcp")
        assert meta.status_code == 200
        assert meta.json()["resource"] == f"{BASE_URL}{MCP_PATH}"

        # 2. Invalid bearer → 401 with challenge.
        bad = await client.post(
            MCP_PATH,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": "Bearer junk"},
        )
        assert bad.status_code == 401
        assert "resource_metadata=" in bad.headers.get("www-authenticate", "")

        # 3. Valid bearer → reaches MCP (not 401).
        token = kp.create_token(
            subject="alice",
            issuer=ISSUER,
            audience="mcp-hydrolix",
            scopes=["hydrolix:read"],
        )
        good = await client.post(
            MCP_PATH,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"},
                },
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )
        assert good.status_code != 401, good.text


@respx.mock(assert_all_mocked=True)
async def test_explicit_jwks_uri_end_to_end(respx_mock):
    """Operator-supplied jwks_uri (backchannel) skips discovery, still verifies tokens."""
    kp = RSAKeyPair.generate()
    respx_mock.get(JWKS_URI).mock(return_value=httpx.Response(200, json=_real_jwks_for(kp)))
    # No discovery mock — any call to it would fail the test.

    cfg = OAuthConfig(
        issuer=ISSUER,
        audience=("mcp-hydrolix",),
        jwks_uri=JWKS_URI,
        required_scopes=(),
        resource_url=BASE_URL,
    )
    provider = await try_activate_oauth(cfg, base_url=BASE_URL)
    assert provider is not None

    mcp = FastMCP(name="e2e", auth=provider)
    app = mcp.http_app(transport="http", path=MCP_PATH)
    token = kp.create_token(subject="bob", issuer=ISSUER, audience="mcp-hydrolix")

    async with _lifespan_client(app) as client:
        r = await client.post(
            MCP_PATH,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"},
                },
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )
        assert r.status_code != 401
