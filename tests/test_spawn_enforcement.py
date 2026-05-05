"""Unit tests for the spawn start method enforcement in ``main()``.

The HTTP/SSE path calls ``uvicorn.run(..., workers=N)`` which creates worker
processes via ``multiprocessing``. On POSIX the default start method is
``fork``, which would let workers inherit supervisor module state, open file
descriptors, and (critically) ``prometheus_client`` collectors keyed to the
supervisor PID. Forcing ``spawn`` makes every worker a fresh interpreter and
is our primary cross-process correctness guarantee.

These tests pin:
  1. ``set_start_method`` is called with ``"spawn"`` and ``force=True``.
  2. It is called *before* ``uvicorn.run``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


def _stub_config(monkeypatch) -> None:
    """Minimal config stub so ``main()`` reaches the uvicorn branch quickly."""
    from mcp_hydrolix import mcp_env

    class _C:
        pass

    cfg = _C()
    cfg.metrics_enabled = False
    cfg.mcp_workers = 1
    cfg.mcp_server_transport = "http"
    cfg.mcp_bind_host = "127.0.0.1"
    cfg.mcp_bind_port = 8000
    cfg.mcp_keepalive = 5
    cfg.mcp_worker_connections = 100
    cfg.mcp_max_requests = 0
    cfg.mcp_max_requests_jitter = 0
    cfg.mcp_graceful_timeout = 10
    cfg.mcp_worker_healthcheck_timeout = 15
    monkeypatch.setattr(mcp_env, "get_config", lambda: cfg)


class TestSpawnEnforcement:
    def test_main_calls_set_start_method_with_spawn_and_force_true(self, monkeypatch) -> None:
        from mcp_hydrolix import main as main_mod

        _stub_config(monkeypatch)

        calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        def recorder(*args: Any, **kwargs: Any) -> None:
            calls.append((args, kwargs))

        monkeypatch.setattr(main_mod.multiprocessing, "set_start_method", recorder)
        monkeypatch.setattr(main_mod.uvicorn, "run", MagicMock())
        # Avoid touching real logging dictConfig
        monkeypatch.setattr(main_mod, "setup_logging", lambda *_a, **_k: {"version": 1})
        monkeypatch.setattr(main_mod.lconfig, "dictConfig", lambda *_a, **_k: None)

        main_mod.main()

        assert calls, "set_start_method was never called"
        args, kwargs = calls[0]
        assert args[0] == "spawn"
        assert kwargs.get("force") is True

    def test_set_start_method_precedes_uvicorn_run(self, monkeypatch) -> None:
        from mcp_hydrolix import main as main_mod

        _stub_config(monkeypatch)

        order: list[str] = []

        def record_set(*_a: Any, **_k: Any) -> None:
            order.append("set_start_method")

        def record_run(*_a: Any, **_k: Any) -> None:
            order.append("uvicorn.run")

        monkeypatch.setattr(main_mod.multiprocessing, "set_start_method", record_set)
        monkeypatch.setattr(main_mod.uvicorn, "run", record_run)
        monkeypatch.setattr(main_mod, "setup_logging", lambda *_a, **_k: {"version": 1})
        monkeypatch.setattr(main_mod.lconfig, "dictConfig", lambda *_a, **_k: None)

        main_mod.main()

        assert order.index("set_start_method") < order.index("uvicorn.run"), (
            f"set_start_method must precede uvicorn.run; got order {order}"
        )
