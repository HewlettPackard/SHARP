#!/usr/bin/env python3
"""
SHARP resource discovery utilities.

Provides functions for listing and inspecting benchmarks and backends.
Used by CLI tools (launch, build, etc.) to discover available resources.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import yaml
from pathlib import Path
from typing import Dict, List, Set


def get_project_root() -> Path:
    """
    Get the project root directory.

    Returns:
        Path to project root (parent of src/)
    """
    return Path(__file__).parent.parent.parent


def get_benchmark_names() -> Dict[str, Path]:
    """
    Get all benchmark names defined in YAML files.

    Parses all benchmark YAML files and extracts the actual benchmark names
    from the 'benchmarks:' section, not just the filenames.

    Returns:
        Dictionary mapping benchmark names to their YAML file paths
    """
    project_root = get_project_root()
    benchmarks_dir = project_root / "benchmarks"

    if not benchmarks_dir.exists():
        return {}

    benchmark_map = {}
    yaml_files = benchmarks_dir.rglob("*.yaml")

    for yaml_file in yaml_files:
        try:
            with open(yaml_file, 'r') as f:
                data = yaml.safe_load(f)

            # Skip files without a 'benchmarks' section
            if not data or 'benchmarks' not in data:
                continue

            benchmarks = data['benchmarks']
            if not isinstance(benchmarks, dict):
                continue

            # Add each benchmark name from this file
            for benchmark_name in benchmarks.keys():
                benchmark_map[benchmark_name] = yaml_file

        except (yaml.YAMLError, IOError) as e:
            # Skip files that can't be parsed
            continue

    return benchmark_map


def list_benchmarks() -> int:
    """
    List all available benchmarks.

    Parses YAML files and shows actual benchmark names, not filenames.

    Returns:
        Exit code (0 for success)
    """
    benchmark_map = get_benchmark_names()

    print("Available benchmarks:")
    print()

    if not benchmark_map:
        print("  (No benchmarks found)")
        return 0

    # Group benchmarks by their YAML file for cleaner display
    file_groups: Dict[Path, List[str]] = {}
    for name, path in benchmark_map.items():
        if path not in file_groups:
            file_groups[path] = []
        file_groups[path].append(name)

    # Sort and display
    project_root = get_project_root()
    benchmarks_dir = project_root / "benchmarks"

    for yaml_file in sorted(file_groups.keys()):
        rel_path = yaml_file.relative_to(benchmarks_dir)
        benchmarks = sorted(file_groups[yaml_file])

        print(f"  From {rel_path}:")
        for benchmark in benchmarks:
            print(f"    {benchmark}")
        print()

    return 0


def show_benchmark(name: str) -> int:
    """
    Show details of a specific benchmark.

    Args:
        name: Benchmark name (as listed by --list-benchmarks)

    Returns:
        Exit code (0 for success, 1 for not found)
    """
    benchmark_map = get_benchmark_names()

    if name not in benchmark_map:
        print(f"Error: Benchmark '{name}' not found")
        print()
        print("Available benchmarks:")
        for benchmark_name in sorted(benchmark_map.keys()):
            print(f"  {benchmark_name}")
        return 1

    yaml_file = benchmark_map[name]
    project_root = get_project_root()
    benchmarks_dir = project_root / "benchmarks"
    rel_path = yaml_file.relative_to(benchmarks_dir)

    print(f"Benchmark: {name}")
    print(f"Defined in: {rel_path}")
    print(f"Full path: {yaml_file}")
    print()

    # Load and display the benchmark definition
    try:
        with open(yaml_file, 'r') as f:
            data = yaml.safe_load(f)

        if 'benchmarks' in data and name in data['benchmarks']:
            print("Benchmark definition:")
            print("-" * 60)
            print(yaml.dump({name: data['benchmarks'][name]}, default_flow_style=False))
            print("-" * 60)
            print()

            # Show other useful info from the file
            if 'tags' in data:
                print(f"Tags: {', '.join(data['tags'])}")
            if 'metrics' in data:
                print(f"Metrics defined: {', '.join(data['metrics'].keys())}")
            if 'include' in data:
                print(f"Includes: {', '.join(data['include'])}")

    except (yaml.YAMLError, IOError) as e:
        print(f"Error reading benchmark file: {e}")
        return 1

    return 0


def get_backend_names() -> Dict[str, Path]:
    """
    Get all backend names defined in YAML files.

    Parses all backend YAML files and extracts the actual backend names
    from the 'backend_options:' section, not just the filenames.

    Returns:
        Dictionary mapping backend names to their YAML file paths
    """
    project_root = get_project_root()
    backends_dir = project_root / "backends"

    if not backends_dir.exists():
        return {}

    backend_map = {}
    yaml_files = backends_dir.glob("*.yaml")

    for yaml_file in yaml_files:
        try:
            with open(yaml_file, 'r') as f:
                data = yaml.safe_load(f)

            # Skip files without a 'backend_options' section
            if not data or 'backend_options' not in data:
                continue

            backend_options = data['backend_options']
            if not isinstance(backend_options, dict):
                continue

            # Add each backend name from this file
            for backend_name in backend_options.keys():
                backend_map[backend_name] = yaml_file

        except (yaml.YAMLError, IOError) as e:
            # Skip files that can't be parsed
            continue

    return backend_map


def list_backends() -> int:
    """
    List all available backends.

    Parses YAML files and shows actual backend names, not filenames.

    Returns:
        Exit code (0 for success)
    """
    backend_map = get_backend_names()

    print("Available backends:")
    print()

    if not backend_map:
        print("  (No backends found)")
        return 0

    # Group backends by their YAML file for cleaner display
    file_groups: Dict[Path, List[str]] = {}
    for name, path in backend_map.items():
        if path not in file_groups:
            file_groups[path] = []
        file_groups[path].append(name)

    # Sort and display
    project_root = get_project_root()
    backends_dir = project_root / "backends"

    for yaml_file in sorted(file_groups.keys()):
        rel_path = yaml_file.relative_to(backends_dir)
        backends = sorted(file_groups[yaml_file])

        print(f"  From {rel_path}:")
        for backend in backends:
            print(f"    {backend}")
        print()

    return 0


def show_backend(name: str) -> int:
    """
    Show details of a specific backend.

    Args:
        name: Backend name (as listed by --list-backends)

    Returns:
        Exit code (0 for success, 1 for not found)
    """
    backend_map = get_backend_names()

    if name not in backend_map:
        print(f"Error: Backend '{name}' not found")
        print()
        print("Available backends:")
        for backend_name in sorted(backend_map.keys()):
            print(f"  {backend_name}")
        return 1

    yaml_file = backend_map[name]
    project_root = get_project_root()
    backends_dir = project_root / "backends"
    rel_path = yaml_file.relative_to(backends_dir)

    print(f"Backend: {name}")
    print(f"Defined in: {rel_path}")
    print(f"Full path: {yaml_file}")
    print()

    # Load and display the backend definition
    try:
        with open(yaml_file, 'r') as f:
            data = yaml.safe_load(f)

        if 'backend_options' in data and name in data['backend_options']:
            print("Backend configuration:")
            print("-" * 60)
            print(yaml.dump({name: data['backend_options'][name]}, default_flow_style=False))
            print("-" * 60)
            print()

            # Show other useful info from the file
            if 'metrics' in data:
                print(f"Metrics defined: {', '.join(data['metrics'].keys())}")

    except (yaml.YAMLError, IOError) as e:
        print(f"Error reading backend file: {e}")
        return 1

    return 0


def get_benchmark_paths() -> List[Path]:
    """
    Get paths to all benchmark YAML files.

    Returns:
        List of paths to benchmark YAML files
    """
    project_root = get_project_root()
    benchmarks_dir = project_root / "benchmarks"

    if not benchmarks_dir.exists():
        return []

    return sorted(benchmarks_dir.rglob("*.yaml"))


def get_backend_paths() -> List[Path]:
    """
    Get paths to all backend YAML files.

    Returns:
        List of paths to backend YAML files
    """
    project_root = get_project_root()
    backends_dir = project_root / "backends"

    if not backends_dir.exists():
        return []

    return sorted(backends_dir.glob("*.yaml"))
