"""
Unit tests for src/cli/launch.py CLI argument parsing and helper functions.

Tests cover:
- Argument parsing with parse_args()
- Configuration loading and merging
- Helper functions for building orchestrator options
- All CLI options from Task 2.7.6

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock
import yaml

from src.cli.launch import (
    build_config_from_sources,
    load_config_file,
    load_repro_file,
    merge_config,
    parse_args,
    build_benchmark_spec,
)


# ========== Argument Parsing Tests ==========

def test_parse_minimal_args():
    """Parse minimal required arguments with defaults."""
    args = parse_args(["-e", "test", "sleep"])
    assert args.experiment == "test"
    assert args.benchmark == "sleep"
    assert args.backend == ["local"], "Should default to local backend"
    assert args.repeater == "MAX", "Should default to MAX repeater"
    assert args.verbose is False


def test_parse_multiple_backends():
    """Parse multiple backend options correctly."""
    args = parse_args(["-e", "test", "sleep", "-b", "perf", "-b", "local"])
    assert args.backend == ["perf", "local"]


def test_parse_task_option():
    """Parse --task option correctly."""
    args = parse_args(["-e", "test", "sleep", "-t", "mytask"])
    assert args.task == "mytask"


def test_parse_timeout_option():
    """Parse --timeout option correctly."""
    args = parse_args(["-e", "test", "sleep", "--timeout", "600"])
    assert args.timeout == 600


def test_parse_copies_option():
    """Parse --copies option correctly."""
    args = parse_args(["-e", "test", "sleep", "--copies", "4"])
    assert args.copies == 4


def test_parse_mpl_alias():
    """Parse --mpl as alias for --copies."""
    args = parse_args(["-e", "test", "sleep", "--mpl", "8"])
    assert args.copies == 8, "--mpl should be alias for --copies"


def test_parse_cold_start():
    """Parse --cold flag correctly."""
    args = parse_args(["-e", "test", "sleep", "--cold"])
    assert args.cold is True
    assert args.warm is False


def test_parse_warm_start():
    """Parse --warm flag correctly."""
    args = parse_args(["-e", "test", "sleep", "--warm"])
    assert args.warm is True
    assert args.cold is False


def test_parse_directory_option():
    """Parse --directory option correctly."""
    args = parse_args(["-e", "test", "sleep", "-d", "/tmp/output"])
    assert args.directory == "/tmp/output"


def test_parse_append_flag():
    """Parse --append flag correctly."""
    args = parse_args(["-e", "test", "sleep", "--append"])
    assert args.append is True


def test_parse_skip_sys_specs_flag():
    """Parse --skip-sys-specs flag correctly."""
    args = parse_args(["-e", "test", "sleep", "--skip-sys-specs"])
    assert args.skip_sys_specs is True


def test_parse_verbose_flag():
    """Parse --verbose flag correctly."""
    args = parse_args(["-e", "test", "sleep", "-v"])
    assert args.verbose is True


def test_parse_config_files():
    """Parse --config option (can specify multiple)."""
    args = parse_args([
        "-e", "test", "sleep",
        "-f", "config1.yaml",
        "-f", "config2.json"
    ])
    assert args.config == ["config1.yaml", "config2.json"]


def test_parse_json_option():
    """Parse --json option correctly."""
    json_str = '{"timeout": 300}'
    args = parse_args(["-e", "test", "sleep", "-j", json_str])
    assert args.json == json_str


def test_parse_repro_option():
    """Parse --repro option correctly."""
    args = parse_args(["-e", "test", "sleep", "--repro", "old_run.md"])
    assert args.repro == "old_run.md"


def test_parse_benchmark_args():
    """Parse positional benchmark arguments correctly."""
    args = parse_args(["-e", "test", "matmul", "1000", "1000"])
    assert args.benchmark_args == ["1000", "1000"]


def test_parse_discovery_list_benchmarks():
    """Parse --list-benchmarks flag correctly."""
    args = parse_args(["--list-benchmarks"])
    assert args.list_benchmarks is True


def test_parse_discovery_show_benchmark():
    """Parse --show-benchmark option correctly."""
    args = parse_args(["--show-benchmark", "sleep"])
    assert args.show_benchmark == "sleep"


def test_parse_discovery_list_backends():
    """Parse --list-backends flag correctly."""
    args = parse_args(["--list-backends"])
    assert args.list_backends is True


def test_parse_discovery_show_backend():
    """Parse --show-backend option correctly."""
    args = parse_args(["--show-backend", "local"])
    assert args.show_backend == "local"


# ========== Configuration Loading Tests ==========

def test_load_yaml_config(tmp_path):
    """Load YAML configuration file correctly."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"timeout": 600, "verbose": True}))

    config = load_config_file(str(config_file))
    assert config["timeout"] == 600
    assert config["verbose"] is True


