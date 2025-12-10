"""Tests for logging configuration and token redaction."""

import logging
import logging.config
import os
import tempfile
from pathlib import Path

import pytest

from mcp_hydrolix.log import setup_logging, JsonFormatter
from mcp_hydrolix.log.utils import AccessLogTokenRedactingFilter


class TestAccessLogTokenRedactingFilter:
    """Tests for the AccessLogTokenRedactingFilter class."""

    @pytest.fixture
    def token_filter(self):
        """Create a filter instance for testing."""
        return AccessLogTokenRedactingFilter()

    @pytest.fixture
    def log_record(self):
        """Create a basic log record for testing."""
        return logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="",
            args=(),
            exc_info=None,
        )

    def test_redacts_token_in_simple_message(self, token_filter, log_record):
        """Test that tokens are redacted from simple log messages."""
        log_record.msg = "GET /api/query?token=secret123&param=value"

        result = token_filter.filter(log_record)

        assert result is True
        assert log_record.msg == "GET /api/query?token=[REDACTED]&param=value"

    def test_redacts_token_at_end_of_url(self, token_filter, log_record):
        """Test that tokens are redacted when they're the last parameter."""
        log_record.msg = "GET /api/query?param=value&token=secret123"

        token_filter.filter(log_record)

        assert log_record.msg == "GET /api/query?param=value&token=[REDACTED]"

    def test_redacts_token_as_only_parameter(self, token_filter, log_record):
        """Test that tokens are redacted when they're the only parameter."""
        log_record.msg = "GET /api/query?token=secret123"

        token_filter.filter(log_record)

        assert log_record.msg == "GET /api/query?token=[REDACTED]"

    def test_handles_multiple_tokens_in_message(self, token_filter, log_record):
        """Test that multiple tokens in the same message are all redacted."""
        log_record.msg = "Request 1: token=abc123 Request 2: token=xyz789"

        token_filter.filter(log_record)

        assert log_record.msg == "Request 1: token=[REDACTED] Request 2: token=[REDACTED]"

    def test_preserves_message_without_token(self, token_filter, log_record):
        """Test that messages without tokens are not modified."""
        original_msg = "GET /api/query?param=value&other=data"
        log_record.msg = original_msg

        token_filter.filter(log_record)

        assert log_record.msg == original_msg

    def test_redacts_token_in_args_tuple(self, token_filter, log_record):
        """Test that tokens are redacted from log record args."""
        log_record.msg = "Request to %s with status %d"
        log_record.args = ("/api?token=secret123", 200)

        token_filter.filter(log_record)

        assert log_record.args == ("/api?token=[REDACTED]", 200)

    def test_handles_non_string_args(self, token_filter, log_record):
        """Test that non-string args are preserved."""
        log_record.msg = "Request with %s %d %f"
        log_record.args = ("path", 42, 3.14)

        token_filter.filter(log_record)

        assert log_record.args == ("path", 42, 3.14)

    def test_handles_empty_args(self, token_filter, log_record):
        """Test that empty args don't cause errors."""
        log_record.msg = "Simple message"
        log_record.args = ()

        result = token_filter.filter(log_record)

        assert result is True
        assert log_record.args == ()

    def test_handles_none_args(self, token_filter, log_record):
        """Test that None args don't cause errors."""
        log_record.msg = "Simple message"
        log_record.args = None

        result = token_filter.filter(log_record)

        assert result is True

    def test_handles_non_string_msg(self, token_filter, log_record):
        """Test that non-string messages don't cause errors."""
        log_record.msg = 12345

        result = token_filter.filter(log_record)

        assert result is True
        assert log_record.msg == 12345

    def test_redacts_complex_token_values(self, token_filter, log_record):
        """Test that complex token values are fully redacted."""
        log_record.msg = (
            "GET /api?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        )

        token_filter.filter(log_record)

        assert log_record.msg == "GET /api?token=[REDACTED]"

    def test_redacts_quoted_token_values(self, token_filter, log_record):
        """Test that complex token values are fully redacted."""
        log_record.msg = (
            'GET /api?token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"'
        )
        token_filter.filter(log_record)
        assert log_record.msg == "GET /api?token=[REDACTED]"

        log_record.msg = (
            "GET /api?token='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0'"
        )
        token_filter.filter(log_record)
        assert log_record.msg == "GET /api?token=[REDACTED]"

        log_record.msg = (
            "GET /api?token=`eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0`"
        )
        token_filter.filter(log_record)
        assert log_record.msg == "GET /api?token=[REDACTED]"

    def test_preserves_other_query_params(self, token_filter, log_record):
        """Test that other query parameters remain unchanged."""
        log_record.msg = "GET /api?user=john&token=secret&page=1&limit=10"

        token_filter.filter(log_record)

        assert log_record.msg == "GET /api?user=john&token=[REDACTED]&page=1&limit=10"


class TestSetupLogging:
    """Tests for the setup_logging function."""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary YAML config file for testing."""
        import mcp_hydrolix

        config_path = f"{os.path.dirname(mcp_hydrolix.log.log.__file__)}/log.yaml"
        with open(config_path) as f:
            config = f.read()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config)
            temp_path = f.name

        yield temp_path

        # Cleanup
        Path(temp_path).unlink()

    def test_setup_logging_with_valid_config(self, temp_config_file):
        """Test that setup_logging loads a valid config file."""
        result = setup_logging(temp_config_file, "DEBUG", "json")

        assert result is not None
        assert isinstance(result, dict)
        assert "root" in result
        assert "handlers" in result
        assert "formatters" in result

    def test_setup_logging_overrides_log_level(self, temp_config_file):
        """Test that setup_logging overrides the log level."""
        result = setup_logging(temp_config_file, "WARNING", "default")

        assert result["root"]["level"] == "WARNING"
        assert result["loggers"]["uvicorn"]["level"] == "WARNING"

    def test_setup_logging_overrides_formatter(self, temp_config_file):
        """Test that setup_logging overrides the formatter."""
        result = setup_logging(temp_config_file, "INFO", "json")

        assert result["handlers"]["default"]["formatter"] == "json"

    def test_setup_logging_with_missing_config_file(self):
        """Test that setup_logging handles missing config files."""
        result = setup_logging("/nonexistent/path/config.yaml", "INFO", "default")

        assert result is None

    def test_setup_logging_with_none_config_path(self):
        """Test that setup_logging handles None config path by using default."""
        # This should try to load log.yaml from the same directory
        result = setup_logging(None, "INFO", "default")

        # Result depends on whether log.yaml exists in the package
        assert result is None or isinstance(result, dict)

    def test_setup_logging_preserves_filters(self, temp_config_file):
        """Test that setup_logging preserves filter configuration."""
        result = setup_logging(temp_config_file, "INFO", "default")

        assert "filters" in result
        assert "token_filter" in result["filters"]
        assert result["handlers"]["default"]["filters"] == ["token_filter"]

    def test_setup_logging_case_insensitive_level(self, temp_config_file):
        """Test that log level is converted to uppercase."""
        result = setup_logging(temp_config_file, "debug", "default")

        assert result["root"]["level"] == "DEBUG"

    @pytest.mark.parametrize(
        "logger_name",
        [
            ("test_logger"),
            ("root"),
            ("uvicorn"),
            ("uvicorn.access"),
            ("uvicorn.error"),
            ("gunicorn"),
            ("gunicorn.access"),
            ("gunicorn.error"),
            (None),
        ],
    )
    @pytest.mark.parametrize("log_format", [("default"), ("json"), (None)])
    def test_filter_integration_with_logging(self, temp_config_file, logger_name, log_format):
        """Test that the filter works when integrated with logging system."""
        config = setup_logging(temp_config_file, "INFO", log_format)

        # Apply the configuration
        logging.config.dictConfig(config)

        # Create a logger with a custom handler to capture output
        logger = logging.getLogger(logger_name)

        # Create a string handler to capture logs
        from io import StringIO

        log_stream = StringIO()
        logging.getHandlerByName("default").stream = log_stream

        # Log a message with a token
        logger.info("GET /api?token=secret123&user=john")

        # Check that the token was redacted in the output
        log_output = log_stream.getvalue()
        assert "secret" not in log_output
        assert "secret123" not in log_output
        assert "token=[REDACTED]" in log_output
        assert "user=john" in log_output


class TestJsonFormatter:
    """Tests for the JsonFormatter class."""

    @pytest.fixture
    def formatter(self):
        """Create a JsonFormatter instance."""
        return JsonFormatter()

    @pytest.fixture
    def log_record(self):
        """Create a log record for testing."""
        return logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

    def test_formats_simple_message_as_json(self, formatter, log_record):
        """Test that simple messages are formatted as JSON."""
        import json

        result = formatter.format(log_record)
        parsed = json.loads(result)

        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["message"] == "Test message"
        assert parsed["component"] == "mcp-hydrolix"
        assert "timestamp" in parsed

    def test_formats_dict_message_as_json(self, formatter, log_record):
        """Test that dict messages are JSON-encoded."""
        import json

        log_record.msg = {"key": "value", "count": 42}
        result = formatter.format(log_record)
        parsed = json.loads(result)

        message_dict = json.loads(parsed["message"])
        assert message_dict["key"] == "value"
        assert message_dict["count"] == 42

    def test_includes_exception_info(self, formatter, log_record):
        """Test that exception info is included when present."""
        import json

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            log_record.exc_info = sys.exc_info()

        result = formatter.format(log_record)
        parsed = json.loads(result)

        assert "exception" in parsed
        assert "ValueError: Test error" in parsed["exception"]
