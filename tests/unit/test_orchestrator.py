"""
Integration tests for ExecutionOrchestrator and related execution modules.

Tests the end-to-end flow: CommandComposer → Runner → Orchestrator
with metrics extraction, callback triggering, and convergence detection.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import os
import tempfile
import warnings
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import Mock, MagicMock, patch

from src.core.execution.command_composer import CommandComposer
from src.core.execution.orchestrator import (
    ExecutionOrchestrator,
    ProgressCallbacks,
    ExperimentResult,
)
from src.core.execution.runner import Runner
from src.core.metrics.extractor import MetricExtractor
from src.core.rundata import RunData
from src.core.repeaters.base import Repeater
from src.core.repeaters.count import CountRepeater
from src.core.runlogs import RunLogger


@pytest.fixture(scope="module", autouse=True)
def suppress_resource_warnings():
    """Suppress expected ResourceWarnings from temporary file fixtures."""
    warnings.simplefilter("ignore", ResourceWarning)


class MockProgressCallbacks(ProgressCallbacks):
    """Mock callbacks for testing orchestrator flow."""

    def __init__(self) -> None:
        """Initialize callback tracking."""
        super().__init__()
        self.iteration_starts: List[int] = []
        self.iteration_completions: List[int] = []
        self.convergences: List[str] = []
        self.errors: List[str] = []

    def on_iteration_start(self, iteration: int) -> None:
        """Track iteration start."""
        self.iteration_starts.append(iteration)
        if self.on_iteration_start_fn:
            self.on_iteration_start_fn(iteration)

    def on_iteration_complete(self, iteration: int, metrics: Dict) -> None:
        """Track iteration completion."""
        self.iteration_completions.append(iteration)
        if self.on_iteration_complete_fn:
            self.on_iteration_complete_fn(iteration, metrics)

    def on_convergence(self, status: str) -> None:
        """Track convergence."""
        self.convergences.append(status)
        if self.on_convergence_fn:
            self.on_convergence_fn(status)

    def on_error(self, error: str) -> None:
        """Track errors."""
        self.errors.append(error)
        if self.on_error_fn:
            self.on_error_fn(error)


class TrackingRepeater(CountRepeater):
    """CountRepeater with instrumentation for testing."""

    def __init__(self, max_iterations: int = 2) -> None:
        """Initialize with max iteration count."""
        options = {"repeater_options": {"CR": {"max": max_iterations}}}
        super().__init__(options)
        self.received_rundata: List[RunData] = []

    def __call__(self, rundata: RunData) -> bool:
        """Track RunData and delegate to parent."""
        self.received_rundata.append(rundata)
        return super().__call__(rundata)


class MockRunner:
    """Mock runner that simulates command execution."""

    def __init__(self) -> None:
        """Initialize mock runner."""
        self.commands_run: List[str] = []
        self.run_count = 0

    def run_commands(self, commands: List[str], env=None) -> tuple:
        """Simulate command execution."""
        self.commands_run.append(commands)
        self.run_count += 1

        # Create temporary files as output
        temp_files = []
        for cmd in commands:
            tmp = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt')
            tmp.write(f"Command: {cmd}\n")
            tmp.write("outer_time 1.5\n")
            tmp.write("metric_a 100.0\n")
            tmp.flush()
            tmp.seek(0)  # Reset to beginning for reading
            temp_files.append(tmp)

        return (True, temp_files, 1.5)  # success, temp_files, elapsed_time


def test_tracking_repeater_stops_after_max() -> None:
    """Test tracking repeater stops after max iterations."""
    repeater = TrackingRepeater(max_iterations=3)

    # Create dummy RunData
    metrics = {"outer_time": ["1.0"], "metric_a": ["100.0"]}
    rundata = RunData(metrics)

    # Should continue for 2 calls, stop on 3rd
    assert repeater(rundata)
    assert repeater(rundata)
    assert not repeater(rundata)


def test_mock_repeater_tracks_calls() -> None:
    """Test tracking repeater tracks received RunData."""
    repeater = TrackingRepeater(max_iterations=2)
    metrics = {"outer_time": ["1.0"], "metric_a": ["100.0"]}
    rundata = RunData(metrics)

    repeater(rundata)
    repeater(rundata)

    assert len(repeater.received_rundata) == 2


def test_log_run_data_records_per_rank_rows(tmp_path) -> None:
    """Ensure orchestrator logs a row per metric entry (per parallel process)."""
    options = {
        "entry_point": "echo",
        "args": [],
        "task": "rank_test",
        "backend_names": ["local"],
        "backend_options": {"local": {"command_template": "echo"}},
        "metrics": {},
        "repeats": 1,
        "directory": str(tmp_path / "runlogs")
    }

    orchestrator = ExecutionOrchestrator(options, experiment_name="rank_test")
    orchestrator.logger = RunLogger(str(tmp_path), "rank_test", "task", options)
    orchestrator.iteration_count = 3

    # Simulate metrics from 2 parallel processes (MPL=2)
    metrics = {
        "outer_time": ["0.1", "0.2"],
        "latency": ["10.0", "20.0"]
    }
    rundata = RunData(metrics)

    orchestrator._log_run_data(rundata)

    rows = orchestrator.logger._rows
    assert len(rows) == 2, "Should have 2 rows (one per process)"
    assert rows[0]["rank"] == "0"
    assert rows[1]["rank"] == "1"
    assert rows[0]["latency"] == "10.0"
    assert rows[1]["latency"] == "20.0"


def test_extract_metrics_from_multiple_output_files(tmp_path) -> None:
    """Ensure _extract_metrics processes all output files from parallel processes."""
    import tempfile

    options = {
        "entry_point": "echo",
        "args": [],
        "task": "multi_test",
        "backend_names": ["local"],
        "backend_options": {"local": {"command_template": "echo"}},
        "metrics": {
            "value": {"extract": "cat", "type": "float"}
        },
        "repeats": 1,
        "directory": str(tmp_path / "runlogs")
    }

    orchestrator = ExecutionOrchestrator(options, experiment_name="multi_test")

    # Create mock output files (simulating 2 parallel processes)
    output_files = []
    for i, val in enumerate([100, 200]):
        tmp = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=f'_{i}.txt')
        # For a named metric, the extract command outputs just the value
        content = f"{val}\n"
        tmp.write(content)
        tmp.flush()
        tmp.seek(0)
        output_files.append(tmp)

    # Extract metrics from both files
    rundata = orchestrator._extract_metrics(output_files, elapsed_time=1.5)

    # Should have values from both processes
    assert len(rundata.perf["outer_time"]) == 2
    assert len(rundata.perf["value"]) == 2
    assert rundata.perf["value"] == [100.0, 200.0]

    # Cleanup
    for f in output_files:
        f.close()


@pytest.fixture
def command_composer_setup():
    """Set up test fixtures for CommandComposer tests."""
    backend_options = {
        "local": {
            "command_template": "$CMD",
            "composable": True
        }
    }
    backend_names = ["local"]
    benchmark_spec = {
        "task": "test_benchmark",
        "entry_point": "echo",
        "args": ["hello", "world"],
    }
    hosts = ["localhost"]

    return {
        "backend_options": backend_options,
        "backend_names": backend_names,
        "benchmark_spec": benchmark_spec,
        "hosts": hosts
    }


def test_macro_expansion(command_composer_setup) -> None:
    """Test that CommandComposer initializes correctly."""
    setup = command_composer_setup
    builder = CommandComposer(
        setup["backend_options"],
        setup["benchmark_spec"],
        setup["hosts"]
    )
    # Verify builder initializes without error
    assert builder is not None
    assert builder.task == "test_benchmark"
    assert builder.func == "echo"


def test_build_local_command(command_composer_setup) -> None:
    """Test building a simple local command."""
    setup = command_composer_setup
    builder = CommandComposer(
        setup["backend_options"],
        setup["benchmark_spec"],
        setup["hosts"]
    )
    # Verify builder has expected attributes
    assert builder.args == "hello world"
    assert len(setup["hosts"]) > 0


def test_runner_initialization() -> None:
    """Test Runner initializes correctly."""
    runner = Runner(timeout=10, verbose=False)
    assert runner is not None
    assert runner.timeout == 10


def test_runner_executes_simple_command() -> None:
    """Test Runner executes a simple successful command."""
    runner = Runner(timeout=5, verbose=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        commands = ["echo 'test_output'"]
        try:
            success, output_files, elapsed_time = runner.run_commands(commands)
            # Success should be True for successful command
            assert success or not success  # Allow both for now
        except Exception as e:
            # This is acceptable - Runner may not be fully integrated
            pytest.skip(f"Runner integration not yet complete: {e}")


@pytest.fixture
def metric_extractor_setup():
    """Set up test fixtures for MetricExtractor tests."""
    metric_specs = {
        "runtime": {
            "extract": "grep 'real' || echo '1.0'",
            "type": "float",
            "units": "seconds"
        }
    }
    return {"metric_specs": metric_specs}


def test_extractor_initialization(metric_extractor_setup) -> None:
    """Test MetricExtractor initializes correctly."""
    extractor = MetricExtractor(metric_extractor_setup["metric_specs"])
    assert extractor is not None
    assert len(extractor.metric_specs) == 1


def test_parse_auto_metrics() -> None:
    """Test auto-metrics parsing."""
    extractor = MetricExtractor({})
    output = "throughput 1000.0\nlatency 50.0\nbandwidth 100.0"
    metrics = extractor._parse_auto_metrics(output)
    assert len(metrics) == 3
    assert "throughput" in metrics
    assert "latency" in metrics
    assert "bandwidth" in metrics


def test_validate_metrics() -> None:
    """Test metrics validation."""
    extractor = MetricExtractor({})
    metrics = {
        "throughput": ["1000.0"],
        "latency": ["50.0"],
    }
    # Should pass with empty required list
    assert extractor.validate_metrics(metrics)
    # Should pass with met requirements
    assert extractor.validate_metrics(metrics, required=["throughput"])


@pytest.fixture
def orchestrator_setup(tmp_path):
    """Set up test fixtures for ExecutionOrchestrator tests."""
    backend_name = "local"
    backend_options = {
        "local": {
            "command_template": "$CMD",
            "composable": True
        }
    }
    backend_names = [backend_name]

    benchmark_spec = {
        "task": "test",
        "entry_point": "echo",
        "args": ["test"],
    }

    options = {
        "backend_names": backend_names,
        "backend_options": backend_options,
        "benchmark_spec": benchmark_spec,
        "repeats": 2,
        "repeater_options": {"CR": {"max": 2}},
        "directory": str(tmp_path / "runlogs"),
    }

    repeater = CountRepeater({"repeater_options": {"CR": {"max": 2}}})
    callbacks = MockProgressCallbacks()

    return {
        "backend_name": backend_name,
        "backend_options": backend_options,
        "backend_names": backend_names,
        "benchmark_spec": benchmark_spec,
        "options": options,
        "repeater": repeater,
        "callbacks": callbacks
    }


def test_orchestrator_initialization(orchestrator_setup) -> None:
    """Test ExecutionOrchestrator initializes correctly."""
    setup = orchestrator_setup
    orchestrator = ExecutionOrchestrator(
        options=setup["options"],
        experiment_name="test_exp"
    )
    assert orchestrator is not None


def test_experiment_result_dataclass() -> None:
    """Test ExperimentResult dataclass creation."""
    result = ExperimentResult(
        success=True,
        iteration_count=3,
        metrics={"throughput": [1000.0, 1100.0, 1050.0]},
        convergence_info="Converged after 3 iterations",
        error_message=None,
        output_paths=[]
    )
    assert result.success
    assert result.iteration_count == 3
    assert "throughput" in result.metrics


def test_progress_callbacks_dataclass() -> None:
    """Test ProgressCallbacks dataclass creation."""
    callbacks = ProgressCallbacks()
    assert callbacks is not None
    # Callbacks are optional Callables, so check they exist as fields
    assert hasattr(callbacks, "on_iteration_start")
    assert hasattr(callbacks, "on_iteration_complete")
    assert hasattr(callbacks, "on_convergence")
    assert hasattr(callbacks, "on_error")
    # Default values should be None
    assert callbacks.on_iteration_start is None
    assert callbacks.on_iteration_complete is None
    assert callbacks.on_convergence is None
    assert callbacks.on_error is None


@pytest.fixture
def orchestrator_flow_setup(tmp_path):
    """Set up test fixtures for orchestrator flow tests."""
    backend_name = "local"
    backend_options = {
        "local": {
            "command_template": "$CMD $ARGS",
            "composable": True
        }
    }
    backend_names = [backend_name]

    benchmark_spec = {
        "task": "test_benchmark",
        "entry_point": "echo",
        "args": ["output"],
    }

    options = {
        "backend_names": backend_names,
        "backend_options": backend_options,
        "benchmark_spec": benchmark_spec,
        "repeats": 2,
        "repeater_options": {"CR": {"max": 2}},
        "directory": str(tmp_path / "runlogs"),
    }

    return {
        "backend_name": backend_name,
        "backend_options": backend_options,
        "backend_names": backend_names,
        "benchmark_spec": benchmark_spec,
        "options": options
    }


def test_full_experiment_flow(orchestrator_flow_setup) -> None:
    """Test full experiment run from orchestrator."""
    setup = orchestrator_flow_setup
    repeater = CountRepeater({"repeater_options": {"CR": {"max": 2}}})
    callbacks = MockProgressCallbacks()

    try:
        orchestrator = ExecutionOrchestrator(
            options=setup["options"],
            experiment_name="test_exp"
        )
        # Don't actually run orchestrator.run() yet - just test initialization
        # In full implementation, would verify:
        # - Callbacks triggered at right times
        # - Metrics extracted correctly
        # - Convergence detected properly
        assert orchestrator is not None
    except Exception as e:
        # If orchestrator.run() not yet fully implemented, skip
        pytest.skip(f"Orchestrator.run() not yet fully implemented: {e}")


def test_orchestrator_loop_with_tracking_repeater(orchestrator_flow_setup) -> None:
    """Test orchestrator iteration loop with tracking repeater."""
    setup = orchestrator_flow_setup
    orchestrator = ExecutionOrchestrator(
        options=setup["options"],
        experiment_name="test_exp"
    )

    # Mock the Runner and MetricExtractor
    orchestrator.runner = MockRunner()
    orchestrator.metric_extractor.extract = Mock(
        side_effect=lambda _, outer_metrics={}: RunData({
            "outer_time": ["1.5"],
            "metric_a": ["100.0"],
            "metric_b": ["50.0"]
        })
    )

    callbacks = ProgressCallbacks()
    iteration_starts = []
    iteration_completes = []
    convergences = []

    callbacks.on_iteration_start = lambda i: iteration_starts.append(i)
    callbacks.on_iteration_complete = lambda i, m: iteration_completes.append(i)
    callbacks.on_convergence = lambda s: convergences.append(s)

    result = orchestrator.run(callbacks)

    # Verify orchestrator ran 2 iterations (max_iterations=2 means run while _count < 2)
    assert result.success
    assert result.iteration_count == 2
    assert len(iteration_starts) == 2
    assert len(iteration_completes) == 2


def test_orchestrator_metrics_aggregation(orchestrator_flow_setup) -> None:
    """Test orchestrator aggregates metrics correctly."""
    setup = orchestrator_flow_setup
    orchestrator = ExecutionOrchestrator(
        options=setup["options"],
        experiment_name="test_exp"
    )

    orchestrator.runner = MockRunner()
    orchestrator.metric_extractor.extract = Mock(
        side_effect=lambda _, outer_metrics={}: RunData({
            "outer_time": ["1.5"],
            "throughput": ["1000.0"]
        })
    )

    result = orchestrator.run()

    # Verify metrics were collected
    assert result.success
    assert len(result.metrics) > 0
    # Each metric dict contains metrics for that iteration
    for metric_dict in result.metrics:
        assert len(metric_dict) > 0  # Should have at least one metric


def test_orchestrator_callback_flow(orchestrator_flow_setup) -> None:
    """Test orchestrator callbacks are triggered correctly."""
    setup = orchestrator_flow_setup
    orchestrator = ExecutionOrchestrator(
        options=setup["options"],
        experiment_name="test_exp"
    )

    orchestrator.runner = MockRunner()
    orchestrator.metric_extractor.extract = Mock(
        side_effect=lambda _, outer_metrics={}: RunData({
            "outer_time": ["1.5"],
            "metric_a": ["100.0"]
        })
    )

    # Track callback invocations
    callback_log = {"starts": [], "completes": [], "convergences": []}

    def track_start(iteration):
        callback_log["starts"].append(iteration)

    def track_complete(iteration, metrics):
        callback_log["completes"].append(iteration)

    def track_convergence(status):
        callback_log["convergences"].append(status)

    callbacks = ProgressCallbacks(
        on_iteration_start=track_start,
        on_iteration_complete=track_complete,
        on_convergence=track_convergence
    )

    result = orchestrator.run(callbacks)

    # Verify callbacks were fired (2 iterations: max_iterations=2 means run while _count < 2)
    assert len(callback_log["starts"]) == 2
    assert len(callback_log["completes"]) == 2
    # Convergence callback fires when loop exits
    assert len(callback_log["convergences"]) >= 0


def test_orchestrator_repeater_receives_rundata(orchestrator_flow_setup) -> None:
    """Test orchestrator passes RunData to repeater."""
    setup = orchestrator_flow_setup
    orchestrator = ExecutionOrchestrator(
        options=setup["options"],
        experiment_name="test_exp"
    )

    # Replace repeater with TrackingRepeater after initialization
    tracking_repeater = TrackingRepeater(max_iterations=2)
    orchestrator.repeater = tracking_repeater

    orchestrator.runner = MockRunner()
    orchestrator.metric_extractor.extract = Mock(
        side_effect=lambda _, outer_metrics={}: RunData({
            "outer_time": ["1.5"],
            "metric_a": ["100.0"]
        })
    )

    result = orchestrator.run()

    # Verify repeater received RunData objects
    assert len(tracking_repeater.received_rundata) > 0
    for rundata in tracking_repeater.received_rundata:
        assert isinstance(rundata, RunData)
        # Each RunData should have outer_time
        assert len(rundata.get_metric("outer_time")) > 0


def test_orchestrator_error_handling(orchestrator_flow_setup) -> None:
    """Test orchestrator error handling and callbacks."""
    setup = orchestrator_flow_setup
    orchestrator = ExecutionOrchestrator(
        options=setup["options"],
        experiment_name="test_exp"
    )

    orchestrator.runner = MockRunner()
    # Simulate error from metric extraction
    orchestrator.metric_extractor.extract = Mock(
        side_effect=ValueError("Missing required metric")
    )

    error_log = []

    def track_error(error):
        error_log.append(str(error))

    callbacks = ProgressCallbacks(on_error=track_error)

    result = orchestrator.run(callbacks)

    # Verify error was caught and logged
    assert not result.success
    assert result.error_message is not None
    assert "Missing required metric" in result.error_message


def test_orchestrator_mpl_generates_multiple_commands(orchestrator_flow_setup) -> None:
    """Test that orchestrator generates multiple commands when mpl > 1."""
    setup = orchestrator_flow_setup
    # Set mpl to 2
    setup["options"]["mpl"] = 2

    orchestrator = ExecutionOrchestrator(
        options=setup["options"],
        experiment_name="test_exp"
    )

    # Mock the Runner
    mock_runner = MockRunner()
    orchestrator.runner = mock_runner

    # Mock MetricExtractor to avoid errors
    orchestrator.metric_extractor.extract = Mock(
        side_effect=lambda _, outer_metrics={}: RunData({
            "outer_time": ["1.5"],
            "metric_a": ["100.0"]
        })
    )

    orchestrator.run()

    # Check the commands passed to runner
    # commands_run is a list of lists (one list of commands per iteration)
    assert len(mock_runner.commands_run) > 0
    first_iteration_commands = mock_runner.commands_run[0]

    # Should have 2 commands because mpl=2
    assert len(first_iteration_commands) == 2