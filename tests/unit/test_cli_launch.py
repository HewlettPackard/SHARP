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
    build_orchestrator_options,
    run_experiment,
)


# ========== Argument Parsing Tests ==========

def test_parse_minimal_args():
    """Parse minimal required arguments with defaults."""
    args = parse_args(["-e", "test", "sleep"])
    assert args.experiment == "test"
    assert args.benchmark == "sleep"
    assert args.backend == ["local"], "Should default to local backend"
    assert args.repeater is None, "Repeater should default to None (resolved later)"
    assert args.verbose is False


def test_parse_multiple_backends():
    """Parse multiple backend options correctly."""
    args = parse_args(["-e", "test", "-b", "perf", "-b", "local", "sleep"])
    assert args.backend == ["perf", "local"]


def test_parse_task_option():
    """Parse --task option correctly."""
    args = parse_args(["-e", "test", "-t", "mytask", "sleep"])
    assert args.task == "mytask"


def test_parse_timeout_option():
    """Parse --timeout option correctly."""
    args = parse_args(["-e", "test", "--timeout", "600", "sleep"])
    assert args.timeout == 600


def test_parse_copies_option():
    """Parse --copies option correctly."""
    args = parse_args(["-e", "test", "--copies", "4", "sleep"])
    assert args.copies == 4


def test_parse_mpl_alias():
    """Parse --mpl as alias for --copies."""
    args = parse_args(["-e", "test", "--mpl", "8", "sleep"])
    assert args.copies == 8, "--mpl should be alias for --copies"


def test_parse_cold_start():
    """Parse --cold flag correctly."""
    args = parse_args(["-e", "test", "--cold", "sleep"])
    assert args.cold is True
    assert args.warm is False


def test_parse_warm_start():
    """Parse --warm flag correctly."""
    args = parse_args(["-e", "test", "--warm", "sleep"])
    assert args.warm is True
    assert args.cold is False


def test_parse_directory_option():
    """Parse --directory option correctly."""
    args = parse_args(["-e", "test", "-d", "/tmp/output", "sleep"])
    assert args.directory == "/tmp/output"


def test_parse_append_flag():
    """Parse --append flag correctly."""
    args = parse_args(["-e", "test", "--append", "sleep"])
    assert args.append is True


def test_parse_skip_sys_specs_flag():
    """Parse --skip-sys-specs flag correctly."""
    args = parse_args(["-e", "test", "--skip-sys-specs", "sleep"])
    assert args.skip_sys_specs is True


def test_parse_verbose_flag():
    """Parse --verbose flag correctly."""
    args = parse_args(["-e", "test", "-v", "sleep"])
    assert args.verbose is True


def test_parse_config_files():
    """Parse --config option (can specify multiple)."""
    args = parse_args([
        "-e", "test",
        "-f", "config1.yaml",
        "-f", "config2.json",
        "sleep"
    ])
    assert args.config == ["config1.yaml", "config2.json"]


def test_parse_json_option():
    """Parse --json option correctly."""
    json_str = '{"timeout": 300}'
    args = parse_args(["-e", "test", "-j", json_str, "sleep"])
    assert args.json == json_str


def test_parse_repro_option():
    """Parse --repro option correctly."""
    args = parse_args(["-e", "test", "--repro", "old_run.md", "sleep"])
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

## Runtime options
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
    markdown = """## Runtime options
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
    markdown = """## Runtime options
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
    """Build basic benchmark spec correctly - CLI args replace YAML args."""
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
    assert spec["args"] == ["arg1", "arg2"], "CLI args should replace YAML args"


def test_build_benchmark_spec_with_task():
    """Build benchmark spec with explicit task name - empty CLI args use YAML defaults."""
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
    assert spec["args"] == ["hello"], "Empty CLI args should use YAML defaults"


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


# ========== build_orchestrator_options Tests ==========

def _make_minimal_args(copies=None):
    args = MagicMock()
    args.backend = ["local"]
    args.timeout = None
    args.verbose = False
    args.directory = None
    args.cold = False
    args.warm = False
    args.skip_sys_specs = False
    args.benchmark = "micro/sleep"
    args.copies = copies
    args.append = False
    return args


