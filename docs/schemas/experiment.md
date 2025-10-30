# Experiment Configuration Schema

**File Location**: `experiments/*.yaml` or any `.yaml` file passed to `launch.py`

**Purpose**: Merge benchmark, backend, and runtime options to define a complete experiment run.

## Schema

```python
class ExperimentConfig(BaseModel):
    """Merged experiment configuration (from includes + top-level overrides)."""

    version: str | None = None
    """Optional: Experiment YAML version (for config compatibility tracking)"""

    description: str | None = None
    """Optional: Human-readable description of the experiment"""

    environment: dict[str, str] = {}
    """Optional: Environment variables to set for all commands"""

    include: list[str] = []
    """Optional: List of YAML files to merge (benchmark, backends, shared configs)"""

    options: dict[str, Any] = {}
    """Runtime options dict (merged with CLI options, CLI takes precedence)"""

    # All fields from included files are merged into result
    # Example: after includes, may contain: name, entry_point, metrics, backends, etc.
```

## Field Semantics

### `version`
- Optional semver string (e.g., "1.0.0")
- Used for tracking config compatibility
- Not enforced by schema; for documentation only

**Example**:
```yaml
version: 1.0.0
```

### `description`
- Optional free-form text
- Describes the purpose of the experiment

**Example**:
```yaml
description: "Performance comparison of matrix multiplication implementations"
```

### `environment`
- Optional dict of environment variables
- Applied to all executed commands
- Example: OMP settings, CUDA configuration

**Example**:
```yaml
environment:
  OMP_NUM_THREADS: "4"
  CUDA_VISIBLE_DEVICES: "0"
```

### `include`
- Optional list of YAML file paths
- Paths resolved relative to experiment file or project root
- Files merged in order (later overrides earlier)
- Supports recursive includes

**Resolution Order**:
1. Relative to including file's directory
2. Relative to `benchmarks/` (for benchmark includes)
3. Relative to `backends/` (for backend includes)
4. Relative to project root

**Example**:
```yaml
include:
  - benchmarks/matmul/benchmark.yaml
  - backends/local.yaml
  - backends/perf.yaml
```

### `options`
- Optional dict of runtime options
- Merged with CLI options (CLI takes precedence)
- Printed in markdown output under "Runtime options" section
- Common options:
  - `experiment`: Experiment name for output directory (same as `-e` flag)
  - `repeater`: Repeater strategy name (same as `-r` flag)
  - `repeater_options`: Dict of strategy-specific parameters
  - `backends`: List of backend names (same as `-b` flags)
  - `verbosity`: debug | info | warning | error

**Example**:
```yaml
options:
  experiment: matmul_perf
  repeater: ci
  repeater_options:
    confidence: 0.95
    width_threshold: 0.1
  backends:
    - local
    - perf
  verbosity: info
```

### Merged Fields (from includes)

After all includes are resolved and merged, the config may contain any fields from referenced YAML files:

**From benchmark YAML**:
- `name`: Benchmark name
- `entry_point`: Executable/command
- `metrics`: Metric definitions
- `tags`: Benchmark tags

**From backend YAML**:
- `backends`: Backend configuration list
- (additional metrics from each backend)

**From shared config**:
- Any custom fields

## Merge Semantics

When resolving includes, merging follows these rules:

1. **Primitive values** (string, number, bool): Later overrides earlier
2. **Lists**: Later appends to earlier (concatenation)
3. **Dicts**: Recursive merge (later keys override earlier)
4. **Type mismatches**: Raise `ConfigError`

## Metric Collection Behavior

All metrics are automatically collected from:
1. Metrics defined in the benchmark's `metrics` section
2. Metrics from all backends used
3. Derived metrics (rank, repeat, outer_time) - always computed

No configuration needed; metrics flow from benchmark + backend definitions.

## Examples

### Minimal Example

```yaml
include:
  - benchmarks/sleep/benchmark.yaml
  - backends/local.yaml
```

Everything is inherited from includes.

### With Runtime Options

```yaml
version: 1.0.0

include:
  - benchmarks/matmul/benchmark.yaml
  - backends/local.yaml
  - backends/perf.yaml

options:
  experiment: matmul_perf
  repeater: ci
  repeater_options:
    confidence: 0.95
    width_threshold: 0.1
  verbosity: debug
```

### With Environment Variables

```yaml
environment:
  OMP_NUM_THREADS: "8"
  MKL_NUM_THREADS: "8"

include:
  - benchmarks/matmul/benchmark.yaml
  - backends/local.yaml
  - backends/mpi.yaml

options:
  experiment: matmul_mpi_8
  backends:
    - local
    - mpi
```

### Complex Experiment

```yaml
version: 1.0.0
description: Multi-backend performance comparison with profiling

environment:
  OMP_NUM_THREADS: "4"
  OMP_PROC_BIND: "close"

include:
  - benchmarks/rodinia/cuda/pathfinder/benchmark.yaml
  - backends/local.yaml
  - backends/perf.yaml
  - backends/strace.yaml

options:
  experiment: pathfinder_profiling
  repeater: se
  repeater_options:
    std_error_threshold: 0.05
  backends:
    - local
    - perf
    - strace
  verbosity: info
```

## Validation

The experiment config is validated against the `ExperimentConfig` schema during loading:

```python
from src.core.config.loader import load_config
from src.core.config.schema import ExperimentConfig

experiment = load_config("experiments/my-exp.yaml", ExperimentConfig)
# Raises ConfigError if validation fails
```

Validation checks:
- All required fields present (none in base ExperimentConfig)
- Field types match schema
- All included files exist and are valid YAML
- No circular includes
- Benchmark and backend names are valid

## Error Handling

Common errors and their meanings:

| Error | Cause | Solution |
|-------|-------|----------|
| `ConfigError: File not found: ...` | Include path doesn't exist | Check path in `include:` list |
| `ConfigError: Circular include detected` | File includes itself (directly or indirectly) | Remove circular reference |
| `ConfigError: validation error for ExperimentConfig` | Field type mismatch | Check YAML syntax and types |
| `ConfigError: Unknown backend: ...` | Backend name not found | Add backend to `backends/` or include its YAML |

## See Also

- [Backend Configuration Schema](backend.md)
- [Benchmark Configuration Schema](benchmark.md)
- [Configuration Loading Guide](../launch.md)
