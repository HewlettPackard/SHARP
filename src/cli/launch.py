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
import sys
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from src.core.repeaters import repeater_factory

from src.cli import discovery
from src.core.execution.orchestrator import ExecutionOrchestrator, ProgressCallbacks, ExperimentResult


def load_config_file(filepath: str) -> Dict[str, Any]:
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
            return yaml.safe_load(f) or {}
        elif filepath.endswith('.json'):
            return json.load(f)
        else:
            raise ValueError(f"Unsupported config file format: {filepath}")


def load_repro_file(filepath: str) -> Dict[str, Any]:
    """
    Load configuration from a previous run's markdown file.

    Args:
        filepath: Path to markdown file

    Returns:
        Dictionary containing configuration
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Repro file not found: {filepath}")

    # Extract JSON block from markdown
    copy_now = False
    json_str = ""

    with open(path, 'r') as f:
        for line in f:
            if line.strip() == "## Runtime options":
                copy_now = True
            elif line.strip() == "## Field description":
                break
            elif copy_now:
                # Skip code block markers
                if line.strip() in ["```json", "```"]:
                    continue
                json_str += line

    return json.loads(json_str)


def merge_config(base: Dict[str, Any], updates: Dict[str, Any]) -> None:
    """
    Merge updates into base configuration (in-place).

    Args:
        base: Base configuration dictionary
        updates: Updates to merge
    """
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            merge_config(base[key], value)
        else:
            base[key] = value


def build_config_from_sources(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Build configuration dictionary from all sources (repro, config files, JSON, CLI args).

    Priority (lowest to highest): --repro < --config files < --json < CLI args

    Args:
        args: Parsed command-line arguments

    Returns:
        Merged configuration dictionary
    """
    config: Dict[str, Any] = {}

    # 1. Load from --repro file (lowest priority) - loads entire options dict
    if args.repro:
        config = load_repro_file(args.repro)

    # 2. Load system spec commands (unless --skip-sys-specs) before user config files
    if not args.skip_sys_specs and "sys_spec_commands" not in config:
        project_root = Path(__file__).parent.parent.parent
        sys_spec_file = project_root / "sys_spec.yaml"
        if sys_spec_file.exists():
            sys_spec_config = load_config_file(str(sys_spec_file))
            if "sys_spec_commands" in sys_spec_config:
                config["sys_spec_commands"] = sys_spec_config["sys_spec_commands"]

    # 3. Load from --config files (can specify multiple, naturally override repro)
    if args.config:
        for config_file in args.config:
            merge_config(config, load_config_file(config_file))

    # 4. Load from --json inline string (naturally overrides config files)
    if args.json:
        merge_config(config, json.loads(args.json))

    # 5. Process CLI args (highest priority) - these naturally override everything
    if args.task:
        config["task"] = args.task

    return config


