"""Tests for ``mcp_hydrolix.metrics`` registration across processes.

Workers run in spawned subprocesses (``main()`` forces
``multiprocessing.set_start_method("spawn", force=True)`` before uvicorn
starts), and this suite mirrors that by driving each scenario through
``multiprocessing.get_context("spawn")``. A fresh interpreter is the only
reliable way to exercise import-time behavior gated on environment variables,
because ``prometheus_client`` binds its ``ValueClass`` during its own import
and module-level globals in ``mcp_hydrolix.metrics`` are not safe to reload
in-place (the default ``REGISTRY`` rejects duplicate names).
"""

from __future__ import annotations

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable


def _run_in_child(target: Callable[[], Any]) -> Any:
    """Run ``target()`` in a fresh spawned interpreter and return its result.

    Env vars set in the parent (e.g. via ``monkeypatch.setenv``) are inherited
    by the child at spawn time.
    """
    with ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn")) as ex:
        return ex.submit(target).result(timeout=30)


def _probe_via_webapp_import() -> dict[str, str]:
    """Import the worker entry path, report the shape of each METRICS collector."""
    import mcp_hydrolix.webapp  # noqa: F401  # triggers mcp_server → metrics chain
    from mcp_hydrolix import metrics
    from mcp_hydrolix.metrics import _PidGuarded

    # Live collectors are wrapped in a _PidGuarded subclass — peek through
    # via _inner. Disabled metrics are a bare _NoOpMetric (not wrapped).
    def inner_name(collector: object) -> str:
        if isinstance(collector, _PidGuarded):
            return type(collector._inner).__name__
        return type(collector).__name__

    return {
        "tool_calls_total": inner_name(metrics.METRICS.tool_calls_total),
        "tool_call_duration_seconds": inner_name(metrics.METRICS.tool_call_duration_seconds),
        "queries_total": inner_name(metrics.METRICS.queries_total),
        "query_duration_seconds": inner_name(metrics.METRICS.query_duration_seconds),
        "active_requests": inner_name(metrics.METRICS.active_requests),
    }


def _probe_filesystem_no_side_effects() -> dict[str, list[str]]:
    """Import metrics with metrics_enabled=false, report REGISTRY state."""
    from mcp_hydrolix import metrics  # noqa: F401  # import-time side effects only
    from prometheus_client import REGISTRY

    hydrolix_names = {
        name
        for _, names in REGISTRY._collector_to_names.items()  # type: ignore[attr-defined]
        for name in names
        if name.startswith("mcp_hydrolix_")
    }
    return {"hydrolix_registered": sorted(hydrolix_names)}


def _set_child_env(monkeypatch, *, metrics_enabled: str) -> None:
    monkeypatch.setenv("HYDROLIX_HOST", "example.invalid")
    monkeypatch.setenv("HYDROLIX_METRICS_ENABLED", metrics_enabled)
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)


class TestMetricsRegistrationInWorkers:
    """Ensure metrics are registered when workers import the app — the regression this plan fixes."""

    def test_live_collectors_when_enabled(self, monkeypatch) -> None:
        _set_child_env(monkeypatch, metrics_enabled="true")
        result = _run_in_child(_probe_via_webapp_import)
        assert result["tool_calls_total"] == "Counter"
        assert result["tool_call_duration_seconds"] == "Histogram"
        assert result["queries_total"] == "Counter"
        assert result["query_duration_seconds"] == "Histogram"
        assert result["active_requests"] == "Gauge"

    def test_noop_collectors_when_disabled(self, monkeypatch) -> None:
        _set_child_env(monkeypatch, metrics_enabled="false")
        result = _run_in_child(_probe_via_webapp_import)
        for field in (
            "tool_calls_total",
            "tool_call_duration_seconds",
            "queries_total",
            "query_duration_seconds",
            "active_requests",
        ):
            assert result[field] == "_NoOpMetric", f"{field} was {result[field]!r}"


class TestFilesystemSideEffects:
    """When metrics are disabled, no collectors touch the default REGISTRY — no mmap files."""

    def test_disabled_does_not_pollute_default_registry(self, monkeypatch) -> None:
        _set_child_env(monkeypatch, metrics_enabled="false")
        result = _run_in_child(_probe_filesystem_no_side_effects)
        assert result["hydrolix_registered"] == []


def _stub_get_config(monkeypatch, *, metrics_enabled: bool, mcp_workers: int) -> None:
    """Replace ``mcp_env.get_config`` with a stub returning a bare config-like object."""
    from mcp_hydrolix import mcp_env

    class _C:
        pass

    cfg = _C()
    cfg.metrics_enabled = metrics_enabled
    cfg.mcp_workers = mcp_workers
    monkeypatch.setattr(mcp_env, "get_config", lambda: cfg)


