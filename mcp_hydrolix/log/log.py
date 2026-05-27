import json
import logging
import logging.config
import os
from pathlib import Path

import yaml


# Standard LogRecord attribute names — anything else on the record came from
# a caller's ``extra={...}`` kwarg and should be surfaced in the JSON envelope.
_STANDARD_LOGRECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__)


class JsonFormatter(logging.Formatter):
    """
    Custom formatter to output logs in JSON format.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Convert log record to JSON format."""
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "component": "mcp-hydrolix",
            "logger": record.name,
        }

        if isinstance(record.msg, dict):
            log_record["message"] = json.dumps(record.msg)
        else:
            log_record["message"] = record.getMessage()

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # ``setdefault`` keeps envelope fields (level, timestamp, ...) from
        # being clobbered if a caller accidentally passes a same-named extra.
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOGRECORD_ATTRS:
                continue
            log_record.setdefault(key, value)

        return json.dumps(log_record)


def setup_logging(config_path: str | None, log_level: str, log_format: str) -> dict | None:
    """
    Configures logging from a YAML file and overrides level/format.
    """
    if config_path is None:
        # print(f"Warning: Logging config file not provided at '{config_path}'. Using basic config.")
        config_path = f"{os.path.dirname(__file__)}/log.yaml"

    config_file = Path(config_path)
    if not config_file.is_file():
        logging.basicConfig(level=log_level.upper())
        return None

    with open(config_file) as f:
        config = yaml.safe_load(f)

    # Override level and formatter based on function arguments
    config["root"]["level"] = log_level.upper()
    if "loggers" in config and isinstance(config["loggers"], dict):
        for logger in config["loggers"].keys():
            config["loggers"][logger]["level"] = log_level.upper()

    config["handlers"]["default"]["formatter"] = log_format

    # logging.config.dictConfig(config)
    return config
