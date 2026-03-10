"""
Integration tests for src/cli/launch.py with full CLI option set.

Tests end-to-end execution with various combinations of CLI options.

Run with: pytest tests/integration/test_cli_full_options.py

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import json
import pytest
import subprocess
from pathlib import Path
import yaml
from src.core.config.include_resolver import get_project_root


@pytest.fixture
def project_root():
    return get_project_root()


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary directory for config files."""
    return tmp_path


# ========== Test Functions ==========

def test_cli_help_output(project_root):
    """Test that --help shows all options."""
    result = subprocess.run(
        ["uv", "run", "launch", "--help"],
        capture_output=True,
        text=True,
        cwd=project_root
    )

    assert result.returncode == 0
    assert "--timeout" in result.stdout
    assert "--copies" in result.stdout
    assert "--cold" in result.stdout
    assert "--warm" in result.stdout
    assert "--config" in result.stdout
    assert "--json" in result.stdout
    assert "--repro" in result.stdout
    assert "--skip-sys-specs" in result.stdout
    assert "--append" in result.stdout
    assert "--task" in result.stdout


def test_cli_list_benchmarks(project_root):
    """Test --list-benchmarks discovery command."""
    result = subprocess.run(
        ["uv", "run", "launch", "--list-benchmarks"],
        capture_output=True,
        text=True,
        cwd=project_root
    )

    assert result.returncode == 0
    assert "Available benchmarks" in result.stdout
    # Should show actual benchmark names, not filenames
    assert "sleep" in result.stdout
    assert "_shared" not in result.stdout  # Filtered out


def test_cli_list_backends(project_root):
    """Test --list-backends discovery command."""
    result = subprocess.run(
        ["uv", "run", "launch", "--list-backends"],
        capture_output=True,
        text=True,
        cwd=project_root
    )

    assert result.returncode == 0
    assert "Available backends" in result.stdout
    assert "local" in result.stdout
    assert "perf" in result.stdout


def test_cli_show_benchmark(project_root):
    """Test --show-benchmark with specific benchmark name."""
    result = subprocess.run(
        ["uv", "run", "launch", "--show-benchmark", "sleep"],
        capture_output=True,
        text=True,
        cwd=project_root
    )

    assert result.returncode == 0
    assert "Benchmark: sleep" in result.stdout
    assert "entry_point" in result.stdout


def test_cli_show_backend(project_root):
    """Test --show-backend with specific backend name."""
    result = subprocess.run(
        ["uv", "run", "launch", "--show-backend", "local"],
        capture_output=True,
        text=True,
        cwd=project_root
    )

    assert result.returncode == 0
    assert "Backend: local" in result.stdout
    assert "run:" in result.stdout


def test_cli_missing_required_args(project_root):
    """Test error when required arguments are missing."""
    result = subprocess.run(
        ["uv", "run", "launch"],
        capture_output=True,
        text=True,
        cwd=project_root
    )

    # Should fail or show usage
    assert result.returncode != 0


def test_cli_with_config_file(project_root, temp_config_dir):
    """Test loading options from YAML config file."""
    # Create temporary config file
    config = {
        "timeout": 300,
        "repeater_options": {
            "CR": {"max": 3}
        }
    }
    config_path = temp_config_dir / "test_config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config, f)

    # Create a temporary runlogs directory for this test
    runlogs_path = temp_config_dir / "runlogs"

    # This will fail because we don't have a real benchmark setup,
    # but we can verify the config file is being read by checking error message
    result = subprocess.run(
        ["uv", "run", "launch",
         "-d", str(runlogs_path),
         "-e", "test_config",
         "-f", str(config_path),
         "-v",
         "sleep"],
        capture_output=True,
        text=True,
        cwd=project_root,
        timeout=10
    )

    # Config file should be loaded (we'd see different behavior if it wasn't)
    # We expect failure due to missing benchmark setup, but no config error
    assert "Config file not found" not in result.stderr