@pytest.mark.parametrize(
    "cli_value, config_value, expected",
    [
        (3, None, 3),
        (None, 4, 4),
    ],
)
def test_build_orchestrator_options_mpl_resolution(cli_value, config_value, expected, monkeypatch):
    """MPL should honor CLI override and fallback to config when absent."""
    args = _make_minimal_args(copies=cli_value)

    def fake_loader(_):
        return ({"entry_point": "/bin/echo", "args": []}, {})

    def fake_resolve_path(name):
        return {"entry_point": "/bin/echo", "args": []}

    def fake_get_benchmark_names():
        return {}

    monkeypatch.setattr("src.cli.launch.load_benchmark_data", fake_loader)
    monkeypatch.setattr("src.cli.launch._resolve_benchmark_path", fake_resolve_path)
    monkeypatch.setattr("src.cli.discovery.get_benchmark_names", fake_get_benchmark_names)
    monkeypatch.setattr("src.cli.launch.load_backend_options", lambda *args, **kwargs: {})

    config = {"copies": config_value} if config_value is not None else {}
    options, _ = build_orchestrator_options(args, config)

    assert options["mpl"] == expected


def test_build_orchestrator_options_directory_priority(monkeypatch):
    """CLI directory should override config directory."""
    args = _make_minimal_args()
    args.directory = "/cli/output"

    def fake_loader(_):
        return ({"entry_point": "/bin/echo", "args": []}, {})

    def fake_resolve_path(name):
        return {"entry_point": "/bin/echo", "args": []}

    def fake_get_benchmark_names():
        return {}

    monkeypatch.setattr("src.cli.launch.load_benchmark_data", fake_loader)
    monkeypatch.setattr("src.cli.launch._resolve_benchmark_path", fake_resolve_path)
    monkeypatch.setattr("src.cli.discovery.get_benchmark_names", fake_get_benchmark_names)
    monkeypatch.setattr("src.cli.launch.load_backend_options", lambda *args, **kwargs: {})

    config = {"directory": "/config/output"}
    options, _ = build_orchestrator_options(args, config)

    assert options["directory"] == "/cli/output"


def test_build_orchestrator_options_directory_fallback(monkeypatch):
    """Config directory should be used when CLI option is absent."""
    args = _make_minimal_args()

    def fake_loader(_):
        return ({"entry_point": "/bin/echo", "args": []}, {})

    def fake_resolve_path(name):
        return {"entry_point": "/bin/echo", "args": []}

    def fake_get_benchmark_names():
        return {}

    monkeypatch.setattr("src.cli.launch.load_benchmark_data", fake_loader)
    monkeypatch.setattr("src.cli.launch._resolve_benchmark_path", fake_resolve_path)
    monkeypatch.setattr("src.cli.discovery.get_benchmark_names", fake_get_benchmark_names)
    monkeypatch.setattr("src.cli.launch.load_backend_options", lambda *args, **kwargs: {})

    config = {"directory": "/config/output"}
    options, _ = build_orchestrator_options(args, config)

    assert options["directory"] == "/config/output"


def test_build_orchestrator_options_skip_sys_specs_fallback(monkeypatch):
    """Config skip_sys_specs should apply when CLI flag not set."""
    args = _make_minimal_args()
    args.skip_sys_specs = False

    def fake_loader(_):
        return ({"entry_point": "/bin/echo", "args": []}, {})

    def fake_resolve_path(name):
        return {"entry_point": "/bin/echo", "args": []}

    def fake_get_benchmark_names():
        return {}

    monkeypatch.setattr("src.cli.launch.load_benchmark_data", fake_loader)
    monkeypatch.setattr("src.cli.launch._resolve_benchmark_path", fake_resolve_path)
    monkeypatch.setattr("src.cli.discovery.get_benchmark_names", fake_get_benchmark_names)
    monkeypatch.setattr("src.cli.launch.load_backend_options", lambda *args, **kwargs: {})

    config = {"skip_sys_specs": True}
    options, _ = build_orchestrator_options(args, config)

    assert options["skip_sys_specs"] is True


def test_build_orchestrator_options_append_mode(monkeypatch):
    """CLI --append flag should force append mode regardless of config."""
    args = _make_minimal_args()
    args.append = True

    def fake_resolve_path(name):
        return {"entry_point": "/bin/echo", "args": []}

    def fake_get_benchmark_names():
        return {}

    monkeypatch.setattr("src.cli.launch._resolve_benchmark_path", fake_resolve_path)
    monkeypatch.setattr("src.cli.discovery.get_benchmark_names", fake_get_benchmark_names)

    def fake_backend_loader(backends, config):
        return {}

    def fake_benchmark_loader(_):
        return ({"entry_point": "/bin/echo", "args": []}, {})

    monkeypatch.setattr("src.cli.launch.load_backend_options", fake_backend_loader)
    monkeypatch.setattr("src.cli.launch.load_benchmark_data", fake_benchmark_loader)

    config = {"mode": "w"}
    options, _ = build_orchestrator_options(args, config)

    assert options["mode"] == "a"


