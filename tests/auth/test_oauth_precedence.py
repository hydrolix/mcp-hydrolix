"""Precedence: OAuth verifier first, legacy SA verifier as fallback.

When OAuth is active on a bearer (or `?token=`), the middleware chain tries
`JWTVerifier` first. If that rejects the token, the same token is tried
against the legacy `ServiceAccountToken` parser so pre-OAuth service-account
callers keep working. A token that neither an OAuth JWT nor a parseable SA
JWT — junk, missing claims, expired — falls off the end of the chain and
the caller gets `401 + WWW-Authenticate`.

These tests exercise the middleware chain directly rather than spinning up a
full ASGI app — the HTTP end-to-end flow is covered by the Phase 7
integration test against `http_app()`.
"""

import time
from unittest.mock import MagicMock

import jwt
import pytest
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend
from starlette.middleware.authentication import AuthenticationMiddleware

from mcp_hydrolix.auth.credentials import ServiceAccountToken
from mcp_hydrolix.auth.mcp_providers import (
    TOKEN_PARAM,
    ChainedAuthBackend,
    GetParamAuthBackend,
    HydrolixCredentialChain,
)
from mcp_hydrolix.auth.oauth import (
    OAuthBearerToken,
    OAuthConfig,
    OAuthHydrolixAuthProvider,
)

ISSUER = "https://example.com/keycloak/realms/hydrolix-users"
AUDIENCE = ("mcp-hydrolix",)
BASE_URL = "https://mcp.example.com/mcp"


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
        resource_url=BASE_URL,
    )
    verifier = JWTVerifier(
        public_key=keypair.public_key,
        issuer=ISSUER,
        audience=list(AUDIENCE),
        algorithm="RS256",
    )
    return OAuthHydrolixAuthProvider(cfg, verifier, BASE_URL)


def _make_conn(*, auth_header: str | None = None, query_token: str | None = None):
    """Build a minimal HTTPConnection-compatible object for auth backends."""
    headers: list[tuple[bytes, bytes]] = []
    if auth_header is not None:
        headers.append((b"authorization", auth_header.encode()))
    query_string = f"{TOKEN_PARAM}={query_token}".encode() if query_token is not None else b""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": headers,
        "query_string": query_string,
    }
    conn = MagicMock()
    conn.scope = scope
    conn.headers = {k.decode(): v.decode() for k, v in headers}
    return conn


def _sa_jwt(
    *,
    subject: str = "svc-account",
    issuer: str = "https://sa-issuer.example.com",
    offset_sec: int = 3600,
) -> str:
    """Craft a JWT that `ServiceAccountToken` will accept.

    Signing key is irrelevant — SA parsing deliberately skips signature
    verification (see `credentials.ServiceAccountToken`).
    """
    now = int(time.time())
    payload = {
        "sub": subject,
        "iss": issuer,
        "iat": now,
        "exp": now + offset_sec,
    }
    return jwt.encode(payload, "irrelevant-secret", algorithm="HS256")


def test_middleware_chain_tries_oauth_then_sa_fallback(provider):
    """OAuth verifier first, legacy SA verifier second — for both bearer and query."""
    mws = provider.get_middleware()
    assert len(mws) == 2

    auth_mw = mws[0]
    assert auth_mw.cls is AuthenticationMiddleware
    backend = auth_mw.kwargs["backend"]
    assert isinstance(backend, ChainedAuthBackend)

    types = [type(b) for b in backend.backends]
    assert types == [
        BearerAuthBackend,
        GetParamAuthBackend,
        BearerAuthBackend,
        GetParamAuthBackend,
    ]

    # First pair verifies via the OAuth provider itself; second pair falls back
    # to the SA verifier.
    oauth_bearer, oauth_query, sa_bearer, sa_query = backend.backends
    assert oauth_bearer.token_verifier is provider
    assert oauth_query.token_verifier is provider
    assert sa_bearer.token_verifier is not provider
    assert sa_query.token_verifier is not provider
    # Both SA backends share the same verifier instance.
    assert sa_bearer.token_verifier is sa_query.token_verifier


async def test_junk_bearer_rejected_by_both_verifiers(provider):
    """A bearer that's not a valid JWT at all must fail OAuth and SA → 401."""
    chain = ChainedAuthBackend(provider.get_middleware()[0].kwargs["backend"].backends)
    conn = _make_conn(auth_header="Bearer not.a.jwt")
    assert await chain.authenticate(conn) is None


