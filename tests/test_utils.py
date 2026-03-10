import json
import ipaddress
import pytest
from datetime import datetime, time
from decimal import Decimal

from mcp_hydrolix.utils import _normalize_value, with_serializer
from fastmcp.tools.tool import ToolResult


class TestNormalizeValue:
    """Test suite for _normalize_value."""

    def test_ipv4_address(self):
        assert _normalize_value(ipaddress.IPv4Address("192.168.1.1")) == "192.168.1.1"

    def test_ipv6_address(self):
        assert _normalize_value(ipaddress.IPv6Address("2001:db8::1")) == "2001:db8::1"

    def test_datetime(self):
        dt = datetime(2024, 1, 15, 14, 30, 45, 123456)
        assert _normalize_value(dt) == dt.timestamp()

    def test_time(self):
        assert _normalize_value(time(14, 30, 45, 123456)) == "14:30:45.123456"

    def test_time_midnight(self):
        assert _normalize_value(time(0, 0, 0)) == "00:00:00"

    def test_bytes_utf8(self):
        assert _normalize_value(b"hello world") == "hello world"

    def test_bytes_non_utf8(self):
        result = _normalize_value(b"\xff\xfe")
        assert isinstance(result, str)  # did not raise

    def test_decimal(self):
        assert _normalize_value(Decimal("123.456")) == "123.456"

    def test_decimal_preserves_precision(self):
        dec = Decimal("0.123456789012345678901234567890")
        assert _normalize_value(dec) == str(dec)

    def test_passthrough_string(self):
        assert _normalize_value("hello") == "hello"

    def test_passthrough_int(self):
        assert _normalize_value(42) == 42

    def test_passthrough_float(self):
        assert _normalize_value(3.14) == 3.14

    def test_passthrough_none(self):
        assert _normalize_value(None) is None

    def test_passthrough_bool(self):
        assert _normalize_value(True) is True


class TestWithSerializerDecorator:
    """Test suite for with_serializer decorator."""

    def test_sync_function_basic(self):
        """Test decorator works with synchronous functions."""

        @with_serializer
        def mock_tool():
            return {"columns": ["status"], "rows": [["ok"]]}

        result = mock_tool()

        assert isinstance(result, ToolResult)
        assert result.structured_content == {"columns": ["status"], "rows": [["ok"]]}

    def test_sync_function_with_args(self):
        """Test decorator passes arguments through correctly."""

        @with_serializer
        def mock_tool(col, val):
            return {"columns": [col], "rows": [[val]]}

        result = mock_tool("name", "Alice")

        assert isinstance(result, ToolResult)
        assert result.structured_content == {"columns": ["name"], "rows": [["Alice"]]}

    def test_sync_function_with_kwargs(self):
        """Test decorator passes keyword arguments through correctly."""

        @with_serializer
        def mock_tool(col, val=None):
            return {"columns": [col], "rows": [[val]]}

        result = mock_tool(col="score", val=42)

        assert isinstance(result, ToolResult)
        assert result.structured_content == {"columns": ["score"], "rows": [[42]]}

    @pytest.mark.asyncio
    async def test_async_function_basic(self):
        """Test decorator works with async functions."""

        @with_serializer
        async def mock_async_tool():
            return {"columns": ["status"], "rows": [["ok"]]}

        result = await mock_async_tool()

        assert isinstance(result, ToolResult)
        assert result.structured_content == {"columns": ["status"], "rows": [["ok"]]}

    @pytest.mark.asyncio
    async def test_async_function_with_args(self):
        """Test decorator passes arguments through correctly for async functions."""

        @with_serializer
        async def mock_async_tool(x, y):
            return {"columns": ["sum"], "rows": [[x + y]]}

        result = await mock_async_tool(5, 10)

        assert isinstance(result, ToolResult)
        assert result.structured_content == {"columns": ["sum"], "rows": [[15]]}

    def test_custom_types_serialization(self):
        """Test decorator normalizes CH-specific types in rows."""

        @with_serializer
        def mock_tool():
            return {
                "columns": ["ip", "amount", "data"],
                "rows": [[ipaddress.IPv4Address("172.16.0.1"), Decimal("500.00"), b"encoded"]],
            }

        result = mock_tool()

        assert isinstance(result, ToolResult)
        row = result.structured_content["rows"][0]
        assert row[0] == "172.16.0.1"
        assert row[1] == "500.00"
        assert row[2] == "encoded"

    @pytest.mark.asyncio
    async def test_async_custom_types_serialization(self):
        """Test decorator normalizes CH-specific types in async functions."""

        @with_serializer
        async def mock_async_tool():
            return {"columns": ["t", "decimal"], "rows": [[time(10, 30, 0), Decimal("123.45")]]}

        result = await mock_async_tool()

        assert isinstance(result, ToolResult)
        row = result.structured_content["rows"][0]
        assert row[0] == "10:30:00"
        assert row[1] == "123.45"


