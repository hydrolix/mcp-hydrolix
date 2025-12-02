"""Hydrolix credential types for authentication."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import jwt


class HydrolixCredential(ABC):
    @abstractmethod
    def clickhouse_config_entries(self) -> dict:
        """
        Returns the entries needed for a ClickHouse client config to use this credential.
        This will typically add `access_token` or (`username` and `password`)
        """
        ...


@dataclass
class ServiceAccountToken(HydrolixCredential):
    """Hydrolix credentials using a service account token."""

    def __init__(self, token: str, expected_iss: Optional[str]):
        """
        Initialize a ServiceAccountToken from a token JWT (or raise an error if the claims are invalid).
        NB the claims' signatures are NOT checked by this function -- these validations MUST NOT be considered
        authoritative.
        """

        claims = jwt.decode(
            token,
            key="",  # NB service account signing key is not publicly-hosted, so we can't verify the signature
            options={
                "verify_signature": False,
                "verify_iss": True,
                "verify_iat": True,
                "verify_exp": True,
            },
            issuer=expected_iss,
        )
        self.token = token
        self.service_account_id = claims["sub"]
        self.issued_at = claims["iss"]
        self.expires_at = claims["exp"]

    def clickhouse_config_entries(self) -> dict:
        return {"access_token": self.token}

    token: str
    service_account_id: str
    issued_at: int
    expires_at: int


@dataclass
class UsernamePassword(HydrolixCredential):
    """Hydrolix credentials using username and password."""

    def clickhouse_config_entries(self) -> dict:
        return {"username": self.username, "password": self.password}

    username: str
    password: str
