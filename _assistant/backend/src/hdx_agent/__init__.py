"""ClickHouse SQL Agent Backend."""
from pathlib import Path

from hdx_agent.config import Config

Config.set_config_path(Path("/Users/odemkovych/Projects/docker/agent/agent.local.yaml"))

