#!/usr/bin/env python3
"""
SHARP benchmark launcher - run benchmarking experiments.

Delegates to core.execution.orchestrator for actual execution.
Can be invoked standalone or via 'sharp launch' subcommand.

By default, runs silently (no output unless errors occur).
Use --verbose to see progress and results.

Usage:
  launch --experiment EXPERIMENT BENCHMARK [ARGS...]
  launch --list-benchmarks
  launch --list-backends
  launch --show-benchmark NAME
  launch --show-backend NAME

Examples:
  launch -e myexp sleep 1
  launch -e myexp -b perf nope
  launch -e myexp -b local -b perf matmul 1000

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, TypeVar, cast
import yaml

from src.core.repeaters import repeater_factory
from src.core.config.backend_loader import (
    load_backend_configs,
    resolve_backend_paths,
    merge_config,
    BackendChainError
)
from src.core.config.include_resolver import get_project_root

from src.cli import discovery
from src.core.execution.orchestrator import ExecutionOrchestrator, ProgressCallbacks, ExperimentResult
from src.core.config.benchmarks import load_benchmark_data
from src.core.runlogs import extract_runtime_options_from_markdown


def _resolve_entry_point_for_backend(benchmark_name: str, benchmark_data: dict[str, Any],
                                      backends: list[str]) -> str:
    """
    Resolve the appropriate entry point based on selected backends.

    Priority:
    1. If backend_entry_points.appimage exists and backend is local/ssh/mpi, use AppImage
    2. If backend_entry_points.docker exists and backend is docker, use Docker image
    3. Auto-discover built artifacts in build/appimages/ or build/docker/
    4. Fall back to default entry_point

    Args:
        benchmark_name: Name of the benchmark
        benchmark_data: Benchmark definition from YAML
        backends: List of selected backend names

    Returns:
        Resolved entry point path or image name
    """
    backend_entry_points: dict[str, str] = benchmark_data.get("backend_entry_points", {})
    default_entry: str = benchmark_data.get("entry_point", "./benchmark")

    # Determine backend type for entry point selection
    # Docker backend needs container entry point, others use AppImage or default
    uses_docker = "docker" in backends
    uses_container = any(b in backends for b in ["knative", "fission"])

    if uses_docker:
        # Check for explicit docker entry point
        if backend_entry_points.get("docker"):
            return backend_entry_points["docker"]
        # Auto-discover built Docker image
        docker_image = f"sharp-{benchmark_name}:latest"
        # Check if image exists (don't fail if docker not available)
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "images", "-q", docker_image],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return docker_image
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    elif uses_container:
        # Check for explicit container entry point
        if backend_entry_points.get("container"):
            return backend_entry_points["container"]
        # For knative/fission, use benchmark name as function/service name
        return benchmark_name

    else:
        # Local/SSH/MPI backends - prefer AppImage if available
        if backend_entry_points.get("appimage"):
            appimage_path = backend_entry_points["appimage"]
            if Path(appimage_path).exists():
                return appimage_path

        # Auto-discover built AppImage
        project_root = get_project_root()
        discovered_appimage = project_root / "build" / "appimages" / f"{benchmark_name}-x86_64.AppImage"
        if discovered_appimage.exists():
            return str(discovered_appimage)

    # Fall back to default entry point
    return default_entry


def _resolve_benchmark_path(benchmark_name: str) -> dict[str, Any]:
    """
    Resolve benchmark name to executable path following priority order:

    1. If benchmark name is found in YAML discovery, use that benchmark spec
    2. Otherwise, if benchmark name exists in filesystem and is executable, use that path
    3. Otherwise, search for program in $PATH (like shell would)
    4. Otherwise, not found (return empty dict)

    Args:
        benchmark_name: Name or path of benchmark to resolve

    Returns:
        Benchmark data dictionary with entry_point and args keys.
        Returns empty dict {} if benchmark not found anywhere.

    Examples:
        _resolve_benchmark_path("sleep") → {"entry_point": "benchmarks/micro/cpu/sleep.py", "args": [...], ...}
        _resolve_benchmark_path("/bin/ls") → {"entry_point": "/bin/ls", "args": []}
        _resolve_benchmark_path("ls") → {"entry_point": "/usr/bin/ls", "args": []}
        _resolve_benchmark_path("nonexistent") → {}
    """
    # Priority 1: Check if benchmark name is in YAML discovery
    benchmark_map = discovery.get_benchmark_names()
    if benchmark_name in benchmark_map:
        try:
            benchmark_data, _ = load_benchmark_data(benchmark_name)
            return benchmark_data
        except ValueError:
            # Shouldn't happen since we found it in discovery, but fall through if it does
            pass

    # Priority 2: Check if benchmark name exists in filesystem and is executable
    path_obj = Path(benchmark_name)
    if path_obj.exists() and os.access(benchmark_name, os.X_OK):
        # Resolve to absolute path
        abs_path = path_obj.resolve()
        return {"entry_point": str(abs_path), "args": []}

    # Priority 3: Search in $PATH (like shell would)
    which_result = shutil.which(benchmark_name)
    if which_result:
        return {"entry_point": which_result, "args": []}

    # Priority 4: Not found
    return {}


T = TypeVar("T")


def _coalesce_option(cli_value: T | None, config_value: T | None, default: T,
                     *, cli_is_set: bool | None = None) -> T:
    """Return CLI value when provided, else config value, else default."""
    is_set = cli_is_set if cli_is_set is not None else cli_value is not None
    if is_set:
        return cast(T, cli_value)
    if config_value is not None:
        return config_value
    return default


def _resolve_repeats(cli_repeater: str | None, config: dict[str, Any]) -> str:
    """Resolve repeater priority: CLI > config > default (MAX)."""
    cli_value = cli_repeater.upper() if cli_repeater else None
    config_value = config.get("repeater")
    if isinstance(config_value, str):
        config_value = config_value.upper()
    else:
        config_value = None
    return _coalesce_option(cli_value, config_value, "MAX")


def _resolve_backends(args: argparse.Namespace, config: dict[str, Any]) -> list[str]:
    """
    Resolve backend names priority: CLI + config (composition) > config > default (local).

    CLI -b flags ADD to config backend_names (like composition layers).
    Auto-inserted default backend is ignored when config provides explicit backends.

    Args:
        args: Parsed command-line arguments
        config: Configuration dictionary

    Returns:
        List of backend names to use
    """
    config_backends: list[str] = config.get("backend_names", [])
    cli_backends: list[str] = []

    if args.backend:
        auto_backend = getattr(args, "auto_backend", False)
        if auto_backend and config_backends:
            # Ignore auto-inserted backend when config provides explicit ones
            cli_backends = []
        else:
            cli_backends = args.backend

    if cli_backends and config_backends:
        return cli_backends + config_backends
    elif cli_backends:
        return cli_backends
    elif config_backends:
        return config_backends
    else:
        return ["local"]


def load_config_file(filepath: str) -> dict[str, Any]:
    """
    Load configuration from a YAML or JSON file.

    Args:
        filepath: Path to config file

    Returns:
        Dictionary containing configuration
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {filepath}")

    with open(path, 'r') as f:
        if filepath.endswith('.yaml') or filepath.endswith('.yml'):
            data = yaml.safe_load(f) or {}
        elif filepath.endswith('.json'):
            data = json.load(f)
        else:
            raise ValueError(f"Unsupported config file format: {filepath}")

    if isinstance(data, dict):
        return data
    return {}


