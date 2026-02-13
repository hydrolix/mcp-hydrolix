"""Unit tests for pagination utilities."""

import base64

import pytest

from mcp_hydrolix.pagination import (
    CursorData,
    decode_cursor,
    encode_cursor,
    hash_query,
    validate_cursor_params,
)


class TestCursorEncoding:
    """Tests for cursor encoding and decoding."""

    @pytest.mark.parametrize(
        "cursor_data",
        [
            # Typical cursor with params
            {
                "type": "table_list",
                "offset": 50,
                "params": {"database": "test", "like": "%.log"},
            },
            # All fields included
            {
                "type": "query_result",
                "offset": 100,
                "params": {"database": "mydb", "like": None, "not_like": "tmp%"},
                "query_hash": "abc123def456",
            },
            # Minimal cursor
            {"type": "table_list", "offset": 0},
        ],
        ids=["typical", "all_fields", "minimal"],
    )
    def test_cursor_encoding_roundtrip(self, cursor_data: CursorData):
        """Test cursor can be encoded and decoded."""
        cursor = encode_cursor(cursor_data)
        decoded = decode_cursor(cursor)
        assert decoded == cursor_data

    def test_encoded_cursor_is_url_safe(self):
        """Test that encoded cursor uses URL-safe base64."""
        data: CursorData = {"type": "table_list", "offset": 50}
        cursor = encode_cursor(data)
        # URL-safe base64 should not contain + or /
        assert "+" not in cursor.rstrip("=")
        assert "/" not in cursor.rstrip("=")

    @pytest.mark.parametrize(
        "invalid_cursor,description",
        [
            ("invalid!!!cursor", "invalid characters"),
            ("not-valid-base64!@#$", "malformed base64"),
            (base64.urlsafe_b64encode(b"not json data").decode(), "invalid json"),
            ("", "empty string"),
        ],
        ids=["invalid_chars", "malformed_base64", "invalid_json", "empty"],
    )
    def test_invalid_cursor_raises_error(self, invalid_cursor: str, description: str):
        """Test various invalid cursors raise ValueError."""
        with pytest.raises(ValueError):
            decode_cursor(invalid_cursor)


class TestQueryHashing:
    """Tests for query hashing."""

    def test_query_hash_consistency(self):
        """Test query hash is consistent."""
        query = "SELECT * FROM table"
        hash1 = hash_query(query)
        hash2 = hash_query(query)
        assert hash1 == hash2

    def test_query_hash_is_sha256(self):
        """Test query hash produces SHA256 hex string."""
        query = "SELECT * FROM table"
        result = hash_query(query)
        # SHA256 hex string is 64 characters
        assert len(result) == 64
        # Should be valid hex
        assert all(c in "0123456789abcdef" for c in result)

    @pytest.mark.parametrize(
        "query1,query2",
        [
            ("SELECT * FROM table", "  SELECT * FROM table"),
            ("SELECT * FROM table", "SELECT * FROM table  "),
            ("SELECT * FROM table", "  SELECT * FROM table  \n"),
            ("SELECT *\nFROM table\nWHERE id = 1", "  SELECT *\nFROM table\nWHERE id = 1  "),
        ],
        ids=["leading_ws", "trailing_ws", "both_ws", "multiline"],
    )
    def test_query_hash_ignores_whitespace(self, query1: str, query2: str):
        """Test query hash ignores leading/trailing whitespace."""
        assert hash_query(query1) == hash_query(query2)

    @pytest.mark.parametrize(
        "query1,query2",
        [
            ("SELECT * FROM table1", "SELECT * FROM table2"),
            ("SELECT * FROM table", "SELECT  *  FROM  table"),
        ],
        ids=["different_content", "internal_whitespace"],
    )
    def test_query_hash_sensitive_to_differences(self, query1: str, query2: str):
        """Test query hash changes with content or internal whitespace."""
        assert hash_query(query1) != hash_query(query2)


