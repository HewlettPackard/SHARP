"""
Execution orchestrator for benchmark experiments.

Coordinates the full lifecycle of a benchmark run:
1. Load configuration (experiment, backends, benchmark)
2. Chain backends (compose profiling/execution tools)
3. Run experiment with adaptive stopping (repeater)
4. Extract and aggregate metrics
5. Write results to CSV/Markdown logs

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import subprocess
import tempfile
import warnings
from pathlib import Path

from src.core.execution.command_composer import CommandComposer
from src.core.execution.runner import Runner
from src.core.repeaters.base import Repeater
from src.core.rundata import RunData
from src.core.metrics.extractor import MetricExtractor
from src.core.logging.writer import RunLogger
from src.core.logging.sysinfo import collect_sysinfo


@dataclass
class ProgressCallbacks:
    """Callbacks for progress updates (GUI integration hooks)."""
    on_iteration_start: Optional[Callable[[int], None]] = None
    on_iteration_complete: Optional[Callable[[int, Dict[str, Any]], None]] = None
    on_convergence: Optional[Callable[[str], None]] = None
    on_error: Optional[Callable[[Exception], None]] = None


@dataclass
class ExperimentResult:
    """Result of experiment execution."""
    success: bool
    iteration_count: int
    metrics: List[Dict[str, Any]] = field(default_factory=list)
    convergence_info: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    output_paths: Dict[str, str] = field(default_factory=dict)  # csv, markdown paths


class ExecutionOrchestrator:
    """
    Orchestrates benchmark execution from config to results.

    Integrates:
    - Command building (backend chaining)
    - Subprocess management (Runner)
    - Adaptive stopping (Repeater)
    - Metrics extraction
    - Result logging
    """

    def __init__(self, options: Dict[str, Any], benchmark_spec: Dict[str, Any],
                 repeater: Repeater, experiment_name: str = "misc") -> None:
        """
        Initialize orchestrator from configuration.

        Args:
            options: Experiment options dict containing:
                - backend_names: List[str] - backend names to compose (left=outermost, right=innermost)
                - backend_options: Dict[str, Dict] - {backend_name: {command_template, ...}}
                - metric_specs: Optional[Dict] - metric extraction specifications
                - timeout: Optional[int] - global timeout in seconds
                - verbose: Optional[bool] - print debug output
            benchmark_spec: Benchmark entry dict with task, function, arguments
            repeater: Adaptive stopping strategy (Repeater instance)
            experiment_name: Name of experiment for logging (default: "misc")

        Raises:
            KeyError: If required keys are missing from options
            TypeError: If types don't match expectations
        """
        # Extract required parameters from options
        self.backend_names = options["backend_names"]
        if not isinstance(self.backend_names, list):
            raise TypeError(f"backend_names must be list, got {type(self.backend_names)}")

        self.benchmark_spec = benchmark_spec
        if not isinstance(self.benchmark_spec, dict):
            raise TypeError(f"benchmark_spec must be dict, got {type(self.benchmark_spec)}")

        # Extract optional parameters with defaults
        self.backend_options = options.get("backend_options", {})
        self.timeout = options.get("timeout")
        self.verbose = options.get("verbose", False)
        self.start = options.get("start", "normal")  # cold, warm, or normal
        self.mode = options.get("mode", "w")  # File write mode: "w" (truncate) or "a" (append)
        self.sys_spec_commands = options.get("sys_spec_commands", {})
        self.skip_sys_specs = options.get("skip_sys_specs", False)
        self.experiment_name = experiment_name

        self.repeater = repeater

        # Initialize runtime components
        self.runner = Runner(timeout=self.timeout, verbose=self.verbose)

        metrics = options.get("metrics", {})
        self.metric_extractor = MetricExtractor(metrics)

        # Initialize logger for results
        task_name = benchmark_spec.get("task", self.experiment_name)
        topdir = options.get("directory", "runlogs")
        self.logger = RunLogger(
            topdir=topdir,
            experiment=self.experiment_name,
            task=task_name,
            options=options
        )

        self.iteration_count = 0
        self.collected_metrics: List[Dict[str, Any]] = []

    def run(self, callbacks: Optional[ProgressCallbacks] = None,
            max_iterations: Optional[int] = None) -> ExperimentResult:
        """
        Execute benchmark with adaptive stopping.

        Runs the experiment in a loop until the repeater signals to stop,
        extracting metrics after each iteration and updating the repeater's state.

        Args:
            callbacks: Optional progress callbacks for GUI integration
            max_iterations: Optional hard limit on iterations (safety valve)

        Returns:
            ExperimentResult with metrics and convergence info
        """
        callbacks = callbacks or ProgressCallbacks()
        max_iterations = max_iterations or 1000
        self.iteration_count = 0
        self.collected_metrics = []

        try:
            # Create command composer (reuse for all iterations)
            composer = CommandComposer(
                self.backend_options,
                self.benchmark_spec
            )

            # Warm start: run benchmark once before measurements
            if self.start == "warm":
                commands = composer.compose(self.backend_names, copies=1)
                self.runner.run_commands(commands)  # Run once, discard results

            # Main iteration loop
            should_continue = True
            while should_continue and self.iteration_count < max_iterations:
                # Cold start: execute reset commands before each iteration
                if self.start == "cold":
                    self._execute_reset()

                # Iteration start callback
                if callbacks.on_iteration_start:
                    callbacks.on_iteration_start(self.iteration_count + 1)

                # Build commands (possibly chained backends)
                commands = composer.compose(
                    self.backend_names,
                    copies=1  # TODO: support multiple copies per iteration
                )

                # Run commands and measure wall-clock time
                success, output_files, elapsed_time = self.runner.run_commands(commands)
                if not success:
                    raise RuntimeError("Command execution timeout or failure")

                # Extract metrics from each output file (returns RunData)
                rundata = self._extract_metrics(output_files, elapsed_time)

                # Increment count BEFORE calling repeater (it expects count to be updated)
                self.iteration_count += 1

                # Update repeater: returns True to continue, False to stop
                should_continue = self.repeater(rundata)

                # Store iteration metrics (with iteration number)
                metrics_with_iteration = {
                    "iteration": [str(self.iteration_count)],
                    **{k: [str(v) for v in vals] for k, vals in rundata.perf.items()}
                }
                self.collected_metrics.append(metrics_with_iteration)

                # Add to logger: iteration number and metrics
                self.logger.add_column("iteration", str(self.iteration_count), "int", "Iteration number")
                self.logger.add_row_data("start", self.start, "string", "Warm, cold, or normal start")
                for field_name, values in rundata.perf.items():
                    # Handle both single values and lists
                    if isinstance(values, list) and len(values) > 0:
                        value = str(values[0])
                    else:
                        value = str(values)
                    self.logger.add_row_data(field_name, value, "float", field_name)

                # Iteration complete callback
                if callbacks.on_iteration_complete:
                    callbacks.on_iteration_complete(self.iteration_count, {
                        "metrics": metrics_with_iteration,
                        "should_continue": should_continue,
                    })

                # Clean up temporary files
                for f in output_files:
                    try:
                        f.close()
                    except Exception:
                        pass

            # Save results to CSV and Markdown
            self.logger.save_csv(mode=self.mode)

            # Collect system specifications (run through backend chain)
            sys_specs = collect_sysinfo(
                self.sys_spec_commands,
                backend_options=self.backend_options,
                backend_names=self.backend_names
            ) if not self.skip_sys_specs else {}
            self.logger.save_md(mode=self.mode, sys_specs=sys_specs)

            # Convergence callback (stopped due to repeater)
            if not should_continue and callbacks.on_convergence:
                callbacks.on_convergence(
                    f"Converged after {self.iteration_count} iterations"
                )

            # Aggregate results
            return ExperimentResult(
                success=True,
                iteration_count=self.iteration_count,
                metrics=self.collected_metrics,
                convergence_info={
                    "stopped_early": not should_continue,
                    "max_iterations_reached": self.iteration_count >= max_iterations,
                    "final_count": self.iteration_count,
                },
                output_paths={
                    "csv": self.logger.get_csv_path(),
                    "markdown": self.logger.get_markdown_path(),
                }
            )

        except Exception as e:
            if callbacks.on_error:
                callbacks.on_error(e)
            return ExperimentResult(
                success=False,
                iteration_count=self.iteration_count,
                metrics=self.collected_metrics,
                error_message=str(e)
            )

    def _execute_reset(self) -> None:
        """
        Execute reset commands from all backends for cold starts.

        Executes the reset command from each backend's configuration.
        Used for cold starts to clear caches and reset state before each iteration.

        Raises:
            RuntimeError: If reset command fails for non-composable backends
            Warning: If reset command fails for composable backends (continues)
        """
        for backend_name in self.backend_names:
            backend_config = self.backend_options.get(backend_name, {})
            reset_cmd = backend_config.get("reset", "")

            if reset_cmd:
                try:
                    result = subprocess.run(
                        reset_cmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode != 0:
                        # Check if backend is composable (can fail gracefully)
                        is_composable = backend_config.get("composable", True)
                        if not is_composable:
                            # Non-composable backends (like 'local') must succeed
                            raise RuntimeError(
                                f"Reset command failed for backend {backend_name}: {result.stderr}"
                            )
                        else:
                            # Composable backends can fail gracefully
                            warnings.warn(
                                f"Reset command failed for backend {backend_name}: {result.stderr}"
                            )
                except subprocess.TimeoutExpired:
                    warnings.warn(f"Reset command timeout for backend {backend_name}")
                except Exception as e:
                    # Check if backend is composable
                    backend_config = self.backend_options.get(backend_name, {})
                    is_composable = backend_config.get("composable", True)
                    if not is_composable:
                        raise RuntimeError(f"Reset command error for backend {backend_name}: {e}")
                    else:
                        warnings.warn(f"Reset command error for backend {backend_name}: {e}")

    def _extract_metrics(self, output_files: list[tempfile._TemporaryFileWrapper[bytes]], elapsed_time: float) -> RunData:
        """
        Extract metrics from output files and add wall-clock execution time.

        Args:
            output_files: List of TemporaryFile objects from runner
            elapsed_time: Wall-clock time in seconds for command execution

        Returns:
            RunData object containing extracted metrics plus outer_time
        """
        # Extract metrics and add outer_time (wall-clock execution time)
        # RunData requires outer_time for repeater convergence decisions
        outer_metrics = {"outer_time": [str(elapsed_time)]}
        return self.metric_extractor.extract(output_files[0].name, outer_metrics)
