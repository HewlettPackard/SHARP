#!/usr/bin/env python3
"""
Unit tests for Settings singleton.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
from pathlib import Path

from src.core.config.settings import Settings
from src.core.singleton import singleton


@pytest.fixture
def settings_file(tmp_path):
    """Create a temporary settings file with test data."""
    settings_path = tmp_path / "test_settings.yaml"
    settings_path.write_text("""
data:
  runlogs_dir: "/tmp/runlogs"

cli:
  default_backend: "mpi"
  default_repeater: "se"
  nested:
    deep:
      value: 123

gui:
  theme: "dark"
""")
    return settings_path


@pytest.fixture(autouse=True)
def reset_settings():
    """Reset Settings singleton before each test."""
    Settings.reset()  # type: ignore
    yield
    Settings.reset()  # type: ignore


class TestSingleton:
    """Test singleton decorator functionality."""

    def test_singleton_creates_single_instance(self):
        """Singleton ensures only one instance exists across multiple instantiations."""
        @singleton
        class TestClass:
            def __init__(self, value=0):
                self.value = value
                self.call_count = getattr(self, 'call_count', 0) + 1

        # Reset any previous instances
        TestClass.reset()  # type: ignore

        # First instantiation creates instance with value=42
        obj1 = TestClass(value=42)
        assert obj1.value == 42
        assert obj1.call_count == 1

        # Second instantiation returns same instance, ignoring new value
        obj2 = TestClass(value=99)
        assert obj1 is obj2, "Singleton should return same instance"
        # Value should NOT change - first initialization wins
        assert obj2.value == 42, "Singleton should preserve first initialization value"
        # __init__ should NOT be called again
        assert obj2.call_count == 1, "Singleton __init__ should only be called once"

        # Third call also returns same instance
        obj3 = TestClass(value=123)
        assert obj1 is obj3
        assert obj3.value == 42

    def test_singleton_reset_allows_new_instance(self):
        """Reset() allows creating a new singleton instance."""
        @singleton
        class Counter:
            def __init__(self):
                self.count = 0

            def increment(self):
                self.count += 1

        Counter.reset()  # type: ignore
        counter1 = Counter()
        counter1.increment()
        assert counter1.count == 1

        # Reset and create new instance
        Counter.reset()  # type: ignore
        counter2 = Counter()
        # Should be a new instance with reset state
        assert counter1 is not counter2, "Reset should allow new instance"
        assert counter2.count == 0, "New instance should have fresh state"


class TestSettings:
    """Test Settings singleton functionality."""

    def test_load_from_file(self, settings_file):
        """Settings correctly parses and stores YAML data structure."""
        settings = Settings(config_path=str(settings_file))

        # Verify multiple keys at different nesting levels
        assert settings.get('data.runlogs_dir') == '/tmp/runlogs'
        assert settings.get('cli.default_backend') == 'mpi'
        assert settings.get('gui.theme') == 'dark'

        # Verify structure preservation (can get intermediate dict)
        data_config = settings.get('data')
        assert isinstance(data_config, dict)
        assert 'runlogs_dir' in data_config

    def test_nested_access(self, settings_file):
        """Dot-notation correctly traverses deep nested structures."""
        settings = Settings(config_path=str(settings_file))

        # Deep nesting (4 levels)
        value = settings.get('cli.nested.deep.value')
        assert value == 123, "Should access 4-level nested value"

        # Intermediate level access
        deep_dict = settings.get('cli.nested.deep')
        assert isinstance(deep_dict, dict)
        assert deep_dict['value'] == 123

        # Partial path should return dict
        nested_dict = settings.get('cli.nested')
        assert 'deep' in nested_dict

    def test_default_value(self, settings_file):
        """Default value mechanism works for missing keys at all levels."""
        settings = Settings(config_path=str(settings_file))

        # Non-existent top-level key
        assert settings.get('nonexistent', 'default_top') == 'default_top'

        # Non-existent nested key
        assert settings.get('data.missing_key', 'default_nested') == 'default_nested'

        # Non-existent deep path
        assert settings.get('nonexistent.key.path', 'default_deep') == 'default_deep'

        # Missing without default should return None
        assert settings.get('another.missing.key') is None

        # Existing key should ignore default
        assert settings.get('data.runlogs_dir', 'default_ignored') == '/tmp/runlogs'

    def test_immutability(self, settings_file):
        """Settings data cannot be mutated through returned references."""
        settings = Settings(config_path=str(settings_file))

        # Get original value
        original_runlogs = settings.get('data.runlogs_dir')
        assert original_runlogs == '/tmp/runlogs'

        # Attempt mutation through .all property
        all_settings = settings.all
        all_settings['data']['runlogs_dir'] = 'MUTATED'

        # Settings should be unchanged (deep copy protection)
        assert settings.get('data.runlogs_dir') == '/tmp/runlogs'

        # Attempt mutation through get() of nested dict
        data_dict = settings.get('data')
        data_dict['runlogs_dir'] = 'MUTATED_AGAIN'  # type: ignore

        # Should still be unchanged
        assert settings.get('data.runlogs_dir') == '/tmp/runlogs'

    def test_missing_file(self, tmp_path):
        """Gracefully handle when settings file is missing or unreadable."""
        nonexistent = tmp_path / "nonexistent.yaml"

        # Should not raise exception
        settings = Settings(config_path=str(nonexistent))

        # Should return defaults for any key
        assert settings.get('any.key', 'default') == 'default'

        # Should return None when no default provided
        assert settings.get('any.other.key') is None

        # .all should return empty dict
        assert settings.all == {}

    def test_singleton_behavior(self, settings_file, tmp_path):
        """Singleton pattern prevents multiple Settings instances."""
        settings1 = Settings(config_path=str(settings_file))
        initial_runlogs = settings1.get('data.runlogs_dir')

        # Second instantiation should return same instance, ignoring new path
        other_file = tmp_path / "other.yaml"
        other_file.write_text("data:\n  runlogs_dir: '/other/path'\n")

        settings2 = Settings(config_path=str(other_file))

        # Should be same instance
        assert settings1 is settings2, "Settings should maintain singleton"

        # Config path should NOT change (first initialization wins)
        assert settings1.config_path == settings2.config_path

        # Data should be from first file, not second
        assert settings2.get('data.runlogs_dir') == initial_runlogs

    def test_config_path_property(self, settings_file):
        """config_path property returns correct Path object."""
        settings = Settings(config_path=str(settings_file))

        # Should return Path object
        assert isinstance(settings.config_path, Path)

        # Should match the file we passed
        assert settings.config_path == settings_file

