"""
Unit tests for configuration include resolution.

Tests merge semantics, cycle detection, depth limits, path resolution,
and error handling for the include_resolver module.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import json
from pathlib import Path

from src.core.config.errors import ConfigError
from src.core.config.include_resolver import (
    merge_dicts,
    resolve_include_path,
    resolve_includes,
)


# ========== Test dictionary merging semantics ==========

def test_merge_primitive_override():
    """Test primitive values are overridden by override dict."""
    base = {'a': 1, 'b': 2}
    override = {'b': 3, 'c': 4}
    result = merge_dicts(base, override)

    assert result['a'] == 1, "Base-only key should be preserved"
    assert result['b'] == 3, "Override should win for primitive values"
    assert result['c'] == 4, "Override-only key should be added"


def test_merge_lists_concatenate():
    """Test lists are concatenated (base + override)."""
    base = {'items': [1, 2, 3]}
    override = {'items': [4, 5]}
    result = merge_dicts(base, override)

    assert result['items'] == [1, 2, 3, 4, 5], "Lists should be concatenated with base first"


def test_merge_nested_dicts_recursive():
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
    assert result['config']['server'] == 'localhost', "Base-only nested key should be preserved"
    assert result['config']['port'] == 9000, "Override should win for nested primitive"
    assert result['config']['options'] == {'verbose': True, 'debug': True}, \
        "Deeply nested dicts should be merged"


def test_merge_type_mismatch_raises_error():
    """Test type mismatch between base and override raises ConfigError."""
    base = {'value': 'string'}
    override = {'value': 123}

    with pytest.raises(ConfigError) as exc_info:
        merge_dicts(base, override)

    error_msg = str(exc_info.value)
    assert 'Type mismatch' in error_msg
    assert 'value' in error_msg
    assert 'str' in error_msg
    assert 'int' in error_msg


def test_merge_list_vs_dict_raises_error():
    """Test mixing lists and dicts for same key raises ConfigError."""
    base = {'config': [1, 2, 3]}
    override = {'config': {'key': 'value'}}

    with pytest.raises(ConfigError) as exc_info:
        merge_dicts(base, override)

    error_msg = str(exc_info.value)
    assert 'Type mismatch' in error_msg
    assert 'config' in error_msg


# ========== Test include path resolution ==========

def test_resolve_relative_to_current_file(tmp_path):
    """Test resolution relative to current file's directory."""
    current_file = tmp_path / "current.yaml"
    current_file.touch()

    # Create test file relative to current
    relative_file = tmp_path / "relative.yaml"
    relative_file.touch()

    resolved = resolve_include_path("relative.yaml", str(current_file))

    assert Path(resolved) == relative_file.resolve(), \
        "Should resolve relative to current file's directory"


def test_resolve_nonexistent_raises_error(tmp_path):
    """Test resolution of nonexistent file raises ConfigError."""
    current_file = tmp_path / "current.yaml"
    current_file.touch()

    with pytest.raises(ConfigError) as exc_info:
        resolve_include_path("nonexistent.yaml", str(current_file))

    error_msg = str(exc_info.value)
    assert "Cannot resolve" in error_msg
    assert "nonexistent.yaml" in error_msg


# ========== Test recursive include resolution ==========

def test_resolve_no_includes(tmp_path):
    """Test file without includes returns content as-is."""
    config_file = tmp_path / "simple.yaml"
    config_file.write_text("key: value\nlist: [1, 2, 3]")

    result = resolve_includes(str(config_file))

    assert result == {'key': 'value', 'list': [1, 2, 3]}


def test_resolve_single_include(tmp_path):
    """Test file with single include merges correctly."""
    # Create included file
    base_file = tmp_path / "base.yaml"
    base_file.write_text("base_key: base_value\nshared: from_base")

    # Create file that includes base
    main_file = tmp_path / "main.yaml"
    main_file.write_text(
        "include:\n  - base.yaml\nshared: from_main\nmain_key: main_value"
    )

    result = resolve_includes(str(main_file))

    # Main file should override shared key
    assert result['base_key'] == 'base_value', "Should include key from base file"
    assert result['main_key'] == 'main_value', "Should include key from main file"
    assert result['shared'] == 'from_main', "Main file should override included file"


