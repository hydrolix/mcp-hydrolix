"""Text-level normalisation of user SQL before it reaches the driver (HDX-12410).

clickhouse-connect appends its own ``FORMAT Native`` to every query, so a FORMAT
clause left in by the agent produces two and ClickHouse refuses the statement.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from mcp_hydrolix.statement import normalize_statement, tokenize


class TestTokenize:
    def test_drops_line_and_block_comments(self):
        texts = [t.text for t in tokenize("/* a */ SELECT 1 -- b\n# c\n#! d\nFROM db.t")]
        assert texts == ["SELECT", "1", "FROM", "db", ".", "t"]

    def test_nested_block_comment_ends_at_last_close(self):
        assert [t.text for t in tokenize("SELECT 1 /* a /* b */ ; DROP */")] == ["SELECT", "1"]

    def test_literal_and_quoted_identifier_are_single_tokens(self):
        tokens = tokenize("SELECT 'it\\'s; x', `weird col`, \"q\" FROM db.t")
        assert [t.kind for t in tokens][:4] == ["word", "literal", "punct", "quoted"]

    def test_apostrophe_in_hash_comment_does_not_open_a_string(self):
        assert [t.text for t in tokenize("SELECT 1 # it's\n; DROP TABLE x")][2:4] == [";", "DROP"]

    def test_keyword_after_identifier_dot_or_as_is_identifier(self):
        tokens = tokenize("SELECT a.format AS format FROM db.settings")
        assert [t.text for t in tokens if t.is_identifier] == ["format", "format", "settings"]

    def test_depth_tracks_parentheses(self):
        tokens = tokenize("SELECT (SELECT 1) FROM db.t")
        assert [t.depth for t in tokens if t.text in ("SELECT", "FROM")] == [0, 1, 0]


class TestNormalizeStatement:
    def test_strips_trailing_format_clause(self):
        result = normalize_statement("SELECT a FROM db.t FORMAT JSONEachRow;")
        assert result.sql == "SELECT a FROM db.t"
        assert result.format_removed is True

    def test_strips_format_with_trailing_comment(self):
        result = normalize_statement("SELECT a FROM db.t FORMAT JSON -- done")
        assert result.sql == "SELECT a FROM db.t"
        assert result.format_removed is True

    def test_keeps_format_function_call(self):
        sql = "SELECT format('{}', a) FROM db.t"
        result = normalize_statement(sql)
        assert result.sql == sql
        assert result.format_removed is False

    @pytest.mark.parametrize(
        "sql",
        ["SELECT toString(1) AS format FROM db.t", "SELECT a FROM db.t ORDER BY format"],
    )
    def test_keeps_format_alias_and_column(self, sql):
        assert normalize_statement(sql).sql == sql

    def test_drops_trailing_semicolon_and_comments(self):
        result = normalize_statement("/* lead */ SELECT 1 FROM db.t;  -- trail")
        assert result.sql == "SELECT 1 FROM db.t"
        assert result.format_removed is False

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT count() FROM db.t WHERE name = 'x'",
            "SELECT * FROM db.t WHERE ts > '2024-01-01'",
            "SELECT `weird col` FROM db.`my table`",
            'SELECT 1 FROM db."quoted table"',
            "SELECT 'a; DROP TABLE x' FROM db.t",
        ],
    )
    def test_preserves_statement_ending_in_literal_or_quoted(self, sql):
        assert normalize_statement(sql).sql == sql

    def test_leaves_inner_semicolons_alone(self):
        assert normalize_statement("SELECT 1; SELECT 2").sql == "SELECT 1; SELECT 2"

    def test_empty_input_is_returned_empty(self):
        assert normalize_statement("  -- nothing \n").sql == ""


@pytest.mark.integration_clickhouse
class TestAgentFormatClauseOnCluster:
    async def test_run_select_query_accepts_agent_format_clause(
        self, mcp_server, setup_test_database
    ):
        test_db, test_table, _ = setup_test_database
        async with Client(mcp_server) as client:
            result = await client.call_tool(
                "run_select_query",
                {
                    "query": f"SELECT id FROM {test_db}.{test_table} ORDER BY id LIMIT 2 FORMAT JSON;"
                },
            )
        assert result.structured_content["rows"] == [[1], [2]]