def test_build_orchestrator_options_benchmark_absolute_path(monkeypatch):
    """Absolute path benchmark should resolve via filesystem/PATH, not YAML lookup."""
    args = _make_minimal_args()
    args.benchmark = "/bin/ls"

    def fake_backend_loader(backends, config):
        return {}

    def fake_resolve_path(name):
        # Simulates finding /bin/ls in filesystem
        return {"entry_point": "/bin/ls", "args": []}

    def fake_get_benchmark_names():
        return {}  # /bin/ls is not in YAML discovery

    monkeypatch.setattr("src.cli.launch.load_backend_options", fake_backend_loader)
    monkeypatch.setattr("src.cli.launch._resolve_benchmark_path", fake_resolve_path)
    monkeypatch.setattr("src.cli.discovery.get_benchmark_names", fake_get_benchmark_names)

    config = {}
    options, benchmark_data = build_orchestrator_options(args, config)

    assert benchmark_data["entry_point"] == "/bin/ls", "Absolute path should be used as-is"
    assert benchmark_data["args"] == [], "No args should be added for path-based benchmarks"
    assert options["metrics"] == {}, "No metrics for path-based benchmarks"


def test_build_orchestrator_options_benchmark_relative_path(monkeypatch):
    """Relative path benchmark should resolve via filesystem/PATH, not YAML lookup."""
    args = _make_minimal_args()
    args.benchmark = "../../bench"

    def fake_backend_loader(backends, config):
        return {}

    def fake_resolve_path(name):
        # Simulates finding ../../bench in filesystem and resolving to absolute path
        return {"entry_point": "/absolute/path/to/bench", "args": []}

    def fake_get_benchmark_names():
        return {}  # Relative path is not in YAML discovery

    monkeypatch.setattr("src.cli.launch.load_backend_options", fake_backend_loader)
    monkeypatch.setattr("src.cli.launch._resolve_benchmark_path", fake_resolve_path)
    monkeypatch.setattr("src.cli.discovery.get_benchmark_names", fake_get_benchmark_names)

    config = {}
    options, benchmark_data = build_orchestrator_options(args, config)

    assert benchmark_data["entry_point"] == "/absolute/path/to/bench", "Relative path should resolve to absolute"
    assert benchmark_data["args"] == [], "No args should be added for path-based benchmarks"


def test_build_orchestrator_options_benchmark_yaml_name(monkeypatch):
    """Benchmark name found in YAML discovery should use YAML spec (priority 1)."""
    args = _make_minimal_args()
    args.benchmark = "sleep"

    def fake_backend_loader(backends, config):
        return {}

    yaml_called = {"called": False}

    def fake_benchmark_loader(name):
        yaml_called["called"] = True
        assert name == "sleep", "YAML loader should receive benchmark name"
        return ({"entry_point": "./sleep.py", "args": []}, {"inner_time": {}})

    def fake_resolve_path(name):
        # Simulates priority 1: found in YAML discovery
        yaml_called["called"] = True
        return {"entry_point": "./sleep.py", "args": []}

    def fake_get_benchmark_names():
        return {"sleep": Path("benchmarks/micro/cpu/sleep.yaml")}

    monkeypatch.setattr("src.cli.launch.load_backend_options", fake_backend_loader)
    monkeypatch.setattr("src.cli.launch.load_benchmark_data", fake_benchmark_loader)
    monkeypatch.setattr("src.cli.launch._resolve_benchmark_path", fake_resolve_path)
    monkeypatch.setattr("src.cli.discovery.get_benchmark_names", fake_get_benchmark_names)

    config = {}
    options, benchmark_data = build_orchestrator_options(args, config)

    assert yaml_called["called"], "YAML loader should be called for benchmark names in discovery"
    assert benchmark_data["entry_point"] == "./sleep.py"
    assert options["metrics"] == {"inner_time": {}}, "Metrics from YAML should be loaded"


