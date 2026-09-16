"""Read-only preflight for user-supplied SQL (HDX-12410).

One statement, read verbs only, no top-level SETTINGS, FORMAT stripped; the
scenario names mirror openspec/changes/gateway-hardening/specs/query-preflight.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp.exceptions import ToolError

from mcp_hydrolix.models import HdxQueryResult
from mcp_hydrolix.preflight import (
    READ_STATEMENT_PREFIXES,
    SETTINGS_CLAUSE_REASON,
    SINGLE_STATEMENT_REASON,
    preflight,
)
from mcp_hydrolix.utils import UnparseableQueryError, strip_conflicting_settings


class TestReadStatementAllowList:
    @pytest.mark.parametrize("prefix", READ_STATEMENT_PREFIXES)
    def test_allows_each_read_prefix(self, prefix):
        result = preflight(f"{prefix.lower()} something FROM db.t")
        assert result.blocked is False
        assert result.sql.startswith(prefix.lower())

    @pytest.mark.parametrize("statement", ["INSERT INTO db.t VALUES (1)", "drop table db.t"])
    def test_blocks_write_statement_with_reason(self, statement):
        result = preflight(statement)
        assert result.blocked is True
        assert "read-only" in result.block_reason
        assert statement.split()[0].upper() in result.block_reason

    def test_suggests_closest_read_keyword_for_typo(self):
        result = preflight("SELCT 1")
        assert result.blocked is True
        assert "Did you mean SELECT?" in result.block_reason

    def test_blocks_statement_not_starting_with_a_word(self):
        result = preflight("(SELECT 1)")
        assert result.blocked is True
        assert "Only SELECT" in result.block_reason

    @pytest.mark.parametrize("sql", ["", "   ", "-- nothing here", "/* only a comment */ ;"])
    def test_blocks_empty_query(self, sql):
        result = preflight(sql)
        assert result.blocked is True
        assert result.block_reason == "Empty query."


class TestSingleStatementGuard:
    def test_blocks_multiple_statements(self):
        result = preflight("SELECT 1; DROP TABLE db.t")
        assert result.blocked is True
        assert result.block_reason == SINGLE_STATEMENT_REASON

    def test_drops_trailing_semicolon(self):
        result = preflight("SELECT 1 FROM db.t;  -- done")
        assert result.blocked is False
        assert result.sql == "SELECT 1 FROM db.t"

    def test_ignores_semicolon_inside_string_literal(self):
        result = preflight("SELECT 'a; DROP TABLE x', 'it\\'s' FROM db.t")
        assert result.blocked is False

    def test_blocks_literal_after_semicolon(self):
        # A literal is a significant element too: the text after the semicolon
        # must never be silently dropped and the first statement run alone.
        result = preflight("SELECT 1; 'x'")
        assert result.blocked is True
        assert result.block_reason == SINGLE_STATEMENT_REASON

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT count() FROM db.t WHERE name = 'x'",
            "SELECT * FROM db.t WHERE ts > '2024-01-01'",
            "SELECT `weird col` FROM db.`my table`",
            'SELECT 1 FROM db."quoted table"',
        ],
    )
    def test_preserves_trailing_literal(self, sql):
        result = preflight(sql)
        assert result.blocked is False
        assert result.sql == sql


class TestSettingsClauseRefused:
    def test_blocks_top_level_settings_clause(self):
        result = preflight("SELECT a FROM db.t SETTINGS readonly = 0")
        assert result.blocked is True
        assert result.block_reason == SETTINGS_CLAUSE_REASON

    def test_allows_system_settings_table(self):
        result = preflight("SELECT name FROM system.settings WHERE name LIKE 'hdx%'")
        assert result.blocked is False

    def test_allows_nested_settings_for_stripper(self):
        result = preflight("SELECT * FROM (SELECT a FROM db.t SETTINGS max_threads = 1) AS s")
        assert result.blocked is False

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT x FROM db.t WHERE a = 1. SETTINGS readonly=0",
            "SELECT x FROM db.t WHERE a = 1.\nSETTINGS readonly=0",
            "SELECT x FROM db.t WHERE a = 'b' SETTINGS readonly=0",
            "SELECT x FROM db.t WHERE a = `b` SETTINGS readonly=0",
        ],
    )
    def test_blocks_settings_after_numeric_literal(self, sql):
        # The identifier exemption applies after `identifier.` only; a float
        # literal's trailing dot or a closing quote must not hide a clause.
        result = preflight(sql)
        assert result.blocked is True
        assert result.block_reason == SETTINGS_CLAUSE_REASON

    def test_allows_settings_as_alias(self):
        result = preflight("SELECT toString(1) AS settings FROM db.t")
        assert result.blocked is False

    def test_refuses_unparseable_query_with_settings(self):
        with pytest.raises(UnparseableQueryError):
            strip_conflicting_settings("SELECT ((( FROM SETTINGS readonly=0", {"readonly"})

    def test_ignores_settings_substring_in_identifier(self):
        # No SETTINGS keyword means no parse, so a statement sqlglot cannot read
        # is not refused just because a column or literal is spelled "settings".
        sql = "SELECT settings_json, 'settings' FROM ((( db.t"
        assert strip_conflicting_settings(sql, {"readonly"}) == sql


class TestFormatClauseRemoved:
    def test_strips_trailing_format_clause(self):
        result = preflight("SELECT a FROM db.t FORMAT JSONEachRow;")
        assert result.blocked is False
        assert result.format_removed is True
        assert result.sql == "SELECT a FROM db.t"

    def test_keeps_format_function_call(self):
        sql = "SELECT format('{}', a) FROM db.t"
        result = preflight(sql)
        assert result.blocked is False
        assert result.format_removed is False
        assert result.sql == sql


class TestCommentsIgnored:
    def test_ignores_leading_and_trailing_comments(self):
        result = preflight("/* lead */ -- more\nSELECT 1 FROM db.t -- trail\n/* end */")
        assert result.blocked is False
        assert result.sql == "SELECT 1 FROM db.t"

    def test_ignores_keyword_inside_comment(self):
        result = preflight("SELECT 1 FROM db.t /* SETTINGS readonly=0; DROP TABLE x */")
        assert result.blocked is False

    def test_ignores_hash_comment(self):
        # ClickHouse treats `#` and `#!` as line comments; an apostrophe inside
        # one must not open a phantom string that hides what follows.
        result = preflight("SELECT 1 FROM db.t # it's a note\n#! and a shebang-style one")
        assert result.blocked is False
        assert result.sql == "SELECT 1 FROM db.t"

    def test_blocks_statement_hidden_behind_hash_comment(self):
        result = preflight("SELECT 1 # it's\n; DROP TABLE db.t")
        assert result.blocked is True
        assert result.block_reason == SINGLE_STATEMENT_REASON

    def test_handles_nested_block_comment(self):
        # ClickHouse nests block comments, so the outer one ends at the last `*/`.
        result = preflight("SELECT 1 FROM db.t /* a /* b */ ; DROP TABLE x */")
        assert result.blocked is False
        assert result.sql == "SELECT 1 FROM db.t"


class TestPreflightAppliedToRunSelectQuery:
    @patch("mcp_hydrolix.mcp_server.execute_query", new_callable=AsyncMock)
    async def test_refused_statement_raises_tool_error(self, mock_execute):
        from mcp_hydrolix.mcp_server import run_select_query

        with pytest.raises(ToolError, match="read-only"):
            await inspect.unwrap(run_select_query)("INSERT INTO db.t VALUES (1)")
        mock_execute.assert_not_awaited()

    @patch(
        "mcp_hydrolix.mcp_server._query_targets_summary_table",
        new_callable=AsyncMock,
        return_value=False,
    )
    @patch(
        "mcp_hydrolix.mcp_server.execute_query",
        new_callable=AsyncMock,
        return_value=HdxQueryResult(columns=["a"], rows=[[1]]),
    )
    async def test_executes_normalised_statement(self, mock_execute, _summary):
        from mcp_hydrolix.mcp_server import run_select_query

        await inspect.unwrap(run_select_query)(
            "SELECT a FROM db.t WHERE ts > now() - INTERVAL 1 HOUR FORMAT JSON;",
            purpose="why",
        )
        kwargs = mock_execute.call_args.kwargs
        assert "FORMAT" not in kwargs["query"].upper()
        assert kwargs["query"].rstrip(";").upper().startswith("SELECT")
        assert kwargs["comment"] == "why"