class TestSerializeQueryResult:
    """Test suite for _serialize_query_result."""

    def test_query_result_produces_toon(self):
        """HdxQueryResult shape produces TOON, not JSON."""
        from mcp_hydrolix.utils import _serialize_query_result

        result = {"columns": ["id", "name"], "rows": [[1, "Alice"], [2, "Bob"]]}
        toon_str, structured = _serialize_query_result(result)

        # Content should be TOON (not valid JSON)
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(toon_str)

        # TOON header declares 2 rows and the column names
        assert "[2]" in toon_str
        assert "id" in toon_str
        assert "name" in toon_str
        assert "Alice" in toon_str

    def test_query_result_structured_content_preserves_columnar_format(self):
        """structured_content keeps the original columns+rows shape."""
        from mcp_hydrolix.utils import _serialize_query_result

        result = {"columns": ["id", "name"], "rows": [[1, "Alice"], [2, "Bob"]]}
        _, structured = _serialize_query_result(result)

        assert structured["columns"] == ["id", "name"]
        assert structured["rows"] == [[1, "Alice"], [2, "Bob"]]

    def test_query_result_empty_rows(self):
        """Empty rows produce valid TOON for an empty list."""
        from mcp_hydrolix.utils import _serialize_query_result

        result = {"columns": ["id", "name"], "rows": []}
        toon_str, structured = _serialize_query_result(result)

        assert "[0]" in toon_str
        assert structured["rows"] == []

    def test_query_result_single_row(self):
        """Single-row result encodes correctly."""
        from mcp_hydrolix.utils import _serialize_query_result

        result = {"columns": ["x"], "rows": [[42]]}
        toon_str, structured = _serialize_query_result(result)

        assert "[1]" in toon_str
        assert "42" in toon_str

    def test_query_result_null_value(self):
        """None values in rows are encoded as null in TOON."""
        from mcp_hydrolix.utils import _serialize_query_result

        result = {"columns": ["a", "b"], "rows": [[None, 1]]}
        toon_str, _ = _serialize_query_result(result)

        assert "null" in toon_str

    def test_query_result_normalizes_datetime(self):
        """datetime in rows is converted to a Unix timestamp before TOON encoding."""
        from mcp_hydrolix.utils import _serialize_query_result

        dt = datetime(2024, 1, 15, 12, 0, 0)
        result = {"columns": ["ts"], "rows": [[dt]]}
        toon_str, structured = _serialize_query_result(result)

        assert str(dt.timestamp()) in toon_str
        assert structured["rows"][0][0] == dt.timestamp()

    def test_query_result_normalizes_decimal(self):
        """Decimal in rows is converted to string before TOON encoding."""
        from mcp_hydrolix.utils import _serialize_query_result

        result = {"columns": ["amount"], "rows": [[Decimal("99.99")]]}
        toon_str, structured = _serialize_query_result(result)

        assert "99.99" in toon_str
        assert structured["rows"][0][0] == "99.99"

    def test_query_result_normalizes_ipv4(self):
        """IPv4Address in rows is converted to string before TOON encoding."""
        from mcp_hydrolix.utils import _serialize_query_result

        result = {"columns": ["ip"], "rows": [[ipaddress.IPv4Address("1.2.3.4")]]}
        toon_str, structured = _serialize_query_result(result)

        assert "1.2.3.4" in toon_str
        assert structured["rows"][0][0] == "1.2.3.4"

    def test_query_result_normalizes_bytes(self):
        """bytes in rows are decoded to a UTF-8 string before TOON encoding."""
        from mcp_hydrolix.utils import _serialize_query_result

        result = {"columns": ["data"], "rows": [[b"hello"]]}
        toon_str, structured = _serialize_query_result(result)

        assert "hello" in toon_str
        assert structured["rows"][0][0] == "hello"

    def test_query_result_normalizes_ipv6(self):
        """IPv6Address in rows is converted to string before TOON encoding."""
        from mcp_hydrolix.utils import _serialize_query_result

        result = {"columns": ["ip"], "rows": [[ipaddress.IPv6Address("2001:db8::1")]]}
        toon_str, structured = _serialize_query_result(result)

        assert "2001:db8::1" in toon_str
        assert structured["rows"][0][0] == "2001:db8::1"

    def test_query_result_toon_failure_falls_back_to_json(self):
        """If toon_encode raises, the result falls back to JSON without crashing."""
        from unittest.mock import patch
        from mcp_hydrolix.utils import _serialize_query_result

        result = {"columns": ["a"], "rows": [[1], [2]]}
        with patch("mcp_hydrolix.utils.toon_encode", side_effect=RuntimeError("boom")):
            encoded, structured = _serialize_query_result(result)

        # Should be valid JSON, not TOON
        parsed = json.loads(encoded)
        assert parsed == [{"a": 1}, {"a": 2}]
        assert structured["rows"] == [[1], [2]]

    def test_with_serializer_query_result_content_is_toon(self):
        """with_serializer produces TOON content for HdxQueryResult-shaped returns."""

        @with_serializer
        def mock_query_tool():
            return {"columns": ["id", "val"], "rows": [[1, "foo"], [2, "bar"]]}

        result = mock_query_tool()

        assert isinstance(result, ToolResult)
        toon_text = result.content[0].text
        # TOON, not JSON
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(toon_text)
        assert "[2]" in toon_text
        assert "id" in toon_text
        assert "foo" in toon_text

    @pytest.mark.asyncio
    async def test_with_serializer_async_query_result_content_is_toon(self):
        """with_serializer async variant also produces TOON for query results."""

        @with_serializer
        async def mock_async_query_tool():
            return {"columns": ["a"], "rows": [[10], [20]]}

        result = await mock_async_query_tool()

        toon_text = result.content[0].text
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(toon_text)
        assert "[2]" in toon_text
        assert "10" in toon_text

    def test_with_serializer_query_result_structured_content(self):
        """structured_content for a query result keeps the columnar dict."""

        @with_serializer
        def mock_query_tool():
            return {"columns": ["x", "y"], "rows": [[1, 2], [3, 4]]}

        result = mock_query_tool()

        assert result.structured_content == {
            "columns": ["x", "y"],
            "rows": [[1, 2], [3, 4]],
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