def load_backend_options(backend_names: list[str], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load backend options, auto-loading YAML files for backends not in config.

    Args:
        backend_names: List of backend names
        config: Base configuration dictionary (modified in-place)

    Returns:
        Backend options dictionary
    """
    if "backend_options" not in config:
        config["backend_options"] = {}

    # Auto-load backend YAML files for any backends that don't have options yet
    project_root = Path(__file__).parent.parent.parent
    backends_dir = project_root / "backends"

    for backend_name in backend_names:
        if backend_name not in config["backend_options"]:
            backend_file = backends_dir / f"{backend_name}.yaml"
            if backend_file.exists():
                backend_config = load_config_file(str(backend_file))
                merge_config(config, backend_config)

    return config.get("backend_options", {})


def load_benchmark_data(benchmark_name: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Load benchmark data from YAML files.

    Args:
        benchmark_name: Name of the benchmark to load

    Returns:
        Tuple of (benchmark_data, metrics) where benchmark_data is the benchmark
        definition and metrics is the metrics dict from the YAML file

    Raises:
        ValueError: If benchmark not found
    """
    project_root = Path(__file__).parent.parent.parent
    benchmarks_dir = project_root / "benchmarks"

    # Find the benchmark file
    benchmark_files = list(benchmarks_dir.rglob("*/*.yaml"))

    for bfile in benchmark_files:
        try:
            with open(bfile, 'r') as f:
                data = yaml.safe_load(f)

            if data and "benchmarks" in data and benchmark_name in data["benchmarks"]:
                benchmark_data = data["benchmarks"][benchmark_name].copy()
                metrics = data.get("metrics", {})

                # Resolve entry_point relative to YAML file directory
                if "entry_point" in benchmark_data:
                    entry_point = benchmark_data["entry_point"]
                    if entry_point.startswith("./") or entry_point.startswith("../"):
                        # Relative path - resolve relative to YAML file directory
                        yaml_dir = bfile.parent
                        abs_path = (yaml_dir / entry_point).resolve()
                        benchmark_data["entry_point"] = str(abs_path)

                return benchmark_data, metrics

        except (yaml.YAMLError, IOError):
            continue

    raise ValueError(f"Benchmark '{benchmark_name}' not found in any YAML file")


def build_orchestrator_options(args: argparse.Namespace, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build options dictionary for ExecutionOrchestrator from CLI args and config.

    Args:
        args: Parsed command-line arguments
        config: Configuration from files/JSON

    Returns:
        Options dictionary for orchestrator
    """
    options: Dict[str, Any] = {}

    # Backend configuration
    # CLI -b flags ADD to config backend_names (like composition layers)
    # If no -b flags and no config backends, default to 'local'
    config_backends = config.get("backend_names", [])
    cli_backends = args.backend if args.backend else []

    # Combine: config backends (from repro/files) + CLI backends
    if cli_backends:
        backend_names = config_backends + cli_backends
    elif config_backends:
        backend_names = config_backends
    else:
        backend_names = ["local"]

    options["backend_names"] = backend_names
    options["backend_options"] = load_backend_options(backend_names, config)

    # Timeout
    options["timeout"] = args.timeout if args.timeout else config.get("timeout", 3600)

    # Verbose
    options["verbose"] = args.verbose

    # Output directory - CLI flag > config > default
    options["directory"] = args.directory if args.directory else config.get("directory", "runlogs")

    # Start type (cold, warm, or normal)
    if args.cold:
        options["start"] = "cold"
    elif args.warm:
        options["start"] = "warm"
    else:
        options["start"] = config.get("start", "normal")

    # File write mode (write/truncate or append)
    options["mode"] = config.get("mode", "w")

    # System spec commands
    options["sys_spec_commands"] = config.get("sys_spec_commands", {})
    options["skip_sys_specs"] = args.skip_sys_specs

    # Load benchmark data and get metrics (skip if benchmark_spec already in config)
    if "benchmark_spec" in config:
        # Using repro or config with embedded benchmark_spec
        benchmark_data = {}
        benchmark_metrics = {}
    else:
        # Load from YAML files
        benchmark_data, benchmark_metrics = load_benchmark_data(args.benchmark)

    # Metrics priority: benchmark file > config
    # Store as "metrics" (not "metric_specs") to match what gets saved/loaded
    options["metrics"] = benchmark_metrics or config.get("metrics", {})

    return options, benchmark_data


def build_benchmark_spec(args: argparse.Namespace, benchmark_data: Dict[str, Any],
                         config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build benchmark specification from CLI args, config, and benchmark data.

    The entry_point in YAML should be the executable path (with shebang).
    Args in YAML are default arguments, which can be extended via CLI.

    Examples:
      YAML: entry_point="./nope.py", args=[]
      YAML: entry_point="./matmul", args=["1000"]

    Args:
        args: Parsed command-line arguments
        benchmark_data: Benchmark definition from YAML
        config: Configuration from files/JSON

    Returns:
        Benchmark spec dictionary for ExecutionOrchestrator
    """
    benchmark_spec: Dict[str, Any] = {}

    # Task name priority: config "task" > benchmark name > experiment name
    benchmark_spec["task"] = config.get("task") or args.benchmark or args.experiment

    benchmark_spec["entry_point"] = benchmark_data.get("entry_point", "./benchmark")
    benchmark_spec["args"] = benchmark_data.get("args", []) + (args.benchmark_args or [])

    return benchmark_spec


def create_repeater(args: argparse.Namespace, config: Dict[str, Any]):
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
        "repeats": args.repeater.upper(),  # Convert to uppercase (count->MAX, ci->CI, etc.)
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


def resolve_benchmark_spec(args: argparse.Namespace, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve benchmark specification from args or config.

    Args:
        args: Parsed command-line arguments
        config: Configuration dictionary from all sources

    Returns:
        Benchmark specification dictionary

    Raises:
        ValueError: If benchmark information cannot be determined
    """
    # If benchmark specified on command line, load from YAML
    if args.benchmark:
        _, benchmark_data = build_orchestrator_options(args, config)
        return build_benchmark_spec(args, benchmark_data, config)

    # Otherwise, try to get from config (--repro, -f, -j)
    benchmark_spec_from_config = config.get("benchmark_spec", {})
    if benchmark_spec_from_config:
        entry_point = benchmark_spec_from_config.get("entry_point", "")
        if not entry_point:
            raise ValueError("No benchmark information found in configuration")
        # Set placeholder so build_orchestrator_options doesn't fail
        args.benchmark = "repro"
        # Apply task override if provided via -t flag
        if "task" in config:
            benchmark_spec_from_config = benchmark_spec_from_config.copy()
            benchmark_spec_from_config["task"] = config["task"]
        return benchmark_spec_from_config

    raise ValueError("No benchmark specified (use BENCHMARK argument or provide benchmark_spec in config)")


def print_experiment_info(args: argparse.Namespace, benchmark_spec: Dict[str, Any]) -> None:
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
            print(f"\n✓ Experiment completed successfully")
            print(f"  Iterations: {result.iteration_count}")
            print(f"  Metrics collected: {len(result.metrics)}")
        return 0
    else:
        print(f"\n✗ Experiment failed")
        print(f"  Error: {result.error_message}")
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
        benchmark_spec = resolve_benchmark_spec(args, config)
        options, _ = build_orchestrator_options(args, config)
        options["benchmark_spec"] = benchmark_spec

        # Create repeater
        repeater = create_repeater(args, config)

        # Create orchestrator
        orchestrator = ExecutionOrchestrator(
            options=options,
            benchmark_spec=benchmark_spec,
            repeater=repeater,
            experiment_name=args.experiment
        )

        # Print experiment info if verbose
        print_experiment_info(args, benchmark_spec)

        # Create progress callbacks and run experiment
        callbacks = create_progress_callbacks(args.verbose)
        result = orchestrator.run(callbacks)

        # Print results and return exit code
        return print_experiment_result(result, args.verbose)

    except ValueError as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n✗ Error running experiment: {e}")
        import traceback
        if hasattr(args, 'verbose') and args.verbose:
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
        default="MAX",
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

    # Positional arguments (must be at the end)
    parser.add_argument(
        "benchmark",
        nargs="?",
        metavar="BENCHMARK",
        help="Benchmark to run (without .yaml extension)"
    )
    parser.add_argument(
        "benchmark_args",
        nargs="*",
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

    return args


def validate_experiment_args(args: argparse.Namespace) -> Optional[int]:
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
    if not args.benchmark and not args.repro:
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

    # Validate experiment arguments
    error_code = validate_experiment_args(args)
    if error_code is not None:
        return error_code

    # Run experiment
    return run_experiment(args)


if __name__ == "__main__":
    sys.exit(main())
