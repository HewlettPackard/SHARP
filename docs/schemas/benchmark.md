# Benchmark Configuration Schema

**File Location**: `benchmarks/*/benchmark.yaml`

**Purpose**: Define benchmark suites, individual benchmarks, sources, build configuration, metrics, and tags.

## Schema

```python
class BenchmarkSource(BaseModel):
    """Source location specification."""

    type: str  # git, archive, local, s3 (future)
    url: str | None = None  # URL for remote sources
    branch: str | None = None  # Git branch (optional)
    subdir: str | None = None  # Subdirectory within repo (for suite benchmarks)

class BenchmarkBuild(BaseModel):
    """Build instructions (shared across suite)."""

    docker: dict[str, Any] = {}  # Docker build config
    supported_backends: list[str] = []  # Backends that work with this suite

class MetricDefinition(BaseModel):
    """Single metric definition."""

    description: str
    extract: str  # Shell command to extract value
    lower_is_better: bool
    type: str  # float, int, string
    units: str | None = None

class BenchmarkEntry(BaseModel):
    """Individual benchmark definition (value in benchmarks dict)."""

    command: str
    args: str | None = None
    description: str | None = None
    tags: list[str] = []

class BenchmarkConfig(BaseModel):
    """Benchmark suite YAML schema (one file per suite directory)."""

    version: str | None = None
    description: str | None = None
    benchmarks: dict[str, BenchmarkEntry]  # Name → benchmark definition
    sources: list[BenchmarkSource] = []
    build: BenchmarkBuild | None = None
    metrics: dict[str, MetricDefinition] = {}
    tags: list[str] = []
    include: list[str] = []
```

## Field Semantics

### Top-Level Fields

#### `benchmarks` (required)
- Dictionary mapping benchmark name to its configuration
- Names must be **globally unique** across all suites (flat namespace)
- Benchmarks in suite inherit suite-level sources, build, metrics, tags

**Example**:
```yaml
benchmarks:
  sleep:
    command: python sleep.py
    args: '{"duration": 1.0}'
    description: Busy-wait sleep
    tags: [cpu, simple]

  matmul:
    command: python matmul.py
    args: '{"size": 512}'
    description: Matrix multiplication
    tags: [compute, cpu]
```

#### `sources` (default: [])
- List of source locations for the suite
- Types: git, archive, local
- Each source downloaded to `~/.sharp/_sources/<suite>/` (for external) or repository (for local)

**Example** (git source):
```yaml
sources:
  - type: git
    url: https://github.com/yuhc/Rodinia_3.1.git
    branch: main  # optional
```

**Example** (local - no download):
```yaml
sources: []  # Files already in repository
```

**Example** (archive):
```yaml
sources:
  - type: archive
    url: https://example.com/benchmark.tar.gz
```

#### `build` (optional)
- Build instructions shared by all benchmarks in suite
- Contains Docker configuration and supported backends

**Example**:
```yaml
build:
  docker:
    base_image: "python:3.10"
    dockerfile_template: |
      FROM {{base_image}}
      RUN pip install -r requirements.txt
      COPY . /app/
      WORKDIR /app
    build_args: {}
  supported_backends: [local, docker, ssh, mpi]
```

#### `metrics` (optional)
- Metric definitions shared by all benchmarks in suite
- Each metric specifies extraction method and properties
- Inherited by all benchmarks

**Example**:
```yaml
metrics:
  inner_time:
    description: Benchmark execution time
    extract: 'grep "time:" output.txt | awk "{print $2}"'
    lower_is_better: true
    type: float
    units: seconds

  throughput:
    description: Operations per second
    extract: 'grep "throughput:" output.txt | awk "{print $2}"'
    lower_is_better: false
    type: float
    units: ops/sec
```

#### `tags` (default: [])
- Suite-level tags (concatenated with benchmark-specific tags)
- Used for categorization and filtering
- Common tags: microbenchmark, gpu, cuda, mpi, llm, ai, etc.

**Example**:
```yaml
tags: [microbenchmark, cpu, python]
```

