"""Authentication backends and providers for MCP Hydrolix server."""

from abc import abstractmethod
import time
from typing import List, ClassVar, Final, Optional

from fastmcp.server.auth import AuthProvider, AccessToken as FastMCPAccessToken
from mcp.server.auth.middleware.auth_context import (
    AuthContextMiddleware as McpAuthContextMiddleware,
)
from mcp.server.auth.middleware.bearer_auth import (
    AuthenticatedUser as McpAuthenticatedUser,
    BearerAuthBackend,
)
from mcp.server.auth.provider import TokenVerifier as McpTokenVerifier
from starlette.authentication import AuthenticationBackend, AuthCredentials
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request, HTTPConnection

from mcp_hydrolix.auth.credentials import HydrolixCredential, ServiceAccountToken


class ChainedAuthBackend(AuthenticationBackend):
    """
    Generic authentication backend that tries multiple backends in order. Returns the first successful
    authentication result. Only tries an auth method once all previous auth methods have failed.
    """

    def __init__(self, backends: List[AuthenticationBackend]):
        self.backends = backends

    async def authenticate(self, conn: HTTPConnection):
        # due to a very strange quirk of python syntax, this CANNOT be an anonymous async generator. The quirk is
        # that async generator expressions aren't allowed to have `await` in their if conditions (though async
        # generators have no such restriction on their if statements)
        async def successful_results():
            for backend in self.backends:
                if (result := await backend.authenticate(conn)) is not None:
                    yield result

        return await anext(successful_results(), None)


class GetParamAuthBackend(AuthenticationBackend):
    """
    Authentication backend that validates tokens from an HTTP GET parameter
    """

    def __init__(self, token_verifier: McpTokenVerifier, token_get_param: str):
        self.token_verifier = token_verifier
        self.token_get_param = token_get_param

    async def authenticate(self, conn: HTTPConnection):
        token = Request(conn.scope).query_params.get(self.token_get_param)

        if token is None:
            return None

        # Validate the token with the verifier
        auth_info = await self.token_verifier.verify_token(token)

        if not auth_info:
            return None

        if auth_info.expires_at and auth_info.expires_at < int(time.time()):
            return None

        return AuthCredentials(auth_info.scopes), McpAuthenticatedUser(auth_info)


class AccessToken(FastMCPAccessToken):
    @abstractmethod
    def as_credential(self) -> HydrolixCredential: ...


class HydrolixCredentialChain(AuthProvider):
    """
    AuthProvider that authenticates with the following precedence:

    - MCP-standard oAuth (not implemented!)
    - Hydrolix service account via the "token" GET parameter
    - Hydrolix service account via the Bearer token
    """

    class ServiceAccountAccess(AccessToken):
        FAKE_CLIENT_ID: ClassVar[Final[str]] = "MCP_CLIENT_VIA_SERVICE_ACCOUNT"
        FAKE_SCOPE: ClassVar[Final[str]] = "MCP_SERVICE_ACCOUNT_SCOPE"

        expected_issuer: Optional[str] = None

        def as_credential(self) -> ServiceAccountToken:
            return ServiceAccountToken(self.token, self.expected_issuer)

    def __init__(self, expected_issuer: Optional[str]):
        """
        Initialize HydrolixCredentialChain.

        Args:
            expected_issuer: The issuer URL that must be used (mitigates credential-stuffing)
        """
        super().__init__()
        self.expected_issuer = expected_issuer

    async def verify_token(self, token: str) -> AccessToken | None:
        """
        This is responsible for validating and authenticating the `token`.
        See ChainedAuthBackend for how the token is obtained in the first place.
        Authorization is performed by individual endpoints via `fastmcp.server.dependencies.get_access_token`
        """
        return HydrolixCredentialChain.ServiceAccountAccess(
            token=token,
            client_id=HydrolixCredentialChain.ServiceAccountAccess.FAKE_CLIENT_ID,
            scopes=[HydrolixCredentialChain.ServiceAccountAccess.FAKE_SCOPE],
            expires_at=None,
            resource=None,
            claims={},
            expected_issuer=self.expected_issuer,
        )

    def get_middleware(self) -> list:
        return [
            Middleware(
                AuthenticationMiddleware,
                backend=ChainedAuthBackend(
                    [
                        BearerAuthBackend(self),
                        GetParamAuthBackend(self, "token"),
                    ]
                ),
            ),
            Middleware(McpAuthContextMiddleware),
        ]
