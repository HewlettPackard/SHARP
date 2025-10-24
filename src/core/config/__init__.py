"""
Configuration system: YAML/JSON loading, Pydantic validation, include resolution,
and benchmark discovery.
"""

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

