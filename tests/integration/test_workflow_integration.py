"""
Integration tests for workflow execution.

Tests the complete workflow functionality end-to-end.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import tempfile
from pathlib import Path
import subprocess


def test_workflow_basic_execution(tmp_path):
    """Test basic workflow execution with 3 tasks."""
    # Create 3 simple task configs
    for i in [1, 2, 3]:
        task_file = tmp_path / f"task{i}.yaml"
        task_file.write_text(f"""
options:
  task: sleep
  repeater: COUNT
  repeats: 2
include:
  - benchmarks/micro/cpu/benchmark.yaml
  - backends/local.yaml
backends:
  - local
""")

    # Create workflow file
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(f"""
version: 1.0.0
description: Integration test workflow
experiment: workflow_test
workflow:
  - include: task1.yaml
  - include: task2.yaml
  - include: task3.yaml
""")

    # Run workflow via launch.py
    result = subprocess.run(
        ["uv", "run", "launch", "-f", str(workflow_file)],
        cwd=Path(__file__).parent.parent.parent,
        capture_output=True,
        text=True
    )

    # Check it succeeded
    assert result.returncode == 0, f"Workflow failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


def test_workflow_with_experiment_field():
    """Test that experiment field from workflow config is used."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create task config without experiment field
        task_file = tmp_path / "task.yaml"
        task_file.write_text("""
options:
  task: sleep
  repeater: COUNT
  repeats: 1
include:
  - benchmarks/micro/cpu/benchmark.yaml
  - backends/local.yaml
backends:
  - local
""")

        # Create workflow with experiment field
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
experiment: my_workflow_exp
workflow:
  - include: task.yaml
""")

        # Run workflow
        result = subprocess.run(
            ["uv", "run", "launch", "-f", str(workflow_file)],
            cwd=Path(__file__).parent.parent.parent,
            capture_output=True,
            text=True
        )

        assert result.returncode == 0

        # Check that runlogs/my_workflow_exp directory was created
        runlogs_dir = Path(__file__).parent.parent.parent / "runlogs" / "my_workflow_exp"
        assert runlogs_dir.exists(), f"Expected runlogs/{runlogs_dir} directory"


def test_workflow_hybrid_composition(tmp_path):
    """Test workflow with hybrid composition: file includes + inline overrides."""
    # Create a base task config
    base_task = tmp_path / "base_task.yaml"
    base_task.write_text("""
options:
  task: sleep
  repeater: COUNT
  repeats: 5
include:
  - benchmarks/micro/cpu/benchmark.yaml
  - backends/local.yaml
backends:
  - local
""")

    # Create workflow that uses base task but overrides options
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(f"""
version: 1.0.0
description: Hybrid composition workflow
experiment: hybrid_test
workflow:
  - include: base_task.yaml
    options:
      repeats: 1
  - include: base_task.yaml
    task: sleep
    options:
      repeats: 2
  - task: sleep
    backends:
      - local
    options:
      repeater: COUNT
      repeats: 3
""")

    # Run workflow
    result = subprocess.run(
        ["uv", "run", "launch", "-f", str(workflow_file)],
        cwd=Path(__file__).parent.parent.parent,
        capture_output=True,
        text=True
    )

    # Check it succeeded
    assert result.returncode == 0, f"Workflow failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

    # Verify runlogs directory was created
    runlogs_dir = Path(__file__).parent.parent.parent / "runlogs" / "hybrid_test"
    assert runlogs_dir.exists(), f"Expected runlogs/hybrid_test directory"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