#### `include` (optional)
- YAML files to include/merge
- Same semantics as experiment config includes
- Used for shared configs (parent directory _shared.yaml)

**Example**:
```yaml
include:
  - ../_shared.yaml  # Inherit from parent
```

#### `version` (optional)
- Semver string for config version
- For documentation/tracking only

#### `description` (optional)
- Human-readable description of the suite

### Per-Benchmark Fields

#### `command` (required)
- Entry point: executable name or Python module
- Example: `python sleep.py`, `./pathfinder`, `run.sh`

#### `args` (optional)
- JSON string with benchmark-specific arguments
- Passed to benchmark as configuration
- Format: `'{"param1": "value1", "param2": 2}'`

**Example**:
```yaml
args: '{"size": 512, "iterations": 10, "verbose": true}'
```

#### `description` (optional)
- Human-readable description of this specific benchmark

#### `tags` (optional)
- Benchmark-specific tags (merged with suite tags)
- Allows sub-categorization within suite

**Example**:
```yaml
benchmarks:
  pathfinder-small:
    command: ./pathfinder
    args: '{"size": 512}'
    tags: [small, pathfinding]

  pathfinder-large:
    command: ./pathfinder
    args: '{"size": 4096}'
    tags: [large, pathfinding]
```

## Merge Semantics (Benchmark-Level Inherits from Suite-Level)

When a benchmark is loaded:

- **sources**: Benchmark sources **replace** suite sources (if specified), else **inherit**
- **build**: Benchmark build **deep merges** with suite build (benchmark overrides conflicts)
- **metrics**: Benchmark metrics **merge** with suite metrics (benchmark overrides conflicts)
- **tags**: Benchmark tags **concatenate** with suite tags

## Examples

### Simple Local Suite (Microbenchmarks - CPU)

```yaml
# benchmarks/micro/cpu/benchmark.yaml
version: 1.0.0
description: CPU microbenchmark suite

benchmarks:
  sleep:
    command: python sleep.py
    args: '{"duration": 1.0}'
    description: Busy-wait for specified duration
    tags: [busy-wait]

  nope:
    command: python nope.py
    args: '{"iterations": 1000000}'
    description: No-op loop (instruction counting)
    tags: [no-op]

  matmul:
    command: python matmul.py
    args: '{"size": 256}'
    description: Matrix multiplication
    tags: [compute]

# Suite-level configuration (inherited by all benchmarks)
sources: []  # Local files in repository

build:
  docker:
    base_image: 'python:3.10'
    dockerfile_template: |
      FROM {{base_image}}
      RUN pip install numpy
      COPY . /app/
      WORKDIR /app
    build_args: {}
  supported_backends: [local, docker, ssh, mpi]

# Shared metric across all CPU benchmarks
metrics:
  inner_time:
    description: Benchmark execution time
    extract: 'grep "time:" output.txt | awk "{print $2}"'
    lower_is_better: true
    type: float
    units: seconds

tags: [microbenchmark, cpu, python]
```

### Suite with Git Source (Rodinia)

```yaml
# benchmarks/rodinia/_shared.yaml
version: 1.0.0
description: Rodinia benchmark suite shared configuration

# Shared source across ALL Rodinia benchmarks
sources:
  - type: git
    url: https://github.com/yuhc/Rodinia_3.1.git
    # No subdir - uses whole repo

build:
  docker:
    base_image: 'nvidia/cuda:11.8.0-runtime-ubuntu22.04'
    dockerfile_template: |
      FROM {{base_image}}
      RUN apt-get update && apt-get install -y build-essential make
      COPY . /app/
      WORKDIR /app
      RUN make -C cuda clean && make -C cuda all
    build_args: {}
  supported_backends: [local, docker, ssh]

metrics:
  kernel_time:
    description: GPU kernel execution time
    extract: 'grep "kernel:" output.txt | awk "{print $2}"'
    lower_is_better: true
    type: float
    units: ms

tags: [rodinia, gpu, cuda]
```

