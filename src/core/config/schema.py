"""
SHARP 4.0 Configuration Schemas

Pydantic v2 models for validating YAML/JSON configuration files.
Supports experiment, backend, benchmark, and workflow configurations.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# =============================================================================
# Parameter Sweep Configuration
# =============================================================================

class SweepConfig(BaseModel):
    """
    Parameter sweep configuration.

    Supports Cartesian product expansion across three dimensions:
    - args: List of complete argument lists
    - env: Dict of environment variables with scalar or list values
    - options: Dict of runtime options with scalar or list values
    """
    args: list[list[str]] | None = Field(None, description="List of argument lists to sweep over")
    env: dict[str, str | list[str]] | None = Field(None, description="Environment variables to sweep")
    options: dict[str, Any] | None = Field(None, description="Runtime options to sweep")

    @model_validator(mode='after')
    def validate_has_content(self) -> 'SweepConfig':
        """Ensure at least one sweep dimension is specified."""
        if not any([self.args, self.env, self.options]):
            raise ValueError("Sweep must specify at least one of: args, env, options")
        return self

    @field_validator('args')
    @classmethod
    def validate_args_structure(cls, v: list[list[str]] | None) -> list[list[str]] | None:
        """Ensure args is a list of lists."""
        if v is not None:
            if not isinstance(v, list):
                raise ValueError("args must be a list")
            for item in v:
                if not isinstance(item, list):
                    raise ValueError("Each args entry must be a list of strings")
        return v


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
    # Parameter sweep - validated configuration
    sweep: SweepConfig | None = None
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
    location: str  # Primary URL or filesystem path
    mirrors: list[str] = []  # Fallback URLs if primary fails (for download type)
    ref: str | None = None  # Git ref/tag/commit
    source_dir: str | None = None  # Shared source directory name (e.g., 'rodinia-shared')
    build_dir: str | None = None  # Subdirectory to build from within sources


class BuildRequirements(BaseModel):
    """Declarative requirements for builds (unified for AppImage and Docker)."""
    python: list[str] = []  # Python packages (pip install)
    system: list[str] = []  # System packages (apt-get install)
    libraries: list[str] = []  # Libraries to build from source (from sources)


class BenchmarkBuild(BaseModel):
    """Build instructions."""
    appimage: dict[str, Any] | None = None  # AppImage-specific config
    docker: dict[str, Any] | None = None  # Docker-specific config
    requires: BuildRequirements | None = None  # Unified declarative requirements
    # Legacy fields (deprecated, use 'requires' instead)
    requirements: list[str] = []  # Python packages (legacy)
    system_deps: list[str] = []  # System libraries (legacy)
    makefile: str | None = None  # Relative path to Makefile
    build_commands: list[str] = []  # Custom build steps
    pre_build: str | None = None  # Script to run before build
    post_build: str | None = None  # Script to run after build


class BenchmarkEntryPoints(BaseModel):
    """Backend-specific entry points for a benchmark.

    Different backends may require different executables:
    - default: Source script/binary (for direct execution)
    - appimage: Path to AppImage (for local/ssh/mpi backends)
    - docker: Docker image name (for docker backend)
    - container: Generic container image (for knative/fission)
    """
    default: str  # Default entry point (source script/binary)
    appimage: str | None = None  # AppImage path (auto-discovered from build/)
    docker: str | None = None  # Docker image name
    container: str | None = None  # Generic container reference


class BenchmarkEntry(BaseModel):
    """Individual benchmark definition (value in benchmarks dict)."""
    sources: list[BenchmarkSource] = []  # Optional - can inherit from suite level
    build: BenchmarkBuild = BenchmarkBuild()  # Optional - can inherit from suite level
    entry_point: str  # Default executable path (source script/binary)
    backend_entry_points: BenchmarkEntryPoints | None = None  # Backend-specific entry point overrides
    args: list[str] = []  # Default arguments
    tags: list[str] = []  # Classification tags


class BenchmarkConfig(BaseModel):
    """Benchmark YAML schema (entire file structure).

    Supports suite-level sources, build, and tags that are inherited by
    all benchmarks in the file unless overridden at benchmark level.
    """
    benchmarks: dict[str, BenchmarkEntry]  # {benchmark_name: entry}
    metrics: dict[str, MetricDefinition] = {}  # Shared metric definitions across benchmarks
    include: list[str] = []
    # Suite-level defaults (inherited by all benchmarks)
    sources: list[BenchmarkSource] = []  # Suite-level sources
    build: BenchmarkBuild = BenchmarkBuild()  # Suite-level build config
    tags: list[str] = []  # Suite-level tags


# =============================================================================
# Workflow Configuration (Currently: minimal sequential workflow)
# =============================================================================

class WorkflowTask(BaseModel):
    """Single workflow task with support for composition.

    Can be specified as:
    1. File include: {"include": "path/to/task.yaml"}
    2. Inline task: {"task": "benchmark_name", "backends": [...], "options": {...}}
    3. Hybrid: {"include": "base.yaml", "task": "override_task", "options": {...}}

    When both include and inline fields are present:
    - File provides base configuration
    - Inline 'task' overrides task from file
    - Inline 'backends' overrides backends from file
    - Inline 'options' are merged with file options (inline takes precedence)
    """
    include: str | None = None  # Path to task config file (base configuration)

    # Inline fields (can override values from included file)
    task: str | None = None  # Benchmark name
    backends: list[str] | None = None
    options: dict[str, Any] | None = None

    @model_validator(mode='after')
    def validate_task_definition(self) -> 'WorkflowTask':
        """Ensure at least include or task is specified."""
        if self.include is None and self.task is None:
            raise ValueError("Must specify either 'include' or 'task' in workflow task")

        return self


class WorkflowConfig(BaseModel):
    """Minimal sequential workflow configuration.

    Supports inline task definitions, file includes, or hybrid composition:
    - Inline: {"task": "benchmark_name", "backends": [...], "options": {...}}
    - Include: {"include": "path/to/task.yaml"}
    - Hybrid: {"include": "base.yaml", "options": {"repeats": 1000}}

    No dependencies, no parallelism, no state passing between tasks.

    Note: 'experiment' field is separate - used for runlogs directory (same as -e flag).
    Top-level 'workflow' and 'task' are mutually exclusive.
    """
    version: str
    description: str | None = None
    experiment: str | None = None  # Runlogs subdirectory (same as -e flag, CLI overrides this)
    workflow: list[WorkflowTask]  # List of tasks (inline or file includes)


# Reserved for future DAG workflow support (Phase 6+)
class WorkflowStep(BaseModel):
    """Single workflow step (future DAG workflow support)."""
    id: str
    experiment: str  # Path to experiment YAML file
    depends_on: list[str] = []  # Step IDs
