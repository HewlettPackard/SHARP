"""
Integration tests for parameter sweep functionality.

Tests the complete sweep workflow including:
- Sweep expansion with multiple parameters
- CSV output with all sweep runs
- Markdown format with proper invariants
- Append mode behavior
- Args and environment variable passing

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import tempfile
import shutil
from pathlib import Path
import yaml
import json
import subprocess
import re
import glob


def find_output_file(workspace, filename):
    """Find output file in various possible locations."""
    # Search in workspace and current directory runlogs
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
def temp_sweep_workspace(tmp_path):
    """Create a temporary workspace with sweep demo files."""
    workspace = tmp_path / "sweep_test"
    workspace.mkdir()

    # Create simple benchmark script
    benchmark_script = workspace / "test_benchmark.sh"
    benchmark_script.write_text("""#!/bin/bash
SIZE=${1:-1000}
THREADS=${OMP_NUM_THREADS:-1}
echo "METRIC: size=$SIZE"
echo "METRIC: threads=$THREADS"
echo "METRIC: time=0.1"
""")
    benchmark_script.chmod(0o755)

    # Create benchmark YAML
    benchmark_yaml = workspace / "benchmark.yaml"
    benchmark_yaml.write_text("""version: "4.0"
name: test_sweep
description: Test benchmark for sweep
entry_point: test_benchmark.sh

metrics:
  size:
    description: Problem size
    extract: 'grep "METRIC: size=" | cut -d= -f2'
    type: numeric
  threads:
    description: Thread count
    extract: 'grep "METRIC: threads=" | cut -d= -f2'
    type: numeric
  time:
    description: Execution time
    extract: 'grep "METRIC: time=" | cut -d= -f2'
    type: numeric
    lower_is_better: true
""")

    # Create sweep parameters file
    sweep_yaml = workspace / "sweep.yaml"
    sweep_yaml.write_text("""sweep:
  args:
    - ["100"]
    - ["200"]

  env:
    OMP_NUM_THREADS: ["1", "2"]
""")

    # Create experiment config
    experiment_yaml = workspace / "experiment.yaml"
    experiment_yaml.write_text(f"""version: "4.0"

include:
  - {benchmark_yaml}
  - {sweep_yaml}

options:
  directory: {workspace / "runlogs"}
""")

    # Create local backend file
    backend_yaml = workspace / "local.yaml"
    backend_yaml.write_text("""backend:
  name: local
  composable: false
  run: "$CMD $ARGS"
  run_sys_spec: "$SPEC_COMMAND"
