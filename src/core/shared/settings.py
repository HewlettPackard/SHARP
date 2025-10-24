"""
Global settings singleton for SHARP configuration.

Provides centralized access to runtime configuration loaded from settings.yaml.
Supports nested settings access via dot notation. Settings are immutable after
initialization to prevent unintended runtime modifications.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from .singleton import singleton


@singleton
class Settings:
    """
    Global settings accessor with nested key support.

    Settings are loaded from settings.yaml (or environment-specified path)
    and accessed via dot notation for nested values. Once loaded, settings
    are immutable to ensure consistent behavior across the application.

    Example:
        settings = Settings()
        runlogs_dir = settings.get('sharp.runlogs_dir', 'runlogs')
        default_backend = settings.get('cli.default_backend', 'local')
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize settings from YAML file.

        Args:
            config_path: Path to settings YAML file. If None, uses
                        SHARP_SETTINGS env var or 'settings.yaml' in project root.
        """
        if config_path is None:
            # Try environment variable first, then default
            config_path = os.environ.get('SHARP_SETTINGS', 'settings.yaml')

        # Convert to absolute path if relative
        config_file = Path(config_path)
        if not config_file.is_absolute():
            # Assume relative to project root (where settings.yaml lives)
            project_root = Path(__file__).parent.parent.parent.parent
            config_file = project_root / config_file

        self._config_path = config_file
        self._data: Dict[str, Any] = {}
        self._load_settings()

    def _load_settings(self) -> None:
        """Load settings from YAML file."""
        if not self._config_path.exists():
            # If settings file doesn't exist, use empty dict (allows runtime-only usage)
            self._data = {}
            return

        with open(self._config_path, 'r') as f:
            self._data = yaml.safe_load(f) or {}

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get nested setting value via dot notation.

        Args:
            key_path: Dot-separated path to setting (e.g., 'sharp.runlogs_dir')
            default: Default value if key not found

        Returns:
            Setting value or default if not found

        Example:
            >>> settings = Settings()
            >>> settings.get('sharp.runlogs_dir', 'runlogs')
            'runlogs'
        """
        keys = key_path.split('.')
        val = self._data

        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
                if val is None:
                    return default
            else:
                return default

        return val

    @property
    def config_path(self) -> Path:
        """Get path to settings file."""
        return self._config_path

    @property
    def all(self) -> Dict[str, Any]:
        """
        Get all settings as dictionary.

        Returns a deep copy to prevent external modification of settings.
        """
        import copy
        return copy.deepcopy(self._data)
