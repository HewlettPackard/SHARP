#!/usr/bin/env python3
"""
Unit tests for Settings singleton.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

import os
import tempfile
import unittest
from pathlib import Path

from src.core.shared.settings import Settings
from src.core.shared.singleton import singleton


class TestSingleton(unittest.TestCase):
    """Test singleton decorator functionality."""

    def test_singleton_creates_single_instance(self):
        """Test that singleton decorator creates only one instance."""
        @singleton
        class TestClass:
            def __init__(self, value=0):
                self.value = value

        # Reset any previous instances
        TestClass.reset()  # type: ignore

        # Create two "instances"
        obj1 = TestClass(value=42)
        obj2 = TestClass(value=99)

        # Should be the same instance
        self.assertIs(obj1, obj2)
        # First initialization value should be preserved
        self.assertEqual(obj1.value, 42)
        self.assertEqual(obj2.value, 42)


class TestSettings(unittest.TestCase):
    """Test Settings singleton functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Reset singleton state before each test
        Settings.reset()  # type: ignore

        # Create a temporary settings file
        self.temp_dir = tempfile.mkdtemp()
        self.settings_file = Path(self.temp_dir) / "test_settings.yaml"

        # Write test settings
        self.settings_file.write_text("""
sharp:
  runlogs_dir: "/tmp/runlogs"
  version: "4.0.0"

cli:
  default_backend: "mpi"
  default_repeater: "se"
  nested:
    deep:
      value: 123

gui:
  theme: "dark"
""")

    def tearDown(self):
        """Clean up test fixtures."""
        if self.settings_file.exists():
            self.settings_file.unlink()
        if Path(self.temp_dir).exists():
            Path(self.temp_dir).rmdir()

    def test_settings_load_from_file(self):
        """Test loading settings from YAML file."""
        settings = Settings(config_path=str(self.settings_file))

        self.assertEqual(settings.get('sharp.runlogs_dir'), '/tmp/runlogs')
        self.assertEqual(settings.get('sharp.version'), '4.0.0')
        self.assertEqual(settings.get('cli.default_backend'), 'mpi')

    def test_settings_nested_access(self):
        """Test accessing deeply nested settings."""
        settings = Settings(config_path=str(self.settings_file))

        value = settings.get('cli.nested.deep.value')
        self.assertEqual(value, 123)

    def test_settings_default_value(self):
        """Test returning default value for missing keys."""
        settings = Settings(config_path=str(self.settings_file))

        # Non-existent key should return default
        value = settings.get('nonexistent.key', 'default_value')
        self.assertEqual(value, 'default_value')

        # Missing without default should return None
        value = settings.get('another.missing.key')
        self.assertIsNone(value)

    def test_settings_immutability(self):
        """Test that settings are immutable after initialization."""
        settings = Settings(config_path=str(self.settings_file))

        # Getting all settings should return a copy
        all_settings = settings.all
        original_runlogs = settings.get('sharp.runlogs_dir')

        # Modifying returned dict shouldn't affect settings
        all_settings['sharp']['runlogs_dir'] = 'modified'
        self.assertEqual(settings.get('sharp.runlogs_dir'), original_runlogs)

    def test_settings_missing_file(self):
        """Test behavior when settings file doesn't exist."""
        Settings.reset()  # type: ignore
        nonexistent = Path(self.temp_dir) / "nonexistent.yaml"
        settings = Settings(config_path=str(nonexistent))

        # Should not crash, just return defaults
        value = settings.get('any.key', 'default')
        self.assertEqual(value, 'default')

    def test_settings_singleton_behavior(self):
        """Test that Settings maintains singleton across calls."""
        settings1 = Settings(config_path=str(self.settings_file))
        settings2 = Settings()  # Should return same instance

        self.assertIs(settings1, settings2)
        # Both should have the same config path
        self.assertEqual(settings1.config_path, settings2.config_path)

    def test_settings_config_path_property(self):
        """Test config_path property."""
        settings = Settings(config_path=str(self.settings_file))

        self.assertEqual(settings.config_path, self.settings_file)


if __name__ == "__main__":
    unittest.main()
