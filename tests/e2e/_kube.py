"""Stub for the e2e Kubernetes harness.

Symbols listed here are imported by ``tests/e2e/conftest.py``; the real
implementations land in a follow-up commit. The session-scoped fixtures call
``pytest.xfail()`` before any of these are invoked, so the placeholders below
exist only so collection succeeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTAINER_KEY = "mcp-hydrolix"
DEFAULT_DEPLOYMENT_NAME = "mcp-hydrolix"


@dataclass(frozen=True)
class KubeContext:
    kubeconfig: str | None
    context: str | None
    namespace: str
    cluster_name: str


@dataclass(frozen=True)
class KubeClients:
    custom: Any
    apps: Any
    core: Any


def _not_implemented(*_args: Any, **_kwargs: Any) -> Any:
    raise NotImplementedError("e2e harness not yet implemented")


acquire_advisory_lock = _not_implemented
apply_image_override = _not_implemented
assert_mcp_enabled = _not_implemented
discover_kube_context = _not_implemented
extract_containers = _not_implemented
latest_snapshot = _not_implemented
load_snapshot_file = _not_implemented
make_clients = _not_implemented
make_owner_token = _not_implemented
read_cr = _not_implemented
read_deployment_generation = _not_implemented
release_advisory_lock = _not_implemented
restore_containers = _not_implemented


def snapshot_path_for(_ctx: KubeContext) -> Path:
    raise NotImplementedError("e2e harness not yet implemented")


wait_for_rollout = _not_implemented
write_snapshot = _not_implemented
