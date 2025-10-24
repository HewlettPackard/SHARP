"""
Unit tests for configuration include resolution.

Tests merge semantics, cycle detection, depth limits, path resolution,
and error handling for the include_resolver module.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import json
import tempfile
import unittest
from pathlib import Path

from src.core.config.errors import ConfigError
from src.core.config.include_resolver import (
    merge_dicts,
    resolve_include_path,
    resolve_includes,
)


class TestMergeDicts(unittest.TestCase):
    """Test dictionary merging semantics."""

    def test_merge_primitive_override(self):
        """Test primitive values are overridden by override dict."""
        base = {'a': 1, 'b': 2}
        override = {'b': 3, 'c': 4}
        result = merge_dicts(base, override)

        self.assertEqual(result['a'], 1,  "Base-only key should be preserved")
        self.assertEqual(result['b'], 3, "Override should win for primitive values")
        self.assertEqual(result['c'], 4, "Override-only key should be added")

    def test_merge_lists_concatenate(self):
        """Test lists are concatenated (base + override)."""
        base = {'items': [1, 2, 3]}
        override = {'items': [4, 5]}
        result = merge_dicts(base, override)

        self.assertEqual(result['items'], [1, 2, 3, 4, 5],
                         "Lists should be concatenated with base first")

    def test_merge_nested_dicts_recursive(self):
        """Test nested dicts are merged recursively."""
        base = {
            'config': {
                'server': 'localhost',
                'port': 8080,
                'options': {'verbose': True}
            }
        }
        override = {
            'config': {
                'port': 9000,
                'options': {'debug': True}
            }
        }
        result = merge_dicts(base, override)

        # Verify recursive merge
        self.assertEqual(result['config']['server'], 'localhost',
                         "Base-only nested key should be preserved")
        self.assertEqual(result['config']['port'], 9000,
                         "Override should win for nested primitive")
        self.assertEqual(result['config']['options'], {'verbose': True, 'debug': True},
                         "Deeply nested dicts should be merged")

    def test_merge_type_mismatch_raises_error(self):
        """Test type mismatch between base and override raises ConfigError."""
        base = {'value': 'string'}
        override = {'value': 123}

        with self.assertRaises(ConfigError) as context:
            merge_dicts(base, override)

        error_msg = str(context.exception)
        self.assertIn('Type mismatch', error_msg)
        self.assertIn('value', error_msg)
        self.assertIn('str', error_msg)
        self.assertIn('int', error_msg)

    def test_merge_list_vs_dict_raises_error(self):
        """Test mixing lists and dicts for same key raises ConfigError."""
        base = {'config': [1, 2, 3]}
        override = {'config': {'key': 'value'}}

        with self.assertRaises(ConfigError) as context:
            merge_dicts(base, override)

        error_msg = str(context.exception)
        self.assertIn('Type mismatch', error_msg)
        self.assertIn('config', error_msg)


class TestResolveIncludePath(unittest.TestCase):
    """Test include path resolution."""

    def setUp(self):
        """Create temporary directory structure for testing."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.current_file = self.temp_dir / "current.yaml"
        self.current_file.touch()

        # Create test file relative to current
        self.relative_file = self.temp_dir / "relative.yaml"
        self.relative_file.touch()

    def tearDown(self):
        """Clean up temporary files."""
        for file in self.temp_dir.glob("*.yaml"):
            file.unlink()
        self.temp_dir.rmdir()

    def test_resolve_relative_to_current_file(self):
        """Test resolution relative to current file's directory."""
        resolved = resolve_include_path("relative.yaml", str(self.current_file))

        self.assertEqual(Path(resolved), self.relative_file.resolve(),
                         "Should resolve relative to current file's directory")

    def test_resolve_nonexistent_raises_error(self):
        """Test resolution of nonexistent file raises ConfigError."""
        with self.assertRaises(ConfigError) as context:
            resolve_include_path("nonexistent.yaml", str(self.current_file))

        error_msg = str(context.exception)
        self.assertIn("Cannot resolve", error_msg)
        self.assertIn("nonexistent.yaml", error_msg)


