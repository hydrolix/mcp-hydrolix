"""Tests for deprecated-alias detection, audience classification, and the
external WARNING log / ``deprecation_notice`` channels.

The version-gated *internal* probe log lives in ``test_internal_deprecation_version_gate.py``
because it requires patching the ``/version`` HTTP probe.
"""

from __future__ import annotations

import logging
import os

import pytest

from mcp_hydrolix import mcp_env
from mcp_hydrolix.mcp_env import (
    DEPRECATED_ALIASES,
    HydrolixConfig,
    _classify_deprecation,
    _detect_deprecated_aliases,
)


@pytest.fixture(autouse=True)
def _isolate_hydrolix_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("HYDROLIX_"):
            monkeypatch.delenv(key, raising=False)
    mcp_env._external_deprecation_warned = False
    mcp_env._internal_deprecation_warned = False


class TestDetectDeprecatedAliases:
    def test_none_set(self) -> None:
        assert _detect_deprecated_aliases() == []

    def test_single_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "x")
        assert _detect_deprecated_aliases() == ["HYDROLIX_HOST"]

    def test_multiple_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "x")
        monkeypatch.setenv("HYDROLIX_API_PORT", "23925")
        assert _detect_deprecated_aliases() == ["HYDROLIX_HOST", "HYDROLIX_API_PORT"]

    def test_all_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in DEPRECATED_ALIASES:
            monkeypatch.setenv(name, "x")
        assert _detect_deprecated_aliases() == list(DEPRECATED_ALIASES)


class TestClassifyDeprecation:
    def test_no_aliases_returns_none(self) -> None:
        assert _classify_deprecation([]) is None

    def test_external(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "x")
        assert _classify_deprecation(["HYDROLIX_HOST"]) == "external"

    def test_internal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "x")
        monkeypatch.setenv("HYDROLIX_NAME", "mycluster")
        assert _classify_deprecation(["HYDROLIX_HOST"]) == "internal"

    def test_partial_migration_external(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # User has set HYDROLIX_URL AND HYDROLIX_HOST but no HYDROLIX_NAME.
        # They should still get the LLM nudge.
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HOST", "x")
        assert _classify_deprecation(["HYDROLIX_HOST"]) == "external"


class TestExternalWarningLog:
    def test_fires_once_at_init(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "myhost")
        with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
            HydrolixConfig()
        warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "Deprecated" in r.getMessage()
        ]
        assert len(warnings) == 1
        assert "HYDROLIX_HOST" in warnings[0].getMessage()
        assert "HYDROLIX_URL" in warnings[0].getMessage()

    def test_no_duplicate_on_second_construction(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "myhost")
        with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
            HydrolixConfig()
            HydrolixConfig()
        warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "Deprecated" in r.getMessage()
        ]
        assert len(warnings) == 1

    def test_internal_audience_silent_at_init(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "myhost")
        monkeypatch.setenv("HYDROLIX_NAME", "mycluster")
        with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
            HydrolixConfig()
        warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "Deprecated" in r.getMessage()
        ]
        assert warnings == []


class TestDeprecationNotice:
    def test_external_returns_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "myhost")
        c = HydrolixConfig()
        notice = c.deprecation_notice
        assert notice is not None
        assert "HYDROLIX_HOST" in notice
        assert "HYDROLIX_URL" in notice

    def test_internal_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_HOST", "myhost")
        monkeypatch.setenv("HYDROLIX_NAME", "mycluster")
        assert HydrolixConfig().deprecation_notice is None

    def test_no_deprecation_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        assert HydrolixConfig().deprecation_notice is None


class TestNoDeprecationPath:
    def test_only_new_vars_external(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_HTTP_QUERY_PORT", "8088")
        with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
            c = HydrolixConfig()
        assert c.deprecation_notice is None
        assert c.deprecation_audience is None
        warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "Deprecated" in r.getMessage()
        ]
        assert warnings == []

    def test_only_new_vars_with_hydrolix_name(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("HYDROLIX_URL", "https://cluster.example.com")
        monkeypatch.setenv("HYDROLIX_NAME", "mycluster")
        with caplog.at_level(logging.WARNING, logger="mcp-hydrolix"):
            c = HydrolixConfig()
        assert c.deprecation_notice is None
        assert c.deprecation_audience is None
