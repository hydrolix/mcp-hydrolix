"""Prometheus metrics for the MCP Hydrolix server.

Lifecycle
---------
When ``HYDROLIX_METRICS_ENABLED=true`` and ``HYDROLIX_MCP_WORKERS > 1``:

1. The launcher (``main.py``) forces ``multiprocessing`` to the ``spawn`` start
   method and sets ``PROMETHEUS_MULTIPROC_DIR`` to a fresh, empty directory
   before uvicorn starts.
2. Each uvicorn worker is a fresh interpreter that re-imports the webapp
   factory, which pulls in this module. Import-time side effects pick up
   ``PROMETHEUS_MULTIPROC_DIR`` and cause ``prometheus_client`` to choose its
   multiprocess, mmap-backed value class; construct the ``METRICS`` dataclass
   of real collectors; and register a ``mark_process_dead`` atexit handler.
3. Any worker's ``/metrics`` endpoint uses ``MultiProcessCollector`` to merge
   every worker's mmap files into a single scrape response.

When metrics are disabled, ``METRICS`` holds inert ``_NoOpMetric`` stand-ins. The
default ``REGISTRY`` is not touched and no mmap files are created.

Cross-process misuse is caught structurally by the ``_PidGuarded`` wrapper
hierarchy below: collectors record ``os.getpid()`` at construction and refuse
access from any other PID.
"""

from __future__ import annotations

import atexit
import logging
import os
from dataclasses import dataclass
from typing import Final, Generic, Self, TypeVar

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)

from .mcp_env import get_config

NAMESPACE = "mcp_hydrolix"
LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, float("inf"))


class _NoOpMetric:
    def labels(self, *args: object, **kwargs: object) -> "_NoOpMetric":
        return self

    def inc(self, amount: float = 1.0) -> None:
        pass

    def dec(self, amount: float = 1.0) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass


_NOOP: Final[_NoOpMetric] = _NoOpMetric()

_MetricT = TypeVar("_MetricT", Counter, Gauge, Histogram)


class _PidGuarded(Generic[_MetricT]):
    """
    Decorator pinning a prometheus collector to its construction PID.

    Any access from a process other than the one that constructed the inner
    collector raises ``RuntimeError``. This is the sole runtime check guarding
    the multiprocess invariant: prometheus_client's mmap files are keyed by the
    PID recorded at collector construction, so cross-process access corrupts
    aggregation silently. Catching it here fails loudly instead.

    ``labels`` wraps its return value in the same concrete guard subclass so
    child collectors inherit both the guard and the static type of the parent.
    Labeled wrappers are cached per label tuple, emulating prometheus's implementation
    """

    __slots__ = ("_inner", "_owner_pid", "_children")
    _inner: _MetricT
    _owner_pid: int

    def __init__(self, inner: _MetricT, *, owner_pid: int | None = None) -> None:
        self._inner = inner
        self._owner_pid = os.getpid() if owner_pid is None else owner_pid
        self._children: dict[tuple[tuple[object, ...], tuple[tuple[str, object], ...]], Self] = (
            dict()
        )

    def _check(self) -> None:
        cur = os.getpid()
        if cur != self._owner_pid:
            raise RuntimeError(
                f"Prometheus collector accessed from pid={cur} but was "
                f"constructed in pid={self._owner_pid}. Cross-process access "
                "corrupts prometheus_client's multiprocess mmap files."
            )

    def labels(self, *args: object, **kwargs: object) -> Self:
        self._check()
        key = (args, tuple(sorted(kwargs.items())))
        cached = self._children.get(key)
        if cached is None:
            cached = type(self)(self._inner.labels(*args, **kwargs), owner_pid=self._owner_pid)
            self._children[key] = cached
        return cached


class _PidGuardedCounter(_PidGuarded[Counter]):
    __slots__ = ()

    def inc(self, amount: float = 1.0) -> None:
        self._check()
        self._inner.inc(amount)


class _PidGuardedGauge(_PidGuarded[Gauge]):
    __slots__ = ()

    def inc(self, amount: float = 1.0) -> None:
        self._check()
        self._inner.inc(amount)

    def dec(self, amount: float = 1.0) -> None:
        self._check()
        self._inner.dec(amount)