class TestResolveIncludes(unittest.TestCase):
    """Test recursive include resolution."""

    def setUp(self):
        """Create temporary directory and test files."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up temporary files."""
        for file in self.temp_dir.rglob("*"):
            if file.is_file():
                file.unlink()
        for dir in sorted(self.temp_dir.rglob("*"), reverse=True):
            if dir.is_dir():
                dir.rmdir()
        self.temp_dir.rmdir()

    def test_resolve_no_includes(self):
        """Test file without includes returns content as-is."""
        config_file = self.temp_dir / "simple.yaml"
        config_file.write_text("key: value\nlist: [1, 2, 3]")

        result = resolve_includes(str(config_file))

        self.assertEqual(result, {'key': 'value', 'list': [1, 2, 3]})

    def test_resolve_single_include(self):
        """Test file with single include merges correctly."""
        # Create included file
        base_file = self.temp_dir / "base.yaml"
        base_file.write_text("base_key: base_value\nshared: from_base")

        # Create file that includes base
        main_file = self.temp_dir / "main.yaml"
        main_file.write_text(
            "include:\n  - base.yaml\nshared: from_main\nmain_key: main_value"
        )

        result = resolve_includes(str(main_file))

        # Main file should override shared key
        self.assertEqual(result['base_key'], 'base_value',
                         "Should include key from base file")
        self.assertEqual(result['main_key'], 'main_value',
                         "Should include key from main file")
        self.assertEqual(result['shared'], 'from_main',
                         "Main file should override included file")

    def test_resolve_multiple_includes_ordered(self):
        """Test multiple includes are merged in order (later overrides earlier)."""
        file1 = self.temp_dir / "file1.yaml"
        file1.write_text("key: from_file1\nvalue1: 1")

        file2 = self.temp_dir / "file2.yaml"
        file2.write_text("key: from_file2\nvalue2: 2")

        main_file = self.temp_dir / "main.yaml"
        main_file.write_text(
            "include:\n  - file1.yaml\n  - file2.yaml\nvalue3: 3"
        )

        result = resolve_includes(str(main_file))

        # file2 should override file1 for 'key'
        self.assertEqual(result['key'], 'from_file2',
                         "Later includes should override earlier ones")
        self.assertEqual(result['value1'], 1)
        self.assertEqual(result['value2'], 2)
        self.assertEqual(result['value3'], 3)

    def test_resolve_nested_includes(self):
        """Test includes can recursively include other files."""
        level2 = self.temp_dir / "level2.yaml"
        level2.write_text("level2_key: level2_value")

        level1 = self.temp_dir / "level1.yaml"
        level1.write_text(
            "include:\n  - level2.yaml\nlevel1_key: level1_value"
        )

        main = self.temp_dir / "main.yaml"
        main.write_text(
            "include:\n  - level1.yaml\nmain_key: main_value"
        )

        result = resolve_includes(str(main))

        self.assertEqual(result['level2_key'], 'level2_value')
        self.assertEqual(result['level1_key'], 'level1_value')
        self.assertEqual(result['main_key'], 'main_value')
        self.assertNotIn('include', result,
                         "Include directives should be removed from final result")

    def test_resolve_cycle_detection(self):
        """Test circular includes are detected and raise ConfigError."""
        file_a = self.temp_dir / "a.yaml"
        file_b = self.temp_dir / "b.yaml"

        file_a.write_text("include:\n  - b.yaml\nkey_a: value_a")
        file_b.write_text("include:\n  - a.yaml\nkey_b: value_b")

        with self.assertRaises(ConfigError) as context:
            resolve_includes(str(file_a))

        error_msg = str(context.exception)
        self.assertIn("Circular include", error_msg)

    def test_resolve_depth_limit(self):
        """Test excessive nesting depth is prevented."""
        # Create chain of 15 files (exceeds default limit of 10)
        files = []
        for i in range(15):
            file = self.temp_dir / f"level{i}.yaml"
            if i == 14:
                # Deepest file has no includes
                file.write_text(f"level{i}: value{i}")
            else:
                # Each file includes the next level
                file.write_text(
                    f"include:\n  - level{i+1}.yaml\nlevel{i}: value{i}"
                )
            files.append(file)

        with self.assertRaises(ConfigError) as context:
            resolve_includes(str(files[0]))

        error_msg = str(context.exception)
        self.assertIn("depth limit", error_msg.lower())

    def test_resolve_json_file(self):
        """Test JSON files are parsed correctly."""
        json_file = self.temp_dir / "config.json"
        json_file.write_text(json.dumps({'key': 'value', 'num': 42}))

        result = resolve_includes(str(json_file))

        self.assertEqual(result, {'key': 'value', 'num': 42})

    def test_resolve_nonexistent_file_raises_error(self):
        """Test resolving nonexistent file raises ConfigError."""
        with self.assertRaises(ConfigError) as context:
            resolve_includes(str(self.temp_dir / "nonexistent.yaml"))

        error_msg = str(context.exception)
        self.assertIn("not found", error_msg.lower())

    def test_resolve_invalid_yaml_raises_error(self):
        """Test invalid YAML syntax raises ConfigError."""
        bad_file = self.temp_dir / "bad.yaml"
        # Actually invalid YAML - unterminated quote
        bad_file.write_text("key: 'unterminated string\nother_key: value")

        with self.assertRaises(ConfigError) as context:
            resolve_includes(str(bad_file))

        error_msg = str(context.exception)
        self.assertIn("parse", error_msg.lower())

    def test_resolve_non_dict_raises_error(self):
        """Test YAML file containing non-dict raises ConfigError."""
        list_file = self.temp_dir / "list.yaml"
        list_file.write_text("- item1\n- item2\n- item3")

        with self.assertRaises(ConfigError) as context:
            resolve_includes(str(list_file))

        error_msg = str(context.exception)
        self.assertIn("must contain a dict", error_msg.lower())

    def test_resolve_include_not_list_raises_error(self):
        """Test include directive that's not a list raises ConfigError."""
        bad_include = self.temp_dir / "bad_include.yaml"
        bad_include.write_text("include: not_a_list.yaml\nkey: value")

        with self.assertRaises(ConfigError) as context:
            resolve_includes(str(bad_include))

        error_msg = str(context.exception)
        self.assertIn("must be a list", error_msg.lower())


if __name__ == '__main__':
    unittest.main()
