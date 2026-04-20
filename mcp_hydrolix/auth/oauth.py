"""OAuth 2.1 bearer-token support for remote MCP transports.

This module is loaded only when `HYDROLIX_OAUTH_ISSUER` is set. It wraps
FastMCP's `JWTVerifier` + `RemoteAuthProvider` into an auth provider that
hands verified JWTs off to Hydrolix via `clickhouse-connect`'s
`access_token` config entry.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Final, Optional
from urllib.parse import urlsplit

import httpx
from fastmcp.server.auth.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from mcp.server.auth.middleware.auth_context import (
    AuthContextMiddleware as McpAuthContextMiddleware,
)
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware

from mcp_hydrolix.auth.credentials import HydrolixCredential, ServiceAccountToken
from mcp_hydrolix.auth.mcp_providers import (
    TOKEN_PARAM,
    AccessToken,
    ChainedAuthBackend,
    GetParamAuthBackend,
    HydrolixCredentialChain,
)


logger = logging.getLogger("mcp-hydrolix")


DISCOVERY_TIMEOUT_SEC: Final[float] = 10.0


class OAuthConfigError(ValueError):
    """Raised when HYDROLIX_OAUTH_* environment variables are set but malformed."""


@dataclass(frozen=True)
class OAuthConfig:
    """Operator-facing OAuth configuration parsed from env vars."""

    issuer: str
    audience: tuple[str, ...]
    jwks_uri: Optional[str]
    required_scopes: tuple[str, ...]
    resource_url: Optional[str]
    allow_insecure_jwks: bool = False

    @property
    def discovery_url(self) -> str:
        return f"{self.issuer.rstrip('/')}/.well-known/openid-configuration"


def _split_comma_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _bool_env(raw: Optional[str]) -> bool:
    return (raw or "").strip().lower() == "true"


def load_oauth_config() -> Optional[OAuthConfig]:
    """Parse the HYDROLIX_OAUTH_* env vars.

    Returns None when OAuth is not activated (issuer unset). Raises
    `OAuthConfigError` on malformed activation.
    """
    issuer = (os.environ.get("HYDROLIX_OAUTH_ISSUER") or "").strip()
    if not issuer:
        return None

    audience_raw = os.environ.get("HYDROLIX_OAUTH_AUDIENCE", "")
    audience = _split_comma_list(audience_raw)
    if not audience:
        raise OAuthConfigError(
            "HYDROLIX_OAUTH_ISSUER is set but HYDROLIX_OAUTH_AUDIENCE is empty. "
            "Supply one or more accepted audience values, e.g. "
            "HYDROLIX_OAUTH_AUDIENCE=mcp-hydrolix."
        )

    jwks_uri_raw = (os.environ.get("HYDROLIX_OAUTH_JWKS_URI") or "").strip() or None
    allow_insecure = _bool_env(os.environ.get("HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS"))

    if jwks_uri_raw is not None:
        scheme = urlsplit(jwks_uri_raw).scheme.lower()
        if scheme == "http" and not allow_insecure:
            raise OAuthConfigError(
                "HYDROLIX_OAUTH_JWKS_URI uses plain HTTP but "
                "HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS is not 'true'. Set the flag "
                "only inside a trusted network segment (e.g. a Kubernetes "
                "cluster's backchannel), otherwise use HTTPS."
            )
        if scheme not in {"http", "https"}:
            raise OAuthConfigError(
                f"HYDROLIX_OAUTH_JWKS_URI must be an http(s) URL, got {jwks_uri_raw!r}."
            )

    required_scopes = tuple(_split_comma_list(os.environ.get("HYDROLIX_OAUTH_REQUIRED_SCOPES", "")))

    resource_url_raw = (os.environ.get("HYDROLIX_OAUTH_RESOURCE_URL") or "").strip() or None

    return OAuthConfig(
        issuer=issuer,
        audience=tuple(audience),
        jwks_uri=jwks_uri_raw,
        required_scopes=required_scopes,
        resource_url=resource_url_raw,
        allow_insecure_jwks=allow_insecure,
    )


@dataclass(frozen=True)
class OAuthBearerToken(HydrolixCredential):
    """Hydrolix credential produced by a verified OAuth bearer JWT.

    The raw token string is forwarded verbatim to Hydrolix via `access_token`.
    Claims are stored for logging / audit only — this class does not re-verify
    the token.
    """

    token: str
    subject: Optional[str]
    expires_at: Optional[int]
    claims: dict[str, Any]

    @property
    def service_account_id(self) -> str:
        """Label used in `create_hydrolix_client` logs."""
        return self.subject or "<oauth-bearer>"

    def clickhouse_config_entries(self) -> dict:
        return {"access_token": self.token}


class _OAuthAccessToken(AccessToken):
    """AccessToken subclass whose `as_credential()` returns an `OAuthBearerToken`."""

    def as_credential(self) -> OAuthBearerToken:
        return OAuthBearerToken(
            token=self.token,
            subject=str(self.claims.get("sub")) if self.claims.get("sub") is not None else None,
            expires_at=self.expires_at,
            claims=dict(self.claims),
        )


class _SATokenVerifier:
    """Verifier for legacy service-account JWTs — the fallback when OAuth fails.

    Matches `HydrolixCredentialChain` semantics: validates the JWT's claims
    (`iss`, `iat`, `exp`) but not its signature (SA signing keys are not
    publicly hosted, so `clickhouse-connect` validates at query time). Junk
    bearers that aren't JWTs at all return `None` here, so the combined
    chain rejects them with 401.
    """

    def __init__(self, expected_issuer: Optional[str]):
        self._expected_issuer = expected_issuer

    async def verify_token(self, token: str):
        try:
            ServiceAccountToken(token, self._expected_issuer)
        except Exception:
            return None
        return HydrolixCredentialChain.ServiceAccountAccess(
            token=token,
            client_id=HydrolixCredentialChain.ServiceAccountAccess.FAKE_CLIENT_ID,
            scopes=[HydrolixCredentialChain.ServiceAccountAccess.FAKE_SCOPE],
            expires_at=None,
            resource=None,
            claims={},
            expected_issuer=self._expected_issuer,
        )


class OAuthHydrolixAuthProvider(RemoteAuthProvider):
    """AuthProvider that accepts verified OAuth bearer tokens, with legacy SA fallback.

    A bearer (or `?token=`) is tried first against the OAuth `JWTVerifier`.
    If that rejects it, the same token is tried against a legacy
    `ServiceAccountToken` parser so pre-OAuth callers keep working. If
    BOTH reject it, the middleware returns `None` → MCP replies `401`
    with an `WWW-Authenticate: Bearer resource_metadata=…` challenge.
    """

    def __init__(
        self,
        cfg: OAuthConfig,
        verifier: JWTVerifier,
        base_url: str,
        *,
        sa_expected_issuer: Optional[str] = None,
    ):
        super().__init__(
            token_verifier=verifier,
            authorization_servers=[cfg.issuer],  # type: ignore[list-item]
            base_url=base_url,
            scopes_supported=list(cfg.required_scopes) or None,
            resource_name="mcp-hydrolix",
        )
        self._oauth_cfg = cfg
        self._sa_verifier = _SATokenVerifier(sa_expected_issuer)

    async def verify_token(self, token: str) -> Optional[_OAuthAccessToken]:
        verified = await self.token_verifier.verify_token(token)
        if verified is None:
            return None
        return _OAuthAccessToken(
            token=verified.token,
            client_id=verified.client_id,
            scopes=list(verified.scopes),
            expires_at=verified.expires_at,
            resource=verified.resource,
            claims=dict(getattr(verified, "claims", {}) or {}),
        )

    def get_middleware(self) -> list:
        return [
            Middleware(
                AuthenticationMiddleware,
                backend=ChainedAuthBackend(
                    [
                        BearerAuthBackend(self),
                        GetParamAuthBackend(self, TOKEN_PARAM),
                        BearerAuthBackend(self._sa_verifier),
                        GetParamAuthBackend(self._sa_verifier, TOKEN_PARAM),
                    ]
                ),
            ),
            Middleware(McpAuthContextMiddleware),
        ]


async def _fetch_json(client: httpx.AsyncClient, url: str) -> dict:
    response = await client.get(url, timeout=DISCOVERY_TIMEOUT_SEC)
    response.raise_for_status()
    return response.json()


def _activation_failure(reason: str) -> None:
    logger.warning(
        "OAuth configured but not activated: %s. "
        "Falling back to service-account / username-password auth.",
        reason,
    )


async def try_activate_oauth(
    cfg: Optional[OAuthConfig],
    *,
    verify_tls: bool = True,
    base_url: Optional[str] = None,
) -> Optional[OAuthHydrolixAuthProvider]:
    """Attempt to construct an `OAuthHydrolixAuthProvider`.

    Returns None (with a structured `WARNING` log) when the config is absent
    or the discovery / JWKS fetch fails. Any exception reaching here is
    swallowed in service of the fail-open-at-startup contract: the server
    keeps working with legacy auth. Once activated, individual request-time
    verification failures still fail closed (`401`, no fallback).
    """
    if cfg is None:
        return None

    effective_resource_url = (
        cfg.resource_url or base_url or f"https://{cfg.issuer.split('//', 1)[-1]}"
    )

    try:
        async with httpx.AsyncClient(verify=verify_tls) as client:
            jwks_uri = cfg.jwks_uri
            if jwks_uri is None:
                discovery = await _fetch_json(client, cfg.discovery_url)
                jwks_uri = discovery.get("jwks_uri")
                if not jwks_uri:
                    _activation_failure(
                        f"OIDC discovery document at {cfg.discovery_url} has no jwks_uri"
                    )
                    return None

            # Validate reachability + shape of JWKS without relying on the
            # verifier's internal cache. We don't keep the payload — the
            # JWTVerifier fetches it again on first use.
            jwks_payload = await _fetch_json(client, jwks_uri)
            if not isinstance(jwks_payload.get("keys"), list) or not jwks_payload["keys"]:
                _activation_failure(f"JWKS at {jwks_uri} returned no keys")
                return None
    except httpx.HTTPStatusError as exc:
        _activation_failure(f"HTTP {exc.response.status_code} from {exc.request.url}")
        return None
    except httpx.HTTPError as exc:
        _activation_failure(f"network error while reaching Keycloak: {exc}")
        return None
    except ValueError as exc:
        # JSON decoding failure
        _activation_failure(f"malformed JSON from Keycloak: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 — startup path must never crash
        _activation_failure(f"unexpected error during OAuth activation: {exc}")
        return None

    verifier = JWTVerifier(
        jwks_uri=jwks_uri,
        issuer=cfg.issuer,
        audience=list(cfg.audience),
        algorithm="RS256",
        required_scopes=list(cfg.required_scopes) or None,
    )

    return OAuthHydrolixAuthProvider(cfg, verifier, effective_resource_url)
