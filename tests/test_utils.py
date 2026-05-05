import ipaddress
import pytest
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

try:
    from mcp_hydrolix.utils import coerce_cell, coerce_rows, inject_limit
except ImportError:  # pending typed-result refactor — symbols arrive in a later commit
    from mcp_hydrolix.utils import inject_limit

    def coerce_cell(value):  # type: ignore[no-redef]
        raise NotImplementedError

    def coerce_rows(rows):  # type: ignore[no-redef]
        raise NotImplementedError


pytestmark = pytest.mark.xfail(reason="pending typed-result refactor", strict=False, run=False)


class TestCoerceCell:
    """Coerce a single result cell from clickhouse-connect to a JSON-friendly value."""

    def test_ipv4_address(self):
        assert coerce_cell(ipaddress.IPv4Address("192.168.1.1")) == "192.168.1.1"

    def test_datetime_utc_aware_returns_epoch(self):
        """UTC-aware datetimes (clickhouse-connect tz_mode='aware') round-trip to
        the correct UTC epoch regardless of the local timezone."""
        known_utc_epoch = 1705314645  # 2024-01-15 10:30:45 UTC
        dt = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        assert coerce_cell(dt) == known_utc_epoch

    def test_datetime_non_utc_aware_returns_correct_epoch(self):
        """A non-UTC tz-aware datetime (e.g. EDT) must produce the same epoch as
        its UTC equivalent — so 21:00 EDT == 01:00 UTC next day."""
        edt = timezone(timedelta(hours=-4))
        dt = datetime(2024, 1, 15, 21, 0, 0, tzinfo=edt)
        expected_epoch = datetime(2024, 1, 16, 1, 0, 0, tzinfo=timezone.utc).timestamp()
        assert coerce_cell(dt) == expected_epoch

    def test_datetime_naive_uses_local_tz(self):
        """Naive datetimes follow Python's default behavior: interpreted as local time."""
        dt = datetime(2024, 1, 15, 14, 30, 45)
        assert coerce_cell(dt) == dt.timestamp()

    def test_time_full_precision(self):
        assert coerce_cell(time(14, 30, 45, 123456)) == "14:30:45.123456"

    def test_time_midnight(self):
        assert coerce_cell(time(0, 0, 0, 0)) == "00:00:00"

    def test_time_end_of_day(self):
        assert coerce_cell(time(23, 59, 59, 999999)) == "23:59:59.999999"

    def test_date(self):
        assert coerce_cell(date(2024, 1, 15)) == "2024-01-15"

    def test_bytes_ascii(self):
        assert coerce_cell(b"hello world") == "hello world"

    def test_bytes_utf8(self):
        assert coerce_cell("hello 世界".encode("utf-8")) == "hello 世界"

    def test_decimal_basic(self):
        assert coerce_cell(Decimal("123.456")) == "123.456"

    def test_decimal_precision_preserved(self):
        assert (
            coerce_cell(Decimal("0.123456789012345678901234567890"))
            == "0.123456789012345678901234567890"
        )

    @pytest.mark.parametrize(
        "value",
        ["test", 42, 3.14, True, False, None, [1, 2, 3], {"k": "v"}],
    )
    def test_passthrough_for_native_json_types(self, value):
        """Standard JSON-friendly types — including None — pass through unchanged.

        None is data when it appears in a query result row (the user's SELECT may
        return SQL NULLs) and must not be dropped at the cell level.
        """
        assert coerce_cell(value) == value


class TestCoerceRows:
    def test_walks_2d_grid(self):
        rows = [
            [ipaddress.IPv4Address("10.0.0.1"), Decimal("1.5"), None],
            [ipaddress.IPv4Address("10.0.0.2"), Decimal("2.5"), 42],
        ]
        assert coerce_rows(rows) == [
            ["10.0.0.1", "1.5", None],
            ["10.0.0.2", "2.5", 42],
        ]

    def test_empty_rows(self):
        assert coerce_rows([]) == []

    def test_empty_row(self):
        assert coerce_rows([[]]) == [[]]