def load_repro_file(filepath: str) -> dict[str, Any]:
    """
    Load configuration from a previous run's markdown file.

    Args:
        filepath: Path to markdown file

    Returns:
        Dictionary containing configuration

    Raises:
        FileNotFoundError: If repro file doesn't exist
        ValueError: If runtime options cannot be extracted
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Repro file not found: {filepath}")

    runtime_opts = extract_runtime_options_from_markdown(path)
    if runtime_opts is None:
        raise ValueError(f"Could not extract runtime options from {filepath}")

    return runtime_opts





def build_config_from_sources(args: argparse.Namespace) -> dict[str, Any]:
    """
    Build configuration dictionary from all sources (repro, config files, JSON, CLI args).

    Priority (lowest to highest): --repro < --config files < --json < CLI args

    Config files are resolved with includes before merging.

    Args:
        args: Parsed command-line arguments

    Returns:
        Merged configuration dictionary
    """
    from src.core.config.include_resolver import resolve_includes

    config: dict[str, Any] = {}

    # 1. Load from --repro file (lowest priority) - loads entire options dict
    if args.repro:
        config = load_repro_file(args.repro)

    # 2. Load from --config files (can specify multiple, naturally override repro)
    # Files are resolved with includes before merging
    if args.config:
        for config_file in args.config:
            resolved_config = resolve_includes(config_file)
            merge_config(config, resolved_config)

    # 4. Load from --json inline string (naturally overrides config files)
    if args.json:
        merge_config(config, json.loads(args.json))

    # 5. Process CLI args (highest priority) - these naturally override everything
    if args.task:
        config["task"] = args.task

    return config


def load_backend_options(backend_names: list[str], config: dict[str, Any]) -> dict[str, Any]:
    """
    Load backend options, auto-loading YAML files for all backends.

    Backend YAML files are loaded first, then user-provided options (from -j or config files)
    are merged on top. This allows users to override specific options (like hosts) while
    keeping the base configuration (like run template) from the YAML files.

    Args:
        backend_names: List of backend names
        config: Base configuration dictionary (modified in-place)

    Returns:
        Backend options dictionary
    """
    # Save user-provided backend options to merge on top of YAML configs
    user_backend_options = config.get("backend_options", {}).copy()

    # Clear backend_options so YAML files are loaded fresh
    config["backend_options"] = {}

    # Load all backend YAML files
    load_backend_configs(resolve_backend_paths(backend_names), config)

    # Merge user options on top (user options take priority)
    for backend_name, user_options in user_backend_options.items():
        if backend_name in config["backend_options"]:
            merge_config(config["backend_options"][backend_name], user_options)
        else:
            config["backend_options"][backend_name] = user_options

    options = config.get("backend_options", {})
    if isinstance(options, dict):
        return options
    return {}


def build_orchestrator_options(args: argparse.Namespace, config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Build options dictionary for ExecutionOrchestrator from CLI args and config.

    Args:
        args: Parsed command-line arguments
        config: Configuration from files/JSON

    Returns:
        Options dictionary for orchestrator
    """
    options: dict[str, Any] = {}

    # Backend configuration
    backend_names = _resolve_backends(args, config)
    options["backend_names"] = backend_names
    options["backend_options"] = load_backend_options(backend_names, config)

    # Timeout
    options["timeout"] = _coalesce_option(args.timeout, config.get("timeout"), 3600)

    # Verbose
    options["verbose"] = _coalesce_option(True if args.verbose else None, config.get("verbose"), False,
                                            cli_is_set=args.verbose)

    # Output directory - CLI flag > config.options.directory > config.directory > default
    # Check both locations for backward compatibility
    config_directory = config.get("options", {}).get("directory") or config.get("directory")
    options["directory"] = _coalesce_option(args.directory, config_directory, "runlogs")

    # Start type (cold, warm, or normal)
    cli_start = "cold" if args.cold else "warm" if args.warm else None
    options["start"] = _coalesce_option(cli_start, config.get("start"), "normal",
                                         cli_is_set=args.cold or args.warm)

    # File write mode (write/truncate or append)
    options["mode"] = _coalesce_option("a" if args.append else None, config.get("mode"), "w",
                                         cli_is_set=args.append)

    # System spec commands
    options["sys_spec_commands"] = config.get("sys_spec_commands", {})
    options["skip_sys_specs"] = _coalesce_option(True if args.skip_sys_specs else None,
                                                  config.get("skip_sys_specs"), False,
                                                  cli_is_set=args.skip_sys_specs)

    # Load benchmark data and get metrics (skip if entry_point already in config)
    if "entry_point" in config or "benchmark_spec" in config:
        # Using repro or config with embedded entry_point/benchmark_spec
        benchmark_data: dict[str, Any] = {}
        benchmark_metrics: dict[str, Any] = {}
    elif args.benchmark:
        # Resolve benchmark name/path using priority logic
        benchmark_data = _resolve_benchmark_path(args.benchmark)
        if not benchmark_data:
            raise ValueError(f"Benchmark '{args.benchmark}' not found in YAML discovery, filesystem, or $PATH")

        # Get metrics from YAML if this was a YAML benchmark
        # Try by name first, then by entry_point path (for absolute paths)
        if args.benchmark in discovery.get_benchmark_names():
            _, benchmark_metrics = load_benchmark_data(args.benchmark)
        else:
            # Try reverse lookup by entry_point (handles absolute paths from --repro)
            try:
                from src.core.config.benchmarks import find_benchmark_by_entry_point
                parts = args.benchmark.split(maxsplit=1)
                entry_point = parts[0]
                _, _, benchmark_metrics = find_benchmark_by_entry_point(entry_point)
            except (ValueError, Exception):
                # Not a known benchmark, no metrics to load
                benchmark_metrics = {}
    else:
        benchmark_data = {}
        benchmark_metrics = {}

    # Metrics priority: config (backends) + benchmark file (merge, benchmark wins on conflict)
    # Store as "metrics" (not "metric_specs") to match what gets saved/loaded
    options["metrics"] = config.get("metrics", {}) | benchmark_metrics

    # Multiprogramming level / copies (CLI overrides config, default=1)
    config_copies = config.get("copies") or config.get("mpl")
    options["mpl"] = _coalesce_option(args.copies, config_copies, 1)

    # Environment variables (from config)
    options["environment"] = config.get("environment", {})

    # Description (from CLI or config)
    if hasattr(args, 'description') and args.description:
        options["description"] = args.description
    elif "description" in config:
        options["description"] = config["description"]

    return options, benchmark_data


