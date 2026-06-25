from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator, Generator
from urllib.parse import urlparse

from fastmcp import Client
import pytest
from dotenv import load_dotenv

from tests.e2e._kube import (
    CONTAINER_KEY,
    DEFAULT_DEPLOYMENT_NAME,
    KubeClients,
    KubeContext,
    acquire_advisory_lock,
    apply_image_override,
    assert_mcp_enabled,
    assert_pod_image,
    discover_kube_context,
    extract_containers,
    latest_snapshot,
    load_snapshot_file,
    make_clients,
    make_owner_token,
    patch_deployment_image,
    read_cr,
    read_deployment_generation,
    read_deployment_image,
    release_advisory_lock,
    restore_containers,
    snapshot_path_for,
    wait_for_rollout,
    write_snapshot,
)
from tests.e2e._mcp_client import login_for_bearer_token, make_client, wait_for_endpoint_ready

REQUIRED_VARS = ("HYDROLIX_USER", "HYDROLIX_PASSWORD", "MCP_HYDROLIX_E2E_KUBE_CONTEXT")
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class E2EConfig:
    hydrolix_user: str
    hydrolix_password: str
    hydrolix_url_override: str | None
    image_override: str | None
    image_tag_override: str | None
    skip_build: bool
    kubeconfig: str | None
    kube_context: str
    namespace: str | None
    cluster_name: str | None
    deployment_name: str
    ready_timeout: float
    # Operator-version override (deliberately gated; see operator_state).
    operator_image: str | None
    operator_deployment: str | None
    operator_namespace: str | None
    operator_container: str | None
    operator_override_ack: str | None


@dataclass(frozen=True)
class ClusterState:
    ctx: KubeContext
    clients: KubeClients
    hydrolix_host: str
    snapshot_path: Path
    pre_patch_deployment_generation: int | None
    expected_image: str
    expected_tag: str


def operator_override_missing_keys(
    image: str | None, deployment: str | None, ack: str | None
) -> list[str]:
    """Names of safety-gate keys still missing for an operator-version override.

    Empty when no override was requested (``image`` falsy) or the presence gate
    is satisfied. The ACK's cluster-name match is enforced in ``operator_state``;
    see tests/e2e/README.md ("Operator-version override") for the rationale.
    """
    if not image:
        return []
    missing: list[str] = []
    if not deployment:
        missing.append("MCP_HYDROLIX_E2E_OPERATOR_DEPLOYMENT")
    if not ack:
        missing.append("MCP_HYDROLIX_E2E_OPERATOR_OVERRIDE_ACK")
    return missing


_SKIP_MSG = (
    "e2e suite skipped: no .env.e2e file found and MCP_HYDROLIX_E2E_ENV_FILE "
    "is not set.  Copy .env.e2e.example → .env.e2e and fill in credentials to "
    "run the end-to-end tests."
)


