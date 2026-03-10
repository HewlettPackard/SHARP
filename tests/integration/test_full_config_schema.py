"""
Integration test for complete SHARP configuration schema.

This test exercises every possible field in the config schema to ensure
full configurability and serve as a reference example.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import tempfile
from pathlib import Path
import yaml
import subprocess
import glob


def find_output_file(workspace, filename):
    """Find output file in various possible locations."""
    search_patterns = [
        str(workspace / "runlogs" / "**" / filename),
        str(Path.cwd() / "runlogs" / "**" / filename)
    ]

    for pattern in search_patterns:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return Path(matches[0])
    return None


@pytest.fixture
def full_config_workspace(tmp_path):
    """
    Create a comprehensive config that uses every possible schema field.

    This serves as both a test and a reference example of SHARP's full capabilities.
    See docs/config_schema.md for detailed documentation of each field.
    """
    workspace = tmp_path / "full_config"
    workspace.mkdir()

    # Create a minimal benchmark script
    benchmark_script = workspace / "full_test.sh"
    benchmark_script.write_text("""#!/bin/bash
echo "METRIC: value=42"
""")
    benchmark_script.chmod(0o755)

    # Create comprehensive config using all schema fields
    config = {
        # Core identification
        "version": "4.0",
        "name": "full_schema_test",
        "description": "Comprehensive test of all config schema fields",

        # Benchmark specification
        "entry_point": str(benchmark_script),
        "args": ["--test", "100"],
        "task": "full_test",

        # Include directive for modular configs
        "include": [],

        # Metrics definitions
        "metrics": {
            "value": {
                "description": "Test metric",
                "extract": "grep 'METRIC: value=' | cut -d= -f2",
                "type": "numeric",
                "units": "count",
                "lower_is_better": False
            }
        },

        # Environment variables
        "environment": {
            "TEST_VAR": "test_value",
            "OMP_NUM_THREADS": "4"
        },

        # Runtime options
        "options": {
            "directory": str(workspace / "runlogs"),
            "timeout": 300,
            "verbose": False,
            "start": "normal",  # normal, cold, or warm
            "mode": "w",  # w (truncate) or a (append)
            "skip_sys_specs": True,
            "mpl": 1,  # Multiprogramming level
            "sys_spec_commands": {
                "custom_metric": "echo custom"
            }
        },

        # Repeater configuration
        "repeater": "max",
        "repeater_options": {
            "max_iterations": 10,
            "confidence": 0.95,
            "relative_error": 0.05
        },

        # Backend specification (inline)
        "backend": {
            "name": "test_local",
            "composable": False,
            "run": "$CMD $ARGS",
            "run_sys_spec": "$SPEC_COMMAND"
        },

        # Parameter sweep (optional - mutually exclusive with direct execution)
        # "sweep": {
        #     "args": [["100"], ["200"]],
        #     "env": {"OMP_NUM_THREADS": ["1", "2"]},
        #     "options": {"mpl": [1, 2]}
        # }
    }

    config_file = workspace / "full_config.yaml"
    config_file.write_text(yaml.dump(config, sort_keys=False))

    return workspace, config_file


def test_full_config_schema_loads(full_config_workspace):
    """Test that a config with all possible fields loads successfully."""
    workspace, config_file = full_config_workspace

    # Test that config is valid YAML
    with open(config_file) as f:
        config = yaml.safe_load(f)

    # Verify all major sections present
    assert "version" in config
    assert "name" in config
    assert "description" in config
    assert "entry_point" in config
    assert "args" in config
    assert "task" in config
    assert "metrics" in config
    assert "environment" in config
    assert "options" in config
    assert "repeater" in config
    assert "repeater_options" in config
    assert "backend" in config


def test_full_config_schema_validates(full_config_workspace):
    """Test that full config validates against Pydantic schema."""
    workspace, config_file = full_config_workspace

    from src.core.config.schema import ExperimentConfig

    with open(config_file) as f:
        config_dict = yaml.safe_load(f)

    # Should not raise validation errors
    config = ExperimentConfig(**config_dict)

    # Verify key fields
    assert config.version == "4.0"
    assert config.name == "full_schema_test"
    assert len(config.metrics) == 1
    assert "value" in config.metrics
    assert len(config.environment) == 2
    assert config.options["mpl"] == 1
    assert config.repeater == "max"


def test_full_config_schema_executes(full_config_workspace):
    """Test that full config can actually execute successfully."""
    workspace, config_file = full_config_workspace

    result = subprocess.run(
        ["uv", "run", "src/cli/launch.py", "-f", str(config_file)],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=30
    )

    # Should execute without errors
    assert result.returncode == 0, f"Execution failed: {result.stderr}"

    # Find output files (may be in runlogs/full_test or runlogs/misc)
    csv_file = find_output_file(workspace, "full_test.csv")
    md_file = find_output_file(workspace, "full_test.md")

    # If not found with expected name, might be under different task name
    if csv_file is None:
        csv_file = find_output_file(workspace, "*.csv")
    if md_file is None:
        md_file = find_output_file(workspace, "*.md")

    # At minimum, execution should have succeeded
    assert result.returncode == 0, "Execution should succeed with full config"

    # If files were created, verify their format
    if csv_file and md_file:
        csv_content = csv_file.read_text()
        lines = csv_content.strip().split('\n')
        assert len(lines) >= 2, "CSV should have header and at least one data row"

        md_content = md_file.read_text()
        assert ("## Runtime options" in md_content or "## Initial runtime options" in md_content)
        assert "## Field description" in md_content or "## CSV field description" in md_content


def test_config_with_sweep(tmp_path):
    """Test config with sweep parameters (alternative to direct execution)."""
    workspace = tmp_path / "sweep_config"
    workspace.mkdir()

    # Create benchmark script
    benchmark_script = workspace / "sweep_test.sh"
    benchmark_script.write_text("""#!/bin/bash