class TestSupervisorPrep:
    """Unit tests for main._prepare_prometheus_multiproc_dir."""

    def test_no_op_when_metrics_disabled(self, tmp_path, monkeypatch) -> None:
        from mcp_hydrolix.main import _prepare_prometheus_multiproc_dir

        _stub_get_config(monkeypatch, metrics_enabled=False, mcp_workers=3)
        monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
        stale = tmp_path / "stale.db"
        stale.write_text("old")

        _prepare_prometheus_multiproc_dir()

        assert stale.exists(), "must not touch the dir when metrics are disabled"

    def test_no_op_when_single_worker(self, tmp_path, monkeypatch) -> None:
        from mcp_hydrolix.main import _prepare_prometheus_multiproc_dir

        _stub_get_config(monkeypatch, metrics_enabled=True, mcp_workers=1)
        monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
        stale = tmp_path / "stale.db"
        stale.write_text("old")

        _prepare_prometheus_multiproc_dir()

        assert stale.exists()

    def test_wipes_multiproc_dir_when_enabled_and_multi_worker(self, tmp_path, monkeypatch) -> None:
        from mcp_hydrolix.main import _prepare_prometheus_multiproc_dir

        _stub_get_config(monkeypatch, metrics_enabled=True, mcp_workers=3)
        monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
        stale = tmp_path / "stale.db"
        stale.write_text("old")

        _prepare_prometheus_multiproc_dir()

        assert not stale.exists(), "wipe should have cleared the pre-existing file"
        assert tmp_path.exists(), "directory should be recreated after wipe"


class _FakeCounter:
    """Picklable stand-in for a prometheus collector.

    Lives at module scope because ``ProcessPoolExecutor`` with the spawn
    context pickles the callable target; locally-defined classes can't be
    re-imported in the child interpreter.
    """

    def labels(self, *_a, **_k):
        return self

    def inc(self, _amount: float = 1.0) -> None:  # pragma: no cover - must not be reached
        raise AssertionError("inner.inc should not be reached when PIDs differ")


def _touch_pid_guarded_counter_in_child(parent_pid: int) -> str:
    """Build a ``_CounterGuarded`` owned by ``parent_pid``, then try to use it here.

    The child's real PID differs from ``parent_pid``, so the guard must
    refuse with ``RuntimeError``.
    """
    from mcp_hydrolix.metrics import _PidGuardedCounter

    # Rebuild the guard in-process rather than shipping a pickled live
    # collector: prometheus_client collectors hold internal locks that don't
    # survive pickling, and the behavior under test is purely the PID check
    # (os.getpid() vs a stored int), so a duck-typed fake is sufficient.
    # owner_pid=parent_pid forces the mismatch _check() must catch.
    guard = _PidGuardedCounter(_FakeCounter(), owner_pid=parent_pid)  # type: ignore[arg-type]

    try:
        guard.labels(tool="x", status="ok").inc()
    except RuntimeError as e:
        return f"raised: {e}"
    return "did-not-raise"


class TestGuarded:
    """The single runtime check protecting the multiprocess collector invariant."""

    def test_raises_on_cross_process_access(self) -> None:
        import functools
        import os

        parent_pid = os.getpid()
        target = functools.partial(_touch_pid_guarded_counter_in_child, parent_pid)
        result = _run_in_child(target)
        assert result.startswith("raised:"), f"expected RuntimeError in child, got {result!r}"
        assert "pid" in result.lower()

    def test_allows_same_process_access(self) -> None:
        """Positive control: in-process access proceeds to the inner collector."""
        # Route each method through the guard that legitimately exposes it —
        # the types forbid e.g. _PidGuardedHistogram.inc.
        from mcp_hydrolix.metrics import _PidGuardedCounter, _PidGuardedGauge, _PidGuardedHistogram

        calls: list[tuple[str, tuple, dict]] = []

        class _FakeCounter:
            def labels(self, *a, **k):
                calls.append(("labels", a, k))
                return self

            def inc(self, amount: float = 1.0) -> None:
                calls.append(("inc", (amount,), {}))

        class _FakeGauge:
            def labels(self, *a, **k):
                calls.append(("labels", a, k))
                return self

            def inc(self, amount: float = 1.0) -> None:
                calls.append(("inc", (amount,), {}))

            def dec(self, amount: float = 1.0) -> None:
                calls.append(("dec", (amount,), {}))

        class _FakeHistogram:
            def labels(self, *a, **k):
                calls.append(("labels", a, k))
                return self

            def observe(self, amount: float) -> None:
                calls.append(("observe", (amount,), {}))

        _PidGuardedCounter(_FakeCounter()).labels(tool="x").inc()  # type: ignore[arg-type]
        _PidGuardedHistogram(_FakeHistogram()).observe(0.42)  # type: ignore[arg-type]
        _PidGuardedGauge(_FakeGauge()).dec()  # type: ignore[arg-type]

        names = [c[0] for c in calls]
        assert names == ["labels", "inc", "observe", "dec"], f"got {calls}"
