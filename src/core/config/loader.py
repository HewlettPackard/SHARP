"""
Configuration file loader with schema validation.

Loads YAML/JSON configuration files, resolves includes, and validates
against Pydantic schemas. Provides high-level API for loading experiment,
backend, and benchmark configurations.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import yaml
from pathlib import Path
from typing import Any, Type, TypeVar, Union, overload

from pydantic import BaseModel, ValidationError

from .errors import ConfigError
from .include_resolver import resolve_includes, get_project_root
from .schema import BackendConfig, BenchmarkConfig

# Type variable for generic schema types
T = TypeVar('T', bound=BaseModel)


@overload
def load_config(path: str, schema: Type[T]) -> T:
    ...


@overload
def load_config(path: str, schema: None = None) -> dict[str, Any]:
    ...


def load_config(
    path: str,
    schema: Type[BaseModel] | None = None
) -> Union[BaseModel, dict[str, Any]]:
    """
    Load and validate configuration file with includes.

    Recursively resolves include directives, merges all configuration
    fragments, and optionally validates against a Pydantic schema.

    Args:
        path: Path to YAML or JSON configuration file
        schema: Optional Pydantic model for validation. If None, returns raw dict.

    Returns:
        Validated configuration object (if schema provided) or raw dictionary

    Raises:
        ConfigError: If file not found, parsing fails, or validation fails

    Examples:
        >>> from src.core.config.schema import ExperimentConfig
        >>> experiment = load_config("experiments/test.yaml", ExperimentConfig)
        >>> isinstance(experiment, ExperimentConfig)
        True

        >>> raw_config = load_config("config.yaml")
        >>> isinstance(raw_config, dict)
        True
    """
    # Resolve to absolute path
    config_path = Path(path)
    if not config_path.is_absolute():
        # Try relative to current directory first
        if config_path.exists():
            config_path = config_path.resolve()
        else:
            # Try relative to project root
            project_root = get_project_root()
            candidate = project_root / path
            if candidate.exists():
                config_path = candidate.resolve()
            else:
                raise ConfigError(f"Configuration file not found: {path}")

    # Recursively resolve all includes
    try:
        merged_data = resolve_includes(str(config_path))
    except ConfigError:
        # Re-raise ConfigError as-is
        raise
    except Exception as e:
        # Wrap other exceptions
        raise ConfigError(f"Failed to load config from {config_path}: {e}")

    # Return raw dict if no schema provided
    if schema is None:
        return merged_data

    # Validate against schema
    try:
        return schema(**merged_data)
    except ValidationError as e:
        raise ConfigError(
            f"Validation failed for {config_path} against {schema.__name__}:\n{e}"
        )


def discover_benchmarks(
    search_path: str | Path = "benchmarks/"
) -> dict[str, tuple[Path, str]]:
    """
    Scan benchmarks directory and return name → (config_file, benchmark_name) mapping.

    A single benchmark.yaml file can contain multiple benchmarks under the
    'benchmarks:' dict. Returns a flat dict mapping each benchmark name to
    a tuple of (config_file_path, benchmark_name).

    Args:
        search_path: Directory to search for benchmark.yaml files (default: benchmarks/)

    Returns:
        Dict mapping benchmark name to (config file Path, benchmark name in file)

    Raises:
        ConfigError: If benchmark.yaml file is invalid or cannot be parsed

    Examples:
        >>> benchmarks = discover_benchmarks()
        >>> 'sleep' in benchmarks
        True
        >>> config_path, bench_name = benchmarks['sleep']
        >>> config_path.name
        'benchmark.yaml'
    """
    benchmarks: dict[str, tuple[Path, str]] = {}
    base_path = Path(search_path)

    # Make path absolute if relative
    if not base_path.is_absolute():
        project_root = get_project_root()
        base_path = project_root / search_path

    # If path doesn't exist, return empty dict
    if not base_path.exists():
        return benchmarks

    # Recursively scan for benchmark.yaml files
    for config_path in base_path.rglob("benchmark.yaml"):
        try:
            # Load the YAML file
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)

            # Parse as BenchmarkConfig (this validates structure)
            config = BenchmarkConfig(**data)

            # Register all benchmarks from this file
            for bench_name in config.benchmarks.keys():
                benchmarks[bench_name] = (config_path, bench_name)

        except Exception as e:
            raise ConfigError(
                f"Failed to load benchmark config from {config_path}: {e}"
            )

    return benchmarks


def load_benchmark_config(benchmark_name_or_path: str) -> BenchmarkConfig:
    """
    Load benchmark configuration by name or path.

    Resolves benchmark name to its YAML file, loads the configuration,
    and returns the parsed BenchmarkConfig object. Suite-level sources,
    build, and tags are merged into individual benchmark entries.

    Args:
        benchmark_name_or_path: Either:
            - Benchmark name (e.g., "sleep", "matmul")
            - Path to benchmark.yaml file

    Returns:
        BenchmarkConfig object with benchmark definitions (suite-level
        config merged into entries)

    Raises:
        ConfigError: If benchmark not found or configuration invalid
        FileNotFoundError: If path specified but file doesn't exist

    Examples:
        >>> config = load_benchmark_config("sleep")
        >>> "sleep" in config.benchmarks
        True

        >>> config = load_benchmark_config("benchmarks/micro/cpu/benchmark.yaml")
        >>> isinstance(config, BenchmarkConfig)
        True

        >>> config = load_benchmark_config("benchmarks/micro/cpu")  # directory
        >>> isinstance(config, BenchmarkConfig)
        True
    """
    # Check if it's a direct path to a YAML file or directory
    path = Path(benchmark_name_or_path)
    if path.suffix in ('.yaml', '.yml') or path.exists():
        # Resolve relative paths
        if not path.is_absolute():
            project_root = get_project_root()
            if not path.exists():
                path = project_root / benchmark_name_or_path

        # Handle directory by looking for benchmark.yaml inside
        if path.is_dir():
            yaml_path = path / 'benchmark.yaml'
            if not yaml_path.exists():
                raise FileNotFoundError(
                    f"No benchmark.yaml found in directory: {path}"
                )
            path = yaml_path

        if not path.exists():
            raise FileNotFoundError(f"Benchmark file not found: {benchmark_name_or_path}")
        config = load_config(str(path), BenchmarkConfig)
        config_path = path
    else:
        # It's a benchmark name - discover and load
        benchmarks = discover_benchmarks()
        if benchmark_name_or_path not in benchmarks:
            available = sorted(benchmarks.keys())[:10]
            msg = f"Benchmark '{benchmark_name_or_path}' not found."
            if available:
                msg += f" Available: {', '.join(available)}"
                if len(benchmarks) > 10:
                    msg += f" (and {len(benchmarks) - 10} more)"
            raise ConfigError(msg)

        config_path, _ = benchmarks[benchmark_name_or_path]
        config = load_config(str(config_path), BenchmarkConfig)

    # Merge suite-level config into benchmark entries
    config = _merge_suite_level_config(config, config_path)
    return config


def _merge_suite_level_config(config: BenchmarkConfig, config_path: Path | None = None) -> BenchmarkConfig:
    """
    Merge suite-level sources, build, and tags into benchmark entries.

    If a benchmark entry has empty sources/build, inherit from suite level.
    Tags are merged (suite + benchmark-specific).
    """
    from src.core.config.schema import BenchmarkEntry, BenchmarkBuild

    updated_benchmarks = {}
    for name, entry in config.benchmarks.items():
        # Inherit sources if benchmark has none
        sources = entry.sources if entry.sources else config.sources

        # Inherit build if benchmark has default/empty build
        if (entry.build.docker is None and entry.build.appimage is None and
            not entry.build.requirements and not entry.build.system_deps and
            not entry.build.build_commands):
            build = config.build
        else:
            build = entry.build

        # Merge tags (suite + benchmark-specific)
        tags = list(set(config.tags + entry.tags))

        updated_benchmarks[name] = BenchmarkEntry(
            sources=sources,
            build=build,
            entry_point=entry.entry_point,
            args=entry.args,
            tags=tags,
        )

    # Return new config with merged entries
    result = BenchmarkConfig(
        benchmarks=updated_benchmarks,
        metrics=config.metrics,
        include=config.include,
        sources=config.sources,
        build=config.build,
        tags=config.tags,
    )
    # Store config path for use by builders
    if config_path:
        result._config_path = config_path  # type: ignore
    return result


def discover_backends(
    search_paths: list[str] | None = None,
    profiling: bool | None = None
) -> dict[str, BackendConfig]:
    """
    Discover available backends, optionally filtered by profiling flag.

    Scans backend configuration directories for .yaml files, loads each as
    a BackendConfig, and optionally filters by the profiling flag in the
    backend options.

    Args:
        search_paths: Directories to search (default: ["backends/"])
        profiling: Filter by profiling flag (True = profiling only,
                  False = execution only, None = all backends)

    Returns:
        Dict mapping backend name to loaded BackendConfig

    Raises:
        ConfigError: If backend config file is invalid or cannot be parsed

    Examples:
        >>> # Get all profiling backends
        >>> profiling_tools = discover_backends(profiling=True)
        >>> 'perf' in profiling_tools
        True

        >>> # Get all execution backends
        >>> execution = discover_backends(profiling=False)
        >>> 'local' in execution
        True

        >>> # Get all backends
        >>> all_backends = discover_backends()
    """
    if search_paths is None:
        search_paths = ["backends/"]

    backends: dict[str, BackendConfig] = {}

    for search_path in search_paths:
        base_path = Path(search_path)

        # Make path absolute if relative
        if not base_path.is_absolute():
            project_root = get_project_root()
            base_path = project_root / search_path

        # Skip if path doesn't exist
        if not base_path.exists():
            continue

        # Scan for .yaml files (not recursively, only top level)
        for config_path in base_path.glob("*.yaml"):
            try:
                # Load the YAML file
                with open(config_path, 'r') as f:
                    data = yaml.safe_load(f)

                # Parse as BackendConfig (this validates structure)
                config = BackendConfig(**data)

                # Extract all backend names from backend_options
                for backend_name, backend_option in config.backend_options.items():
                    # Apply profiling filter if specified
                    if profiling is not None:
                        if backend_option.profiling != profiling:
                            continue

                    # Store the backend config
                    backends[backend_name] = config

            except Exception as e:
                raise ConfigError(
                    f"Failed to load backend config from {config_path}: {e}"
                )

    return backends
