import json
import ipaddress
import pytest
from datetime import datetime, time
from decimal import Decimal

from mcp.types import TextContent

from mcp_hydrolix.utils import ExtendedEncoder, with_serializer
from fastmcp.tools.tool import ToolResult


class TestExtendedEncoder:
    """Test suite for ExtendedEncoder class."""

    def test_ipv4_address_serialization(self):
        """Test that IPv4 addresses are serialized to strings."""
        ip = ipaddress.IPv4Address("192.168.1.1")
        result = json.dumps({"ip": ip}, cls=ExtendedEncoder)
        assert result == '{"ip": "192.168.1.1"}'

    def test_datetime_serialization(self):
        """Test that datetime objects are converted to time objects."""
        dt = datetime(2024, 1, 15, 14, 30, 45, 123456)
        result = json.dumps({"timestamp": dt}, cls=ExtendedEncoder)
        expected_time = dt.timestamp()
        assert result == f'{{"timestamp": {expected_time}}}'

    def test_time_serialization(self):
        """Test that time objects are converted to seconds."""
        t = time(14, 30, 45, 123456)
        result = json.dumps({"time": t}, cls=ExtendedEncoder)
        expected_time = "14:30:45.123456"
        assert result == f'{{"time": "{expected_time}"}}'

    def test_time_serialization_midnight(self):
        """Test time serialization at midnight (edge case)."""
        t = time(0, 0, 0, 0)
        result = json.dumps({"time": t}, cls=ExtendedEncoder)
        assert result == '{"time": "00:00:00"}'

    def test_time_serialization_end_of_day(self):
        """Test time serialization at end of day (edge case)."""
        t = time(23, 59, 59, 999999)
        result = json.dumps({"time": t}, cls=ExtendedEncoder)
        assert result == '{"time": "23:59:59.999999"}'

    def test_bytes_serialization(self):
        """Test that bytes are decoded to strings."""
        data = b"hello world"
        result = json.dumps({"data": data}, cls=ExtendedEncoder)
        assert result == '{"data": "hello world"}'

    def test_bytes_serialization_utf8(self):
        """Test bytes serialization with UTF-8 characters."""
        data = "hello 世界".encode("utf-8")
        result = json.dumps({"data": data}, cls=ExtendedEncoder)
        assert result == '{"data": "hello 世界"}'.encode("unicode-escape").decode("utf-8")

    def test_decimal_serialization(self):
        """Test that Decimal objects are converted to strings."""
        dec = Decimal("123.456")
        result = json.dumps({"amount": dec}, cls=ExtendedEncoder)
        assert result == '{"amount": "123.456"}'

    def test_decimal_serialization_precision(self):
        """Test Decimal serialization preserves precision."""
        dec = Decimal("0.123456789012345678901234567890")
        result = json.dumps({"value": dec}, cls=ExtendedEncoder)
        assert result == '{"value": "0.123456789012345678901234567890"}'

    def test_combined_types_serialization(self):
        """Test serialization of multiple custom types together."""
        data = {
            "ip": ipaddress.IPv4Address("10.0.0.1"),
            "time": time(12, 0, 0),
            "data": b"test",
            "amount": Decimal("99.99"),
        }
        result = json.dumps(data, cls=ExtendedEncoder)
        parsed = json.loads(result)

        assert parsed["ip"] == "10.0.0.1"
        assert parsed["time"] == "12:00:00"
        assert parsed["data"] == "test"
        assert parsed["amount"] == "99.99"

    def test_nested_serialization(self):
        """Test serialization of nested structures."""
        data = {
            "users": [
                {"ip": ipaddress.IPv4Address("192.168.1.100"), "balance": Decimal("1000.50")},
                {"ip": ipaddress.IPv4Address("192.168.1.101"), "balance": Decimal("2000.75")},
            ]
        }
        result = json.dumps(data, cls=ExtendedEncoder)
        parsed = json.loads(result)

        assert parsed["users"][0]["ip"] == "192.168.1.100"
        assert parsed["users"][0]["balance"] == "1000.50"
        assert parsed["users"][1]["ip"] == "192.168.1.101"
        assert parsed["users"][1]["balance"] == "2000.75"

    def test_standard_types_unchanged(self):
        """Test that standard JSON types are serialized normally."""
        data = {
            "string": "test",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "list": [1, 2, 3],
            "dict": {"key": "value"},
        }
        result = json.dumps(data, cls=ExtendedEncoder)
        parsed = json.loads(result)
        assert parsed == data