class _PidGuardedHistogram(_PidGuarded[Histogram]):
    __slots__ = ()

    def observe(self, amount: float) -> None:
        self._check()
        self._inner.observe(amount)


@dataclass(frozen=True)
class Metrics:
    tool_calls_total: _PidGuardedCounter | _NoOpMetric
    tool_call_duration_seconds: _PidGuardedHistogram | _NoOpMetric
    queries_total: _PidGuardedCounter | _NoOpMetric
    query_duration_seconds: _PidGuardedHistogram | _NoOpMetric
    active_requests: _PidGuardedGauge | _NoOpMetric


def _build_live() -> Metrics:
    return Metrics(
        tool_calls_total=_PidGuardedCounter(
            Counter(
                "tool_calls_total",
                "Total MCP tool calls by tool name and outcome",
                ["tool", "status"],
                namespace=NAMESPACE,
            )
        ),
        tool_call_duration_seconds=_PidGuardedHistogram(
            Histogram(
                "tool_call_duration_seconds",
                "MCP tool call latency in seconds",
                ["tool"],
                namespace=NAMESPACE,
                buckets=LATENCY_BUCKETS,
            )
        ),
        queries_total=_PidGuardedCounter(
            Counter(
                "queries_total",
                "Total Hydrolix queries by outcome",
                ["status"],
                namespace=NAMESPACE,
            )
        ),
        query_duration_seconds=_PidGuardedHistogram(
            Histogram(
                "query_duration_seconds",
                "Hydrolix query latency in seconds",
                namespace=NAMESPACE,
                buckets=LATENCY_BUCKETS,
            )
        ),
        active_requests=_PidGuardedGauge(
            Gauge(
                "active_requests",
                "Number of in-flight MCP tool calls",
                namespace=NAMESPACE,
                multiprocess_mode="sum",
            )
        ),
    )


def _build_noop() -> Metrics:
    return Metrics(
        tool_calls_total=_NOOP,
        tool_call_duration_seconds=_NOOP,
        queries_total=_NOOP,
        query_duration_seconds=_NOOP,
        active_requests=_NOOP,
    )


_config: Final = get_config()
_enabled: Final[bool] = _config.metrics_enabled
METRICS: Final[Metrics] = _build_live() if _enabled else _build_noop()


def _mark_worker_dead() -> None:
    """atexit handler for prometheus multiprocess mode."""
    multiprocess.mark_process_dead(os.getpid())


if _enabled and "PROMETHEUS_MULTIPROC_DIR" in os.environ:
    atexit.register(_mark_worker_dead)
    if _config.mcp_workers == 1:
        # prometheus_client is now in mmap mode (that decision was already
        # baked in at its own import time), but the launcher only wipes the
        # dir when workers>1. Stale samples from a prior run will merge into
        # scrapes; single-worker mode should use the default REGISTRY instead.
        logging.getLogger(__name__).warning(
            "HYDROLIX_METRICS_ENABLED=true with workers=1 but "
            "PROMETHEUS_MULTIPROC_DIR is set. prometheus_client is operating "
            "in multiprocess mode and the directory was not wiped at startup, "
            "so stale samples from prior runs may appear in /metrics. Unset "
            "PROMETHEUS_MULTIPROC_DIR for single-worker mode."
        )
elif _enabled and _config.mcp_workers > 1:
    # With workers>1 this means the launcher was bypassed (e.g.
    # ``uvicorn mcp_hydrolix.webapp:create_app --workers 2`` directly, or a
    # container manifest that forgets the ``mcp-hydrolix`` CLI): each worker
    # would register its own in-memory REGISTRY and /metrics would return
    # per-process, inconsistent data across scrapes.
    logging.getLogger(__name__).warning(
        "HYDROLIX_METRICS_ENABLED=true and workers>1 but PROMETHEUS_MULTIPROC_DIR "
        "is unset. Metrics will not be aggregated correctly across workers. "
        "Please launch via the mcp-hydrolix:main module."
    )


def generate_metrics() -> tuple[bytes, str]:
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = REGISTRY
    return generate_latest(registry), CONTENT_TYPE_LATEST