def build_benchmark_spec(args: argparse.Namespace, benchmark_data: dict[str, Any],
                         config: dict[str, Any], backends: list[str] | None = None) -> dict[str, Any]:
    """
    Build benchmark specification from CLI args, config, and benchmark data.

    The entry_point is resolved based on selected backends:
    - For docker backend: uses Docker image name
    - For local/ssh/mpi: prefers AppImage if available, else source script
    - Auto-discovers built artifacts in build/ directory

    Args in YAML are default arguments, used only if no CLI args provided.

    Example:
      YAML: entry_point="./matmul", args=["1000"]
      CLI: launch matmul → uses YAML args ["1000"]
      CLI: launch matmul 500 → uses CLI args ["500"], ignores YAML args

    Args:
        args: Parsed command-line arguments
        benchmark_data: Benchmark definition from YAML
        config: Configuration from files/JSON
        backends: List of selected backend names (default: ["local"])

    Returns:
        Benchmark spec dictionary for ExecutionOrchestrator
    """
    benchmark_spec: dict[str, Any] = {}

    # Default backends if not provided
    if backends is None:
        backends = ["local"]

    # Task name: use benchmark name (not full path)
    # Priority: config "task" > benchmark name from CLI > experiment name
    benchmark_spec["task"] = config.get("task") or args.benchmark or args.experiment

    # Resolve entry point based on backend
    # Priority: config "entry_point" (via -j) > auto-resolve based on backend
    # This allows overriding the entry point for remote backends (SSH, SLURM)
    # where the executable may be at a different path than on the local system.
    # Example: -j '{"entry_point": "/remote/path/to/benchmark.AppImage"}'
    if config.get("entry_point"):
        benchmark_spec["entry_point"] = config["entry_point"]
    else:
        benchmark_spec["entry_point"] = _resolve_entry_point_for_backend(
            args.benchmark or "benchmark",
            benchmark_data,
            backends
        )

    # CLI args replace YAML args if provided, otherwise use YAML args as defaults
    if args.benchmark_args:
        benchmark_spec["args"] = args.benchmark_args
    else:
        benchmark_spec["args"] = benchmark_data.get("args", [])

    return benchmark_spec