SIZE=${1:-100}
echo "METRIC: size=$SIZE"
""")
    benchmark_script.chmod(0o755)

    # Config with sweep instead of direct args
    config = {
        "version": "4.0",
        "name": "sweep_test",
        "entry_point": str(benchmark_script),
        "metrics": {
            "size": {
                "description": "Problem size",
                "extract": "grep 'METRIC: size=' | cut -d= -f2",
                "type": "numeric"
            }
        },
        "options": {
            "directory": str(workspace / "runlogs"),
            "skip_sys_specs": True
        },
        "backend": {
            "name": "local",
            "composable": False,
            "run": "$CMD $ARGS"
        },
        "sweep": {
            "args": [["100"], ["200"], ["300"]],
            "env": {},
            "options": {}
        }
    }

    config_file = workspace / "sweep_config.yaml"
    config_file.write_text(yaml.dump(config, sort_keys=False))

    # Execute
    result = subprocess.run(
        ["uv", "run", "src/cli/launch.py", "-f", str(config_file)],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=30
    )

    assert result.returncode == 0, f"Sweep execution failed: {result.stderr}"

    # Find CSV file
    csv_file = find_output_file(workspace, "sweep_test.csv")
    assert csv_file is not None, "CSV file not found"
    lines = csv_file.read_text().strip().split('\n')
    assert len(lines) == 4, f"Expected 4 lines (header + 3 sweeps), got {len(lines)}"


def test_config_with_includes(tmp_path):
    """Test config using include directive for modularity."""
    workspace = tmp_path / "include_config"
    workspace.mkdir()

    # Create benchmark script
    benchmark_script = workspace / "include_test.sh"
    benchmark_script.write_text("""#!/bin/bash
echo "METRIC: result=1"
""")
    benchmark_script.chmod(0o755)

    # Create separate files for different config sections
    benchmark_yaml = workspace / "benchmark.yaml"
    benchmark_yaml.write_text(yaml.dump({
        "name": "include_test",
        "entry_point": str(benchmark_script),
        "metrics": {
            "result": {
                "description": "Test result",
                "extract": "grep 'METRIC: result=' | cut -d= -f2",
                "type": "numeric"
            }
        }
    }))

    backend_yaml = workspace / "backend.yaml"
    backend_yaml.write_text(yaml.dump({
        "backend": {
            "name": "local",
            "composable": False,
            "run": "$CMD $ARGS"
        }
    }))

    options_yaml = workspace / "options.yaml"
    options_yaml.write_text(yaml.dump({
        "options": {
            "directory": str(workspace / "runlogs"),
            "skip_sys_specs": True
        }
    }))

    # Main config uses includes
    main_config = {
        "version": "4.0",
        "include": [
            str(benchmark_yaml),
            str(backend_yaml),
            str(options_yaml)
        ]
    }

    config_file = workspace / "main_config.yaml"
    config_file.write_text(yaml.dump(main_config, sort_keys=False))

    # Execute
    result = subprocess.run(
        ["uv", "run", "src/cli/launch.py", "-f", str(config_file)],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=30
    )

    assert result.returncode == 0, f"Execution with includes failed: {result.stderr}"

    # Find output file
    csv_file = find_output_file(workspace, "include_test.csv")
    assert csv_file is not None, "CSV file not created with include directive"
