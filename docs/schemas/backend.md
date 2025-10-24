# Backend Configuration Schema

**File Location**: `backends/*.yaml`

**Purpose**: Define execution environments, profiling tools, and metric extraction for benchmarks.

## Schema

```python
class BackendOptionConfig(BaseModel):
    """Individual backend configuration."""

    version: str | None = None
    description: str | None = None
    profiling: bool = False
    composable: bool = True
    command_template: str = ""
    reset: str = ""
    placeholders: dict[str, str] = {}

class BackendConfig(BaseModel):
    """Backend YAML schema (entire file structure)."""

    version: str | None = None
    description: str | None = None
    backend_options: dict[str, BackendOptionConfig]
    metrics: dict[str, MetricDefinition] = {}
    include: list[str] = []
```

## Field Semantics

### Top-Level Fields

#### `backend_options` (required)
- Dictionary mapping backend name to its configuration
- Allows multiple backend variants in one file

**Example**:
```yaml
backend_options:
  perf:
    profiling: true
    command_template: "perf stat -e cycles,instructions $CMD $ARGS"
  perf-detailed:
    profiling: true
    command_template: "perf stat -e cycles,instructions,cache-misses,LLC-loads $CMD $ARGS"
```

#### `metrics` (optional)
- Metric definitions shared by all backends in this file
- Each metric: `{description, extract, lower_is_better, type, units}`
- Applied to all benchmarks using this backend

**Example**:
```yaml
metrics:
  cycles:
    description: CPU cycles
    extract: 'grep "cycles" perf.out | awk "{print $1}"'
    lower_is_better: true
    type: int
    units: cycles
```

#### `include` (optional)
- YAML files to include/merge (same semantics as experiment config)

### Per-Backend Fields

#### `version` (optional)
- Backend config version (e.g., "1.0.0")
- For documentation/tracking only

#### `description` (optional)
- Human-readable description of the backend

#### `profiling` (default: false)
- Boolean flag: is this a profiling tool or execution backend?
- **true**: Profiling backend (perf, strace, mpip, vtune, temps)
  - GUI profile tab filters for `profiling: true`
  - Can wrap other commands or replace execution
- **false**: Execution backend (local, ssh, mpi, docker, knative, fission)
  - Default for most backends

**Example**:
```yaml
backend_options:
  perf:
    profiling: true
  local:
    profiling: false
```

#### `composable` (default: true)
- Boolean flag: can this backend wrap other backends?
- **true**: Backend can appear anywhere in chain (wraps or is wrapped)
  - Example: `perf`, `strace` (profiling tools)
  - Example: `local`, `ssh` (execution environments)
  - Composition: `-b A -b B -b C` → A wraps B wraps C