@pytest.fixture(scope="session")
def _e2e_env_guard() -> E2EConfig:
    explicit = os.environ.get("MCP_HYDROLIX_E2E_ENV_FILE")
    env_file = explicit or str(REPO_ROOT / ".env.e2e")
    if not Path(env_file).exists():
        print(f"[e2e] {_SKIP_MSG}", file=sys.stderr)
        pytest.skip(_SKIP_MSG)
    # override=True because tests/__init__.py calls load_dotenv() at package
    # import time, which loads tests/.env (localhost connection vars for unit
    # tests). Without override, those pre-set values win and e2e tests would
    # talk to localhost instead of the live cluster.
    load_dotenv(env_file, override=True)
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        pytest.fail(
            f"e2e env file {env_file} is missing required vars: {', '.join(missing)}",
            pytrace=False,
        )

    def _opt(name: str) -> str | None:
        v = os.environ.get(name)
        return v if v else None

    operator_image = _opt("MCP_HYDROLIX_E2E_OPERATOR_IMAGE")
    operator_deployment = _opt("MCP_HYDROLIX_E2E_OPERATOR_DEPLOYMENT")
    operator_override_ack = _opt("MCP_HYDROLIX_E2E_OPERATOR_OVERRIDE_ACK")
    # Presence half of the operator-version-override safety gate; the ACK's
    # cluster-name match is enforced later in operator_state. Rationale and the
    # full key reference live in tests/e2e/README.md ("Operator-version override").
    missing_keys = operator_override_missing_keys(
        operator_image, operator_deployment, operator_override_ack
    )
    if missing_keys:
        pytest.fail(
            "MCP_HYDROLIX_E2E_OPERATOR_IMAGE is set (operator-version override "
            "requested) but the safety gate is incomplete. Also set: "
            f"{', '.join(missing_keys)}. "
            "OPERATOR_OVERRIDE_ACK must equal the target cluster name.",
            pytrace=False,
        )

    return E2EConfig(
        hydrolix_user=os.environ["HYDROLIX_USER"],
        hydrolix_password=os.environ["HYDROLIX_PASSWORD"],
        hydrolix_url_override=_opt("HYDROLIX_URL"),
        image_override=_opt("MCP_HYDROLIX_E2E_IMAGE"),
        image_tag_override=_opt("MCP_HYDROLIX_E2E_IMAGE_TAG"),
        skip_build=os.environ.get("MCP_HYDROLIX_E2E_SKIP_BUILD", "0") == "1",
        kubeconfig=_opt("MCP_HYDROLIX_E2E_KUBECONFIG"),
        kube_context=os.environ["MCP_HYDROLIX_E2E_KUBE_CONTEXT"],
        namespace=_opt("MCP_HYDROLIX_E2E_NAMESPACE"),
        cluster_name=_opt("MCP_HYDROLIX_E2E_CLUSTER_NAME"),
        deployment_name=os.environ.get("MCP_HYDROLIX_E2E_DEPLOYMENT_NAME", DEFAULT_DEPLOYMENT_NAME),
        ready_timeout=float(os.environ.get("MCP_HYDROLIX_E2E_READY_TIMEOUT", "180")),
        operator_image=operator_image,
        operator_deployment=operator_deployment,
        operator_namespace=_opt("MCP_HYDROLIX_E2E_OPERATOR_NAMESPACE"),
        operator_container=_opt("MCP_HYDROLIX_E2E_OPERATOR_CONTAINER"),
        operator_override_ack=operator_override_ack,
    )


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _is_dirty() -> bool:
    return subprocess.call(["git", "diff", "--quiet", "HEAD"], cwd=REPO_ROOT) != 0


def _git_user_id() -> str:
    """Local part of `git config user.email`, sanitized for image names."""
    try:
        email = _git_output("config", "user.email")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "git config user.email is not set; required for e2e image naming. "
            "Set it with `git config --global user.email <you@example.com>`."
        ) from exc
    local = email.split("@", 1)[0]
    return re.sub(r"[^a-zA-Z0-9._-]", "-", local)


def _derive_image_and_tag(cfg: E2EConfig) -> tuple[str, str]:
    branch = _git_output("rev-parse", "--abbrev-ref", "HEAD")
    short_sha = _git_output("rev-parse", "--short=7", "HEAD")
    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "-", branch)
    dirty = "-dirty" if _is_dirty() else ""
    if cfg.image_override:
        image = cfg.image_override
        default_tag = f"branch-{sanitized}-{short_sha}{dirty}"
    else:
        epoch = int(time.time())
        image = f"ttl.sh/mcp-hydrolix-e2e-{_git_user_id()}-{sanitized}-{short_sha}{dirty}-{epoch}"
        default_tag = "10m"
    tag = cfg.image_tag_override or default_tag
    return image, tag


@pytest.fixture(scope="session")
def built_image(_e2e_env_guard: E2EConfig) -> tuple[str, str]:
    image, tag = _derive_image_and_tag(_e2e_env_guard)
    if _e2e_env_guard.skip_build:
        print(f"[e2e] MCP_HYDROLIX_E2E_SKIP_BUILD=1; using {image}:{tag}", file=sys.stderr)
        return image, tag
    # Per-run label gives byte-identical source a unique image digest, so
    # content-addressed registries (ttl.sh) don't dedup re-pushes under a new tag
    # and report a stale tag in containerStatuses — which would fail the rollout
    # image check and cause spurious timeouts on repeated runs.
    build_id = str(int(time.time()))
    print(f"[e2e] docker build -t {image}:{tag} . (build-id={build_id})", file=sys.stderr)
    subprocess.check_call(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "--label",
            f"com.hydrolix.mcp-e2e-test-build={build_id}",
            "-t",
            f"{image}:{tag}",
            ".",
        ],
        cwd=REPO_ROOT,
    )
    print(f"[e2e] docker push {image}:{tag}", file=sys.stderr)
    subprocess.check_call(["docker", "push", f"{image}:{tag}"])
    return image, tag


