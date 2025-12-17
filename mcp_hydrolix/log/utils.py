"""Logging utilities for redacting sensitive information from logs."""

import logging
import re

from mcp_hydrolix.auth import TOKEN_PARAM


class AccessLogTokenRedactingFilter(logging.Filter):
    """
    Filter that redacts token query parameters from uvicorn access logs.

    This filter is specifically designed to intercept log messages that contain
    request URLs with query parameters and replace token values with [REDACTED].
    """

    # Regex pattern to match token=<value> in query strings
    # Matches: token=<anything except & or whitespace>
    TOKEN_PATTERN = re.compile(rf"{TOKEN_PARAM}=[^&\s]+")

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter method that redacts tokens from the log message.

        Args:
            record: The log record to filter

        Returns:
            True (side-effect only)
        """
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self.TOKEN_PATTERN.sub(rf"{TOKEN_PARAM}=[REDACTED]", record.msg)

        # Also check args if they exist (for formatted log messages)
        if hasattr(record, "args") and record.args:
            # Convert args to list for modification
            if isinstance(record.args, tuple):
                modified_args: list = []
                for arg in record.args:
                    if isinstance(arg, str):
                        # Redact tokens from string arguments
                        modified_args.append(
                            self.TOKEN_PATTERN.sub(rf"{TOKEN_PARAM}=[REDACTED]", arg)
                        )
                    elif isinstance(arg, bytes):
                        # Redact tokens from string arguments
                        modified_args.append(
                            self.TOKEN_PATTERN.sub(
                                rf"{TOKEN_PARAM}=[REDACTED]", arg.decode("utf-8")
                            )
                        )
                    else:
                        modified_args.append(arg)
                record.args = tuple(modified_args)

        return True
