"""Unit tests for the static query analyzer."""

from mcp_hydrolix.query_analysis import analyze_sql


def codes(analysis) -> set[str]:
    return {f.code for f in analysis.findings}


class TestNoTimeRange:
    def test_no_where_clause_flagged(self):
        a = analyze_sql("SELECT count(*) FROM logs")
        assert "NO_TIME_RANGE" in codes(a)
        assert not a.ok

    def test_where_without_ts_predicate_flagged(self):
        a = analyze_sql("SELECT count(*) FROM logs WHERE app = 'foo'")
        assert "NO_TIME_RANGE" in codes(a)
        assert not a.ok

    def test_bounded_ts_predicate_not_flagged(self):
        a = analyze_sql(
            "SELECT count(*) FROM logs WHERE timestamp >= '2024-01-01' AND timestamp < '2024-01-02'"
        )
        assert "NO_TIME_RANGE" not in codes(a)


class TestUnboundedTimeRange:
    def test_only_lower_bound_flagged(self):
        a = analyze_sql("SELECT app FROM logs WHERE timestamp > now() - INTERVAL 1 HOUR")
        assert "UNBOUNDED_TIME_RANGE" in codes(a)

    def test_only_upper_bound_flagged(self):
        a = analyze_sql("SELECT app FROM logs WHERE timestamp < '2024-01-02'")
        assert "UNBOUNDED_TIME_RANGE" in codes(a)

    def test_both_bounds_not_flagged(self):
        a = analyze_sql(
            "SELECT app FROM logs WHERE timestamp >= '2024-01-01' AND timestamp < '2024-01-02'"
        )
        assert "UNBOUNDED_TIME_RANGE" not in codes(a)

    def test_between_not_flagged(self):
        a = analyze_sql(
            "SELECT app FROM logs WHERE timestamp BETWEEN '2024-01-01' AND '2024-01-02'"
        )
        assert "UNBOUNDED_TIME_RANGE" not in codes(a)

    def test_equality_not_flagged(self):
        a = analyze_sql("SELECT app FROM logs WHERE timestamp = '2024-01-01 00:00:00'")
        assert "UNBOUNDED_TIME_RANGE" not in codes(a)


class TestFnOnTsPk:
    def test_to_date_wrapped_pk_flagged(self):
        a = analyze_sql("SELECT count(*) FROM logs WHERE toDate(timestamp) = '2024-01-01'")
        assert "FN_ON_TS_PK" in codes(a)
        assert not a.ok

    def test_to_start_of_hour_wrapped_pk_flagged(self):
        a = analyze_sql(
            "SELECT count(*) FROM logs "
            "WHERE toStartOfHour(timestamp) >= '2024-01-01' "
            "AND toStartOfHour(timestamp) < '2024-01-02'"
        )
        assert "FN_ON_TS_PK" in codes(a)

    def test_raw_pk_not_flagged(self):
        a = analyze_sql(
            "SELECT count(*) FROM logs WHERE timestamp >= '2024-01-01' AND timestamp < '2024-01-02'"
        )
        assert "FN_ON_TS_PK" not in codes(a)


class TestSelectStar:
    def test_bare_star_flagged(self):
        a = analyze_sql(
            "SELECT * FROM logs WHERE timestamp >= '2024-01-01' AND timestamp < '2024-01-02'"
        )
        assert "SELECT_STAR" in codes(a)

    def test_count_star_not_flagged(self):
        a = analyze_sql(
            "SELECT count(*) FROM logs WHERE timestamp >= '2024-01-01' AND timestamp < '2024-01-02'"
        )
        assert "SELECT_STAR" not in codes(a)

    def test_explicit_columns_not_flagged(self):
        a = analyze_sql(
            "SELECT app, message FROM logs "
            "WHERE timestamp >= '2024-01-01' AND timestamp < '2024-01-02'"
        )
        assert "SELECT_STAR" not in codes(a)