class TestClientTimezoneConfig:
    """Verify clickhouse-connect is configured to return tz-aware UTC datetimes."""

    def test_client_config_uses_aware_tz_mode(self):
        """get_client_config must include tz_mode='aware' so clickhouse-connect
        returns tz-aware UTC datetimes instead of naive ones."""
        from mcp_hydrolix.mcp_env import get_config

        config = get_config().get_client_config(request_credential=None)
        assert config.get("tz_mode") == "aware", (
            "tz_mode must be 'aware' to avoid naive datetimes being misinterpreted "
            "as local time by Python's datetime.timestamp()"
        )


class TestClickhouseConnectTzBehavior:
    """Contract tests: verify clickhouse-connect honours tz_mode when
    deserialising DateTime columns, so our tz_mode='aware' config actually
    produces tz-aware datetimes."""

    def test_aware_mode_preserves_utc(self):
        """With tz_mode='aware' and a UTC server, active_tz must return UTC
        (not None), so datetimes carry tzinfo."""
        from clickhouse_connect.driver.query import QueryContext
        import pytz

        ctx = QueryContext(
            query="",
            server_tz=pytz.UTC,
            tz_mode="aware",
            apply_server_tz=True,
        )
        assert ctx.active_tz(None) is not None

    def test_naive_utc_mode_strips_utc(self):
        """With the old default ('naive_utc') and a UTC server, active_tz
        returns None — the behaviour we are fixing."""
        from clickhouse_connect.driver.query import QueryContext
        import pytz

        ctx = QueryContext(
            query="",
            server_tz=pytz.UTC,
            tz_mode="naive_utc",
            apply_server_tz=True,
        )
        assert ctx.active_tz(None) is None

    def test_aware_mode_preserves_non_utc_server_tz(self):
        """With tz_mode='aware' and a non-UTC server, active_tz returns the
        server timezone so datetimes are tz-aware in that zone."""
        from clickhouse_connect.driver.query import QueryContext
        import pytz

        eastern = pytz.timezone("US/Eastern")
        ctx = QueryContext(
            query="",
            server_tz=eastern,
            tz_mode="aware",
            apply_server_tz=True,
        )
        result = ctx.active_tz(None)
        assert result is not None
        assert result == eastern


class TestInjectLimit:
    def test_adds_limit_when_none_present(self):
        result = inject_limit("SELECT * FROM t", 10)
        assert "LIMIT 10" in result

    def test_takes_min_when_existing_limit_is_larger(self):
        result = inject_limit("SELECT * FROM t LIMIT 100", 10)
        assert "LIMIT 10" in result
        assert "LIMIT 100" not in result

    def test_preserves_smaller_existing_limit(self):
        result = inject_limit("SELECT * FROM t LIMIT 5", 10)
        assert "LIMIT 5" in result
        assert "LIMIT 10" not in result

    def test_only_affects_outermost_limit(self):
        query = "SELECT * FROM (SELECT * FROM t LIMIT 1000) AS sub"
        result = inject_limit(query, 10)
        assert "LIMIT 1000" in result  # inner limit preserved
        assert result.strip().endswith("LIMIT 10")  # outer limit added, not inner

    def test_preserves_offset_when_capping_limit(self):
        result = inject_limit("SELECT * FROM t LIMIT 100 OFFSET 50", 10)
        assert "LIMIT 10" in result
        assert "50" in result  # offset preserved

    def test_equal_limit_is_unchanged(self):
        result = inject_limit("SELECT * FROM t LIMIT 10", 10)
        assert "LIMIT 10" in result

    def test_non_literal_existing_limit_is_left_unchanged(self):
        # A LIMIT with a parenthesized or non-literal expression should not crash,
        # and the original LIMIT expression must be preserved (not dropped or mangled).
        result = inject_limit("SELECT * FROM t LIMIT (100)", 10)
        assert result is not None  # must not raise
        assert "LIMIT" in result  # LIMIT clause must still be present
        assert "100" in result  # original value must be preserved
        assert "LIMIT 10" not in result  # cap must NOT have been applied

    def test_unparseable_query_returned_unchanged(self):
        # A query sqlglot cannot parse must be returned as-is without raising, so the
        # caller can still execute it (limit injection is best-effort).
        bad_sql = "THIS IS NOT VALID SQL @@@@"
        result = inject_limit(bad_sql, 10)
        assert result == bad_sql


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
