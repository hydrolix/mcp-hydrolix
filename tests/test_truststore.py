"""Tests for truststore OS certificate store integration."""

import logging
import sys
import types
import unittest.mock as mock

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
