"""Tests for truststore OS certificate store integration."""

import json
import logging
import os
import subprocess
import sys
import textwrap
import types
import unittest.mock as mock

import pytest

from mcp_hydrolix import inject_truststore


class TestTruststoreDisableEnvVar:
    """MCP_HYDROLIX_TRUSTSTORE_DISABLE=1 must be the only value that skips injection."""

    @staticmethod
    def _run(monkeypatch, disable_value=None):
        if disable_value is None:
            monkeypatch.delenv("MCP_HYDROLIX_TRUSTSTORE_DISABLE", raising=False)
        else:
            monkeypatch.setenv("MCP_HYDROLIX_TRUSTSTORE_DISABLE", disable_value)

        mock_inject = mock.MagicMock()
        fake_ts = types.ModuleType("truststore")
        fake_ts.inject_into_ssl = mock_inject

        with mock.patch.dict(sys.modules, {"truststore": fake_ts}):
            inject_truststore()

        return mock_inject

    def test_inject_called_without_env_var(self, monkeypatch):
        self._run(monkeypatch).assert_called_once()

    def test_inject_skipped_when_set_to_1(self, monkeypatch):
        self._run(monkeypatch, "1").assert_not_called()

    def test_inject_called_when_set_to_0(self, monkeypatch):
        self._run(monkeypatch, "0").assert_called_once()

    def test_inject_called_when_set_to_true(self, monkeypatch):
        # Only the exact string "1" opts out — "true" must not suppress injection
        self._run(monkeypatch, "true").assert_called_once()


class TestTruststoreFailureIsolation:
    """Errors from truststore must never prevent the server from starting."""

    def test_inject_exception_emits_log_warning(self, monkeypatch, caplog):
        monkeypatch.delenv("MCP_HYDROLIX_TRUSTSTORE_DISABLE", raising=False)
        failing_ts = types.ModuleType("truststore")
        failing_ts.inject_into_ssl = mock.MagicMock(side_effect=RuntimeError("ssl init error"))

        with mock.patch.dict(sys.modules, {"truststore": failing_ts}):
            with caplog.at_level(logging.WARNING, logger="mcp_hydrolix"):
                inject_truststore()

        assert any("truststore injection failed" in r.message for r in caplog.records)
        assert any("ssl init error" in r.message for r in caplog.records)

    def test_missing_package_emits_log_warning(self, monkeypatch, caplog):
        # sys.modules[key] = None makes `import key` raise ImportError
        monkeypatch.delenv("MCP_HYDROLIX_TRUSTSTORE_DISABLE", raising=False)
        with mock.patch.dict(sys.modules, {"truststore": None}):
            with caplog.at_level(logging.WARNING, logger="mcp_hydrolix"):
                inject_truststore()

        assert any("truststore injection failed" in r.message for r in caplog.records)


class TestTruststoreInjectedInWorkerProcess:
    """Regression: a fresh Python interpreter that imports the package (or any submodule)
    must end up with truststore patched into ssl. Worker processes spawned by the HTTP
    server rely on this side effect firing at package-import time. Migrating between
    servers (gunicorn -> uvicorn) or worker start methods (fork -> spawn) must not
    silently break the invariant. The suites above verify the behavior of `inject_truststore`,
    this suite verifies that inject_truststore gets called when it needs to be.
    """

    @pytest.mark.parametrize(
        "import_stmt",  # any of these should be sufficient to load the truststore
        [
            "import mcp_hydrolix",
            "import mcp_hydrolix.main",
            "import mcp_hydrolix.mcp_server",
        ],
    )
    def test_package_import_patches_ssl_in_fresh_process(self, import_stmt: str) -> None:
        # truststore.inject_into_ssl() rebinds ssl.SSLContext to truststore.SSLContext.
        # Emit the pre/post module names as JSON on the last stdout line so the
        # parent can recover them robustly even if upstream emits stray stdout
        # (deprecation notices, plugin chatter, etc.).
        subprocess_code = textwrap.dedent(f"""
            import json, ssl
            pre = ssl.SSLContext.__module__
            {import_stmt}
            post = ssl.SSLContext.__module__
            print(json.dumps({{"pre": pre, "post": post}}))
        """)
        result = subprocess.run(
            [sys.executable, "-c", subprocess_code],
            capture_output=True,
            text=True,
            check=True,
            env={
                **os.environ,
                # mcp_hydrolix/__init__.py imports mcp_server, which calls get_config()
                # at module level and requires HYDROLIX_HOST. The value is unused here;
                # we never connect.
                "HYDROLIX_HOST": "localhost",
                # Ensure no stray opt-out leaks from the parent test environment.
                "MCP_HYDROLIX_TRUSTSTORE_DISABLE": "",
            },
        )
        last_line = result.stdout.strip().splitlines()[-1]
        parts = json.loads(last_line)
        assert parts["pre"] == "ssl", (
            f"expected unpatched ssl before import; got pre={parts['pre']!r}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        # truststore.inject_into_ssl() rebinds ssl.SSLContext to the class defined in
        # truststore._api; accept any submodule of truststore so the test isn't brittle
        # to truststore's internal layout.
        assert parts["post"] == "truststore" or parts["post"].startswith("truststore."), (
            f"expected ssl.SSLContext to be replaced by truststore after "
            f"{import_stmt!r}; got post={parts['post']!r}. "
            f"Worker processes will not have OS trust store integration.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

    def test_disable_env_var_respected_in_fresh_process(self) -> None:
        # Confirms the opt-out path also works at the worker-process boundary —
        # so the regression test above can't be satisfied by always-on injection.
        code = textwrap.dedent("""
            import ssl
            import mcp_hydrolix  # noqa: F401
            print(ssl.SSLContext.__module__)
        """)
        env = {
            **os.environ,
            "HYDROLIX_HOST": "localhost",
            "MCP_HYDROLIX_TRUSTSTORE_DISABLE": "1",
        }
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        assert result.stdout.strip() == "ssl", (
            f"MCP_HYDROLIX_TRUSTSTORE_DISABLE=1 should suppress injection; "
            f"got ssl.SSLContext.__module__={result.stdout.strip()!r}"
        )