class TestBroadLike:
    def test_leading_wildcard_flagged(self):
        a = analyze_sql(
            "SELECT message FROM logs "
            "WHERE timestamp >= '2024-01-01' AND timestamp < '2024-01-02' "
            "AND message LIKE '%error%'"
        )
        assert "BROAD_LIKE" in codes(a)

    def test_prefix_match_not_flagged(self):
        a = analyze_sql(
            "SELECT message FROM logs "
            "WHERE timestamp >= '2024-01-01' AND timestamp < '2024-01-02' "
            "AND message LIKE 'error%'"
        )
        assert "BROAD_LIKE" not in codes(a)


class TestParseError:
    def test_garbage_returns_parse_error(self):
        a = analyze_sql("THIS IS NOT VALID SQL %%%")
        assert "PARSE_ERROR" in codes(a)
        assert not a.ok
        assert a.parsed_tables == []


class TestParsedTables:
    def test_qualified_table_extracted(self):
        a = analyze_sql(
            "SELECT app FROM hydro.logs "
            "WHERE timestamp >= '2024-01-01' AND timestamp < '2024-01-02'"
        )
        assert "hydro.logs" in a.parsed_tables

    def test_unqualified_table_extracted(self):
        a = analyze_sql(
            "SELECT app FROM logs WHERE timestamp >= '2024-01-01' AND timestamp < '2024-01-02'"
        )
        assert "logs" in a.parsed_tables


class TestCustomTimestampColumn:
    def test_non_default_pk_with_override(self):
        # cdn.low_card_day_basic uses `day_ts` as its PK timestamp.
        sql = (
            "SELECT cnt_all FROM cdn.low_card_day_basic "
            "WHERE day_ts >= toDateTime(1777659986) AND day_ts < toDateTime(1778264786)"
        )
        a = analyze_sql(sql, timestamp_column="day_ts")
        assert "NO_TIME_RANGE" not in codes(a)
        assert "UNBOUNDED_TIME_RANGE" not in codes(a)

    def test_non_default_pk_default_arg_misses_time_range(self):
        # Documents the v1 limitation: without the override we false-positive.
        sql = (
            "SELECT cnt_all FROM cdn.low_card_day_basic "
            "WHERE day_ts >= toDateTime(1777659986) AND day_ts < toDateTime(1778264786)"
        )
        a = analyze_sql(sql)
        assert "NO_TIME_RANGE" in codes(a)


class TestNoLimitAdvice:
    """Regression tests: the analyzer must NEVER recommend adding LIMIT.

    LIMIT does not reduce cluster work in Hydrolix — the query head and peers
    still scan every matching partition before LIMIT applies. See the module
    docstring of query_analysis.py for the full rationale.
    """

    QUERIES = [
        "SELECT * FROM logs",
        "SELECT count(*) FROM logs WHERE app = 'foo'",
        "SELECT * FROM logs WHERE timestamp > now() - INTERVAL 1 HOUR",
        "SELECT message FROM logs WHERE message LIKE '%error%'",
        "SELECT count(*) FROM logs WHERE toDate(timestamp) = '2024-01-01'",
    ]

    def test_no_finding_mentions_limit(self):
        for sql in self.QUERIES:
            a = analyze_sql(sql)
            for f in a.findings:
                assert "LIMIT" not in (f.suggested_rewrite or "").upper(), (
                    f"Finding {f.code} for query {sql!r} suggested LIMIT: {f.suggested_rewrite!r}"
                )
                assert "LIMIT" not in f.message.upper(), (
                    f"Finding {f.code} for query {sql!r} mentioned LIMIT in message: {f.message!r}"
                )

    def test_no_no_limit_finding_code_exists(self):
        # If a future contributor reintroduces a LIMIT-related rule, this fails.
        for sql in self.QUERIES:
            a = analyze_sql(sql)
            for f in a.findings:
                assert "LIMIT" not in f.code.upper(), (
                    f"Finding code {f.code!r} references LIMIT — see "
                    f"feedback_hydrolix_no_limit_advice in user memory."
                )