def test_load_json_config(tmp_path):
    """Load JSON configuration file correctly."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"timeout": 300, "copies": 4}))

    config = load_config_file(str(config_file))
    assert config["timeout"] == 300
    assert config["copies"] == 4


def test_load_config_file_not_found():
    """Loading non-existent config file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_config_file("/nonexistent/config.yaml")


def test_merge_config_simple():
    """Merge simple configuration dictionaries correctly."""
    base = {"timeout": 600, "verbose": False}
    updates = {"verbose": True, "copies": 2}

    merge_config(base, updates)

    assert base["timeout"] == 600, "Unchanged values preserved"
    assert base["verbose"] is True, "Updated values applied"
    assert base["copies"] == 2, "New values added"


def test_merge_config_nested():
    """Merge nested configuration dictionaries correctly."""
    base = {
        "backend_options": {
            "local": {"run": "$CMD"},
            "perf": {"run": "perf stat $CMD"}
        }
    }
    updates = {
        "backend_options": {
            "local": {"timeout": 30},
            "docker": {"run": "docker exec $CMD"}
        }
    }

    merge_config(base, updates)

    # Nested merge should preserve and extend
    assert base["backend_options"]["local"]["run"] == "$CMD", "Existing nested preserved"
    assert base["backend_options"]["local"]["timeout"] == 30, "New nested value added"
    assert "docker" in base["backend_options"], "New nested key added"
    assert base["backend_options"]["docker"]["run"] == "docker exec $CMD"


def test_load_repro_file(tmp_path):
    """Load configuration from markdown repro file correctly."""
    markdown_content = """# Previous Run

## Initial runtime options
```json
{
  "experiment": "old_test",
  "timeout": 500,
  "verbose": true
}
```

## CSV field description
Other content here...
"""
    repro_file = tmp_path / "repro.md"
    repro_file.write_text(markdown_content)

    config = load_repro_file(str(repro_file))
    assert config["experiment"] == "old_test"
    assert config["timeout"] == 500
    assert config["verbose"] is True


# ========== Build Config From Sources Tests ==========

def test_build_config_from_repro_only(tmp_path):
    """Build config from repro file only."""
    markdown = """## Initial runtime options
```json
{"timeout": 400}
```
## CSV field description
"""
    repro_file = tmp_path / "repro.md"
    repro_file.write_text(markdown)

    args = MagicMock()
    args.repro = str(repro_file)
    args.config = None
    args.json = None

    config = build_config_from_sources(args)
    assert config["timeout"] == 400


def test_build_config_priority(tmp_path):
    """Config priority works correctly: repro < files < json < CLI."""
    # Create repro file
    markdown = """## Initial runtime options
```json
{"timeout": 100, "verbose": false, "copies": 1}
```
## CSV field description
"""
    repro_file = tmp_path / "repro.md"
    repro_file.write_text(markdown)

    # Create config file
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"timeout": 200, "verbose": True}))

    args = MagicMock()
    args.repro = str(repro_file)
    args.config = [str(config_file)]
    args.json = '{"timeout": 300}'

    config = build_config_from_sources(args)

    # JSON has highest priority
    assert config["timeout"] == 300, "JSON should override all other sources"
    # Config file overrides repro
    assert config["verbose"] is True, "Config file should override repro"
    # Repro provides base value
    assert config["copies"] == 1, "Repro should provide values not in higher priority sources"


# ========== Build Benchmark Spec Tests ==========

def test_build_benchmark_spec_basic():
    """Build basic benchmark spec correctly."""
    args = MagicMock()
    args.task = None
    args.benchmark = None  # No benchmark name, should default to experiment
    args.experiment = "test_exp"
    args.benchmark_args = ["arg1", "arg2"]

    benchmark_data = {
        "entry_point": "python3",
        "args": ["script.py"]
    }

    spec = build_benchmark_spec(args, benchmark_data, {})

    assert spec["task"] == "test_exp", "Task should default to experiment name"
    assert spec["entry_point"] == "python3"
    assert spec["args"] == ["script.py", "arg1", "arg2"], "Args should be appended"


def test_build_benchmark_spec_with_task():
    """Build benchmark spec with explicit task name."""
    args = MagicMock()
    args.task = "custom_task"
    args.experiment = "test_exp"
    args.benchmark_args = []

    benchmark_data = {
        "entry_point": "/bin/echo",
        "args": ["hello"]
    }

    # Task should be in config (added by build_config_from_sources)
    config = {"task": "custom_task"}

    spec = build_benchmark_spec(args, benchmark_data, config)

    assert spec["task"] == "custom_task", "Explicit task name should be used"
    assert spec["args"] == ["hello"]


def test_build_benchmark_spec_no_benchmark_args():
    """Build benchmark spec with no additional args."""
    args = MagicMock()
    args.task = "mytask"
    args.experiment = "exp"
    args.benchmark_args = None

    benchmark_data = {
        "entry_point": "node",
        "args": ["app.js"]
    }

    spec = build_benchmark_spec(args, benchmark_data, {})

    assert spec["args"] == ["app.js"], "Should use only benchmark args when no additional args"
