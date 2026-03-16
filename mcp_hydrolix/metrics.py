import os
from dataclasses import dataclass

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

NAMESPACE = "mcp_hydrolix"
LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, float("inf"))


@dataclass
class _Metrics:
    tool_calls_total: Counter
    tool_call_duration_seconds: Histogram
    queries_total: Counter
    query_duration_seconds: Histogram
    active_requests: Gauge


_instance: _Metrics | None = None


def enable() -> None:
    """Register all metrics. Must be called before any instrumentation."""
    global _instance
    _instance = _Metrics(
        tool_calls_total=Counter(
            "tool_calls_total",
            "Total MCP tool calls by tool name and outcome",
            ["tool", "status"],
            namespace=NAMESPACE,
        ),
        tool_call_duration_seconds=Histogram(
            "tool_call_duration_seconds",
            "MCP tool call latency in seconds",
            ["tool"],
            namespace=NAMESPACE,
            buckets=LATENCY_BUCKETS,
        ),
        queries_total=Counter(
            "queries_total",
            "Total Hydrolix queries by outcome",
            ["status"],
            namespace=NAMESPACE,
        ),
        query_duration_seconds=Histogram(
            "query_duration_seconds",
            "Hydrolix query latency in seconds",
            namespace=NAMESPACE,
            buckets=LATENCY_BUCKETS,
        ),
        active_requests=Gauge(
            "active_requests",
            "Number of in-flight MCP tool calls",
            namespace=NAMESPACE,
            multiprocess_mode="sum",
        ),
    )


def get_instance() -> _Metrics | None:
    return _instance


def generate_metrics() -> tuple[bytes, str]:
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = REGISTRY
    return generate_latest(registry), CONTENT_TYPE_LATEST
