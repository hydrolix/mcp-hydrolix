import os
import re
import threading
from pathlib import Path
from typing import Any

import yaml


class EnvVarLoader(yaml.SafeLoader):  # type: ignore[misc]
    """Yaml loader which replaces environment variables."""

    pass


EnvVarLoader.add_implicit_resolver("!path", re.compile(r".*\$\{([^}^{]+)\}.*"), None)
EnvVarLoader.add_constructor("!path", lambda loader, node: os.path.expandvars(node.value))


class _OctoDict(dict):
    """Dictionary with dynamic entries."""

    def __getattr__(self, item: str) -> Any:  # noqa: ANN401
        """Dynamically retrieve an attribute."""
        if item not in self:
            raise AttributeError(f"{item} not found in {self.keys()} keys")
        v = super().__getitem__(item)
        if isinstance(v, dict):
            return _OctoDict(v)
        return v

    def __getitem__(self, item: str) -> Any:  # noqa: ANN401
        """Dynamically retrieve an item when iterated."""
        return self.__getattr__(item)

    def __hasattr__(self, item: str) -> Any:  # noqa: ANN401
        """Check if item exists."""
        return item in self  # noqa: ANN401

    def get(self, item: str, __default: any = None) -> any:
        if self.__hasattr__(item):
            return self.__getattr__(item)
        return __default


class Config:
    """Configuration singleton."""

    _instance = None
    """Singleton instance of configuration."""
    _lock = threading.Lock()
    """Thread lock."""

    def __new__(cls, *args, **kwargs):  # noqa: ANN003, ANN002, ANN204
        """Thread-safe constructor."""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls, *args, **kwargs)
                    cls._instance._config_inited = False
        return cls._instance

    _config_path: Path | None = None
    """Path to configuration file."""
    _dataset_dir_path: Path | None = None
    """Path to dataset directory."""
    _prompt_dir_path: Path | None = None
    """Path to prompt directory."""

    @classmethod
    def set_config_path(cls, config_path: Path | None) -> None:
        """Set config file path"""
        cls._config_path = config_path
        if cls._instance:
            cls._instance = Config()

    @classmethod
    def set_dataset_dir_path(cls, dataset_dir_path: Path | None) -> None:
        """Set data dir path"""
        cls._dataset_dir_path = dataset_dir_path
        if cls._instance:
            cls._instance._dataset_dir_path = dataset_dir_path

    @classmethod
    def set_prompt_dir_path(cls, prompt_dir_path: Path | None) -> None:
        """Set data dir path"""
        cls._prompt_dir_path = prompt_dir_path

    def __init__(self) -> None:
        """Initialize config"""
        with open(str(self._config_path)) as f:
            self.config = _OctoDict(yaml.load(f, Loader=EnvVarLoader))  # noqa: S506

    def __getattr__(self, item: str) -> int | float | str | Path | _OctoDict:
        """Retrieve attribute."""
        if item == "dataset_dir":
            return self._dataset_dir_path
        if item == "prompt_dir":
            return self._prompt_dir_path

        return self.config[item]