def _hydrolix_host_from_cr(cr: dict, override: str | None) -> str:
    # The override (HYDROLIX_URL) and the CR's spec.hydrolix_url are both full
    # URLs; parse whichever is present down to a bare host for endpoint building.
    url = override
    if not url:
        spec = cr.get("spec") or {}
        url = spec.get("hydrolix_url")
    if not url:
        raise RuntimeError("spec.hydrolix_url not set on the CR and HYDROLIX_URL not provided")
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    if not host:
        raise RuntimeError(f"could not parse host from HYDROLIX_URL/spec.hydrolix_url={url!r}")
    return host.rstrip("/")


def _idempotent_precleanup(
    clients: KubeClients, ctx: KubeContext, containers: dict | None
) -> dict | None:
    """Best-effort recovery from a prior crashed run before snapshotting state.

    The advisory lock and the session try/finally cleanup are the primary
    safety net. This is a third tier that only fires for the narrow case
    where a previous run died, released the lock, but failed to restore
    `spec.containers`. We detect that by sniffing for the ttl.sh image-name
    prefix the harness uses (`mcp-hydrolix-e2e-`) and re-apply the most
    recent on-disk snapshot, returning the post-restore containers value as
    the new "original" to snapshot.

    Limitations: only covers the ttl.sh path. Runs that override
    MCP_HYDROLIX_E2E_IMAGE to a non-ttl.sh registry produce image strings
    that don't match this heuristic; for those, use the manual recovery
    CLI documented in tests/e2e/README.md.
    """
    if not containers or CONTAINER_KEY not in containers:
        return containers
    leftover_image = (containers[CONTAINER_KEY] or {}).get("image", "")
    if "mcp-hydrolix-e2e-" not in leftover_image:
        return containers
    prior = latest_snapshot(ctx.cluster_name, ctx.namespace)
    if not prior:
        print(
            f"[e2e] WARNING: leftover e2e override (image={leftover_image!r}) "
            f"detected but no snapshot file exists; leaving as-is.",
            file=sys.stderr,
        )
        return containers
    snap = load_snapshot_file(prior)
    print(
        f"[e2e] orphaned e2e override detected; restoring from {prior} before starting",
        file=sys.stderr,
    )
    restore_containers(clients.custom, ctx, snap.get("containers_value"))
    cr = read_cr(clients.custom, ctx)
    return extract_containers(cr)