class TestWithSerializerDecorator:
    """Test suite for with_serializer decorator."""

    def test_sync_function_basic(self):
        """Test decorator works with synchronous functions."""

        @with_serializer
        def mock_tool():
            return {"result": "success"}

        result = mock_tool()

        assert isinstance(result, ToolResult)
        assert result.content == [TextContent(type="text", text='{"result": "success"}')]
        assert result.structured_content == {"result": "success"}

    def test_sync_function_with_args(self):
        """Test decorator works with function arguments."""

        @with_serializer
        def mock_tool(arg1, arg2):
            return {"arg1": arg1, "arg2": arg2}

        result = mock_tool("value1", "value2")

        assert isinstance(result, ToolResult)
        assert result.structured_content == {"arg1": "value1", "arg2": "value2"}

    def test_sync_function_with_kwargs(self):
        """Test decorator works with keyword arguments."""

        @with_serializer
        def mock_tool(name, age=0):
            return {"name": name, "age": age}

        result = mock_tool(name="Alice", age=30)

        assert isinstance(result, ToolResult)
        assert result.structured_content == {"name": "Alice", "age": 30}

    @pytest.mark.asyncio
    async def test_async_function_basic(self):
        """Test decorator works with async functions."""

        @with_serializer
        async def mock_async_tool():
            return {"result": "async success"}

        result = await mock_async_tool()

        assert isinstance(result, ToolResult)
        assert result.content == [TextContent(type="text", text='{"result": "async success"}')]
        assert result.structured_content == {"result": "async success"}

    @pytest.mark.asyncio
    async def test_async_function_with_args(self):
        """Test decorator works with async function arguments."""

        @with_serializer
        async def mock_async_tool(x, y):
            return {"sum": x + y}

        result = await mock_async_tool(5, 10)

        assert isinstance(result, ToolResult)
        assert result.structured_content == {"sum": 15}

    def test_custom_types_serialization(self):
        """Test decorator properly serializes custom types."""

        @with_serializer
        def mock_tool():
            return {
                "ip": ipaddress.IPv4Address("172.16.0.1"),
                "amount": Decimal("500.00"),
                "data": b"encoded",
            }

        result = mock_tool()

        assert isinstance(result, ToolResult)
        parsed = result.structured_content
        assert parsed["ip"] == "172.16.0.1"
        assert parsed["amount"] == "500.00"
        assert parsed["data"] == "encoded"

    @pytest.mark.asyncio
    async def test_async_custom_types_serialization(self):
        """Test decorator serializes custom types in async functions."""

        @with_serializer
        async def mock_async_tool():
            return {"time": time(10, 30, 0), "decimal": Decimal("123.45")}

        result = await mock_async_tool()

        assert isinstance(result, ToolResult)
        parsed = result.structured_content
        assert parsed["time"] == "10:30:00"
        assert parsed["decimal"] == "123.45"

    def test_content_structured_content_match(self):
        """Test that content and structured_content are consistent."""

        @with_serializer
        def mock_tool():
            return {"key": "value", "number": 42}

        result: ToolResult = mock_tool()

        # Parse the content string and verify it matches structured_content
        parsed_content = json.loads(result.content[0].text)
        assert parsed_content == result.structured_content

    def test_complex_nested_structure(self):
        """Test decorator handles complex nested structures."""

        @with_serializer
        def mock_tool():
            return {
                "users": [
                    {
                        "id": 1,
                        "ip": ipaddress.IPv4Address("192.168.1.1"),
                        "balance": Decimal("1000.50"),
                    },
                    {
                        "id": 2,
                        "ip": ipaddress.IPv4Address("192.168.1.2"),
                        "balance": Decimal("2000.75"),
                    },
                ],
                "metadata": {"timestamp": time(14, 30, 0), "data": b"metadata"},
            }

        result = mock_tool()

        assert isinstance(result, ToolResult)
        parsed = result.structured_content
        assert len(parsed["users"]) == 2
        assert parsed["users"][0]["ip"] == "192.168.1.1"
        assert parsed["users"][0]["balance"] == "1000.50"
        assert parsed["metadata"]["data"] == "metadata"

    def test_empty_result(self):
        """Test decorator handles empty results."""

        @with_serializer
        def mock_tool():
            return {}

        result = mock_tool()

        assert isinstance(result, ToolResult)
        assert result.content == [TextContent(type="text", text="{}")]
        assert result.structured_content == {}

    def test_list_result(self):
        """Test decorator handles list results."""

        @with_serializer
        def mock_tool():
            return [1, 2, 3, 4, 5]

        result = mock_tool()

        assert isinstance(result, ToolResult)
        assert result.content == [TextContent(type="text", text='{"result": [1, 2, 3, 4, 5]}')]
        assert result.structured_content == {"result": [1, 2, 3, 4, 5]}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
