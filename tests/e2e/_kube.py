from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

GROUP = "hydrolix.io"
VERSION = "v1"
PLURAL = "hydrolixclusters"
LOCK_ANNOTATION = "mcp-hydrolix-e2e/lock"
CONTAINER_KEY = "mcp-hydrolix"
DEFAULT_DEPLOYMENT_NAME = "mcp-hydrolix"
SNAPSHOT_DIR = Path.home() / ".cache" / "mcp-hydrolix-e2e"


@dataclass(frozen=True)
class KubeContext:
    kubeconfig: str | None
    context: str | None
    namespace: str
    cluster_name: str


@dataclass(frozen=True)
class KubeClients:
    custom: client.CustomObjectsApi
    apps: client.AppsV1Api
    core: client.CoreV1Api


def discover_kube_context(
    kubeconfig: str | None,
    context: str | None,
    namespace: str | None,
    cluster_name: str | None,
) -> KubeContext:
    config.load_kube_config(config_file=kubeconfig, context=context)
    if namespace is None:
        contexts, active = config.list_kube_config_contexts(config_file=kubeconfig)
        target_name = context or active["name"]
        target = next((c for c in contexts if c["name"] == target_name), active)
        namespace = target.get("context", {}).get("namespace") or "default"
    if cluster_name is None:
        api = client.CustomObjectsApi()
        listing = api.list_namespaced_custom_object(
            group=GROUP, version=VERSION, namespace=namespace, plural=PLURAL
        )
        items = listing.get("items", [])
        if len(items) != 1:
            names = [i["metadata"]["name"] for i in items]
            raise RuntimeError(
                f"expected exactly one {PLURAL}.{GROUP} CR in namespace {namespace!r}, "
                f"found {len(items)}: {names}. Set MCP_HYDROLIX_E2E_CLUSTER_NAME."
            )
        cluster_name = items[0]["metadata"]["name"]
    return KubeContext(
        kubeconfig=kubeconfig, context=context, namespace=namespace, cluster_name=cluster_name
    )


def make_clients() -> KubeClients:
    return KubeClients(
        custom=client.CustomObjectsApi(),
        apps=client.AppsV1Api(),
        core=client.CoreV1Api(),
    )


def read_cr(api: client.CustomObjectsApi, ctx: KubeContext) -> dict[str, Any]:
    return api.get_namespaced_custom_object(
        group=GROUP,
        version=VERSION,
        namespace=ctx.namespace,
        plural=PLURAL,
        name=ctx.cluster_name,
    )


def assert_mcp_enabled(cr: dict[str, Any], ctx: KubeContext) -> None:
    spec = cr.get("spec") or {}
    mcp = spec.get("mcp_hydrolix") or {}
    if not mcp.get("enabled"):
        raise RuntimeError(
            f"MCP is disabled on cluster {ctx.cluster_name!r} (namespace "
            f"{ctx.namespace!r}); either enable it via spec.mcp_hydrolix.enabled "
            f"or run against a different cluster."
        )


def extract_containers(cr: dict[str, Any]) -> Any:
    spec = cr.get("spec") or {}
    return spec.get("containers")


def snapshot_path_for(ctx: KubeContext) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return SNAPSHOT_DIR / f"{ctx.cluster_name}-{ctx.namespace}-{ts}.json"


