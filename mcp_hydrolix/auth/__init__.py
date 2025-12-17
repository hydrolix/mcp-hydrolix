"""Authentication package for MCP Hydrolix.

This package contains authentication-related types used to define hydrolix auth
in terms of FastMCP infrastructure
"""

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

__all__ = [
    "HydrolixCredential",
    "ServiceAccountToken",
    "UsernamePassword",
    "AccessToken",
    "ChainedAuthBackend",
    "GetParamAuthBackend",
    "HydrolixCredentialChain",
    "TOKEN_PARAM",
]
