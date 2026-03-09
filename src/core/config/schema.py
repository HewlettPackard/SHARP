"""
SHARP 4.0 Configuration Schemas

Pydantic v2 models for validating YAML/JSON configuration files.
Supports experiment, backend, benchmark, and workflow configurations.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, field_validator


# =============================================================================
# Metric Definitions (shared by backends and benchmarks)
# =============================================================================

class MetricDefinition(BaseModel):
    """Single metric definition for extraction from command output."""
    description: str
    extract: str  # Shell command to extract metric from output
    lower_is_better: bool = True
    type: Literal['numeric', 'string'] = 'numeric'
    units: str | None = None  # seconds, count, MHz, etc.


# =============================================================================
# Experiment Configuration
# =============================================================================

class ExperimentConfig(BaseModel):
    """Merged experiment configuration (from includes + top-level overrides)."""
    # Experiment metadata (optional)
    version: str | None = None
    environment: dict[str, str] = {}
    # Include directive - all actual config comes from here
    include: list[str] = []
    # Runtime options (merged with CLI options and other includes)
    options: dict[str, Any] = {}
    # All other fields from included configs (optional here)
    # BenchmarkConfig fields: name, entry_point, sources, metrics, etc.
    # BackendConfig fields (one or more): name, profiling, composable, command_template, etc.

    model_config = ConfigDict(extra='allow')  # Allow fields from included configs


# =============================================================================
# Backend Configuration
# =============================================================================

class BackendOptionConfig(BaseModel):
    """Individual backend configuration."""
    version: str | None = None
    description: str | None = None
    profiling: bool = False  # True for profiling tools (perf, strace, mpip)
    composable: bool = True  # False means outermost backend (cannot be wrapped)
    command_template: str = ""  # Shell command with $CMD and $ARGS placeholders
    placeholders: dict[str, str] = {}  # Macro substitutions (e.g., PROCS for MPI)
    reset: str | None = None  # Reset command for cold starts (e.g., clear caches)

    @field_validator('command_template')
    @classmethod
    def validate_command_template(cls, v: str) -> str:
        """Ensure command template contains $CMD and $ARGS placeholders."""
        if v and ('$CMD' not in v or '$ARGS' not in v):
            raise ValueError("command_template must contain $CMD and $ARGS placeholders")
        return v


class BackendConfig(BaseModel):
    """Backend YAML schema (entire file structure)."""
    backend_options: dict[str, BackendOptionConfig] = {}  # {backend_name: config}
    metrics: dict[str, MetricDefinition] = {}  # Metric definitions shared by backends
    include: list[str] = []


# =============================================================================
# Benchmark Configuration
# =============================================================================

class BenchmarkSource(BaseModel):
    """Source location specification."""
    type: Literal['git', 'path', 'download']
    location: str  # URL or filesystem path
    ref: str | None = None  # Git ref/tag/commit
    subdir: str | None = None  # Subdirectory for suite benchmarks


class BenchmarkBuild(BaseModel):
    """Build instructions."""
    appimage: dict[str, Any] | None = None  # AppImage build config
    docker: dict[str, Any] | None = None  # Docker build config
    requirements: list[str] = []  # Python packages
    system_deps: list[str] = []  # System libraries
    makefile: str | None = None  # Relative path to Makefile
    build_commands: list[str] = []  # Custom build steps


class BenchmarkEntry(BaseModel):
    """Individual benchmark definition (value in benchmarks dict)."""
    sources: list[BenchmarkSource]
    build: BenchmarkBuild
    entry_point: str  # Executable path after build
    args: list[str] = []  # Default arguments
    tags: list[str] = []  # Classification tags


class BenchmarkConfig(BaseModel):
    """Benchmark YAML schema (entire file structure)."""
    benchmarks: dict[str, BenchmarkEntry]  # {benchmark_name: entry}
    metrics: dict[str, MetricDefinition] = {}  # Shared metric definitions across benchmarks
    include: list[str] = []


# =============================================================================
# Workflow Configuration (Optional - deferred to Phase 4)
# =============================================================================

class WorkflowStep(BaseModel):
    """Single workflow step."""
    id: str
    benchmark: str
    backend: str
    args: list[str] = []
    depends_on: list[str] = []  # Step IDs


class WorkflowConfig(BaseModel):
    """Workflow YAML schema (optional, not implemented initially)."""
    version: str
    description: str | None = None
    steps: list[WorkflowStep]
    parallel_groups: list[list[str]] = []  # Concurrent step groups
    include: list[str] = []