class TestCursorParameterValidation:
    """Tests for cursor parameter validation."""

    @pytest.mark.parametrize(
        "cursor_params,expected_params",
        [
            # Exact match
            (
                {"database": "test", "like": "%.log", "not_like": None},
                {"database": "test", "like": "%.log", "not_like": None},
            ),
            # Empty params
            ({}, {}),
            # Subset validation (only validates expected keys)
            (
                {"database": "test", "like": "%.log", "extra": "value"},
                {"database": "test"},
            ),
            # None values
            (
                {"database": "test", "like": None, "not_like": None},
                {"database": "test", "like": None, "not_like": None},
            ),
        ],
        ids=["exact_match", "empty", "subset", "with_none"],
    )
    def test_validate_cursor_params_success(self, cursor_params: dict, expected_params: dict):
        """Test validation passes with matching params."""
        cursor_data: CursorData = {"params": cursor_params}
        validate_cursor_params(cursor_data, expected_params)  # Should not raise

    @pytest.mark.parametrize(
        "cursor_params,expected_params,description",
        [
            # Different value
            ({"database": "test1"}, {"database": "test2"}, "different value"),
            # Missing param
            ({"like": "%.log"}, {"database": "test"}, "missing param"),
            # None vs value
            ({"like": None}, {"like": "%.log"}, "none vs value"),
            # Value vs None
            ({"like": "%.log"}, {"like": None}, "value vs none"),
            # Multiple mismatches
            (
                {"database": "test1", "like": "%.txt"},
                {"database": "test2", "like": "%.log"},
                "multiple mismatches",
            ),
        ],
        ids=["different_value", "missing_param", "none_vs_value", "value_vs_none", "multiple"],
    )
    def test_validate_cursor_params_failure(
        self, cursor_params: dict, expected_params: dict, description: str
    ):
        """Test validation fails with mismatched params."""
        cursor_data: CursorData = {"params": cursor_params}
        with pytest.raises(ValueError, match="Cursor parameter mismatch"):
            validate_cursor_params(cursor_data, expected_params)

    def test_validate_cursor_params_no_params_field(self):
        """Test validation when cursor has no params field."""
        cursor_data: CursorData = {"type": "table_list", "offset": 50}
        expected = {"database": "test"}
        with pytest.raises(ValueError, match="Cursor parameter mismatch"):
            validate_cursor_params(cursor_data, expected)


class TestCursorDataIntegration:
    """Integration tests combining multiple cursor operations."""

    def test_full_cursor_workflow(self):
        """Test complete cursor workflow: create, encode, decode, validate."""
        # Create cursor
        original_data: CursorData = {
            "type": "table_list",
            "offset": 50,
            "params": {"database": "prod", "like": "events_%", "not_like": None},
        }

        # Encode
        cursor_string = encode_cursor(original_data)

        # Decode
        decoded_data = decode_cursor(cursor_string)

        # Validate structure
        assert decoded_data["type"] == "table_list"
        assert decoded_data["offset"] == 50

        # Validate params
        expected_params = {"database": "prod", "like": "events_%", "not_like": None}
        validate_cursor_params(decoded_data, expected_params)

    def test_query_result_cursor_workflow(self):
        """Test cursor workflow for query results with hash."""
        query = "SELECT * FROM large_table ORDER BY timestamp"
        query_hash_value = hash_query(query)

        original_data: CursorData = {
            "type": "query_result",
            "offset": 10000,
            "params": {},
            "query_hash": query_hash_value,
        }

        # Encode and decode
        cursor_string = encode_cursor(original_data)
        decoded_data = decode_cursor(cursor_string)

        # Verify hash matches
        assert decoded_data["query_hash"] == query_hash_value
        assert decoded_data["query_hash"] == hash_query(query)

        # Verify hash changes if query changes
        different_query = "SELECT * FROM large_table ORDER BY id"
        assert decoded_data["query_hash"] != hash_query(different_query)

    def test_cursor_prevents_parameter_change_attack(self):
        """Test cursor validation prevents parameter tampering."""
        # Create cursor for database "test"
        cursor_data: CursorData = {
            "type": "table_list",
            "offset": 50,
            "params": {"database": "test"},
        }
        cursor = encode_cursor(cursor_data)

        # Attacker tries to use cursor with different database
        decoded = decode_cursor(cursor)
        with pytest.raises(ValueError, match="Cursor parameter mismatch"):
            validate_cursor_params(decoded, {"database": "prod"})

    def test_cursor_prevents_query_change_attack(self):
        """Test cursor validation prevents query tampering."""
        # Create cursor for specific query
        original_query = "SELECT * FROM users"
        cursor_data: CursorData = {
            "type": "query_result",
            "offset": 100,
            "query_hash": hash_query(original_query),
        }
        cursor = encode_cursor(cursor_data)

        # Attacker tries to use cursor with different query
        decoded = decode_cursor(cursor)
        different_query = "SELECT * FROM admin_users"

        # Validation should fail
        assert decoded["query_hash"] != hash_query(different_query)