def create_repeater(args: argparse.Namespace, config: dict[str, Any]) -> Any:
    """
    Create repeater instance from CLI args and config.

    Args:
        args: Parsed command-line arguments
        config: Configuration from files/JSON

    Returns:
        Repeater instance
    """
    # Map CLI repeater name to options format
    repeater_config = {
        "repeats": _resolve_repeats(args.repeater, config),
        "repeater_options": config.get("repeater_options", {})
    }

    return repeater_factory(repeater_config)


def create_progress_callbacks(verbose: bool) -> ProgressCallbacks:
    """
    Create progress callback functions for experiment execution.

    Args:
        verbose: Whether to enable verbose output

    Returns:
        ProgressCallbacks object with callback functions
    """
    def on_iteration_start(iteration: int) -> None:
        if verbose:
            print(f"\n=== Iteration {iteration} ===")

    def on_iteration_complete(iteration: int, data: Any) -> None:
        if verbose:
            print(f"Iteration {iteration} complete")

    def on_convergence(reason: str) -> None:
        if verbose:
            print(f"\nConvergence detected: {reason}")

    def on_error(error: Exception) -> None:
        print(f"\n✗ Error running experiment: {error}", file=sys.stderr)

    return ProgressCallbacks(
        on_iteration_start=on_iteration_start,
        on_iteration_complete=on_iteration_complete,
        on_convergence=on_convergence,
        on_error=on_error
    )