def write_snapshot(path: Path, ctx: KubeContext, containers_value: Any) -> None:
    payload = {
        "cluster_name": ctx.cluster_name,
        "namespace": ctx.namespace,
        "captured_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "containers_value": containers_value,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def load_snapshot_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def latest_snapshot(cluster_name: str | None = None, namespace: str | None = None) -> Path | None:
    if not SNAPSHOT_DIR.exists():
        return None
    candidates: list[Path] = []
    for p in SNAPSHOT_DIR.glob("*.json"):
        if cluster_name and not p.name.startswith(f"{cluster_name}-"):
            continue
        if namespace and f"-{namespace}-" not in p.name:
            continue
        candidates.append(p)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def acquire_advisory_lock(api: client.CustomObjectsApi, ctx: KubeContext, owner: str) -> None:
    cr = read_cr(api, ctx)
    annotations = (cr.get("metadata") or {}).get("annotations") or {}
    existing = annotations.get(LOCK_ANNOTATION)
    if existing and existing != owner:
        raise RuntimeError(
            f"advisory lock {LOCK_ANNOTATION!r} on {ctx.cluster_name} held by "
            f"another run (owner={existing!r}). If you are sure no other run is "
            f"in progress, clear it with: kubectl annotate -n {ctx.namespace} "
            f"{PLURAL}/{ctx.cluster_name} {LOCK_ANNOTATION}-"
        )
    _patch_annotation(api, ctx, owner)


def release_advisory_lock(api: client.CustomObjectsApi, ctx: KubeContext) -> None:
    _patch_annotation(api, ctx, None)


def _patch_annotation(api: client.CustomObjectsApi, ctx: KubeContext, value: str | None) -> None:
    body = {"metadata": {"annotations": {LOCK_ANNOTATION: value}}}
    api.patch_namespaced_custom_object(
        group=GROUP,
        version=VERSION,
        namespace=ctx.namespace,
        plural=PLURAL,
        name=ctx.cluster_name,
        body=body,
    )


def apply_image_override(
    api: client.CustomObjectsApi, ctx: KubeContext, image: str, tag: str
) -> None:
    body = {"spec": {"containers": {CONTAINER_KEY: {"image": image, "tag": tag}}}}
    api.patch_namespaced_custom_object(
        group=GROUP,
        version=VERSION,
        namespace=ctx.namespace,
        plural=PLURAL,
        name=ctx.cluster_name,
        body=body,
    )


def restore_containers(api: client.CustomObjectsApi, ctx: KubeContext, original: Any) -> None:
    # JSON merge-patch (RFC 7396) recursively merges sub-objects, so writing
    # `original` back in one shot is not sufficient to drop the {image, tag}
    # keys we injected via apply_image_override — they would survive the merge
    # whenever the original mcp-hydrolix entry was missing one of them. Always
    # null our key first (deletes it under merge-patch), then re-apply original
    # so any pre-existing mcp-hydrolix value comes back cleanly.
    _patch_cr(api, ctx, {"spec": {"containers": {CONTAINER_KEY: None}}})
    if original is None:
        # Original CR had no spec.containers at all — drop the (now possibly
        # empty) map entirely.
        _patch_cr(api, ctx, {"spec": {"containers": None}})
        return
    if not original:
        # Original was {} — leave the now-empty containers map in place.
        return
    _patch_cr(api, ctx, {"spec": {"containers": original}})


def _patch_cr(api: client.CustomObjectsApi, ctx: KubeContext, body: dict[str, Any]) -> None:
    api.patch_namespaced_custom_object(
        group=GROUP,
        version=VERSION,
        namespace=ctx.namespace,
        plural=PLURAL,
        name=ctx.cluster_name,
        body=body,
    )


def read_deployment_generation(
    clients: KubeClients, ctx: KubeContext, deployment_name: str
) -> int | None:
    # Snapshot before mutating the CR; pass to wait_for_rollout's `min_generation`
    # so readiness isn't satisfied trivially by the pre-patch Deployment state.
    try:
        dep = clients.apps.read_namespaced_deployment(name=deployment_name, namespace=ctx.namespace)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise
    return dep.metadata.generation


def wait_for_rollout(
    clients: KubeClients,
    ctx: KubeContext,
    deployment_name: str,
    timeout: float,
    poll_interval: float = 3.0,
    min_generation: int | None = None,
) -> None:
    deadline = time.monotonic() + timeout
    last_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            dep = clients.apps.read_namespaced_deployment(
                name=deployment_name, namespace=ctx.namespace
            )
        except ApiException as exc:
            if exc.status == 404:
                time.sleep(poll_interval)
                continue
            raise
        spec_replicas = dep.spec.replicas or 1
        status = dep.status
        last_status = {
            "generation": dep.metadata.generation,
            "observed_generation": status.observed_generation,
            "ready_replicas": status.ready_replicas,
            "updated_replicas": status.updated_replicas,
            "available_replicas": status.available_replicas,
            "spec_replicas": spec_replicas,
            "min_generation": min_generation,
        }
        generation_advanced = (
            min_generation is None or (dep.metadata.generation or 0) > min_generation
        )
        if (
            generation_advanced
            and status.observed_generation
            and dep.metadata.generation
            and status.observed_generation >= dep.metadata.generation
            and (status.ready_replicas or 0) >= spec_replicas
            and (status.updated_replicas or 0) >= spec_replicas
        ):
            return
        time.sleep(poll_interval)
    pod_dump = pod_status_dump(clients, ctx, deployment_name)
    raise TimeoutError(
        f"Deployment {deployment_name!r} did not become ready within {timeout}s. "
        f"Last status: {last_status}\nPods:\n{pod_dump}"
    )


def pod_status_dump(clients: KubeClients, ctx: KubeContext, deployment_name: str) -> str:
    try:
        dep = clients.apps.read_namespaced_deployment(name=deployment_name, namespace=ctx.namespace)
    except ApiException as exc:
        return f"<could not read Deployment {deployment_name}: {exc.status} {exc.reason}>"
    selector_match = (dep.spec.selector.match_labels or {}) if dep.spec.selector else {}
    if not selector_match:
        return "<no selector on deployment>"
    label_selector = ",".join(f"{k}={v}" for k, v in selector_match.items())
    pods = clients.core.list_namespaced_pod(namespace=ctx.namespace, label_selector=label_selector)
    lines: list[str] = []
    for pod in pods.items:
        phase = pod.status.phase
        conditions = ", ".join(f"{c.type}={c.status}" for c in (pod.status.conditions or []))
        cstatuses = []
        for c in pod.status.container_statuses or []:
            state_dict = c.state.to_dict() if c.state else {}
            state_keys = [k for k, v in state_dict.items() if v]
            cstatuses.append(f"{c.name}({','.join(state_keys) or '?'},restarts={c.restart_count})")
        lines.append(
            f"  {pod.metadata.name}: phase={phase} conditions=[{conditions}] "
            f"containers=[{', '.join(cstatuses)}]"
        )
    return "\n".join(lines) if lines else "<no pods matched selector>"


def make_owner_token() -> str:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"
    return f"{user}-{os.getpid()}-{int(time.time())}"


def cleanup_from_snapshot(
    snapshot_path: Path,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
) -> None:
    snap = load_snapshot_file(snapshot_path)
    config.load_kube_config(config_file=kubeconfig, context=kube_context)
    # Surface the active context so an operator can verify it matches the
    # snapshot's cluster before any patch lands.
    try:
        contexts, active = config.list_kube_config_contexts(config_file=kubeconfig)
        active_name = (kube_context or active.get("name")) if active else kube_context
    except Exception:
        active_name = kube_context or "<unknown>"
    print(
        f"[e2e cleanup] using kubectl context {active_name!r}; "
        f"target {snap['cluster_name']!r} in namespace {snap['namespace']!r} "
        f"(from {snapshot_path}). If this is the wrong cluster, abort now.",
        file=sys.stderr,
    )
    api = client.CustomObjectsApi()
    ctx = KubeContext(
        kubeconfig=kubeconfig,
        context=kube_context,
        namespace=snap["namespace"],
        cluster_name=snap["cluster_name"],
    )
    restore_containers(api, ctx, snap.get("containers_value"))
    try:
        release_advisory_lock(api, ctx)
    except ApiException as exc:
        print(
            f"[e2e cleanup] WARNING: failed to release advisory lock on "
            f"{ctx.cluster_name!r}: {exc.status} {exc.reason}",
            file=sys.stderr,
        )
    print(
        f"restored spec.containers on {ctx.cluster_name!r} (namespace "
        f"{ctx.namespace!r}) from {snapshot_path}",
        file=sys.stderr,
    )


def _cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.e2e._kube")
    sub = parser.add_subparsers(dest="cmd", required=True)
    cleanup = sub.add_parser("cleanup", help="restore the CR from the latest snapshot")
    cleanup.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="path to a snapshot file (defaults to the most recent in the cache dir)",
    )
    cleanup.add_argument(
        "--kubeconfig",
        default=None,
        help="path to a kubeconfig file (defaults to KUBECONFIG/$HOME/.kube/config)",
    )
    cleanup.add_argument(
        "--kube-context",
        default=None,
        help="kubectl context name (defaults to the active context)",
    )
    args = parser.parse_args(argv)
    if args.cmd == "cleanup":
        path = args.snapshot or latest_snapshot()
        if not path or not path.exists():
            print(
                f"no snapshot file found under {SNAPSHOT_DIR}; pass --snapshot explicitly",
                file=sys.stderr,
            )
            return 2
        cleanup_from_snapshot(path, args.kubeconfig, args.kube_context)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
