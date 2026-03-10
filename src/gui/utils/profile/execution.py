"""
Profile tab execution helpers.

Handles profiling execution orchestration with clean separation of concerns:
- Task name determination
- Options building
- Orchestrator execution
- Result loading

© Copyright 2025 Hewlett Packard Enterprise Development LP
"""

import traceback
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple

from src.core.runlogs import (
    load_csv,
    parse_markdown_runtime_options,
    extract_runtime_options_from_markdown
)
from src.gui.utils.profile.files import extract_repeater_max_from_md
from src.core.execution.orchestrator import ExecutionOrchestrator, ProgressCallbacks
from src.core.config.backend_loader import load_backend_configs, resolve_backend_paths
from src.core.config.settings import Settings
from src.core.config.include_resolver import get_project_root

# Path to mitigations.yaml (contains backend_options for mitigations)
MITIGATIONS_YAML = get_project_root() / "src" / "core" / "metrics" / "mitigations.yaml"


def determine_task_name_for_profiling(md_path: str) -> str:
    """
    Determine task name for profiling run.

    Extracts the original task name and appends profiling suffix from settings.

    Args:
        md_path: Path to original markdown file

    Returns:
        Task name with profiling suffix
    """
    runtime_opts = parse_markdown_runtime_options(Path(md_path))
    original_task = runtime_opts.get('task', Path(md_path).stem)

    # Ensure profiling suffix from settings
    prof_suffix = Settings().get("profiling.prof_suffix", "-prof")
    if not original_task.endswith(prof_suffix):
        return f"{original_task}{prof_suffix}"
    return original_task


def build_orchestrator_options(
    md_path: str,
    backends: list[str],
    task_name: str
) -> Dict[str, Any]:
    """
    Build orchestrator options for profiling/reproduction run.

    Extracts runtime options from markdown, composes new backends with existing ones,
    and overrides the task name. This implements the --repro behavior where new backends
    are prepended to the original backend chain.

    Args:
        md_path: Path to source markdown file (any .md file)
        backends: List of new backend names to prepend to the chain
        task_name: Task name for the output

    Returns:
        Dictionary of options for ExecutionOrchestrator

    Raises:
        ValueError: If runtime options cannot be extracted from markdown
    """
    # Extract runtime options (try both v4 and pre-v4 formats)
    runtime_opts = extract_runtime_options_from_markdown(md_path)
    if not runtime_opts:
        runtime_opts = parse_markdown_runtime_options(Path(md_path))

    if not runtime_opts:
        raise ValueError(f"Could not extract runtime options from {md_path}")

    # Use runtime options as base
    options = runtime_opts.copy()

    # Extract existing backends from source markdown (handle multiple possible key names)
    existing_backends = []
    if "backend_names" in runtime_opts and runtime_opts.get("backend_names"):
        existing_backends = runtime_opts.get("backend_names")
    elif "backends" in runtime_opts and runtime_opts.get("backends"):
        existing_backends = runtime_opts.get("backends")
    elif "backend_options" in runtime_opts and isinstance(runtime_opts.get("backend_options"), dict):
        existing_backends = list(runtime_opts.get("backend_options").keys())

    # Ensure it's a list
    if not isinstance(existing_backends, list):
        existing_backends = [existing_backends] if existing_backends else []

    # Compose: prepend new backends to existing backends (implements --repro -b behavior)
    # Example: source has ["local"], new ["perf"] → final ["perf", "local"]
    final_backends = list(backends) + list(existing_backends)

    options["backend_names"] = final_backends
    options["backends"] = final_backends

    # Load backend configurations (merges metrics and backend_options)
    # Include mitigations.yaml for mitigation backends, plus standard backend paths
    config_files = [MITIGATIONS_YAML] + resolve_backend_paths(backends)
    load_backend_configs(config_files, options)

    # Override task name
    options["task"] = task_name

    return options


class ProfilingExecutor:
    """
    Handles profiling execution with progress callbacks.

    Separates async execution concerns from UI logic.
    """

    def __init__(
        self,
        md_path: str,
        backends: list[str],
        task_name: str
    ):
        """
        Initialize profiling executor.

        Args:
            md_path: Path to original markdown file
            backends: List of profiling backend names
            task_name: Task name for profiling run
        """
        self.md_path = md_path
        self.backends = backends
        self.task_name = task_name
        self.experiment_name = Path(md_path).parent.name

        # Get expected iterations for progress tracking
        self.total_iterations = extract_repeater_max_from_md(md_path) or 100

        # Callbacks
        self.on_progress: Optional[Callable[[int, int], None]] = None
        self.on_complete: Optional[Callable[[bool, Dict], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None

    def set_callbacks(
        self,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_complete: Optional[Callable[[bool, Dict], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        """
        Set callbacks for execution events.

        Args:
            on_progress: Called with (current_iteration, total_iterations)
            on_complete: Called with (success, result_dict)
            on_error: Called with exception
        """
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error

    def execute(self):
        """
        Execute the profiling run.

        This is a blocking call that runs the orchestrator.
        Should be called from a background thread/task.
        """
        try:
            # Build options
            options = build_orchestrator_options(
                self.md_path,
                self.backends,
                self.task_name
            )

            # Create orchestrator
            orchestrator = ExecutionOrchestrator(
                options=options,
                experiment_name=self.experiment_name
            )

            # Define callbacks
            def on_iteration_start(iteration: int):
                if self.on_progress:
                    self.on_progress(iteration, self.total_iterations)

            def on_iteration_complete(iteration: int, metrics: dict):
                pass  # Could add detailed tracking here

            def on_convergence(status: str):
                pass  # Convergence notification

            def on_error_callback(error: Exception):
                if self.on_error:
                    self.on_error(error)

            callbacks = ProgressCallbacks(
                on_iteration_start=on_iteration_start,
                on_iteration_complete=on_iteration_complete,
                on_convergence=on_convergence,
                on_error=on_error_callback
            )

            # Execute
            result = orchestrator.run(callbacks)

            # Prepare result
            result_dict = {
                "success": result.success,
                "error_message": result.error_message if not result.success else None,
                "output_paths": result.output_paths if result.success else {}
            }

            if self.on_complete:
                self.on_complete(result.success, result_dict)

        except Exception as e:
            print(f"[ERROR] Profiling execution failed: {e}")
            traceback.print_exc()
            if self.on_error:
                self.on_error(e)


def load_profiling_data(prof_csv_path: str) -> Tuple[Any, Optional[str]]:
    """
    Load profiling results from CSV.

    Args:
        prof_csv_path: Path to profiling CSV file

    Returns:
        Tuple of (data, error_message)
        - data: Loaded DataFrame or None if error
        - error_message: Error string or None if successful
    """
    try:
        data = load_csv(prof_csv_path)
        return data, None
    except Exception as e:
        error_msg = f"Error loading profiling results: {str(e)}"
        print(f"[ERROR] {error_msg}")
        traceback.print_exc()
        return None, error_msg
