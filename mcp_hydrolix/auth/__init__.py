"""Authentication package for MCP Hydrolix.

This package contains authentication-related types used to define hydrolix auth
in terms of FastMCP infrastructure
"""

from typing import Optional

from fastmcp.server.dependencies import get_access_token
from jwt import DecodeError

from mcp_hydrolix.auth.credentials import (
    HydrolixCredential,
    ServiceAccountToken,
    UsernamePassword,
)
from mcp_hydrolix.auth.mcp_providers import (
    TOKEN_PARAM,
    AccessToken,
    ChainedAuthBackend,
    GetParamAuthBackend,
    HydrolixCredentialChain,
)


def get_request_credential() -> Optional[HydrolixCredential]:
    """Resolve the per-request Hydrolix credential from the FastMCP auth context.

    Returns the credential decoded from the per-request access token (HTTP /
    SSE transports with a Bearer or ``?token=`` param), or ``None`` when there
    is no per-request auth context (stdio transport, or HTTP without a
    bearer). Callers typically pass the result to
    ``HydrolixConfig.creds_with(...)`` to fold in the env-supplied default.

    Raises ``ValueError`` if a token is present but invalid or of an
    unexpected access-token type.
    """
    if (token := get_access_token()) is not None:
        if isinstance(token, AccessToken):
            try:
                return token.as_credential()
            except DecodeError:
                raise ValueError("The provided access token is invalid.")
        else:
            raise ValueError(
                "Found non-hydrolix access token on request -- this should be impossible!"
            )
    return None


__all__ = [
    "HydrolixCredential",
    "ServiceAccountToken",
    "UsernamePassword",
    "AccessToken",
    "ChainedAuthBackend",
    "GetParamAuthBackend",
    "HydrolixCredentialChain",
    "TOKEN_PARAM",
    "get_request_credential",
]
