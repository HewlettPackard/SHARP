"""
Benchmark configuration loading and resolution.

Functions for loading benchmark definitions from YAML files and resolving
benchmark names or paths to executable entry points.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from pathlib import Path
from typing import Dict, Any, Tuple
import yaml
from src.core.config.include_resolver import get_project_root


def load_benchmark_data(benchmark_name: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
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
    project_root = get_project_root()
    benchmarks_dir = project_root / "benchmarks"

    # Find all benchmark YAML files (rglob searches recursively)
    benchmark_files = list(benchmarks_dir.rglob("*/*.yaml"))

    for bfile in benchmark_files:
        try:
            with open(bfile, 'r') as f:
                data = yaml.safe_load(f)

            if data and "benchmarks" in data and benchmark_name in data["benchmarks"]:
                benchmark_data = data["benchmarks"][benchmark_name].copy()
                metrics = data.get("metrics", {})

                # Process includes to merge metrics from parent files
                if "include" in data:
                    includes = data["include"]
                    if not isinstance(includes, list):
                        includes = [includes]

                    for include_path in includes:
                        # Resolve include path relative to current YAML file
                        include_file = (bfile.parent / include_path).resolve()
                        if include_file.exists():
                            with open(include_file, 'r') as inc_f:
                                inc_data = yaml.safe_load(inc_f) or {}
                                # Merge metrics from included file
                                if "metrics" in inc_data:
                                    merged_metrics = inc_data["metrics"].copy()
                                    merged_metrics.update(metrics)  # Local metrics override
                                    metrics = merged_metrics

                # Merge benchmark-level metrics (benchmark-level overrides suite-level)
                if "metrics" in benchmark_data:
                    metrics = metrics | benchmark_data.pop("metrics")

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


def find_benchmark_by_entry_point(entry_point_path: str) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    Find benchmark name by matching entry_point path.

    Used for reverse lookup when given an absolute path (e.g., from --repro).

    Args:
        entry_point_path: Absolute or relative path to benchmark executable

    Returns:
        Tuple of (benchmark_name, benchmark_data, metrics)

    Raises:
        ValueError: If no benchmark found with matching entry_point
    """
    project_root = get_project_root()
    benchmarks_dir = project_root / "benchmarks"

    # Normalize the input path for comparison
    try:
        input_path = Path(entry_point_path).resolve()
    except (OSError, RuntimeError):
        # Can't resolve path, try string comparison
        input_path = Path(entry_point_path)

    # Find all benchmark YAML files
    benchmark_files = list(benchmarks_dir.rglob("*/*.yaml"))

    for bfile in benchmark_files:
        try:
            with open(bfile, 'r') as f:
                data = yaml.safe_load(f)

            if not data or "benchmarks" not in data:
                continue

            # Check each benchmark in this file
            for bench_name, bench_data in data["benchmarks"].items():
                if "entry_point" not in bench_data:
                    continue

                bench_entry = bench_data["entry_point"]

                # Resolve entry_point relative to YAML file if it's relative
                if bench_entry.startswith("./") or bench_entry.startswith("../"):
                    yaml_dir = bfile.parent
                    bench_entry_path = (yaml_dir / bench_entry).resolve()
                else:
                    bench_entry_path = Path(bench_entry).resolve()

                # Compare resolved paths
                if bench_entry_path == input_path:
                    # Found a match! Load full data including metrics
                    benchmark_data = bench_data.copy()
                    metrics = data.get("metrics", {})

                    # Process includes
                    if "include" in data:
                        includes = data["include"]
                        if not isinstance(includes, list):
                            includes = [includes]

                        for include_path in includes:
                            include_file = (bfile.parent / include_path).resolve()
                            if include_file.exists():
                                with open(include_file, 'r') as inc_f:
                                    inc_data = yaml.safe_load(inc_f) or {}
                                    if "metrics" in inc_data:
                                        merged_metrics = inc_data["metrics"].copy()
                                        merged_metrics.update(metrics)
                                        metrics = merged_metrics

                    return bench_name, benchmark_data, metrics

        except (yaml.YAMLError, IOError):
            continue

    raise ValueError(f"No benchmark found with entry_point matching '{entry_point_path}'")


def resolve_benchmark_input(benchmark_input: str, override_task: str | None = None) -> Dict[str, Any]:
    """
    Resolve benchmark input to entry_point, args, and task.

    Tries to load from YAML first. If not found, treats as direct command/path.
    If user provides args after benchmark name, they override YAML defaults.

    Args:
        benchmark_input: Benchmark name (e.g., "nope") or direct path (e.g., "/bin/sleep 1")
        override_task: Optional task name to override the resolved task

    Returns:
        Dictionary with 'entry_point', 'args', and 'task' keys

    Examples:
        resolve_benchmark_input("nope") -> loads from YAML
        resolve_benchmark_input("inc 500") -> loads from YAML but overrides args with ["500"]
        resolve_benchmark_input("/bin/sleep 1") -> direct command
        resolve_benchmark_input("matmul", override_task="my_test") -> loads from YAML with custom task
    """
    entry_point = ""
    args = []
    task_name = ""

    try:
        # Try to load as benchmark name from YAML
        parts = benchmark_input.strip().split()
        benchmark_name = parts[0]  # First word is benchmark name
        user_args = parts[1:] if len(parts) > 1 else None  # Remaining words are args

        benchmark_data, _ = load_benchmark_data(benchmark_name)

        # Successfully loaded from YAML
        entry_point = benchmark_data.get("entry_point", "")

        # Use user-provided args if given, otherwise use YAML defaults
        if user_args is not None:
            args = user_args
        else:
            args = benchmark_data.get("args", [])

        task_name = benchmark_data.get("task", benchmark_name)

    except ValueError:
        # Benchmark not found in YAML by name
        # Try reverse lookup by entry_point path (for absolute paths from --repro)
        parts = benchmark_input.split(maxsplit=1)
        entry_point = parts[0] if parts else ""
        user_args = parts[1].split() if len(parts) > 1 else None

        try:
            # Check if entry_point matches a known benchmark
            benchmark_name, benchmark_data, _ = find_benchmark_by_entry_point(entry_point)

            # Found it! Use the benchmark data
            # Use user-provided args if given, otherwise use YAML defaults
            if user_args is not None:
                args = user_args
            else:
                args = benchmark_data.get("args", [])

            task_name = benchmark_data.get("task", benchmark_name)

        except ValueError:
            # Not a known benchmark path either, treat as direct command/path
            args = user_args if user_args is not None else []
            task_name = entry_point.split('/')[-1] if entry_point else "unknown"

    # Override task name if provided
    if override_task:
        task_name = override_task

    return {
        "entry_point": entry_point,
        "args": args,
        "task": task_name,
    }