@pytest.fixture(scope="session")
def operator_state(_e2e_env_guard: E2EConfig) -> Generator[str | None, None, None]:
    """Optionally pin the Hydrolix operator to a specific image for the run.

    No-op unless MCP_HYDROLIX_E2E_OPERATOR_IMAGE is set (the common case). When
    engaged it snapshots the operator Deployment's current image, patches it to
    the override, waits for the operator to roll out, and restores the original
    image on teardown.

    Ordered before cluster_state (which depends on this fixture) so the
    overridden operator is reconciling before the CR's mcp-hydrolix container is
    patched — that is what lets the new operator inject its new tunables. The
    override is gated so it can't fire by accident: the presence check is in
    _e2e_env_guard and the cluster-name ACK match is below. See
    tests/e2e/README.md ("Operator-version override") for the rationale.
    """
    cfg = _e2e_env_guard
    if not cfg.operator_image:
        yield None
        return
    op_image: str = cfg.operator_image

    ctx = discover_kube_context(cfg.kubeconfig, cfg.kube_context, cfg.namespace, cfg.cluster_name)
    if cfg.operator_override_ack != ctx.cluster_name:
        pytest.fail(
            "operator-version override refused: MCP_HYDROLIX_E2E_OPERATOR_OVERRIDE_ACK="
            f"{cfg.operator_override_ack!r} does not match the resolved cluster name "
            f"{ctx.cluster_name!r}. Set the ACK to the exact cluster you intend to mutate.",
            pytrace=False,
        )

    clients = make_clients()
    assert cfg.operator_deployment is not None  # guaranteed by the guard
    op_deployment: str = cfg.operator_deployment
    op_namespace: str = cfg.operator_namespace or ctx.namespace
    # The container within the operator pod whose image we patch; defaults to
    # the Deployment name, which is the usual convention.
    op_container: str = cfg.operator_container or op_deployment

    original_image = read_deployment_image(clients, op_namespace, op_deployment, op_container)
    if original_image is None:
        pytest.fail(
            f"operator-version override: could not find container {op_container!r} on "
            f"Deployment {op_deployment!r} in namespace {op_namespace!r}. Check "
            "MCP_HYDROLIX_E2E_OPERATOR_DEPLOYMENT / _NAMESPACE / _CONTAINER.",
            pytrace=False,
        )
    assert original_image is not None  # pytest.fail above is NoReturn at runtime

    op_ctx = KubeContext(
        kubeconfig=ctx.kubeconfig,
        context=ctx.context,
        namespace=op_namespace,
        cluster_name=ctx.cluster_name,
    )
    print(
        f"[e2e] !!! OPERATOR OVERRIDE ENGAGED on cluster {ctx.cluster_name!r}: patching "
        f"{op_deployment!r}/{op_container!r} in {op_namespace!r} "
        f"from {original_image!r} to {op_image!r}. The original image will be "
        f"restored on teardown.",
        file=sys.stderr,
    )
    pre_patch_gen = read_deployment_generation(clients, op_ctx, op_deployment)
    try:
        patch_deployment_image(clients, op_namespace, op_deployment, op_container, op_image)
        wait_for_rollout(
            clients,
            op_ctx,
            deployment_name=op_deployment,
            timeout=cfg.ready_timeout,
            min_generation=pre_patch_gen,
            expected_image=op_image,
            container_name=op_container,
        )
        yield op_image
    finally:
        try:
            patch_deployment_image(
                clients, op_namespace, op_deployment, op_container, original_image
            )
            print(
                f"[e2e] restored operator image on {op_deployment!r} "
                f"({op_namespace!r}) to {original_image!r}",
                file=sys.stderr,
            )
        except Exception as exc:
            print(
                f"[e2e] FAILED to restore operator image on {op_deployment!r} "
                f"({op_namespace!r}) to {original_image!r}: {exc}\n"
                f"[e2e] Restore it manually with: kubectl -n {op_namespace} set image "
                f"deployment/{op_deployment} {op_container}={original_image}",
                file=sys.stderr,
            )