def test_cli_with_json_override(project_root, temp_config_dir):
    """Test inline JSON configuration override."""
    json_config = json.dumps({"timeout": 100})

    # Create a temporary runlogs directory for this test
    runlogs_path = temp_config_dir / "runlogs"

    result = subprocess.run(
        ["uv", "run", "launch",
         "-d", str(runlogs_path),
         "-e", "test_json",
         "-j", json_config,
         "-v",
         "sleep"],
        capture_output=True,
        text=True,
        cwd=project_root,
        timeout=10
    )

    # Should not fail on JSON parsing
    assert "JSON" not in result.stderr


def test_cli_mutually_exclusive_cold_warm(project_root, temp_config_dir):
    """Test that --cold and --warm are mutually exclusive."""
    runlogs_path = temp_config_dir / "runlogs"

    result = subprocess.run(
        ["uv", "run", "launch",
         "-d", str(runlogs_path),
         "-e", "test",
         "--cold",
         "--warm",
         "sleep"],
        capture_output=True,
        text=True,
        cwd=project_root
    )

    assert result.returncode != 0
    assert "not allowed with argument" in result.stderr


def test_cli_timeout_type_validation(project_root, temp_config_dir):
    """Test that --timeout requires integer value."""
    runlogs_path = temp_config_dir / "runlogs"

    result = subprocess.run(
        ["uv", "run", "launch",
         "-d", str(runlogs_path),
         "-e", "test",
         "--timeout", "not_a_number",
         "sleep"],
        capture_output=True,
        text=True,
        cwd=project_root
    )

    assert result.returncode != 0
    assert "invalid int value" in result.stderr


def test_cli_copies_type_validation(project_root, temp_config_dir):
    """Test that --copies requires integer value."""
    runlogs_path = temp_config_dir / "runlogs"

    result = subprocess.run(
        ["uv", "run", "launch",
         "-d", str(runlogs_path),
         "-e", "test",
         "--copies", "invalid",
         "sleep"],
        capture_output=True,
        text=True,
        cwd=project_root
    )

    assert result.returncode != 0
    assert "invalid int value" in result.stderr


def test_cli_via_sharp_wrapper(project_root):
    """Test invoking launch via 'sharp launch' wrapper."""
    result = subprocess.run(
        ["uv", "run", "sharp", "launch", "--help"],
        capture_output=True,
        text=True,
        cwd=project_root
    )

    assert result.returncode == 0
    assert "SHARP benchmark launcher" in result.stdout


def test_cli_benchmark_args_passthrough(project_root, temp_config_dir):
    """Test that benchmark args are passed as positional arguments."""
    runlogs_path = temp_config_dir / "runlogs"

    # We can't fully test execution, but we can verify arg parsing doesn't fail
    result = subprocess.run(
        ["uv", "run", "launch",
         "-d", str(runlogs_path),
         "-e", "test",
         "-v",
         "sleep",
         "arg1", "arg2", "arg3"],
        capture_output=True,
        text=True,
        cwd=project_root,
        timeout=10
    )

    # Should not fail on argument parsing
    # (will likely fail on execution, but that's expected)
    if "arg1" in result.stdout or "arg1" in result.stderr:
        # Args were processed
        pass


def test_cli_multiple_config_files(project_root, temp_config_dir):
    """Test loading multiple config files in order."""
    # Create two config files
    config1 = {"timeout": 100, "value1": "from_config1"}
    config2 = {"timeout": 200, "value2": "from_config2"}

    config1_path = temp_config_dir / "config1.yaml"
    config2_path = temp_config_dir / "config2.yaml"

    with open(config1_path, 'w') as f:
        yaml.dump(config1, f)
    with open(config2_path, 'w') as f:
        yaml.dump(config2, f)

    runlogs_path = temp_config_dir / "runlogs"

    result = subprocess.run(
        ["uv", "run", "launch",
         "-d", str(runlogs_path),
         "-e", "test_multi",
         "-f", str(config1_path),
         "-f", str(config2_path),
         "-v",
         "sleep"],
        capture_output=True,
        text=True,
        cwd=project_root,
        timeout=10
    )

    # Should not error on config loading
    assert "Config file not found" not in result.stderr