def test_build_orchestrator_options_benchmark_path_resolution(monkeypatch):
    """Benchmark not in YAML should be found via $PATH (priority 3)."""
    args = _make_minimal_args()
    args.benchmark = "python3"

    def fake_backend_loader(backends, config):
        return {}

    def fake_resolve_path(name):
        # Simulates priority 3: found in $PATH
        return {"entry_point": "/usr/bin/python3", "args": []}

    def fake_get_benchmark_names():
        return {}  # python3 is not in YAML discovery

    monkeypatch.setattr("src.cli.launch.load_backend_options", fake_backend_loader)
    monkeypatch.setattr("src.cli.launch._resolve_benchmark_path", fake_resolve_path)
    monkeypatch.setattr("src.cli.discovery.get_benchmark_names", fake_get_benchmark_names)

    config = {}
    options, benchmark_data = build_orchestrator_options(args, config)

    assert benchmark_data["entry_point"] == "/usr/bin/python3", "$PATH resolution should work"
    assert benchmark_data["args"] == [], "No args for PATH-resolved benchmarks"
    assert options["metrics"] == {}, "No metrics for PATH-resolved benchmarks"


def test_build_orchestrator_options_benchmark_not_found(monkeypatch):
    """Benchmark not found anywhere should raise ValueError (priority 4)."""
    args = _make_minimal_args()
    args.benchmark = "nonexistent_benchmark_12345"

    def fake_backend_loader(backends, config):
        return {}

    def fake_resolve_path(name):
        # Simulates priority 4: not found (empty dict)
        return {}

    def fake_get_benchmark_names():
        return {}

    monkeypatch.setattr("src.cli.launch.load_backend_options", fake_backend_loader)
    monkeypatch.setattr("src.cli.launch._resolve_benchmark_path", fake_resolve_path)
    monkeypatch.setattr("src.cli.discovery.get_benchmark_names", fake_get_benchmark_names)

    config = {}

    with pytest.raises(ValueError, match="not found in YAML discovery, filesystem, or \\$PATH"):
        build_orchestrator_options(args, config)


def _setup_run_experiment_stubs(monkeypatch, captured_options):
    class DummyOrchestrator:
        def __init__(self, options, experiment_name):
            captured_options.update(options)

        def run(self, callbacks):
            class Result:
                success = True
                iteration_count = 0
                metrics = []

            return Result()

    monkeypatch.setattr("src.cli.launch.ExecutionOrchestrator", DummyOrchestrator)
    monkeypatch.setattr("src.cli.launch.print_experiment_info", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.cli.launch.create_progress_callbacks", lambda verbose: object())
    monkeypatch.setattr("src.cli.launch.print_experiment_result", lambda result, verbose: 0)


def test_run_experiment_repeater_uses_config(monkeypatch):
    """Config repeater should apply when CLI flag is omitted."""
    args = parse_args(["-e", "test", "sleep"])
    args.repeater = None

    config = {"repeater": "count"}  # Fixed: was "repeats", should be "repeater"
    monkeypatch.setattr("src.cli.launch.build_config_from_sources", lambda _args: config)
    monkeypatch.setattr("src.cli.launch.resolve_benchmark_spec",
                        lambda _args, _config: {"entry_point": "/bin/echo", "args": [], "task": "sleep"})
    monkeypatch.setattr("src.cli.launch.build_orchestrator_options",
                        lambda _args, _config: ({"backend_names": ["local"], "backend_options": {}}, {}))

    captured = {}
    _setup_run_experiment_stubs(monkeypatch, captured)

    exit_code = run_experiment(args)

    assert exit_code == 0
    assert captured["repeats"] == "COUNT"


def test_run_experiment_repeater_cli_override(monkeypatch):
    """CLI repeater should override config when provided."""
    args = parse_args(["-e", "test", "sleep"])  # Default repeater None
    args.repeater = "ci"

    config = {"repeater": "count"}  # Fixed: was "repeats", should be "repeater"
    monkeypatch.setattr("src.cli.launch.build_config_from_sources", lambda _args: config)
    monkeypatch.setattr("src.cli.launch.resolve_benchmark_spec",
                        lambda _args, _config: {"entry_point": "/bin/echo", "args": [], "task": "sleep"})
    monkeypatch.setattr("src.cli.launch.build_orchestrator_options",
                        lambda _args, _config: ({"backend_names": ["local"], "backend_options": {}}, {}))

    captured = {}
    _setup_run_experiment_stubs(monkeypatch, captured)

    exit_code = run_experiment(args)

    assert exit_code == 0
    assert captured["repeats"] == "CI"
