"""Stub fixtures for the e2e suite.

The real harness lands in the follow-up commits that introduce
tests/e2e/_kube.py and tests/e2e/_mcp_client.py. In the meantime the e2e
tests carry an xfail marker so collection succeeds and the test surface is
reviewable in isolation from the harness implementation.
"""

from __future__ import annotations

from typing import Any

import pytest

_PENDING = (
    "e2e harness implementation pending; see follow-up commits for "
    "tests/e2e/_kube.py, tests/e2e/_mcp_client.py, and the real conftest."
)


@pytest.fixture(scope="session")
def _e2e_env_guard() -> Any:
    pytest.skip(_PENDING)


@pytest.fixture(scope="session")
def built_image(_e2e_env_guard: Any) -> tuple[str, str]:
    pytest.skip(_PENDING)


@pytest.fixture(scope="session")
def cluster_state(_e2e_env_guard: Any, built_image: Any) -> Any:
    pytest.skip(_PENDING)


@pytest.fixture(scope="session")
def mcp_ready(_e2e_env_guard: Any, cluster_state: Any) -> Any:
    pytest.skip(_PENDING)


@pytest.fixture(scope="session")
def bearer_token(_e2e_env_guard: Any, mcp_ready: Any) -> str:
    pytest.skip(_PENDING)


@pytest.fixture
async def mcp_client(mcp_ready: Any, bearer_token: str) -> Any:
    pytest.skip(_PENDING)