def resolve_benchmark_spec(args: argparse.Namespace, config: dict[str, Any],
                           backends: list[str] | None = None) -> dict[str, Any]:
    """
    Resolve benchmark specification from CLI args or config files.

    Resolution order:
    1. CLI: args.benchmark → resolve via _resolve_benchmark_path() → build_benchmark_spec()
       - Unless config already has entry_point (repro mode), then use empty benchmark_data
    2. Config: config["entry_point"] → return as spec directly (repro file pattern)
    3. Config: config["benchmark_spec"] → return as-is (legacy pattern)
    4. Error: No benchmark found anywhere

    Sets args.benchmark = "repro" when using config patterns so other code doesn't break.

    Args:
        args: Parsed command-line arguments
        config: Configuration dictionary from all sources (repro/config files/JSON)
        backends: List of backend names for entry point resolution

    Returns:
        Benchmark specification dict with entry_point, args, and task keys

    Raises:
        ValueError: If no benchmark information can be determined
    """
    # Default backends if not provided
    if backends is None:
        backends = _resolve_backends(args, config)

    # Case 1: Benchmark name provided on command line
    if args.benchmark:
        # Skip resolution if config already has entry_point (repro mode - config overrides CLI)
        if "entry_point" in config or "benchmark_spec" in config:
            benchmark_data = {}
        else:
            benchmark_data = _resolve_benchmark_path(args.benchmark)
            if not benchmark_data:
                raise ValueError(f"Benchmark '{args.benchmark}' not found in YAML discovery, filesystem, or $PATH")
        return build_benchmark_spec(args, benchmark_data, config, backends)

    # Case 2: Config has entry_point directly (repro file pattern: entry_point, args, task at top level)
    if "entry_point" in config:
        # NOTE: Don't set args.benchmark = "repro" here - it mutates shared state and breaks sweep iterations
        # Prioritize args in options (sweep expansion), fall back to top level
        benchmark_args = []
        if "options" in config and "args" in config["options"]:
            benchmark_args = config["options"]["args"]
        elif "args" in config:
            benchmark_args = config["args"]

        return {
            "entry_point": config["entry_point"],
            "args": benchmark_args,
            "task": config.get("task") or config.get("name") or args.experiment,
        }

    # Case 3: Config has benchmark_spec key (legacy pattern: benchmark_spec as nested dict)
    if "benchmark_spec" in config:
        benchmark_spec = config["benchmark_spec"]
        if isinstance(benchmark_spec, dict):
            if not benchmark_spec.get("entry_point"):
                raise ValueError("benchmark_spec in config is missing entry_point")
            return benchmark_spec

    # Case 4: No benchmark information found anywhere
    raise ValueError("No benchmark specified (use BENCHMARK argument or provide entry_point in config)")


def print_experiment_info(args: argparse.Namespace, benchmark_spec: dict[str, Any]) -> None:
    """Print experiment information if verbose mode is enabled."""
    if not args.verbose:
        return

    print(f"Running experiment: {args.experiment}")
    print(f"  Backend(s): {', '.join(args.backend)}")
    print(f"  Benchmark: {args.benchmark}")
    print(f"  Repeater: {args.repeater}")
    if args.benchmark_args:
        print(f"  Args: {' '.join(args.benchmark_args)}")
    print()