def test_resolve_multiple_includes_ordered(tmp_path):
    """Test multiple includes are merged in order (later overrides earlier)."""
    file1 = tmp_path / "file1.yaml"
    file1.write_text("key: from_file1\nvalue1: 1")

    file2 = tmp_path / "file2.yaml"
    file2.write_text("key: from_file2\nvalue2: 2")

    main_file = tmp_path / "main.yaml"
    main_file.write_text(
        "include:\n  - file1.yaml\n  - file2.yaml\nvalue3: 3"
    )

    result = resolve_includes(str(main_file))

    # file2 should override file1 for 'key'
    assert result['key'] == 'from_file2', "Later includes should override earlier ones"
    assert result['value1'] == 1
    assert result['value2'] == 2
    assert result['value3'] == 3


def test_resolve_nested_includes(tmp_path):
    """Test includes can recursively include other files."""
    level2 = tmp_path / "level2.yaml"
    level2.write_text("level2_key: level2_value")

    level1 = tmp_path / "level1.yaml"
    level1.write_text(
        "include:\n  - level2.yaml\nlevel1_key: level1_value"
    )

    main = tmp_path / "main.yaml"
    main.write_text(
        "include:\n  - level1.yaml\nmain_key: main_value"
    )

    result = resolve_includes(str(main))

    assert result['level2_key'] == 'level2_value'
    assert result['level1_key'] == 'level1_value'
    assert result['main_key'] == 'main_value'
    assert 'include' not in result, \
        "Include directives should be removed from final result"


def test_resolve_cycle_detection(tmp_path):
    """Test circular includes are detected and raise ConfigError."""
    file_a = tmp_path / "a.yaml"
    file_b = tmp_path / "b.yaml"

    file_a.write_text("include:\n  - b.yaml\nkey_a: value_a")
    file_b.write_text("include:\n  - a.yaml\nkey_b: value_b")

    with pytest.raises(ConfigError) as exc_info:
        resolve_includes(str(file_a))

    error_msg = str(exc_info.value)
    assert "Circular include" in error_msg


def test_resolve_depth_limit(tmp_path):
    """Test excessive nesting depth is prevented."""
    # Create chain of 15 files (exceeds default limit of 10)
    files = []
    for i in range(15):
        file = tmp_path / f"level{i}.yaml"
        if i == 14:
            # Deepest file has no includes
            file.write_text(f"level{i}: value{i}")
        else:
            # Each file includes the next level
            file.write_text(
                f"include:\n  - level{i+1}.yaml\nlevel{i}: value{i}"
            )
        files.append(file)

    with pytest.raises(ConfigError) as exc_info:
        resolve_includes(str(files[0]))

    error_msg = str(exc_info.value)
    assert "depth limit" in error_msg.lower()


def test_resolve_json_file(tmp_path):
    """Test JSON files are parsed correctly."""
    json_file = tmp_path / "config.json"
    json_file.write_text(json.dumps({'key': 'value', 'num': 42}))

    result = resolve_includes(str(json_file))

    assert result == {'key': 'value', 'num': 42}


def test_resolve_nonexistent_file_raises_error(tmp_path):
    """Test resolving nonexistent file raises ConfigError."""
    with pytest.raises(ConfigError) as exc_info:
        resolve_includes(str(tmp_path / "nonexistent.yaml"))

    error_msg = str(exc_info.value)
    assert "not found" in error_msg.lower()


def test_resolve_invalid_yaml_raises_error(tmp_path):
    """Test invalid YAML syntax raises ConfigError."""
    bad_file = tmp_path / "bad.yaml"
    # Actually invalid YAML - unterminated quote
    bad_file.write_text("key: 'unterminated string\nother_key: value")

    with pytest.raises(ConfigError) as exc_info:
        resolve_includes(str(bad_file))

    error_msg = str(exc_info.value)
    assert "parse" in error_msg.lower()


def test_resolve_non_dict_raises_error(tmp_path):
    """Test YAML file containing non-dict raises ConfigError."""
    list_file = tmp_path / "list.yaml"
    list_file.write_text("- item1\n- item2\n- item3")

    with pytest.raises(ConfigError) as exc_info:
        resolve_includes(str(list_file))

    error_msg = str(exc_info.value)
    assert "must contain a dict" in error_msg.lower()


def test_resolve_include_not_list_raises_error(tmp_path):
    """Test include directive that's not a list raises ConfigError."""
    bad_include = tmp_path / "bad_include.yaml"
    bad_include.write_text("include: not_a_list.yaml\nkey: value")

    with pytest.raises(ConfigError) as exc_info:
        resolve_includes(str(bad_include))

    error_msg = str(exc_info.value)
    assert "must be a list" in error_msg.lower()

