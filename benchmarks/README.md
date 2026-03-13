# SHARP Benchmark Suite Guide

This directory contains benchmark suites organized by type and category. Benchmarks follow a **suite-first architecture** where related benchmarks share infrastructure and configuration.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Directory Structure](#directory-structure)
3. [Shipped Benchmark Suites](#shipped-benchmark-suites)
4. [Registry-Available Benchmarks](#registry-available-benchmarks)
5. [Suite Configuration Patterns](#suite-configuration-patterns)
6. [Benchmark YAML Schema](#benchmark-yaml-schema)

## Quick Start

List all available benchmarks:
```bash
launch.py --list-benchmarks
```

Show details of a specific benchmark:
```bash
launch.py --show-benchmark sleep
```

Run a benchmark:
```bash
launch.py sleep 1.5
```

Run with a specific backend:
```bash
launch.py -b docker cuda-inc 2.0
```

## Directory Structure

```
benchmarks/
├── README.md                          # This file
├── micro/                             # Microbenchmarks (shipped)
│   ├── _shared.yaml                   # Shared config for all micro suites
│   ├── cpu/                           # CPU microbenchmarks
│   │   ├── benchmark.yaml
│   │   ├── sleep.py
│   │   ├── nope.py
│   │   ├── inc.py
│   │   ├── matmul.py
│   │   └── bounce.py
│   ├── gpu/                           # GPU microbenchmarks
│   │   ├── benchmark.yaml
│   │   ├── cuda-inc.py
│   │   └── cuda-matmul.py
│   ├── mpi/                           # MPI microbenchmarks
│   │   ├── benchmark.yaml
│   │   └── mpi-pingpong-single.py
│   └── io/                            # I/O microbenchmarks
│       ├── benchmark.yaml
│       └── swapbytes.py
├── rodinia/                           # Rodinia benchmark suite (shipped)
│   ├── README.md
│   ├── cuda/
│   │   └── benchmark.yaml
│   └── omp/
│       └── benchmark.yaml
└── _sources/                          # Downloaded sources (created by build.py)
    └── rodinia-shared/                # Shared for all Rodinia benchmarks
```

## Shipped Benchmark Suites

These benchmarks are included with SHARP.

### Microbenchmark Suites (micro/)

#### CPU Benchmarks (micro/cpu)

**Benchmarks**: `sleep`, `nope`, `inc`, `matmul`, `bounce`

Lightweight CPU-focused microbenchmarks for basic performance testing:
- **sleep**: Busy-wait for specified duration (controls baseline variability)
- **nope**: No-op loop (instruction count validation)
- **inc**: Increment counter (memory bandwidth validation)
- **matmul**: Small matrix multiplication (compute-bound)
- **bounce**: Pointer chasing (cache behavior analysis)

**Build**: Docker image with Python 3.10
**Backends**: all (local, docker, ssh, mpi, knative, fission)

#### GPU Benchmarks (micro/gpu)

**Benchmarks**: `cuda-inc`, `cuda-matmul`

CUDA-based GPU microbenchmarks:
- **cuda-inc**: GPU counter increment (memory bandwidth)
- **cuda-matmul**: GPU matrix multiplication (compute)

**Build**: Docker image with CUDA 11.8 + cuDNN
**Backends**: local, docker, ssh (GPU-enabled hosts only)

#### MPI Benchmarks (micro/mpi)

**Benchmarks**: `mpi-pingpong-single`

MPI point-to-point communication:
- **mpi-pingpong-single**: Message passing between two ranks

**Build**: Docker image with OpenMPI
**Backends**: local (with MPI), docker, ssh, mpi

#### I/O Benchmarks (micro/io)

**Benchmarks**: `swapbytes`

I/O-focused microbenchmark:
- **swapbytes**: Random file I/O (read/write patterns)

**Build**: Python 3.10
**Backends**: all

### Rodinia Benchmark Suite (rodinia/)

**Location**: `benchmarks/rodinia/` (shipped with SHARP)

**Total Benchmarks**: 29 (15 CUDA GPU + 14 OpenMP CPU)

The Rodinia Benchmark Suite is a widely-used academic collection for heterogeneous computing research. It includes parallel implementations across multiple domains:

**Categories**:
- Medical Imaging: heartwall, leukocyte
- Graph Algorithms: bfs, pathfinder, streamcluster
- Linear Algebra: lud, gaussian
- Machine Learning: backprop, nn, kmeans
- Scientific Computing: lavamd, hotspot, srad
- Bioinformatics: needle
- Monte Carlo: particle-filter

**See**: `benchmarks/rodinia/README.md` for complete documentation including:
- Detailed benchmark descriptions and parameters
- Build requirements and instructions
- Data file information
- Troubleshooting guide
- Lessons learned from suite integration

## Suite Configuration Patterns

**Location**: `benchmarks/ollama/` (from registry)

**Use Case**: Benchmark LLM inference performance with different models

```yaml
# benchmarks/ollama/benchmark.yaml
version: 1.0.0
description: Ollama LLM inference benchmarks

benchmarks:
  ollama-mistral:
    command: python ollama.py
    args: '{"model": "mistral:latest", "prompt": "Explain SHARP in 100 words"}'
    description: Mistral 7B inference performance
    tags: [llm, inference, mistral]

  ollama-neural-chat:
### Pattern 1: Suite with Shared External Source (Rodinia)
    ├── pathfinder/
    │   └── benchmark.yaml
    └── hotspot/
        └── benchmark.yaml
```

**_shared.yaml** (inherited by all suite benchmarks):
```yaml
# benchmarks/suite/cuda/benchmark.yaml
sources:
  - type: git
    url: https://github.com/example/suite.git
  - type: download
    location: https://example.com/data.tar.gz
    sha256: abc123...
    extract: true

build:
  docker:
    base_image: nvidia/cuda:11.8.0-devel-ubuntu22.04
  system: [make, git, wget]
  build_commands:
    - cd cuda && make all

benchmarks:
  benchmark-1:
    entry_point: ./bin_benchmark1
    args: ["arg1", "arg2"]
  benchmark-2:
    entry_point: ./bin_benchmark2
    args: ["data/input.txt"]

tags: [suite, cuda, gpu]
```

**See**: `benchmarks/rodinia/` for a complete working example with 29 benchmarks.

### Pattern 2: Local Benchmarks (Microbenchmarks)
    # No subdir - whole repo downloaded

benchmarks:  # Defined in child benchmark.yaml files

metrics:  # Shared across suite
  time:
    extract: ...

tags: [suite]
```

**Child files** (`benchmarks/suite/variant/benchmark.yaml`):
```yaml
include:
  - ../_shared.yaml

benchmarks:
  benchmark-name:
    command: ./executable
    args: '...'
```

**Key Point**: All benchmarks download the same source to `~/.sharp/_sources/suite/`

### Pattern 2: Local Benchmarks (Microbenchmarks)

Use when benchmarks are simple scripts in the repository:

```yaml
# benchmarks/micro/cpu/benchmark.yaml
sources: []  # No external sources

build:
  docker:
    base_image: python:3.10
    # Builds image with all benchmarks

benchmarks:
  sleep:
    command: python sleep.py
    args: '...'
  nope:
    command: python nope.py
    args: '...'
  # ...
```

**Key Point**: No source caching needed, files already in repository

### Pattern 3: Hierarchical Suites (Multiple Variants)

Use when same algorithm appears in multiple implementations:

```
benchmarks/suite/
├── _shared.yaml           # Common source, metrics
├── cuda/
│   ├── pathfinder/
│   │   └── benchmark.yaml
│   └── hotspot/
│       └── benchmark.yaml
└── opencl/
    ├── pathfinder/
    │   └── benchmark.yaml
    └── hotspot/
        └── benchmark.yaml
```

**Key Point**: Flat namespace - `pathfinder` vs `pathfinder-opencl` (use tags to distinguish)

---

## Benchmark YAML Schema

### Top-Level Fields

```yaml
version: "1.0.0"                      # Semver string (required)
description: "..."                   # Free-form text (optional)

include:
  - path/to/parent.yaml             # Recursive includes with merge (optional)

# Benchmark definitions (flat namespace, names must be unique across suites)
benchmarks:
  benchmark-name:                    # Benchmark identifier (no slashes)
    command: executable              # Entry point
    args: '{"param1": "value"}'      # JSON string
    description: "..."              # Human-readable description
    tags: [extra, tags]             # Benchmark-specific tags (merged with suite tags)

# Source specification (inherited from parent if included)
sources:
  - type: git                        # git, archive, local, s3 (future)
    url: https://...
    branch: main                     # Optional
    # No subdir - uses whole repo

# Build configuration (inherited and deep-merged from parent)
build:
  docker:
    base_image: ubuntu:22.04
    dockerfile_template: |
      # Jinja2 template with {{base_image}}, {{...}}
    build_args: {}                   # e.g., CUDA_VERSION=11.8
  supported_backends: [local, docker, ssh, mpi]

# Metric definitions (inherited and merged from parent)
metrics:
  metric-name:
    description: "..."
    extract: 'grep ... | awk ...'   # Shell command to extract value
    lower_is_better: true           # bool
    type: float | int | string
    units: ms | MOPS | ...          # Optional

# Suite-level tags (concatenated with benchmark-specific tags)
tags: [suite, category]
```

### Source Types

- **git**: Clone from GitHub/GitLab with optional branch
- **archive**: Download and extract .tar.gz or .zip
- **local**: Files in suite directory (empty sources list)

### Build Docker Configuration

```yaml
build:
  docker:
    base_image: "ubuntu:22.04"
    dockerfile_template: |
      FROM {{base_image}}
      RUN apt-get update
      COPY . /app/
      WORKDIR /app
      RUN make
    build_args:
      CUDA_VERSION: "11.8"
      ARCH: "x86_64"
```

**Template Variables**:
- `{{base_image}}`: Substituted with value from `base_image` field
- `{{build_args.VAR_NAME}}`: Custom variables from `build_args`

### Metric Extraction

```yaml
metrics:
  throughput:
    extract: 'grep "MOPS:" output.txt | awk "{print $2}"'
    # or
    extract: 'cat metrics.csv | tail -1 | cut -d, -f3'
```

The `extract` field is a shell one-liner executed in the output directory after benchmark completes.

---

## Lessons Learned: Importing Benchmark Suites

Based on integrating the Rodinia suite (29 benchmarks), here are key lessons for importing external benchmark collections into SHARP.

### Common Challenges & Solutions

#### 1. Download URL Instability

**Problem**: External download links (Dropbox, Google Drive) change format or break over time.

**Example**: Rodinia data archive URL changed from `dropbox.com/s/...` to `dropbox.com/scl/fi/...?rlkey=...&dl=1`

**Solutions**:
- ✅ Use SHA256 checksums to detect failures (file corrupted or HTML returned)
- ✅ Pin to specific URLs with direct download parameters (`?dl=1` for Dropbox)
- ✅ Consider mirroring critical data to stable infrastructure
- ✅ Add URL validation in build system to fail fast

#### 2. Archive Structure Mismatches

### Pattern 3: Local Benchmarks (Microbenchmarks)
- ✅ Test on multiple distributions (Ubuntu, RHEL, Arch)
- ⚠️ Trade-off: Static linking increases artifact size (193 KB → 944 KB for AppImage runtime)

#### 5. Build Output Filename Variations

**Problem**: Build process outputs different filename than expected by copy commands.

**Example**: BFS CUDA makefile produced `bfs.out` instead of `bfs`

**Solutions**:
- ✅ Run build manually first to identify actual output files
- ✅ Use flexible glob patterns in build commands: `cp bfs* ../../bin_bfs`
- ✅ Add validation step to check artifact exists after build

#### 6. Metrics Extraction from Application Output

**Problem**: Benchmarks don't always report timing in consistent formats, and stdout buffering can lose output on crashes.

**Examples from Rodinia integration**:
- Gaussian reports both "Time total" and "Time for CUDA kernels"
- LUD reports time in milliseconds that needs conversion
- BFS segfaults during cleanup but had already printed timing
- Particle filter reports detailed breakdown but only need total time
- Some benchmarks report no timing at all

**Solutions**:
- ✅ **Run each benchmark manually first** to see actual output format
- ✅ **Test extraction patterns** with `grep | awk` on sample output before adding to YAML
- ✅ **Prioritize `inner_time`**: Application-reported total execution time (not just kernel time)
- ✅ **Add supplementary metrics** like `kernel_time`, `filter_time` when available and meaningful
- ✅ **Use `pre_build` to add `fflush(stdout)`** after timing prints to handle crashes gracefully
- ✅ **Verify units**: Convert milliseconds to seconds for consistency
- ✅ **Test field numbers**: `awk` field positions depend on exact output format (use `awk '{ for(i=1;i<=NF;i++) print i":"$i }'` to debug)
- ❌ **Don't add metrics** if you can't verify what they represent or if timing is absent

**Metrics Priority Guide**:
1. **inner_time** (required): Total application runtime as reported by the program
2. **kernel_time** (optional): GPU/compute kernel time only (when separate from total)
3. **Component times** (optional): Meaningful breakdowns (e.g., IO time, filter time) only if well-documented

**Example Metric Definition**:
```yaml
metrics:
  inner_time:
    description: Total execution time including memory transfers
    extract: grep 'Time total' | awk '{ print $6; }'
    lower_is_better: true
    type: numeric
    units: seconds
  kernel_time:
    description: Time for CUDA kernels only
    extract: grep 'Time for CUDA kernels:' | awk '{ print $5; }'
    lower_is_better: true
    type: numeric
    units: seconds
```

### Best Practices Checklist

When importing a new benchmark suite, follow this workflow:

**Phase 1: Reconnaissance (Manual)**
1. [ ] Clone/download sources manually
2. [ ] Read build instructions (README, INSTALL, Makefile)
3. [ ] Run build commands interactively
4. [ ] Identify required system packages
5. [ ] Check for data dependencies (input files, datasets)
6. [ ] Test each benchmark manually to verify correctness
7. [ ] Document input parameters and expected outputs

**Phase 2: Configuration (YAML)**
1. [ ] Create suite directory structure: `benchmarks/suite-name/`
2. [ ] Define sources in `benchmark.yaml` with checksums
3. [ ] Write build commands (may need `pre_build` patches)
4. [ ] List system package dependencies
5. [ ] Define benchmark entries with correct entry_point paths
6. [ ] Add `args` with correct data file paths
7. [ ] Specify supported backends based on requirements

**Phase 3: Build & Test**
1. [ ] Run `uv run build --clean` to test full rebuild
2. [ ] Verify all artifacts created successfully
3. [ ] Check artifact sizes (AppImage < 100 MB ideal)
4. [ ] Test each benchmark with `uv run launch`
5. [ ] Verify exit codes (0 = success)
6. [ ] Inspect output for correctness (metrics extracted properly)

**Phase 4: Documentation**
1. [ ] Create suite README with benchmark descriptions
2. [ ] Document build requirements and dependencies
3. [ ] List known issues and workarounds
4. [ ] Add examples of common usage patterns
5. [ ] Include performance baselines if available
6. [ ] Credit original authors and link to paper/source

**Phase 5: Integration**
1. [ ] Update main `benchmarks/README.md` to reference new suite
2. [ ] Add suite to discovery tests
**Key Point**: No source caching needed, files already in repository

---

## Benchmark YAML Schemae.tar.gz

# Compare against expected
echo "b90994d5208ec5a0a133dfb9ab7928a1e8a16741503a91d212884b9e4fce8cd8  file.tar.gz" | sha256sum -c
```

**Test portability**:
```bash
# Run on different systems
docker run -it --rm -v $PWD:/work ubuntu:22.04 /work/benchmark
docker run -it --rm -v $PWD:/work ubuntu:20.04 /work/benchmark

# Check AppImage on FUSE-less system
./benchmark.AppImage --appimage-extract-and-run
```

### Further Reading

- Rodinia integration details: `benchmarks/rodinia/README.md`
- Benchmark YAML schema: `docs/schemas/benchmark.md`
- Build system documentation: `docs/packaging.md`
- AppImage best practices: https://docs.appimage.org/

---

## Creating New Benchmark Suites

### Checklist

1. Create suite directory: `benchmarks/suite-name/`
2. Create `_shared.yaml` with:
   - sources (git, archive, local)
   - build configuration
   - shared metrics
   - suite-level tags
3. Create variant subdirectories if needed (e.g., `cuda/`, `openmp/`)
4. Create `benchmark.yaml` in each variant with:
   - `include: [../_shared.yaml]` (or `../../_shared.yaml` for nested)
   - benchmark entries
5. Test with discovery: `launch.py --list-benchmarks`
6. Submit to registry for community (Phase 4+)

### Example: Adding a New Suite

```bash
# Create directory structure
mkdir -p benchmarks/my-suite/

# Create _shared.yaml
cat > benchmarks/my-suite/_shared.yaml << 'EOF'
version: 1.0.0
description: My benchmark suite

sources:
  - type: git
    url: https://github.com/...

build:
  docker:
    base_image: ubuntu:22.04
    dockerfile_template: |
      FROM {{base_image}}
      COPY . /app/
      WORKDIR /app
      RUN make

benchmarks: {}  # Defined in child files
metrics: {}
tags: [my-suite]
EOF

# Create benchmark.yaml
cat > benchmarks/my-suite/benchmark.yaml << 'EOF'
version: 1.0.0
include:
  - _shared.yaml

benchmarks:
  my-benchmark:
    command: ./run
    args: '{"param": "value"}'
    description: My benchmark
EOF

# Test discovery
launch.py --list-benchmarks | grep my-benchmark
```

---

## Registry Submission (Phase 4+)

Once implemented, submit benchmarks to the community registry:

```bash
launch.py --registry-push benchmarks/my-suite/ \
  --registry-url https://registry.sharp-benchmarks.org/ \
  --tags [category, new]
```

Registry will validate YAML schema and archive the suite for distribution.
### Further Reading

- **Rodinia suite integration**: See `benchmarks/rodinia/README.md` for a complete working example
- Benchmark YAML schema: `docs/schemas/benchmark.md`
- Build system documentation: `docs/packaging.md`
- AppImage best practices: https://docs.appimage.org/---

## Creating New Benchmark Suites

### Quick Checklist

1. Create suite directory: `benchmarks/suite-name/`
2. Create `benchmark.yaml` with:
   - sources (git, download, or local files)
   - build configuration
   - benchmark entries with entry_point and args
   - metrics definitions
   - tags
3. Create variant subdirectories if needed (e.g., `cuda/`, `omp/`)
4. Test with discovery: `uv run launch --list-benchmarks`
5. Test build: `uv run build -t docker suite-name` (or `-t appimage`)
6. Test execution: `uv run launch -b local suite-name`
7. Document in suite README.md### Example: Adding a Simple Suite

```bash
# Create directory structure
mkdir -p benchmarks/my-suite/

# Create benchmark.yaml
cat > benchmarks/my-suite/benchmark.yaml << 'EOF'
sources:
  - type: git
    location: https://github.com/example/my-suite.git
    tag: v1.0.0

build:
  requires:
    system: [gcc, make]
  build_commands:
    - make all

benchmarks:
  my-benchmark:
    entry_point: ./bin/benchmark
    args: ["--size", "1000"]
    tags: [compute, test]

tags: [my-suite]
EOF

# Test discovery
uv run launch --list-benchmarks | grep my-benchmark

# Build and test
uv run build -t docker my-benchmark
uv run launch -b local my-benchmark
```

For a complete working example with 29 benchmarks, see `benchmarks/rodinia/`.