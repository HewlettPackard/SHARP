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
        """Test singleton ensures only one instance exists across multiple instantiations."""
        @singleton
        class TestClass:
            def __init__(self, value=0):
                self.value = value
                self.call_count = getattr(self, 'call_count', 0) + 1

        # Reset any previous instances
        TestClass.reset()  # type: ignore

        # First instantiation should create instance with value=42
        obj1 = TestClass(value=42)
        self.assertEqual(obj1.value, 42)
        self.assertEqual(obj1.call_count, 1)

        # Second instantiation should return same instance, ignoring new value
        obj2 = TestClass(value=99)
        self.assertIs(obj1, obj2, "Singleton should return same instance")
        # Value should NOT change - first initialization wins
        self.assertEqual(obj2.value, 42, "Singleton should preserve first initialization value")
        # __init__ should NOT be called again
        self.assertEqual(obj2.call_count, 1, "Singleton __init__ should only be called once")

        # Third call should also return same instance
        obj3 = TestClass(value=123)
        self.assertIs(obj1, obj3)
        self.assertEqual(obj3.value, 42)

    def test_singleton_reset_allows_new_instance(self):
        """Test that reset() allows creating a new singleton instance."""
        @singleton
        class Counter:
            def __init__(self):
                self.count = 0

            def increment(self):
                self.count += 1

        Counter.reset()  # type: ignore
        counter1 = Counter()
        counter1.increment()
        self.assertEqual(counter1.count, 1)

        # Reset and create new instance
        Counter.reset()  # type: ignore
        counter2 = Counter()
        # Should be a new instance with reset state
        self.assertIsNot(counter1, counter2, "Reset should allow new instance")
        self.assertEqual(counter2.count, 0, "New instance should have fresh state")


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
        """Test settings correctly parses and stores YAML data structure."""
        settings = Settings(config_path=str(self.settings_file))

        # Verify multiple keys at different nesting levels
        self.assertEqual(settings.get('sharp.runlogs_dir'), '/tmp/runlogs')
        self.assertEqual(settings.get('sharp.version'), '4.0.0')
        self.assertEqual(settings.get('cli.default_backend'), 'mpi')
        self.assertEqual(settings.get('gui.theme'), 'dark')

        # Verify structure preservation (can't get intermediate dict)
        sharp_config = settings.get('sharp')
        self.assertIsInstance(sharp_config, dict)
        self.assertIn('runlogs_dir', sharp_config)
        self.assertIn('version', sharp_config)

    def test_settings_nested_access(self):
        """Test dot-notation correctly traverses deep nested structures."""
        settings = Settings(config_path=str(self.settings_file))

        # Deep nesting (4 levels)
        value = settings.get('cli.nested.deep.value')
        self.assertEqual(value, 123, "Should access 4-level nested value")

        # Intermediate level access
        deep_dict = settings.get('cli.nested.deep')
        self.assertIsInstance(deep_dict, dict)
        self.assertEqual(deep_dict['value'], 123)

        # Partial path should return dict
        nested_dict = settings.get('cli.nested')
        self.assertIn('deep', nested_dict)

    def test_settings_default_value(self):
        """Test default value mechanism for missing keys at all levels."""
        settings = Settings(config_path=str(self.settings_file))

        # Non-existent top-level key
        value = settings.get('nonexistent', 'default_top')
        self.assertEqual(value, 'default_top')

        # Non-existent nested key
        value = settings.get('sharp.missing_key', 'default_nested')
        self.assertEqual(value, 'default_nested')

        # Non-existent deep path
        value = settings.get('nonexistent.key.path', 'default_deep')
        self.assertEqual(value, 'default_deep')

        # Missing without default should return None
        value = settings.get('another.missing.key')
        self.assertIsNone(value)

        # Existing key should ignore default
        value = settings.get('sharp.version', 'default_ignored')
        self.assertEqual(value, '4.0.0', "Default should be ignored for existing keys")

    def test_settings_immutability(self):
        """Test settings data cannot be mutated through returned references."""
        settings = Settings(config_path=str(self.settings_file))

        # Get original value
        original_runlogs = settings.get('sharp.runlogs_dir')
        self.assertEqual(original_runlogs, '/tmp/runlogs')

        # Attempt mutation through .all property
        all_settings = settings.all
        all_settings['sharp']['runlogs_dir'] = 'MUTATED'
        all_settings['sharp']['version'] = 'MUTATED'

        # Settings should be unchanged (deep copy protection)
        self.assertEqual(settings.get('sharp.runlogs_dir'), '/tmp/runlogs',
                         "Mutating .all return value should not affect settings")
        self.assertEqual(settings.get('sharp.version'), '4.0.0',
                         "Settings should remain immutable")

        # Attempt mutation through get() of nested dict
        sharp_dict = settings.get('sharp')
        sharp_dict['runlogs_dir'] = 'MUTATED_AGAIN'  # type: ignore

        # Should still be unchanged
        self.assertEqual(settings.get('sharp.runlogs_dir'), '/tmp/runlogs',
                         "Mutating get() return value should not affect settings")

    def test_settings_missing_file(self):
        """Test graceful handling when settings file is missing or unreadable."""
        Settings.reset()  # type: ignore
        nonexistent = Path(self.temp_dir) / "nonexistent.yaml"

        # Should not raise exception
        settings = Settings(config_path=str(nonexistent))

        # Should return defaults for any key
        value = settings.get('any.key', 'default')
        self.assertEqual(value, 'default')

        # Should return None when no default provided
        value = settings.get('any.other.key')
        self.assertIsNone(value)

        # .all should return empty dict
        all_settings = settings.all
        self.assertEqual(all_settings, {})

    def test_settings_singleton_behavior(self):
        """Test singleton pattern prevents multiple Settings instances."""
        settings1 = Settings(config_path=str(self.settings_file))
        initial_runlogs = settings1.get('sharp.runlogs_dir')

        # Second instantiation should return same instance, ignoring new path
        other_file = Path(self.temp_dir) / "other.yaml"
        other_file.write_text("sharp:\n  runlogs_dir: '/other/path'\n")

        settings2 = Settings(config_path=str(other_file))

        # Should be same instance
        self.assertIs(settings1, settings2, "Settings should maintain singleton")

        # Config path should NOT change (first initialization wins)
        self.assertEqual(settings1.config_path, settings2.config_path,
                         "Config path should not change after first initialization")

        # Data should be from first file, not second
        self.assertEqual(settings2.get('sharp.runlogs_dir'), initial_runlogs,
                         "Singleton should preserve first config, ignore subsequent paths")

        other_file.unlink()

    def test_settings_config_path_property(self):
        """Test config_path property returns correct Path object."""
        settings = Settings(config_path=str(self.settings_file))

        # Should return Path object
        self.assertIsInstance(settings.config_path, Path)

        # Should match the file we passed
        self.assertEqual(settings.config_path, self.settings_file)


if __name__ == "__main__":
    unittest.main()