- **false**: Non-composable backend must be leftmost (outermost)
  - Example: `mpip` (replaces MPI execution, can't wrap it)
  - Can only appear alone or leftmost in chain

**Example**:
```yaml
backend_options:
  perf:
    composable: true  # Can wrap other backends

  mpip:
    composable: false  # Non-composable, must be alone or leftmost
```

#### `command_template` (required, default: "$CMD $ARGS")
- Shell command with placeholders for the benchmark and its arguments
- **Must include `$CMD`** (the benchmark executable path) and `$ARGS` (benchmark arguments)
- Placeholders replaced by launcher before execution
- Output file path determined by launcher's `-t` parameter, NOT by backend
- Validation: If neither `$CMD` nor `$ARGS` is present, config will raise an error

**Example** (local - direct execution):
```yaml
command_template: "$CMD $ARGS"
# Usage: launcher.py -b local sleep 1.5
# Expands to: sleep 1.5
```

**Example** (perf - wrapping the command):
```yaml
command_template: "perf stat -e cycles,instructions $CMD $ARGS"
# Usage: launcher.py -b perf sleep 1.5
# Expands to: perf stat -e cycles,instructions sleep 1.5
```

**Example** (MPI with custom placeholders):
```yaml
command_template: "mpirun -np $MPIPROCS $CMD $ARGS"
# Usage: launcher.py -b mpi --mpiprocs 4 sleep 1.5
# Expands to: mpirun -np 4 sleep 1.5
```

#### `placeholders` (default: {})
- Macro definitions for custom template substitutions
- Used ONLY for command template substitutions
- Maps placeholder name to default value or description

**Example**:
```yaml
backend_options:
  mpi:
    command_template: "mpirun -np $MPIPROCS $CMD $ARGS"
    placeholders:
      MPIPROCS: "2"  # Default value if --mpiprocs not specified
```

**CLI Usage**:
```bash
launch.py -b mpi --mpiprocs 8 sleep 1.5
# $MPIPROCS replaced with 8
# Expands to: mpirun -np 8 sleep 1.5
```

#### `reset` (default: "")
- Optional shell command to execute before each benchmark run
- Used for cache clearing, resource cleanup, or cold-start scenarios
- Executed once per iteration, before the benchmark command
- Empty string means no reset operation
- Typically requires elevated privileges (sudo)

**Common use cases**:
- **Cache clearing** (local): `sudo sh -c '/usr/bin/sync; /sbin/sysctl vm.drop_caches=3'`
- **FaaS warm-up** (Fission, Knative): Delete and recreate function to ensure cold start
- **Container cleanup** (Docker): Stop and remove old containers
- **Database cleanup** (profiling): Clear buffers or caches

**Example** (local with cache drop):
```yaml
backend_options:
  local:
    command_template: ""
    reset: "sudo sh -c '/usr/bin/sync; /sbin/sysctl vm.drop_caches=3'"
    placeholders: {}
```

**Example** (FaaS cold-start):
```yaml
backend_options:
  fission:
    profiling: false
    command_template: "fission function invoke --name $FUNCTION_NAME"
    reset: |
      fission function delete --name $FUNCTION_NAME
      fission function create --name $FUNCTION_NAME --env python3 --code function.py
    placeholders:
      FUNCTION_NAME: "benchmark-func"
```

**Example** (empty reset - no warm-up needed):
```yaml
backend_options:
  perf:
    profiling: true
    command_template: "perf stat -e cycles,instructions $CMD $ARGS"
    reset: ""  # No reset needed - perf is lightweight
    placeholders: {}
```

**Execution flow**:
1. If `reset` is non-empty, execute it
2. Execute `command_template`
3. Collect metrics and output
4. Repeat for next iteration (back to step 1)

## Backend Composition Rules

### Execution Order

Backends are composed **right-to-left** (first backend is outermost, last is innermost):

```bash
launch.py -b perf -b mpi -b local sleep 1.5
```

Composition order: perf wraps mpi wraps local

```
perf stat -- mpirun -np 2 local_shell sleep 1.5
```

### Composability Constraints

1. **All composable**: Can appear in any order
   - Example: `-b perf -b strace -b local` ✓

2. **One non-composable**: Must be leftmost (outermost)
   - Example: `-b mpip` (alone) ✓
   - Example: `-b mpip -b perf` ✗ (wrong order - mpip must be alone)

3. **Empty chain**: Defaults to `local` backend
   - No `-b` flag specified → uses local execution

### Output Files

- Determined by launcher's `-t` parameter, NOT by backend configuration
- Backend `command_template` does NOT specify output file path
- Each profiling tool handles output differently (extracted by MetricExtractor)

## Examples

### Simple Execution Backend (local)

```yaml
version: 1.0.0
description: Local execution backend

backend_options:
  local:
    version: 1.0.0
    description: Execute commands locally (no wrapper)
    profiling: false
    composable: true
    command_template: "$CMD $ARGS"
    reset: "sudo sh -c '/usr/bin/sync; /sbin/sysctl vm.drop_caches=3'"
    placeholders: {}

metrics: {}
```

### Profiling Backend (perf)

```yaml
version: 1.0.0
description: Linux perf performance profiler

backend_options:
  perf:
    version: 1.0.0
    description: Collect CPU performance counters with perf stat
    profiling: true
    composable: true
    command_template: "perf stat -e cycles,instructions,cache-misses $CMD $ARGS"
    reset: ""
    placeholders: {}

metrics:
  cycles:
    description: CPU cycles
    extract: 'grep "cycles" output.txt | head -1 | awk "{print $1}"'
    lower_is_better: true
    type: int
    units: cycles
  instructions:
    description: Instructions executed
    extract: 'grep "instructions" output.txt | head -1 | awk "{print $1}"'
    lower_is_better: false
    type: int
    units: instructions
  cache_misses:
    description: Cache misses
    extract: 'grep "cache-misses" output.txt | head -1 | awk "{print $1}"'
    lower_is_better: true
    type: int
    units: misses
```

### Execution Backend with Placeholders (MPI)

```yaml
version: 1.0.0
description: MPI execution backend

backend_options:
  mpi:
    version: 1.0.0
    description: Execute with OpenMPI (mpirun)
    profiling: false
    composable: true
    command_template: "mpirun -np $MPIPROCS $CMD $ARGS"
    reset: ""  # MPI can't really reset jobs
    placeholders:
      MPIPROCS: "2"

metrics: {}
```

**Usage**:
```bash
launch.py -b mpi --mpiprocs 4 sleep 1.5
# Executes: mpirun -np 4 sleep 1.5
```

### Non-Composable Profiling Backend (mpip)

```yaml
version: 1.0.0
description: MPI Profiler (non-composable)

backend_options:
  mpip:
    version: 1.0.0
    description: Profile MPI performance with mpiP
    profiling: true
    composable: false  # Non-composable!
    command_template: "mpirun -np $MPIPROCS --oversubscribe -x MPIP_ENABLE_MPIIO=yes $CMD $ARGS"
    reset: ""  # mpiP handles its own cleanup
    placeholders:
      MPIPROCS: "2"

metrics:
  mpi_time:
    description: Time spent in MPI calls
    extract: 'grep "Total time" mpip.txt | awk "{print $3}"'
    lower_is_better: true
    type: float
    units: seconds
  mpi_calls:
    description: Total MPI calls
    extract: 'grep "Total MPI calls" mpip.txt | awk "{print $4}"'
    lower_is_better: false
    type: int
    units: calls
```

**Usage**:
```bash
launch.py -b mpip --mpiprocs 4 sleep 1.5
# Executes: mpirun -np 4 --oversubscribe -x MPIP_ENABLE_MPIIO=yes sleep 1.5

# ERROR - can't compose:
# launch.py -b mpip -b perf sleep 1.5
```

### Multiple Backends in One File

```yaml
version: 1.0.0
description: Performance profiling backends

backend_options:
  perf:
    profiling: true
    command_template: "perf stat -e cycles,instructions $CMD $ARGS"
    reset: ""

  perf-detailed:
    profiling: true
    command_template: "perf stat -e cycles,instructions,cache-misses,LLC-loads,branch-misses $CMD $ARGS"
    reset: ""

  strace:
    profiling: true
    command_template: "strace -c -f $CMD $ARGS"
    reset: ""

  local:
    profiling: false
    command_template: "$CMD $ARGS"
    reset: "sudo sh -c '/usr/bin/sync; /sbin/sysctl vm.drop_caches=3'"

metrics:
  cycles:
    description: CPU cycles
    extract: 'grep "cycles" output.txt | head -1 | awk "{print $1}"'
    lower_is_better: true
    type: int
    units: cycles
```

## Validation

Backend configs are validated during loading:

```python
from src.core.config.loader import load_config
from src.core.config.schema import BackendConfig

backend = load_config("backends/perf.yaml", BackendConfig)
# Raises ConfigError if validation fails
```

Validation checks:
- `backend_options` is not empty
- Each backend entry has valid configuration
- Metrics (if present) have valid definitions
- Template variables are well-formed

## Backend Composition Examples

### Example 1: Perf + Local

```bash
launch.py -b perf -b local sleep 1.5
```

**Command built**: `perf stat -- sleep 1.5`

### Example 2: Perf + Strace + Local

```bash
launch.py -b perf -b strace -b local sleep 1.5
```

**Command built**: `perf stat -- strace -c -f sleep 1.5`

### Example 3: MPI Profiling (non-composable)

```bash
launch.py -b mpip --mpiprocs 4 sleep 1.5
```

**Command built**: `mpirun -np 4 --oversubscribe -x MPIP_ENABLE_MPIIO=yes sleep 1.5`

Cannot compose with other backends.

## See Also

- [Experiment Configuration Schema](experiment.md)
- [Benchmark Configuration Schema](benchmark.md)
- [Profiling Framework Documentation](../profiling.md)
