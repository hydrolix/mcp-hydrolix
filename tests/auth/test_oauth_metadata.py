"""RFC 9728 protected-resource-metadata + WWW-Authenticate challenge.

Both behaviours are provided by FastMCP's `RemoteAuthProvider` + the MCP SDK's
bearer auth middleware — `OAuthHydrolixAuthProvider` just has to pass the right
wiring through `super().__init__`. These tests pin that contract so operator
changes (e.g. renaming the env var that feeds `base_url`) don't silently
produce a broken metadata URL or a 401 without the `resource_metadata`
challenge.
"""

import contextlib

import httpx
import pytest
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair
from httpx import ASGITransport

from mcp_hydrolix.auth.oauth import OAuthConfig, OAuthHydrolixAuthProvider

ISSUER = "https://example.com/keycloak/realms/hydrolix-users"
BASE_URL = "https://mcp.example.com"
MCP_PATH = "/mcp"


@contextlib.asynccontextmanager
async def _lifespan_client(app):
    """Wrap the ASGI app in its lifespan context, so FastMCP's session manager is live."""
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            yield client


@pytest.fixture
def keypair() -> RSAKeyPair:
    return RSAKeyPair.generate()


@pytest.fixture
def provider(keypair: RSAKeyPair) -> OAuthHydrolixAuthProvider:
    cfg = OAuthConfig(
        issuer=ISSUER,
        audience=("mcp-hydrolix",),
        jwks_uri=None,
        required_scopes=("hydrolix:read",),
        resource_url=BASE_URL,
    )
    verifier = JWTVerifier(
        public_key=keypair.public_key,
        issuer=ISSUER,
        audience=["mcp-hydrolix"],
        algorithm="RS256",
        required_scopes=["hydrolix:read"],
    )
    return OAuthHydrolixAuthProvider(cfg, verifier, BASE_URL)


@pytest.fixture
def asgi_app(provider):
    mcp = FastMCP(name="test-oauth", auth=provider)
    return mcp.http_app(transport="http", path=MCP_PATH)


async def test_protected_resource_metadata_endpoint_exists(asgi_app):
    async with httpx.AsyncClient(
        transport=ASGITransport(app=asgi_app), base_url=BASE_URL
    ) as client:
        r = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    body = r.json()
    # RFC 9728 §2 required fields
    assert body["resource"] == f"{BASE_URL}{MCP_PATH}"
    assert body["authorization_servers"] == [ISSUER + "/"] or body["authorization_servers"] == [
        ISSUER
    ]
    assert body["scopes_supported"] == ["hydrolix:read"]
    assert body["bearer_methods_supported"] == ["header"]
    assert body["resource_name"] == "mcp-hydrolix"


async def test_invalid_bearer_returns_401_with_www_authenticate(asgi_app):
    async with httpx.AsyncClient(
        transport=ASGITransport(app=asgi_app), base_url=BASE_URL
    ) as client:
        r = await client.post(
            MCP_PATH,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": "Bearer not.a.jwt"},
        )
    assert r.status_code == 401
    challenge = r.headers.get("www-authenticate")
    assert challenge is not None
    assert challenge.lower().startswith("bearer")
    assert 'error="invalid_token"' in challenge
    # RFC 9728 §5.1: challenge must advertise the resource metadata URL.
    assert "resource_metadata=" in challenge
    assert "/.well-known/oauth-protected-resource/mcp" in challenge


async def test_missing_bearer_returns_401_with_www_authenticate(asgi_app):
    """No Authorization header at all must still get a proper challenge.

    This is the legacy-fallback blocker: when OAuth is active, the server
    never silently uses env-var service-account creds for an HTTP caller;
    the caller gets a 401 and must present a JWT.
    """
    async with httpx.AsyncClient(
        transport=ASGITransport(app=asgi_app), base_url=BASE_URL
    ) as client:
        r = await client.post(
            MCP_PATH,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
    assert r.status_code == 401
    challenge = r.headers.get("www-authenticate")
    assert challenge is not None
    assert challenge.lower().startswith("bearer")
    assert "resource_metadata=" in challenge


async def test_expired_bearer_returns_401(keypair, asgi_app):
    token = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience="mcp-hydrolix",
        scopes=["hydrolix:read"],
        expires_in_seconds=-60,
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=asgi_app), base_url=BASE_URL
    ) as client:
        r = await client.post(
            MCP_PATH,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 401


async def test_valid_bearer_reaches_mcp_layer(keypair, asgi_app):
    """A verifying bearer passes the auth middleware and lands at MCP.

    We don't assert on the JSON-RPC response shape — just that it is no longer
    the 401 auth rejection. This proves the middleware chain is wired correctly.
    """
    token = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience="mcp-hydrolix",
        scopes=["hydrolix:read"],
    )
    async with _lifespan_client(asgi_app) as client:
        r = await client.post(
            MCP_PATH,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )
    # Anything other than 401 means the auth middleware accepted the token.
    assert r.status_code != 401, (
        f"Valid bearer was rejected: {r.status_code} {r.headers.get('www-authenticate')}"
    )


async def test_metadata_advertises_required_scopes_when_configured(keypair):
    cfg = OAuthConfig(
        issuer=ISSUER,
        audience=("mcp-hydrolix",),
        jwks_uri=None,
        required_scopes=("hydrolix:read", "hydrolix:write"),
        resource_url=BASE_URL,
    )
    verifier = JWTVerifier(
        public_key=keypair.public_key,
        issuer=ISSUER,
        audience=["mcp-hydrolix"],
        algorithm="RS256",
        required_scopes=["hydrolix:read", "hydrolix:write"],
    )
    provider = OAuthHydrolixAuthProvider(cfg, verifier, BASE_URL)
    app = FastMCP(name="t", auth=provider).http_app(transport="http", path=MCP_PATH)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
        r = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    assert r.json()["scopes_supported"] == ["hydrolix:read", "hydrolix:write"]