@pytest.fixture(scope="session")
def cluster_state(
    _e2e_env_guard: E2EConfig, operator_state: str | None, built_image: tuple[str, str]
) -> Generator[ClusterState, None, None]:
    cfg = _e2e_env_guard
    image, tag = built_image
    ctx = discover_kube_context(cfg.kubeconfig, cfg.kube_context, cfg.namespace, cfg.cluster_name)
    clients = make_clients()
    cr = read_cr(clients.custom, ctx)
    assert_mcp_enabled(cr, ctx)
    hydrolix_host = _hydrolix_host_from_cr(cr, cfg.hydrolix_url_override)

    # Acquire the advisory lock BEFORE any CR-mutating call (precleanup or
    # apply_image_override). Otherwise a concurrent run could clobber an active
    # holder's deployed state via _idempotent_precleanup before failing on the
    # lock.
    owner = make_owner_token()
    acquire_advisory_lock(clients.custom, ctx, owner)

    snap_path: Path | None = None
    original_containers: Any = None
    original_containers_set = False
    try:
        # Re-read the CR after taking the lock so precleanup operates on a
        # post-lock view of state.
        cr = read_cr(clients.custom, ctx)
        original_containers = _idempotent_precleanup(clients, ctx, extract_containers(cr))
        original_containers_set = True
        snap_path = snapshot_path_for(ctx)
        write_snapshot(snap_path, ctx, original_containers)

        # Snapshot Deployment generation BEFORE the CR patch so wait_for_rollout
        # doesn't satisfy readiness against pre-patch pods.
        pre_patch_gen = read_deployment_generation(clients, ctx, _e2e_env_guard.deployment_name)

        state = ClusterState(
            ctx=ctx,
            clients=clients,
            hydrolix_host=hydrolix_host,
            snapshot_path=snap_path,
            pre_patch_deployment_generation=pre_patch_gen,
            expected_image=image,
            expected_tag=tag,
        )
        apply_image_override(clients.custom, ctx, image, tag)
        yield state
    finally:
        restore_ok = False
        if original_containers_set:
            try:
                restore_containers(clients.custom, ctx, original_containers)
                restore_ok = True
            except Exception as exc:
                snap_hint = str(snap_path) if snap_path is not None else "<snapshot not written>"
                cmd = "uv run python -m tests.e2e._kube cleanup" + (
                    f" --snapshot {snap_path}" if snap_path is not None else ""
                )
                print(
                    f"[e2e] FAILED to restore spec.containers on {ctx.cluster_name}: {exc}\n"
                    f"[e2e] Snapshot left at {snap_hint} for manual recovery via\n"
                    f"[e2e]   {cmd}",
                    file=sys.stderr,
                )
        try:
            release_advisory_lock(clients.custom, ctx)
        except Exception as exc:
            print(
                f"[e2e] WARNING: failed to release advisory lock on {ctx.cluster_name}: {exc}",
                file=sys.stderr,
            )
        if restore_ok and snap_path is not None:
            try:
                snap_path.unlink()
            except OSError:
                pass


@pytest.fixture(scope="session")
def bearer_token(_e2e_env_guard: E2EConfig, cluster_state: ClusterState) -> str:
    # Login is served by the always-on Hydrolix API (`/config/v1/login`), not
    # by the mcp-hydrolix process under test, so it's available immediately —
    # no need to gate on mcp_ready.
    return login_for_bearer_token(
        host=cluster_state.hydrolix_host,
        username=_e2e_env_guard.hydrolix_user,
        password=_e2e_env_guard.hydrolix_password,
    )


@pytest.fixture(scope="session")
def mcp_ready(
    _e2e_env_guard: E2EConfig,
    cluster_state: ClusterState,
    bearer_token: str,
) -> ClusterState:
    expected_full = f"{cluster_state.expected_image}:{cluster_state.expected_tag}"
    wait_for_rollout(
        cluster_state.clients,
        cluster_state.ctx,
        deployment_name=_e2e_env_guard.deployment_name,
        timeout=_e2e_env_guard.ready_timeout,
        min_generation=cluster_state.pre_patch_deployment_generation,
        expected_image=expected_full,
    )
    assert_pod_image(
        cluster_state.clients,
        cluster_state.ctx,
        deployment_name=_e2e_env_guard.deployment_name,
        expected_image=cluster_state.expected_image,
        expected_tag=cluster_state.expected_tag,
    )
    # k8s reports the Deployment Ready before the front-end LB has finished
    # routing traffic to the new pods, so the public endpoint can still serve
    # 5xx — or 401s minted by the LB itself before requests reach us — after
    # wait_for_rollout returns. Probe authed and require a JSON-RPC serverInfo
    # response so an LB-issued 401 can't masquerade as readiness.
    wait_for_endpoint_ready(
        cluster_state.hydrolix_host,
        bearer_token,
        timeout=_e2e_env_guard.ready_timeout,
    )
    return cluster_state


@pytest.fixture
async def mcp_client(mcp_ready: ClusterState, bearer_token: str) -> AsyncGenerator[Client, None]:
    """Yields an entered, authed `fastmcp.Client`.

    The MCP `initialize` handshake runs inside `__aenter__`. Tests that need
    to assert the tool surface should do so explicitly (see
    `test_initialize_lists_expected_tools`).
    """
    async with make_client(mcp_ready.hydrolix_host, bearer_token) as client:
        yield client
