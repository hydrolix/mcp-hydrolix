"""Stub for the fastmcp client helpers used by the e2e suite.

Replaced with a real implementation in a follow-up commit. The fixtures in
``conftest.py`` call ``pytest.xfail()`` before reaching any of these, so the
stubs only need to exist for import to succeed.
"""

from __future__ import annotations

from typing import Any


def make_client(*_args: Any, **_kwargs: Any) -> Any:
    raise NotImplementedError("e2e harness not yet implemented")


def login_for_bearer_token(*_args: Any, **_kwargs: Any) -> str:
    raise NotImplementedError("e2e harness not yet implemented")


def wait_for_endpoint_ready(*_args: Any, **_kwargs: Any) -> None:
    raise NotImplementedError("e2e harness not yet implemented")


def parsed_payload(*_args: Any, **_kwargs: Any) -> Any:
    raise NotImplementedError("e2e harness not yet implemented")


def unauthed_initialize_status(*_args: Any, **_kwargs: Any) -> tuple[int, str]:
    raise NotImplementedError("e2e harness not yet implemented")