def print_experiment_result(result: ExperimentResult, verbose: bool) -> int:
    """
    Print experiment results and return exit code.

    Args:
        result: Experiment result from orchestrator
        verbose: Whether to print verbose output

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    if result.success:
        if verbose:
            print("\n✓ Experiment completed successfully")
            print(f"  Iterations: {result.iteration_count}")
            print(f"  Metrics collected: {len(result.metrics)}")
        return 0
    else:
        print("\n✗ Experiment failed")
        print(f"  Error: {result.error_message}")
        return 1


def run_parameter_sweep(args: argparse.Namespace, config: dict[str, Any]) -> int:
    """
    Run a parameter sweep experiment.

    Sweep is an inline dict with args/env/options keys.
    For external files, use include directive with a file containing sweep: key.

    Args:
        args: Parsed command-line arguments
        config: Merged config containing 'sweep' field (inline dict)

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    from src.core.config.schema import ExperimentConfig, SweepConfig
    from src.core.execution.parameter_space import CartesianSweepStrategy

    if args.verbose:
        print("\n=== Parameter Sweep ===")

    # Remove sweep from base config so it doesn't interfere
    base_config_dict = config.copy()
    sweep_dict = base_config_dict.pop('sweep')

    # Parse base config and sweep config with validation
    try:
        base_config = ExperimentConfig(**base_config_dict)
        sweep_config = SweepConfig(**sweep_dict)
    except Exception as e:
        print(f"\n✗ Error parsing configuration: {e}", file=sys.stderr)
        return 1

    # Create strategy and generate all configurations
    strategy = CartesianSweepStrategy(base_config, sweep_config)
    try:
        configurations = strategy.generate_configurations()
    except Exception as e:
        print(f"\n✗ Error generating sweep configurations: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    if args.verbose:
        print(f"Total configurations: {len(configurations)}")

    # Run each configuration
    all_success = True
    for i, (launch_id, exp_config, parameters) in enumerate(configurations):
        if args.verbose:
            print(f"\n--- Running {launch_id} ---")

        # Convert config to dict for run_experiment_with_config
        config_dict = exp_config.model_dump()

        # For sweeps, use append mode starting from second run to accumulate results
        if i >= 1:
            config_dict["mode"] = "a"

        # Use parameters dict directly (already extracted by strategy)
        sweep_params = parameters

        # Run the experiment with this specific config
        try:
            exit_code = run_experiment_with_config(args, config_dict, launch_id, sweep_params)
            if exit_code != 0:
                all_success = False
                if not args.verbose:
                    print(f"✗ {launch_id} failed")
        except Exception as e:
            print(f"\n✗ Error in {launch_id}: {e}", file=sys.stderr)
            all_success = False

    if args.verbose:
        print("\n=== Sweep Complete ===")
        print(f"Configurations run: {len(configurations)}")
        print(f"Status: {'✓ All succeeded' if all_success else '✗ Some failed'}")

    return 0 if all_success else 1


def run_experiment_with_config(args: argparse.Namespace, config: dict[str, Any],
                                launch_id: str | None = None,
                                sweep_params: dict[str, Any] | None = None) -> int:
    """
    Run a single experiment with a specific configuration.

    Args:
        args: Parsed command-line arguments
        config: Experiment configuration dict
        launch_id: Optional launch identifier for sweep runs
        sweep_params: Optional sweep parameters for this specific run (added as invariants)

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    try:
        benchmark_spec = resolve_benchmark_spec(args, config)
        options, _ = build_orchestrator_options(args, config)

        # Merge benchmark spec into options (V3 pattern - everything in options)
        options["entry_point"] = benchmark_spec["entry_point"]
        options["args"] = benchmark_spec.get("args", [])
        options["task"] = benchmark_spec.get("task", args.experiment)

        # Add repeater config to options (V3 pattern)
        options["repeats"] = _resolve_repeats(args.repeater, config)
        options["repeater_options"] = config.get("repeater_options", {})

        # Add launch_id if provided (for sweep tracking)
        if launch_id:
            options["launch_id"] = launch_id

        # Add sweep params as regular invariants if provided
        if sweep_params:
            options["sweep_params"] = sweep_params

        # Create orchestrator
        orchestrator = ExecutionOrchestrator(
            options=options,
            experiment_name=args.experiment
        )

        # Print experiment info if verbose
        if args.verbose and not launch_id:
            print_experiment_info(args, benchmark_spec)

        # Create progress callbacks and run experiment
        callbacks = create_progress_callbacks(args.verbose)
        result = orchestrator.run(callbacks)

        # Print results and return exit code
        if args.verbose or not launch_id:
            return print_experiment_result(result, args.verbose)
        else:
            # Silent mode for sweep - just return exit code
            return 0 if result.success else 1

    except BackendChainError as e:
        print(f"\n✗ Backend Composition Error: {e}", file=sys.stderr)
        print("\nBackend composition rules:", file=sys.stderr)
        print("  • Composable backends can appear anywhere in the chain", file=sys.stderr)
        print("  • Non-composable backends must be leftmost (first in -b list)", file=sys.stderr)
        print("\nExamples:", file=sys.stderr)
        print("  Valid:   -b local", file=sys.stderr)
        print("  Valid:   -b perf -b local", file=sys.stderr)
        print("  Valid:   -b mpip", file=sys.stderr)
        print("  Invalid: -b perf -b mpip  (mpip is non-composable, must be leftmost)", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n✗ Error running experiment: {e}")
        import traceback
        if hasattr(args, 'verbose') and args.verbose:
            traceback.print_exc()
        return 1


def run_experiment(args: argparse.Namespace) -> int:
    """
    Run a benchmarking experiment using the orchestrator.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    try:
        config = build_config_from_sources(args)
        return run_experiment_with_config(args, config)
    except Exception as e:
        print(f"\n✗ Error loading configuration: {e}", file=sys.stderr)
        if hasattr(args, 'verbose') and args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def list_repeaters() -> int:
    """
    List all available repeater strategies with one-line descriptions.

    Returns:
        Exit code (always 0)
    """
    from src.core.repeaters import REPEATER_REGISTRY

    print("\nAvailable Repeater Strategies:\n")
    print(f"{'Name':<20} {'Description'}")
    print("-" * 80)

    for name, metadata in sorted(REPEATER_REGISTRY.items()):
        desc = metadata["description"]
        # Truncate description if too long
        if len(desc) > 57:
            desc = desc[:54] + "..."
        # Add aliases if present
        display_name = name
        if "aliases" in metadata and metadata["aliases"]:
            aliases_str = " / ".join(metadata["aliases"])
            display_name = f"{name} / {aliases_str}"
        print(f"{display_name:<20} {desc}")

    print()
    return 0


def show_repeater(name: str) -> int:
    """
    Show detailed information about a specific repeater strategy.

    Args:
        name: Repeater name (e.g., 'RSE', 'CI', 'COUNT', 'MAX')

    Returns:
        Exit code (0 for success, 1 if repeater not found)
    """
    from src.core.repeaters import REPEATER_REGISTRY

    name_upper = name.upper()

    # Check if it's an alias
    actual_name = None
    for primary_name, metadata in REPEATER_REGISTRY.items():
        if name_upper == primary_name:
            actual_name = primary_name
            break
        if "aliases" in metadata:
            if name_upper in metadata["aliases"]:
                actual_name = primary_name
                break

    if actual_name is None:
        print(f"\n✗ Error: Repeater '{name}' not found", file=sys.stderr)
        print("\nAvailable repeaters:")
        for repeater_name in sorted(REPEATER_REGISTRY.keys()):
            aliases = REPEATER_REGISTRY[repeater_name].get("aliases", [])
            if aliases:
                print(f"  - {repeater_name} (aliases: {', '.join(aliases)})")
            else:
                print(f"  - {repeater_name}")
        print()
        return 1

    metadata = REPEATER_REGISTRY[actual_name]
    desc = metadata["description"]
    defaults = metadata["defaults"]

    # Format the title with name and aliases
    title = actual_name
    if "aliases" in metadata and metadata["aliases"]:
        aliases_str = " / ".join(metadata["aliases"])
        title = f"{actual_name} / {aliases_str}"

    print(f"\n{'='*80}")
    print(f"Repeater: {title}")
    print(f"{'='*80}")
    print(f"\nDescription: {desc}\n")

    if defaults:
        print("Options:")
        print(f"  {'Option':<30} {'Type':<10} {'Default':<15} {'Help'}")
        print(f"  {'-'*30} {'-'*10} {'-'*15} {'-'*30}")

        for option_name, option_info in sorted(defaults.items()):
            default_val = option_info["default"]
            option_type = option_info["type"].__name__
            help_text = option_info["help"]

            # Format default value for display
            if isinstance(default_val, list):
                default_str = str(default_val)
                if len(default_str) > 15:
                    default_str = default_str[:12] + "..."
            else:
                default_str = str(default_val)

            print(f"  {option_name:<30} {option_type:<10} {default_str:<15} {help_text}")
    else:
        print("No configurable options.")

    print()
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Parse command-line arguments.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="SHARP benchmark launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available benchmarks and backends
  launch --list-benchmarks
  launch --list-backends

  # Show benchmark/backend details
  launch --show-benchmark micro/sleep
  launch --show-backend local

  # Run an experiment
  launch -e myexp -b local -r count micro/sleep
  launch -e test -b local -r ci micro/matmul 1000 1000

  # Run with verbosity
  launch -v -e debug -b local -r count micro/sleep
        """.strip()
    )

    # Discovery commands
    discovery = parser.add_argument_group("discovery")
    discovery.add_argument(
        "--list-benchmarks",
        action="store_true",
        help="List all available benchmarks"
    )
    discovery.add_argument(
        "--show-benchmark",
        metavar="NAME",
        help="Show details of a specific benchmark"
    )
    discovery.add_argument(
        "--list-backends",
        action="store_true",
        help="List all available backends"
    )
    discovery.add_argument(
        "--show-backend",
        metavar="NAME",
        help="Show details of a specific backend"
    )
    discovery.add_argument(
        "--list-repeaters",
        action="store_true",
        help="List all available repeater strategies"
    )
    discovery.add_argument(
        "--show-repeater",
        metavar="NAME",
        help="Show details of a specific repeater strategy"
    )

    # Experiment configuration
    experiment = parser.add_argument_group("experiment configuration")
    experiment.add_argument(
        "-e", "--experiment",
        metavar="NAME",
        default="misc",
        help="Experiment name (for output directory, default: misc)"
    )
    experiment.add_argument(
        "-b", "--backend",
        action="append",
        default=[],
        help="Backend to use (can specify multiple, e.g., -b perf -b local)"
    )
    experiment.add_argument(
        "-r", "--repeater",
        default=None,
        help="Repeater strategy (default: MAX)"
    )

    # Start mode (mutually exclusive)
    start_mode = experiment.add_mutually_exclusive_group()
    start_mode.add_argument(
        "-c", "--cold",
        action="store_true",
        help="Cold start: execute reset command before each iteration"
    )
    start_mode.add_argument(
        "-w", "--warm",
        action="store_true",
        help="Warm start: run benchmark once before measurements to warm up caches"
    )

    experiment.add_argument(
        "-t", "--task",
        metavar="NAME",
        help="Task name for output file (defaults to experiment name)"
    )

    # Configuration options
    config = parser.add_argument_group("configuration")
    config.add_argument(
        "-f", "--config",
        action="append",
        metavar="FILE",
        help="Load additional YAML/JSON config file (can specify multiple)"
    )
    config.add_argument(
        "-j", "--json",
        metavar="STRING",
        help="Inline JSON config override"
    )
    config.add_argument(
        "--repro",
        metavar="FILE.md",
        help="Reproduce experiment from previous markdown output"
    )

    # Execution options
    execution = parser.add_argument_group("execution options")
    execution.add_argument(
        "--timeout",
        type=int,
        metavar="SECONDS",
        help="Global timeout in seconds (default: 3600)"
    )
    execution.add_argument(
        "--copies",
        type=int,
        metavar="N",
        help="Number of concurrent copies to run (multiprogramming level)"
    )
    execution.add_argument(
        "--mpl",
        type=int,
        metavar="N",
        dest="copies",
        help="Alias for --copies (multiprogramming level)"
    )

    # Output options
    output = parser.add_argument_group("output options")
    output.add_argument(
        "-d", "--directory",
        metavar="DIR",
        help="Output directory (default: runlogs/)"
    )
    output.add_argument(
        "-a", "--append",
        action="store_true",
        help="Append to existing run data instead of overwrite"
    )

    # General options
    options = parser.add_argument_group("general options")
    options.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    options.add_argument(
        "--skip-sys-specs",
        action="store_true",
        help="Skip system specification collection (faster for testing)"
    )
    options.add_argument(
        "--description", "--desc",
        metavar="TEXT",
        help="Description of the experiment/task for documentation"
    )

    # Positional arguments (must be at the end)
    parser.add_argument(
        "benchmark",
        nargs="?",
        metavar="BENCHMARK",
        help="Benchmark to run (without .yaml extension)"
    )
    parser.add_argument(
        "benchmark_args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to the benchmark"
    )

    args = parser.parse_args(argv)

    # Validate discovery mode exclusivity: discovery flags cannot be combined with experiment options
    discovery_flags = [args.list_benchmarks, args.show_benchmark,
                       args.list_backends, args.show_backend,
                       args.list_repeaters, args.show_repeater]

    if any(discovery_flags):
        # Discovery mode: verify no experiment arguments were provided
        experiment_args = [args.benchmark, args.backend, args.config,
                          args.json, args.repro]
        if any(experiment_args):
            parser.error(
                "Discovery flags (--list-*, --show-*) are mutually exclusive with experiment options.\n"
                "Cannot combine discovery with: BENCHMARK, -b/--backend, -f/--config, -j/--json, --repro"
            )
    else:
        # Experiment mode: set default backend if not specified
        if not args.backend:
            args.backend = ["local"]
            args.auto_backend = True
        else:
            args.auto_backend = False
    if not hasattr(args, "auto_backend"):
        args.auto_backend = False

    return args


def validate_experiment_args(args: argparse.Namespace) -> int | None:
    """
    Validate arguments for running an experiment.

    Args:
        args: Parsed command-line arguments

    Returns:
        None if validation passes, otherwise error code
    """
    if not args.experiment:
        print("Error: --experiment is required when running an experiment", file=sys.stderr)
        print("Use --help for usage information", file=sys.stderr)
        return 1

    # When using --repro or config files, benchmark can come from configuration
    if not args.benchmark and not args.repro and not args.config:
        print("Error: --benchmark is required when running an experiment", file=sys.stderr)
        print("Use --help for usage information", file=sys.stderr)
        return 1

    return None


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for the launch command.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    args = parse_args(argv)

    # Handle discovery commands
    if args.list_benchmarks:
        return discovery.list_benchmarks()

    if args.show_benchmark:
        return discovery.show_benchmark(args.show_benchmark)

    if args.list_backends:
        return discovery.list_backends()

    if args.show_backend:
        return discovery.show_backend(args.show_backend)

    if args.list_repeaters:
        return list_repeaters()

    if args.show_repeater:
        return show_repeater(args.show_repeater)

    # Build merged config from all sources
    try:
        config = build_config_from_sources(args)
    except Exception as e:
        print(f"\n✗ Error loading configuration: {e}", file=sys.stderr)
        return 1

    # Use config name as experiment name if provided (and not overridden by CLI -e flag)
    # CLI -e flag has priority, then config name, then default "misc"
    if 'name' in config and args.experiment == "misc":  # "misc" is the default
        args.experiment = config['name']

    # Check if config contains a parameter sweep (Task 4.10)
    if 'sweep' in config and config['sweep']:
        return run_parameter_sweep(args, config)

    # Check if merged config contains a workflow (Phase 4: minimal sequential workflows)
    # 'workflow' and 'task' are mutually exclusive at top-level
    if 'workflow' in config:
        if 'task' in config:
            print("\n✗ Error: 'workflow' and 'task' are mutually exclusive at top-level", file=sys.stderr)
            return 1
        # This is a workflow - delegate to workflow module
        from src.cli import workflow

        # Determine base directory for resolving relative task paths
        # If loading from a single config file, use that file's directory
        # Otherwise, use current directory
        base_dir = None
        if args.config and len(args.config) == 1 and not args.json:
            base_dir = Path(args.config[0]).parent

        # Pass config dict directly - no temp file needed!
        return workflow.run_workflow(config, args.verbose, base_dir=base_dir)

    # Validate experiment arguments for regular task execution
    error_code = validate_experiment_args(args)
    if error_code is not None:
        return error_code

    # Run regular task
    return run_experiment(args)


if __name__ == "__main__":
    sys.exit(main())
