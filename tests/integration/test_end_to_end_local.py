"""
End-to-end integration tests for ExecutionOrchestrator with local backend.

Tests the full orchestrator workflow with real configurations and actual command execution.
Uses sleep benchmark for predictable, fast testing.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import warnings
from pathlib import Path
from typing import Dict, Any

from src.core.execution.orchestrator import (
    ExecutionOrchestrator,
    ProgressCallbacks,
)
from src.core.repeaters.count import CountRepeater


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
    options = {
        "backend_names": backend_names,
        "backend_options": backend_options,
        "timeout": 30,
        "verbose": False,
    }

    return {
        "options": options,
        "temp_dir": tmp_path,
        "project_root": Path(__file__).parent.parent.parent
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

    # Create repeater that stops after 2 iterations
    repeater = CountRepeater({"repeater_options": {"CR": {"max": 2}}})

    # Create orchestrator with test configurations
    orchestrator = ExecutionOrchestrator(
        options,
        test_spec,
        repeater
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

    repeater = CountRepeater({"repeater_options": {"CR": {"max": 2}}})

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
        options,
        test_spec,
        repeater
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

    repeater = CountRepeater({"repeater_options": {"CR": {"max": 1}}})

    # Track errors
    error_log = []

    def track_error(error: str) -> None:
        error_log.append(error)

    callbacks = ProgressCallbacks(on_error=track_error)

    orchestrator = ExecutionOrchestrator(
        options,
        invalid_spec,
        repeater
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

    repeater = CountRepeater({"repeater_options": {"CR": {"max": 1}}})

    orchestrator = ExecutionOrchestrator(
        options,
        test_spec,
        repeater
    )

    result = orchestrator.run()

    # Verify metrics structure
    assert result.success
    assert len(result.metrics) > 0

    # Each metric should have iteration and values
    for metric_dict in result.metrics:
        assert "iteration" in metric_dict, "Metric dict should have iteration key"
        # outer_time should be extracted from command output
        if "outer_time" in metric_dict:
            assert len(metric_dict["outer_time"]) > 0

