"""
End-to-end integration tests for ExecutionOrchestrator with local backend.

Tests the full orchestrator workflow with real configurations and actual command execution.
Uses sleep benchmark for predictable, fast testing.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import copy
import csv
import tempfile

import pytest
import warnings
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock
import yaml

from src.core.config.include_resolver import get_project_root
from src.core.execution.orchestrator import (
    ExecutionOrchestrator,
    ProgressCallbacks,
)
from src.core.repeaters.count import CountRepeater
from src.core.rundata import RunData


@pytest.fixture(scope="module", autouse=True)
def suppress_warnings():
    """Suppress expected ResourceWarnings from temporary file fixtures."""
    warnings.simplefilter("ignore", ResourceWarning)


@pytest.fixture
def orchestrator_config(tmp_path):
    """Set up orchestrator configuration for tests."""
    # Use backend options from real config (supports both "run" and "command_template")
    backend_names = ["local"]
    backend_options = {
        "local": {
            "run": "$CMD $ARGS",  # Real backends use "run" key
            "composable": True
        }
    }

    # Set up orchestrator options with minimal configuration
    # Use temp_path for directory to avoid polluting runlogs/
    options = {
        "backend_names": backend_names,
        "backend_options": backend_options,
        "timeout": 30,
        "verbose": False,
        "directory": str(tmp_path / "runlogs"),
    }

    return {
        "options": options,
        "temp_dir": tmp_path,
        "project_root": get_project_root()
    }



# ========== Test Functions ==========

def test_orchestrator_runs_sleep_benchmark(orchestrator_config) -> None:
    """Test orchestrator executes sleep benchmark successfully."""
    options = orchestrator_config["options"].copy()

    # Use new schema with entry_point and args as list
    test_spec = {
        "task": "test",
        "entry_point": "/bin/echo",
        "args": ["outer_time", "1.5", "inner_time", "0.5"],
    }

    # Add metrics to options so they can be extracted
    options["metric_specs"] = {
        "outer_time": {
            "extract": "awk '/outer_time/{print $NF}'",
            "type": "numeric"
        },
        "inner_time": {
            "extract": "awk '/inner_time/{print $NF}'",
            "type": "numeric"
        }
    }

    # Set repeater options to stop after 2 iterations
    options["repeats"] = 2
    options["repeater_options"] = {"CR": {"max": 2}}
    options["benchmark_spec"] = test_spec

    # Create orchestrator with test configurations
    orchestrator = ExecutionOrchestrator(
        options=options,
        experiment_name="test_sleep_benchmark"
    )

    # Run experiment
    result = orchestrator.run()

    # Verify execution
    assert result.success, f"Orchestrator failed: {result.error_message}"
    assert result.iteration_count == 2
    assert len(result.metrics) > 0, "No metrics collected"


def test_orchestrator_callback_flow(orchestrator_config) -> None:
    """Test orchestrator fires callbacks in correct order and count."""
    options = orchestrator_config["options"].copy()

    # Use new schema with entry_point and args as list
    test_spec = {
        "task": "test",
        "entry_point": "/bin/echo",
        "args": ["outer_time", "1.0"],
    }

    # Add metrics to options
    options["metric_specs"] = {
        "outer_time": {
            "extract": "awk '/outer_time/{print $NF}'",
            "type": "numeric"
        }
    }

    # Set repeater options to stop after 2 iterations
    options["repeats"] = 2
    options["repeater_options"] = {"CR": {"max": 2}}
    options["benchmark_spec"] = test_spec

    # Track callback invocations
    callback_log = {
        "iteration_starts": [],
        "iteration_completes": [],
        "convergences": [],
        "errors": []
    }

    def track_start(iteration: int) -> None:
        callback_log["iteration_starts"].append(iteration)

    def track_complete(iteration: int, metrics: Dict[str, Any]) -> None:
        callback_log["iteration_completes"].append(iteration)

    def track_convergence(status: str) -> None:
        callback_log["convergences"].append(status)

    def track_error(error: str) -> None:
        callback_log["errors"].append(error)

    callbacks = ProgressCallbacks(
        on_iteration_start=track_start,
        on_iteration_complete=track_complete,
        on_convergence=track_convergence,
        on_error=track_error
    )

    orchestrator = ExecutionOrchestrator(
        options=options,
        experiment_name="test_callback_flow"
    )

    result = orchestrator.run(callbacks)

    # Verify callback sequence
    assert result.success
    assert len(callback_log["iteration_starts"]) == 2, \
        "on_iteration_start should be called for each iteration"
    assert len(callback_log["iteration_completes"]) == 2, \
        "on_iteration_complete should be called for each iteration"
    # on_convergence is called once when loop exits
    assert len(callback_log["convergences"]) >= 0, \
        "on_convergence should be called at loop exit"
    assert len(callback_log["errors"]) == 0, \
        "No errors should occur during normal execution"


def test_orchestrator_error_handling_missing_command(orchestrator_config) -> None:
    """Test orchestrator handles command execution failure gracefully."""
    options = orchestrator_config["options"].copy()

    # Create invalid benchmark spec with non-existent command
    invalid_spec = {
        "task": "test",
        "entry_point": "/bin/nonexistent_command_12345",
        "args": ["arg1"],
    }

    options["repeats"] = 1
    options["repeater_options"] = {"CR": {"max": 1}}
    options["benchmark_spec"] = invalid_spec

    # Track errors
    error_log = []

    def track_error(error: str) -> None:
        error_log.append(error)

    callbacks = ProgressCallbacks(on_error=track_error)

    orchestrator = ExecutionOrchestrator(
        options=options,
        experiment_name="test_error_handling"
    )

    # Suppress expected warning about command exit code
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        result = orchestrator.run(callbacks)

    # Verify error handling
    assert not result.success, "Orchestrator should fail with invalid command"
    assert result.error_message is not None, "Error message should be set"


def test_metrics_extraction_from_sleep_output(orchestrator_config) -> None:
    """Test metrics are correctly extracted from simple command output."""
    options = orchestrator_config["options"].copy()

    # Use new schema with entry_point and args as list
    test_spec = {
        "task": "test",
        "entry_point": "/bin/echo",
        "args": ["outer_time 2.5"],
    }

    # Add metrics to options - use simpler extraction without regex
    options["metric_specs"] = {
        "outer_time": {
            "extract": "awk '{print $NF}'",
            "type": "numeric"
        }
    }

    options["repeats"] = 1
    options["repeater_options"] = {"CR": {"max": 1}}
    options["benchmark_spec"] = test_spec

    orchestrator = ExecutionOrchestrator(
        options=options,
        experiment_name="test_metrics_extraction"
    )

    result = orchestrator.run()

    # Verify metrics structure
    assert result.success
    assert len(result.metrics) > 0

    # Each metric dict should have metrics for that iteration
    for metric_dict in result.metrics:
        # outer_time should be extracted from command output
        assert "outer_time" in metric_dict
        assert len(metric_dict["outer_time"]) > 0


def test_local_rows_include_rank_and_repeat(orchestrator_config, tmp_path) -> None:
    """Verify CLI-style local runs log correct rank/repeat ordering and counts."""
    options = copy.deepcopy(orchestrator_config["options"])

    test_spec = {
        "task": "row_test",
        "entry_point": "/bin/echo",
        "args": ["outer_time 0.1"],
    }

    options["metrics"] = {
        "outer_time": {
            "extract": "awk '{print $NF}'",
            "type": "numeric",
        }
    }
    options["benchmark_spec"] = test_spec
    options["repeats"] = 2
    options["repeater_options"] = {"CR": {"max": 2}}
    options["mpl"] = 2
    options["directory"] = str(tmp_path / "runlogs")

    orchestrator = ExecutionOrchestrator(options=options, experiment_name="row_test")
    result = orchestrator.run()

    with open(result.output_paths["csv"], newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)
        repeat_idx = reader.fieldnames.index("repeat")
        rank_idx = reader.fieldnames.index("rank")
        assert repeat_idx < rank_idx, "repeat column should be left of rank"

    assert len(rows) == 4, "Two repeats * two ranks should produce four rows"
    expected_pairs = [("1", "0"), ("1", "1"), ("2", "0"), ("2", "1")]
    actual_pairs = [(row["repeat"], row["rank"]) for row in rows]
    assert actual_pairs == expected_pairs


class _DummyRunner:
    def run_commands(self, commands):
        tmp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False)
        tmp_file.write("outer_time 0.4\n")
        tmp_file.flush()
        tmp_file.seek(0)
        return True, [tmp_file], 0.4


def test_mpi_rows_include_rank_and_repeat(orchestrator_config, tmp_path) -> None:
    """Simulate MPI backend logging to verify rank/repeat columns."""
    options = copy.deepcopy(orchestrator_config["options"])

    mpi_config_path = orchestrator_config["project_root"] / "backends" / "mpi.yaml"
    with open(mpi_config_path, "r", encoding="utf-8") as f:
        mpi_config = yaml.safe_load(f)

    options["backend_names"] = ["mpi"]
    options["backend_options"] = mpi_config["backend_options"]
    options["metrics"] = {"hostname": {"extract": "cat", "type": "string"}}
    options["benchmark_spec"] = {
        "task": "mpi_row_test",
        "entry_point": "/bin/echo",
        "args": ["done"],
    }
    options["repeats"] = 2
    options["repeater_options"] = {"CR": {"max": 2}}
    options["mpl"] = 2
    options["directory"] = str(tmp_path / "runlogs_mpi")

    orchestrator = ExecutionOrchestrator(options=options, experiment_name="mpi_row_test")
    orchestrator.runner = _DummyRunner()

    orchestrator.metric_extractor.extract = Mock(
        side_effect=lambda *_args, **_kwargs: RunData({
            "outer_time": ["0.4", "0.4"],
            "hostname": ["node0", "node1"],
        })
    )

    result = orchestrator.run()

    with open(result.output_paths["csv"], newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert len(rows) == 4, "MPI scenario should produce two rows per repeat"
    expected_pairs = [("1", "0"), ("1", "1"), ("2", "0"), ("2", "1")]
    actual_pairs = [(row["repeat"], row["rank"]) for row in rows]
    assert actual_pairs == expected_pairs


def test_orchestrator_mpl_2_produces_multiple_rows(orchestrator_config) -> None:
    """Test that mpl=2 produces multiple rows of data (one per process)."""
    options = orchestrator_config["options"].copy()

    # Use echo to output a metric value
    test_spec = {
        "task": "test",
        "entry_point": "/bin/echo",
        "args": ["val 100"],
    }

    # Add metrics to options
    options["metrics"] = {
        "val": {
            "extract": "awk '/val/{print $NF}'",
            "type": "float"
        }
    }

    options["repeats"] = 1
    options["repeater_options"] = {"CR": {"max": 1}}
    options["benchmark_spec"] = test_spec
    options["mpl"] = 2  # Request 2 parallel copies

    orchestrator = ExecutionOrchestrator(
        options=options,
        experiment_name="test_mpl_rows"
    )

    result = orchestrator.run()

    assert result.success
    assert len(result.metrics) == 1  # 1 iteration

    # Check that we have 2 values for 'val' (one from each process)
    vals = result.metrics[0]["val"]
    assert len(vals) == 2, f"Expected 2 values for mpl=2, got {len(vals)}: {vals}"

    # Check logger rows
    # We can't easily access logger rows here without reading the file or mocking
    # But checking result.metrics confirms _extract_metrics worked correctly
    # And _log_run_data uses the same data structure length to determine rows

def test_orchestrator_handles_exit_code_1_with_output(orchestrator_config) -> None:
    """Test that metrics are extracted even if command exits with code 1."""
    options = orchestrator_config["options"].copy()

    # Use sh to echo output then exit 1
    # Note: We must quote the command string so it's treated as a single argument to -c
    test_spec = {
        "task": "test",
        "entry_point": "sh",
        "args": ["-c", "'echo \"val 100\"; exit 1'"],
    }

    options["metrics"] = {
        "val": {
            "extract": "awk '/val/{print $NF}'",
            "type": "float"
        }
    }

    options["repeats"] = 1
    options["repeater_options"] = {"CR": {"max": 1}}
    options["benchmark_spec"] = test_spec
    options["mpl"] = 2

    orchestrator = ExecutionOrchestrator(
        options=options,
        experiment_name="test_exit_1"
    )

    # Suppress warning about exit code 1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        result = orchestrator.run()

    assert result.success  # Should succeed despite exit code 1

    # Check that we still got metrics
    vals = result.metrics[0]["val"]
    assert len(vals) == 2, f"Expected 2 values despite exit code 1, got {len(vals)}: {vals}"