```yaml
# benchmarks/rodinia/cuda/pathfinder/benchmark.yaml
version: 1.0.0
description: Rodinia pathfinder algorithm

include:
  - ../../_shared.yaml  # Inherit shared source, build, metrics, tags

benchmarks:
  pathfinder:
    command: ./pathfinder
    args: '{"rows": 16384, "cols": 100}'
    description: Pathfinder on 16384x100 grid
    tags: [pathfinding, dynamic-programming]
```

### Hierarchical Suite with Multiple Variants

```yaml
# benchmarks/npb/mpi/benchmark.yaml
version: 1.0.0
description: NAS Parallel Benchmarks - MPI variant

include:
  - ../_shared.yaml  # Inherit sources, build, metrics from parent

benchmarks:
  cg-s:
    command: ./cg
    args: '{"problem_size": "S"}'
    description: Conjugate gradient solver, Small problem
    tags: [cg, small]

  cg-w:
    command: ./cg
    args: '{"problem_size": "W"}'
    description: Conjugate gradient solver, Workstation
    tags: [cg, workstation]

  cg-a:
    command: ./cg
    args: '{"problem_size": "A"}'
    description: Conjugate gradient solver, Class A
    tags: [cg, classA]
```

### Suite with Shared Metrics

```yaml
# benchmarks/micro/_shared.yaml
version: 1.0.0
description: Shared config for all micro-benchmarks

# Empty benchmarks dict (defined in child suites)
benchmarks: {}

# Shared metric across ALL micro-benchmarks
metrics:
  inner_time:
    description: Time to execute benchmark
    extract: 'tail -1 output.txt | awk "{print $1}"'
    lower_is_better: true
    type: float
    units: seconds

tags: [microbenchmark]
```

```yaml
# benchmarks/micro/cpu/benchmark.yaml
version: 1.0.0

include:
  - ../_shared.yaml  # Inherit inner_time metric and microbenchmark tag

benchmarks:
  sleep:
    command: python sleep.py
    description: Sleep benchmark

tags: [cpu]  # Concatenated with inherited [microbenchmark]
# Final tags: [microbenchmark, cpu]
```

## Benchmark Naming

### Flat Namespace

All benchmark names are globally unique across suites:

```bash
# Good
benchmarks/micro/cpu/benchmark.yaml defines: sleep, nope, inc, matmul
benchmarks/micro/gpu/benchmark.yaml defines: cuda-inc, cuda-matmul
benchmarks/micro/mpi/benchmark.yaml defines: mpi-pingpong-single

launch.py sleep 1.0      # No prefix needed
launch.py cuda-inc 1.0
launch.py mpi-pingpong-single 1.0
```

### Naming Conflicts

If two suites define the same benchmark name, discovery fails:

```bash
# Error - duplicate name
benchmarks/suite1/benchmark.yaml defines: pathfinder
benchmarks/suite2/benchmark.yaml defines: pathfinder
launch.py --list-benchmarks  # ConfigError: Duplicate benchmark name 'pathfinder'
```

### Solution: Use Tags for Distinction

```yaml
# benchmarks/rodinia/cuda/pathfinder/benchmark.yaml
benchmarks:
  pathfinder:
    tags: [rodinia, cuda, gpu]

# benchmarks/other/opencl/pathfinder/benchmark.yaml
benchmarks:
  pathfinder-opencl:  # Different name
    tags: [pathfinding, opencl]
```

## Validation

Benchmark configs are validated during loading:

```python
from src.core.config.loader import load_config
from src.core.config.schema import BenchmarkConfig

benchmark = load_config("benchmarks/micro/cpu/benchmark.yaml", BenchmarkConfig)
# Raises ConfigError if validation fails
```

Validation checks:
- `benchmarks` dict is not empty
- Each benchmark entry has `command` field
- All metric definitions are valid
- No duplicate benchmark names across suites
- Includes (if present) resolve successfully

## See Also

- [Experiment Configuration Schema](experiment.md)
- [Backend Configuration Schema](backend.md)
- [Benchmarks Directory Guide](../../benchmarks/README.md)
