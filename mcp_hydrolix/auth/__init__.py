"""Authentication package for MCP Hydrolix.

This package contains authentication-related types used to define hydrolix auth
in terms of FastMCP infrastructure
"""

from .credentials import (
    HydrolixCredential,
    ServiceAccountToken,
    UsernamePassword,
)
from .mcp_providers import (
    AccessToken,
    ChainedAuthBackend,
    GetParamAuthBackend,
    HydrolixCredentialChain,
    TOKEN_PARAM,
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
