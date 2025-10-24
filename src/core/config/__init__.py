"""
Configuration system: YAML/JSON loading, Pydantic validation, include resolution,
and benchmark discovery.
"""

from src.core.config.errors import ConfigError
from src.core.config.include_resolver import resolve_includes, merge_dicts
from src.core.config.loader import load_config, discover_benchmarks, discover_backends
from src.core.config.schema import (
    ExperimentConfig,
    BackendConfig,
    BackendOptionConfig,
    BenchmarkConfig,
    BenchmarkSource,
    BenchmarkBuild,
    BenchmarkEntry,
    MetricDefinition,
    WorkflowConfig,
    WorkflowStep,
)

__all__ = [
    # Loader functions
    'load_config',
    'discover_benchmarks',
    'discover_backends',
    'resolve_includes',
    'merge_dicts',
    # Exceptions
    'ConfigError',
    # Schemas
    'ExperimentConfig',
    'BackendConfig',
    'BackendOptionConfig',
    'BenchmarkConfig',
    'BenchmarkSource',
    'BenchmarkBuild',
    'BenchmarkEntry',
    'MetricDefinition',
    'WorkflowConfig',
    'WorkflowStep',
]

