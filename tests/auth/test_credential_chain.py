"""Direct tests for `HydrolixCredentialChain` — the non-OAuth default auth provider.

Ensures `verify_token` validates SA JWTs eagerly and returns `None` for anything
that isn't a parseable, unexpired SA token. This is the path `mcp.auth` takes
when `HYDROLIX_OAUTH_ISSUER` is unset (see `mcp_hydrolix/mcp_server.py`).

Historical note: before unifying with `_SATokenVerifier`, `verify_token` here
blindly wrapped any string in a `ServiceAccountAccess` and deferred validation
until `get_request_credential()`. That produced 500-level errors for junk
bearers (since `get_request_credential` only caught `jwt.DecodeError`, not
`InvalidIssuerError`/`ExpiredSignatureError`). These tests pin the new
401-on-junk behavior.
"""

import time

import jwt

from mcp_hydrolix.auth.mcp_providers import HydrolixCredentialChain


def _sa_jwt(
    *,
    subject: str = "svc-account",
    issuer: str = "https://sa-issuer.example.com",
    offset_sec: int = 3600,
) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "iss": issuer,
        "iat": now,
        "exp": now + offset_sec,
    }
    return jwt.encode(payload, "irrelevant-secret", algorithm="HS256")


async def test_verify_token_accepts_valid_sa_jwt():
    chain = HydrolixCredentialChain(expected_issuer=None)
    token = _sa_jwt(subject="svc-1")
    access = await chain.verify_token(token)
    assert isinstance(access, HydrolixCredentialChain.ServiceAccountAccess)
    assert access.token == token


async def test_verify_token_returns_none_for_junk_bearer():
    """Regression: junk must fail at the verifier (→ 401), not later as 500."""
    chain = HydrolixCredentialChain(expected_issuer=None)
    assert await chain.verify_token("not.a.jwt") is None


async def test_verify_token_returns_none_for_expired_sa_jwt():
    """Regression: expired JWT must fail at the verifier, not propagate as 500."""
    chain = HydrolixCredentialChain(expected_issuer=None)
    token = _sa_jwt(subject="svc-1", offset_sec=-60)
    assert await chain.verify_token(token) is None


async def test_verify_token_enforces_expected_issuer():
    chain = HydrolixCredentialChain(expected_issuer="https://expected-issuer.example.com")
    wrong_issuer_token = _sa_jwt(issuer="https://sa-issuer.example.com")
    assert await chain.verify_token(wrong_issuer_token) is None

    right_issuer_token = _sa_jwt(issuer="https://expected-issuer.example.com")
    access = await chain.verify_token(right_issuer_token)
    assert isinstance(access, HydrolixCredentialChain.ServiceAccountAccess)
