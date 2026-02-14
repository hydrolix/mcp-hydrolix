"""Pagination utilities for MCP Hydrolix tools."""

import base64
import hashlib
import json
from typing import Any, TypedDict


class CursorData(TypedDict, total=False):
    """Structure of cursor data.

    Attributes:
        type: Type of cursor ('table_list' or 'query_result')
        offset: Current offset in the result set
        params: Original request parameters for validation
        query_hash: SHA256 hash of query for validation (query_result only)
    """

    type: str
    offset: int
    params: dict[str, Any]
    query_hash: str


def encode_cursor(cursor_data: CursorData) -> str:
    """Encode cursor data to opaque string.

    Args:
        cursor_data: Dictionary with cursor state

    Returns:
        Base64-encoded JSON string (URL-safe)

    Example:
        >>> encode_cursor({"type": "table_list", "offset": 50})
        'eyJvZmZzZXQiOjUwLCJ0eXBlIjoidGFibGVfbGlzdCJ9'
    """
    json_str = json.dumps(cursor_data, sort_keys=True)
    return base64.urlsafe_b64encode(json_str.encode()).decode()


def decode_cursor(cursor: str) -> CursorData:
    """Decode cursor string to data dictionary.

    Args:
        cursor: Opaque cursor string from previous response

    Returns:
        Dictionary with cursor state

    Raises:
        ValueError: If cursor is invalid or malformed

    Example:
        >>> decode_cursor('eyJvZmZzZXQiOjUwLCJ0eXBlIjoidGFibGVfbGlzdCJ9')
        {'offset': 50, 'type': 'table_list'}
    """
    try:
        json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
        return json.loads(json_str)
    except Exception as e:
        raise ValueError(f"Invalid cursor format: {str(e)}")


def hash_query(query: str) -> str:
    """Generate hash of query for cursor validation.

    Strips leading/trailing whitespace before hashing to ensure
    queries that differ only in whitespace produce the same hash.

    Args:
        query: SQL query string

    Returns:
        SHA256 hash as hex string

    Example:
        >>> hash_query("SELECT * FROM table")
        'a3b2c1...'
    """
    return hashlib.sha256(query.strip().encode()).hexdigest()


def validate_cursor_params(cursor_data: CursorData, expected_params: dict[str, Any]) -> None:
    """Validate cursor parameters match expected values.

    Ensures that the cursor is being used with the same parameters
    as when it was created, preventing cursor reuse across different queries.

    Args:
        cursor_data: Decoded cursor data
        expected_params: Expected parameter values

    Raises:
        ValueError: If parameters don't match

    Example:
        >>> cursor = {"params": {"database": "test"}}
        >>> validate_cursor_params(cursor, {"database": "test"})  # OK
        >>> validate_cursor_params(cursor, {"database": "prod"})  # Raises ValueError
    """
    cursor_params = cursor_data.get("params", {})
    for key, expected_value in expected_params.items():
        if cursor_params.get(key) != expected_value:
            raise ValueError(
                f"Cursor parameter mismatch: {key}={cursor_params.get(key)} "
                f"(expected {expected_value})"
            )