async def test_expired_bearer_rejected_by_both_verifiers(keypair, provider):
    """An expired JWT fails OAuth (exp check) AND SA (also enforces exp) → 401."""
    chain = ChainedAuthBackend(provider.get_middleware()[0].kwargs["backend"].backends)
    token = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience="mcp-hydrolix",
        expires_in_seconds=-60,
    )
    conn = _make_conn(auth_header=f"Bearer {token}")
    assert await chain.authenticate(conn) is None


async def test_valid_oauth_bearer_wins_over_sa_verifier(keypair, provider):
    """Valid OAuth bearer → first backend returns OAuthBearerToken, SA never runs."""
    chain = ChainedAuthBackend(provider.get_middleware()[0].kwargs["backend"].backends)
    token = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience="mcp-hydrolix",
        scopes=["hydrolix:read"],
    )
    conn = _make_conn(auth_header=f"Bearer {token}")
    result = await chain.authenticate(conn)
    assert result is not None
    _, user = result
    access = getattr(user, "access_token", None)
    assert access is not None
    cred = access.as_credential()
    assert isinstance(cred, OAuthBearerToken)
    assert cred.token == token


async def test_non_oauth_bearer_falls_back_to_sa_verification(provider):
    """A JWT that is not an OAuth token (wrong aud) is still accepted as SA.

    This is the explicit fallback: a pre-OAuth caller presenting a legacy
    service-account JWT keeps working when the operator flips OAuth on.
    """
    chain = ChainedAuthBackend(provider.get_middleware()[0].kwargs["backend"].backends)
    sa_token = _sa_jwt(subject="svc-1")
    conn = _make_conn(auth_header=f"Bearer {sa_token}")
    result = await chain.authenticate(conn)
    assert result is not None
    _, user = result
    access = getattr(user, "access_token", None)
    assert isinstance(access, HydrolixCredentialChain.ServiceAccountAccess)
    cred = access.as_credential()
    assert isinstance(cred, ServiceAccountToken)
    assert cred.service_account_id == "svc-1"


async def test_valid_oauth_query_param_accepted(keypair, provider):
    """`?token=<oauth-jwt>` succeeds via the OAuth query backend."""
    chain = ChainedAuthBackend(provider.get_middleware()[0].kwargs["backend"].backends)
    token = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience="mcp-hydrolix",
    )
    conn = _make_conn(query_token=token)
    result = await chain.authenticate(conn)
    assert result is not None
    _, user = result
    access = user.access_token
    assert access.as_credential().__class__.__name__ == "OAuthBearerToken"


async def test_sa_query_param_accepted_as_fallback(provider):
    """`?token=<legacy-sa-jwt>` succeeds via the SA query fallback backend."""
    chain = ChainedAuthBackend(provider.get_middleware()[0].kwargs["backend"].backends)
    sa_token = _sa_jwt(subject="svc-2")
    conn = _make_conn(query_token=sa_token)
    result = await chain.authenticate(conn)
    assert result is not None
    _, user = result
    access = user.access_token
    assert isinstance(access, HydrolixCredentialChain.ServiceAccountAccess)


async def test_junk_query_param_rejected_by_both_verifiers(provider):
    chain = ChainedAuthBackend(provider.get_middleware()[0].kwargs["backend"].backends)
    conn = _make_conn(query_token="not.a.jwt")
    assert await chain.authenticate(conn) is None


async def test_no_credentials_returns_none(provider):
    """No bearer and no query param → chain returns None → Starlette surfaces 401."""
    chain = ChainedAuthBackend(provider.get_middleware()[0].kwargs["backend"].backends)
    conn = _make_conn()
    assert await chain.authenticate(conn) is None


async def test_provider_verify_token_returns_oauth_access_token(keypair, provider):
    """Provider-level verify_token wraps verified tokens as _OAuthAccessToken."""
    token = keypair.create_token(subject="alice", issuer=ISSUER, audience="mcp-hydrolix")
    result = await provider.verify_token(token)
    assert result is not None
    cred = result.as_credential()
    assert isinstance(cred, OAuthBearerToken)
    assert cred.token == token
    assert cred.clickhouse_config_entries() == {"access_token": token}


async def test_provider_verify_token_returns_none_for_bad_token(provider):
    """Provider verify_token is OAuth-only — SA fallback lives in the chain, not here."""
    assert await provider.verify_token("bad.token") is None
