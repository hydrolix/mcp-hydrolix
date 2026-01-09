"""ClickHouse SQL Agent Backend."""

from pathlib import Path

from hdx_agent.config import Config, get_settings

settings = get_settings()
Config.set_config_path(Path(settings.config_path))