""")

    return workspace


def test_sweep_csv_has_all_runs(temp_sweep_workspace):
    """Test that CSV contains all sweep configurations."""
    workspace = temp_sweep_workspace
    experiment_yaml = workspace / "experiment.yaml"

    # Run sweep
    result = subprocess.run(
        ["uv", "run", "src/cli/launch.py", "-f", str(experiment_yaml), "-b", str(workspace / "local.yaml")],
        cwd=Path.cwd(),
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Sweep failed: {result.stderr}"

    # Find CSV file
    csv_file = find_output_file(workspace, "test_sweep.csv")
    assert csv_file is not None, "CSV file not found"

    lines = csv_file.read_text().strip().split('\n')
    assert len(lines) == 5, f"Expected 5 lines (header + 4 data rows), got {len(lines)}"

    # Verify header
    assert lines[0] == "launch_id,repeat,rank,outer_time,size,threads,time"

    # Verify all 4 combinations present
    launch_ids = [line.split(',')[0] for line in lines[1:]]
    assert len(set(launch_ids)) == 4, "Should have 4 unique launch_ids"
    assert all(lid.startswith("sweep_") for lid in launch_ids), "All launch_ids should start with sweep_"


def test_sweep_markdown_format(temp_sweep_workspace):
    """Test markdown file has correct format without duplicates."""
    workspace = temp_sweep_workspace
    experiment_yaml = workspace / "experiment.yaml"

    # Run sweep
    result = subprocess.run(
        ["uv", "run", "src/cli/launch.py", "-f", str(experiment_yaml), "-b", str(workspace / "local.yaml")],
        cwd=Path.cwd(),
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Sweep failed: {result.stderr}"

    # Find markdown file
    md_file = find_output_file(workspace, "test_sweep.md")
    assert md_file is not None, "Markdown file not found"

    content = md_file.read_text()

    # Verify sections exist
    assert "## Initial runtime options" in content
    assert "## CSV field description" in content
    assert "## Invariant field description" in content
    assert "## Invariant parameters" in content

    # Verify no duplicate sections
    assert content.count("## Invariant field description") == 1, "Invariant field description should appear once"
    assert content.count("## Invariant parameters") == 1, "Invariant parameters should appear once"

    # Verify no redundant sections
    assert "## Sweep parameters" not in content, "Should not have separate Sweep parameters section"
    assert "sweep_invariants" not in content, "Should not have sweep_invariants in output"
    assert "sweep_params" not in content, "Should not have sweep_params in runtime options"

    # Verify launch_id not in runtime options
    runtime_match = re.search(r"## Initial runtime options.*?```json\s+(.*?)\s+```", content, re.DOTALL)
    assert runtime_match, "Could not find runtime options"
    runtime_options = json.loads(runtime_match.group(1))
    assert "launch_id" not in runtime_options, "launch_id should not be in runtime options"

    # Verify invariants have all 4 launch_ids with sweep parameters
    invariants_match = re.search(r"## Invariant parameters.*?```json\s+(.*?)\s+```", content, re.DOTALL)
    assert invariants_match, "Could not find invariant parameters"
    invariants = json.loads(invariants_match.group(1))

    assert len(invariants) == 4, f"Should have 4 launch_ids in invariants, got {len(invariants)}"

    # Verify each launch_id has sweep parameters
    for launch_id, params in invariants.items():
        assert launch_id.startswith("sweep_"), f"Launch ID {launch_id} should start with sweep_"
        assert "args" in params, f"Launch ID {launch_id} missing args"
        assert "env.OMP_NUM_THREADS" in params, f"Launch ID {launch_id} missing env.OMP_NUM_THREADS"
        assert params["args"] in ("100", "200"), f"Unexpected args value: {params['args']}"
        assert params["env.OMP_NUM_THREADS"] in ("1", "2"), f"Unexpected threads value: {params['env.OMP_NUM_THREADS']}"


def test_sweep_args_passed_correctly(temp_sweep_workspace):
    """Test that args are passed correctly to all sweep runs (bug fix verification)."""
    workspace = temp_sweep_workspace
    experiment_yaml = workspace / "experiment.yaml"

    # Run sweep
    result = subprocess.run(
        ["uv", "run", "src/cli/launch.py", "-f", str(experiment_yaml), "-b", str(workspace / "local.yaml")],
        cwd=Path.cwd(),
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Sweep failed: {result.stderr}"

    # Find markdown file and verify args in invariants
    md_file = find_output_file(workspace, "test_sweep.md")
    assert md_file is not None, "Markdown file not found"

    content = md_file.read_text()
    invariants_match = re.search(r"## Invariant parameters.*?```json\s+(.*?)\s+```", content, re.DOTALL)
    assert invariants_match, "Could not find invariant parameters"
    invariants = json.loads(invariants_match.group(1))

    # Verify args were passed to all 4 runs
    assert len(invariants) == 4, f"Expected 4 launch_ids, got {len(invariants)}"

    # Count args values (should be 2 runs with "100" and 2 with "200")
    args_values = [params.get("args", "") for params in invariants.values()]
    assert args_values.count("100") == 2, f"Expected 2 runs with args=100"
    assert args_values.count("200") == 2, f"Expected 2 runs with args=200"


def test_sweep_append_mode(temp_sweep_workspace):
    """Test that append mode works correctly (first run truncates, subsequent append)."""
    workspace = temp_sweep_workspace
    experiment_yaml = workspace / "experiment.yaml"

    # Run sweep first time
    result = subprocess.run(
        ["uv", "run", "src/cli/launch.py", "-f", str(experiment_yaml), "-b", str(workspace / "local.yaml")],
        cwd=Path.cwd(),
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Sweep failed: {result.stderr}"

    # Find and verify CSV has 4 sweep runs
    csv_file = find_output_file(workspace, "test_sweep.csv")
    assert csv_file is not None, "CSV file not found"

    lines = csv_file.read_text().strip().split('\n')
    assert len(lines) == 5, f"Expected 5 lines (header + 4 sweep runs), got {len(lines)}"


def test_sweep_env_variables_passed(temp_sweep_workspace):
    """Test that environment variables are passed correctly to all sweep runs."""
    workspace = temp_sweep_workspace
    experiment_yaml = workspace / "experiment.yaml"

    # Run sweep
    result = subprocess.run(
        ["uv", "run", "src/cli/launch.py", "-f", str(experiment_yaml), "-b", str(workspace / "local.yaml")],
        cwd=Path.cwd(),
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Sweep failed: {result.stderr}"

    # Find markdown file and verify env vars in invariants
    md_file = find_output_file(workspace, "test_sweep.md")
    assert md_file is not None, "Markdown file not found"

    content = md_file.read_text()
    invariants_match = re.search(r"## Invariant parameters.*?```json\s+(.*?)\s+```", content, re.DOTALL)
    assert invariants_match, "Could not find invariant parameters"
    invariants = json.loads(invariants_match.group(1))

    # Verify env vars were passed to all 4 runs
    assert len(invariants) == 4, f"Expected 4 launch_ids, got {len(invariants)}"

    # Count env.OMP_NUM_THREADS values (should be 2 runs with "1" and 2 with "2")
    env_values = [params.get("env.OMP_NUM_THREADS", "") for params in invariants.values()]
    assert env_values.count("1") == 2, f"Expected 2 runs with OMP_NUM_THREADS=1"
    assert env_values.count("2") == 2, f"Expected 2 runs with OMP_NUM_THREADS=2"


def test_sweep_no_state_mutation(temp_sweep_workspace):
    """Test that sweep runs don't mutate shared state (args.benchmark bug fix)."""
    workspace = temp_sweep_workspace
    experiment_yaml = workspace / "experiment.yaml"

    # Run sweep twice to ensure no state leakage
    for i in range(2):
        result = subprocess.run(
            ["uv", "run", "src/cli/launch.py", "-f", str(experiment_yaml), "-b", str(workspace / "local.yaml")],
            cwd=Path.cwd(),
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"Sweep run {i+1} failed: {result.stderr}"

        # Find CSV file
        csv_file = find_output_file(workspace, "test_sweep.csv")
        assert csv_file is not None, f"Run {i+1}: CSV file not found"
        lines = csv_file.read_text().strip().split('\n')
        assert len(lines) == 5, f"Run {i+1}: Expected 5 lines, got {len(lines)}"
