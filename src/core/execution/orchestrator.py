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
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import subprocess
import tempfile
import warnings

import yaml

from src.core.config.backend_loader import load_backend_configs, resolve_backend_paths
from src.core.execution.command_composer import CommandComposer
from src.core.execution.runner import Runner
from src.core.repeaters import repeater_factory
from src.core.rundata import RunData
from src.core.metrics.extractor import MetricExtractor
from src.core.runlogs import RunLogger, collect_sysinfo


def _load_default_sys_spec_commands() -> Dict[str, Dict[str, str]]:
    """Load default sys_spec commands from src/core/config/sys_spec.yaml."""
    sys_spec_path = Path(__file__).resolve().parent.parent / "config" / "sys_spec.yaml"
    if not sys_spec_path.exists():
        return {}
    try:
        with open(sys_spec_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        commands = config.get("sys_spec_commands", {})
        return commands if isinstance(commands, dict) else {}
    except Exception:
        return {}


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

    def __init__(self, options: Dict[str, Any], experiment_name: str = "misc") -> None:
        """
        Initialize orchestrator from complete configuration.

        Args:
            options: Complete experiment configuration dict containing:
                - entry_point: str - path to executable/script
                - args: List[str] - command-line arguments
                - task: str - task/benchmark name (for filenames)
                - backend_names: List[str] - backend names to compose
                - backend_options: Dict[str, Dict] - {backend_name: {command_template, ...}}
                - metrics: Dict - metric extraction specifications
                - repeats: str - repeater type (COUNT, MAX, RSE, etc.)
                - repeater_options: Dict - repeater-specific configuration
                - timeout: Optional[int] - global timeout in seconds
                - verbose: Optional[bool] - print debug output
                - start: Optional[str] - cold, warm, or normal
                - mpl: Optional[int] - multiprogramming level (concurrency)
                - directory: Optional[str] - output directory
                - mode: Optional[str] - file write mode (w or a)
                - sys_spec_commands: Optional[Dict] - system spec commands
                - skip_sys_specs: Optional[bool] - skip system specs
            experiment_name: Name of experiment for logging (default: "misc")

        Raises:
            KeyError: If required keys are missing from options
            TypeError: If types don't match expectations
        """
        # Build benchmark spec from options or use provided spec
        if "benchmark_spec" in options:
            self.benchmark_spec = options["benchmark_spec"]
        else:
            self.benchmark_spec = {
                "entry_point": options["entry_point"],
                "args": options.get("args", []),
                "task": options.get("task", "unknown"),
            }

        # Extract required parameters from options
        self.backend_names = options["backend_names"]
        if not isinstance(self.backend_names, list):
            raise TypeError(f"backend_names must be list, got {type(self.backend_names)}")

        # Default to 'local' backend if none specified (consistent with CLI behavior)
        if not self.backend_names:
            self.backend_names = ["local"]

        # Extract optional parameters with defaults
        self.backend_options = options.get("backend_options", {})

        # If we're using backends but don't have their options loaded, load them now
        # This handles the case where backend_names defaults to ["local"] but
        # backend_options was empty (e.g., from a --repro run)
        missing_backends = [
            name for name in self.backend_names
            if name not in self.backend_options
        ]
        if missing_backends:
            temp_config: Dict[str, Any] = {"backend_options": {}}
            load_backend_configs(resolve_backend_paths(missing_backends), temp_config)
            for backend_name in missing_backends:
                if backend_name in temp_config.get("backend_options", {}):
                    self.backend_options[backend_name] = temp_config["backend_options"][backend_name]

        self.timeout = options.get("timeout")
        self.verbose = options.get("verbose", False)
        self.start = options.get("start", "normal")  # cold, warm, or normal
        self.mode = options.get("mode", "w")  # File write mode: "w" (truncate) or "a" (append)
        self.skip_sys_specs = options.get("skip_sys_specs", False)
        # Load sys_spec_commands: use provided, or load defaults if not skipping
        self.sys_spec_commands = options.get("sys_spec_commands", {})
        if not self.sys_spec_commands and not self.skip_sys_specs:
            self.sys_spec_commands = _load_default_sys_spec_commands()
        self.mpl = options.get("mpl", 1)  # Multiprogramming level (concurrency)
        self.experiment_name = experiment_name

        # Create repeater from options
        repeater_config = {
            "repeats": options["repeats"],
            "repeater_options": options.get("repeater_options", {}),
        }
        self.repeater = repeater_factory(repeater_config)

        # Initialize runtime components
        self.runner = Runner(timeout=self.timeout, verbose=self.verbose)

        metrics = options.get("metrics", {})
        self.metric_extractor = MetricExtractor(metrics)

        task_name = self.benchmark_spec.get("task", self.experiment_name)
        topdir = options.get("directory", "runlogs")

        self.logger = RunLogger(
            topdir=topdir,
            experiment=self.experiment_name,
            task=task_name,
            options=options  # Pass complete options dict directly
        )

        # Add invariant parameters (constants for this run)
        self.logger.add_invariant("task", task_name, "string", "Task/benchmark name")
        self.logger.add_invariant("start", self.start, "string", "Warm, cold, or as-is start")
        self.logger.add_invariant("concurrency", self.mpl, "int", "Concurrent copies (MPL)")
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
                commands = composer.compose(self.backend_names, copies=self.mpl)
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
                    copies=self.mpl
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

                # Store iteration metrics (for callbacks/result only)
                self.collected_metrics.append({
                    k: [str(v) for v in vals] for k, vals in rundata.perf.items()
                })

                # Add row data for each metric entry (preserves per-rank rows)
                self._log_run_data(rundata)

                # Iteration complete callback
                if callbacks.on_iteration_complete:
                    callbacks.on_iteration_complete(self.iteration_count, {
                        "metrics": rundata.perf,
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

    def _log_run_data(self, rundata: RunData) -> None:
        """Log CSV rows for each metric entry (e.g., per MPI rank)."""
        perf = rundata.perf
        row_count = self._row_count_from_perf(perf)
        outer_values = perf.get("outer_time", [])
        metric_items = [(name, values) for name, values in perf.items() if name != "outer_time"]

        for row_index in range(row_count):
            self.logger.add_row_data("repeat", str(self.iteration_count), "int", "Iteration/repeat number")
            rank_value = str(row_index)
            self.logger.add_row_data("rank", rank_value, "int", "MPI rank (0 for non-MPI)")

            outer_time_value = self._value_for_row(outer_values, row_index, default=str(outer_values[-1]) if outer_values else "")
            self.logger.add_row_data("outer_time", outer_time_value, "float", "outer_time")

            for field_name, values in metric_items:
                value = self._value_for_row(values, row_index)
                self.logger.add_row_data(field_name, value, "float", field_name)

    def _row_count_from_perf(self, perf: Dict[str, List[Any]]) -> int:
        counts = [len(values) for values in perf.values()]
        if not counts:
            return 1
        row_count = max(counts)
        return row_count if row_count > 0 else 1

    def _value_for_row(self, values: List[Any], index: int, default: str = "") -> str:
        if not values:
            return default
        if index < len(values):
            return str(values[index])
        return str(values[-1])

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
            output_files: List of TemporaryFile objects from runner (one per parallel process)
            elapsed_time: Wall-clock time in seconds for command execution

        Returns:
            RunData object containing extracted metrics plus outer_time

        Raises:
            RuntimeError: If no output files are available for metric extraction
        """
        # Validate we have output to extract from
        if not output_files or len(output_files) == 0:
            raise RuntimeError("No output files available for metric extraction")

        # Extract metrics from all output files (one per parallel process)
        # and merge them into a single RunData with lists of values
        outer_metrics = {"outer_time": [str(elapsed_time)]}
        merged_metrics: Dict[str, List[str]] = {}

        for output_file in output_files:
            file_rundata = self.metric_extractor.extract(output_file.name, outer_metrics)
            for metric_name, values in file_rundata.perf.items():
                if metric_name not in merged_metrics:
                    merged_metrics[metric_name] = []
                # RunData converts to float/other types, so convert back to strings
                merged_metrics[metric_name].extend(str(v) for v in values)

        return RunData(merged_metrics)
