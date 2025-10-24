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
├── (rodinia/, ollama/, npb/ would be added from registry)
└── _sources/                          # Downloaded sources (created by build.py)
    ├── rodinia/                       # Shared for all Rodinia benchmarks
    ├── npb/                           # Shared for all NPB benchmarks
    └── ...
```

## Shipped Benchmark Suites

These benchmarks are included with SHARP in the `micro/` directory.

### Microbenchmark Suites

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

## Registry-Available Benchmarks

These benchmarks are not shipped with SHARP but are available through the registry (Phase 4+). Examples below show the configuration patterns.

### Example 1: Ollama (LLM Inference)

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
    command: python ollama.py
    args: '{"model": "neural-chat:latest", "prompt": "What is benchmark performance?"}'
    description: Neural Chat inference performance
    tags: [llm, inference, neural-chat]

# Suite-level configuration (inherited by all benchmarks)
sources:
  - type: git
    url: https://github.com/ollama/ollama
    branch: main

build:
  docker:
    base_image: 'ubuntu:22.04'
    dockerfile_template: |
      FROM {{base_image}}
      RUN apt-get update && apt-get install -y python3 python3-pip
      RUN pip install requests
      COPY ollama.py /app/
      WORKDIR /app
      CMD ["python3", "ollama.py"]
    build_args: {}
  supported_backends: [local, docker, ssh]

metrics:
  inference_latency:
    description: Inference latency in milliseconds
    extract: 'grep "latency:" output.txt | awk "{print $2}"'
    lower_is_better: true
    type: float
    units: ms
  tokens_per_second:
    description: Inference throughput
    extract: 'grep "throughput:" output.txt | awk "{print $2}"'
    lower_is_better: false
    type: float
    units: tokens/s

tags: [llm, inference, ai]
```

**ollama.py Implementation**:
```python
#!/usr/bin/env python3
"""Ollama inference benchmark."""
import sys, json, time, requests

args = json.loads(sys.argv[1])
model = args.get('model', 'mistral:latest')
prompt = args.get('prompt', 'Hello')

# Start ollama server (assumes running)
url = 'http://localhost:11434/api/generate'

start = time.time()
response = requests.post(url, json={
    'model': model,
    'prompt': prompt,
    'stream': False
})
elapsed = time.time() - start

print(f"latency: {elapsed * 1000:.2f} ms")
print(f"throughput: {len(response.json()['response'].split()) / elapsed:.2f} tokens/s")
```

**Usage**:
```bash
# Registry install (Phase 4+)
launch.py --registry-install ollama --backend docker

# Run benchmark
launch.py ollama-mistral 1.0
launch.py ollama-neural-chat 2.0
```

---

### Example 2: Rodinia CUDA Benchmarks (Suite with Git Source)

**Location**: `benchmarks/rodinia/` (from registry)

**Use Case**: Standardized GPU benchmark suite with multiple algorithms

**Directory Structure** (suite-first pattern):
```
benchmarks/rodinia/
├── _shared.yaml                     # Shared config for all Rodinia benchmarks
├── cuda/
│   ├── pathfinder/
│   │   └── benchmark.yaml           # Defines pathfinder benchmark
│   ├── hotspot/
│   │   └── benchmark.yaml           # Defines hotspot benchmark
│   └── other_cuda_kernels/
│       └── benchmark.yaml
└── opencl/
    ├── pathfinder/
    │   └── benchmark.yaml
    └── hotspot/
        └── benchmark.yaml
```

**_shared.yaml** (inherited by all suite benchmarks):
```yaml
version: 1.0.0
description: Rodinia benchmark suite shared configuration

# Shared source across ALL Rodinia benchmarks
sources:
  - type: git
    url: https://github.com/yuhc/Rodinia_3.1.git
    # No branch specified - uses repo default
    # No subdir specified - whole repo cloned

# Shared build config (inherited by all benchmarks)
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

# Shared metrics across all Rodinia benchmarks
metrics:
  kernel_time:
    description: GPU kernel execution time
    extract: 'grep "kernel:" output.txt | awk "{print $2}"'
    lower_is_better: true
    type: float
    units: ms

tags: [rodinia, gpu, cuda]
```

**rodinia/cuda/pathfinder/benchmark.yaml** (inherits from _shared.yaml):
```yaml
version: 1.0.0
description: Rodinia pathfinder algorithm

include:
  - ../../_shared.yaml              # Inherit shared source, build, metrics, tags

benchmarks:
  pathfinder:
    command: ./pathfinder
    args: 16384 100
    description: Pathfinder on 16384x100 grid
    tags: [pathfinding, dynamic-programming]

# Benchmark-level overrides (if needed)
# build: {}  # Use suite-level build
# metrics: {} # Use suite-level metrics
```

**rodinia/cuda/hotspot/benchmark.yaml** (inherits from _shared.yaml):
```yaml
version: 1.0.0
description: Rodinia hotspot thermal simulation

include:
  - ../../_shared.yaml

benchmarks:
  hotspot:
    command: ./hotspot
    args: 1024 1024 2 200 input.dat output.dat
    description: Thermal simulation on 1024x1024 grid

# Override metrics for hotspot-specific measurements (optional)
metrics:
  kernel_time:
    description: Hotspot kernel execution time
    extract: 'grep "kernel:" output.txt | awk "{print $2}"'
    lower_is_better: true
    type: float
    units: ms
```

**Usage** (after registry install):
```bash
# List all Rodinia benchmarks
launch.py --list-benchmarks | grep rodinia

# Run pathfinder on GPU
launch.py -b docker pathfinder 1.0

# Run hotspot with profiling
launch.py -b docker -b perf hotspot 2.0
```

**Key Patterns**:
1. **Suite-first**: All benchmarks share one git source repo
2. **Shared config**: `_shared.yaml` defines source, build, metrics, tags
3. **Includes**: Child `benchmark.yaml` files include `_shared.yaml`
4. **Flat namespace**: `pathfinder` and `hotspot` are discovered as top-level benchmarks
5. **Hierarchical dirs**: `cuda/pathfinder/`, `opencl/hotspot/` organize by variant

---

### Example 3: NPB-CG (MPI Conjugate Gradient Solver)

**Location**: `benchmarks/npb/` (from registry)

**Use Case**: Multi-variant benchmark (serial, OpenMP, MPI) with Fortran source

**Directory Structure**:
```
benchmarks/npb/
├── _shared.yaml
├── serial/
│   └── benchmark.yaml
├── openmp/
│   └── benchmark.yaml
└── mpi/
    └── benchmark.yaml
```

**_shared.yaml**:
```yaml
version: 1.0.0
description: NAS Parallel Benchmarks suite

sources:
  - type: git
    url: https://github.com/nasa/NPB3.4.3.git

build:
  docker:
    base_image: 'ubuntu:22.04'
    dockerfile_template: |
      FROM {{base_image}}
      RUN apt-get update && apt-get install -y gfortran build-essential openmpi-bin libopenmpi-dev
      COPY . /app/
      WORKDIR /app/NPB3.4-MPI
      RUN make suite
    build_args: {}
  supported_backends: [local, docker, ssh, mpi]

metrics:
  cg_time:
    description: Conjugate gradient solver time
    extract: 'grep "Time" output.txt | head -1 | awk "{print $3}"'
    lower_is_better: true
    type: float
    units: seconds
  mops:
    description: Million operations per second
    extract: 'grep "MOPS:" output.txt | awk "{print $2}"'
    lower_is_better: false
    type: float
    units: MOPS

tags: [npb, fortran, numerical]
```

**npb/mpi/benchmark.yaml**:
```yaml
version: 1.0.0
description: NAS Parallel Benchmarks - MPI versions

include:
  - ../_shared.yaml

benchmarks:
  cg-mpi-s:
    command: ./cg S
    args: ''
    description: Conjugate gradient solver, Small problem
    tags: [cg, mpi, small]

  cg-mpi-w:
    command: ./cg W
    args: ''
    description: Conjugate gradient solver, Workstation problem
    tags: [cg, mpi, workstation]

  cg-mpi-a:
    command: ./cg A
    args: ''
    description: Conjugate gradient solver, Class A
    tags: [cg, mpi, classA]

# Benchmark-level build override (use MPI suite)
build:
  docker:
    base_image: 'ubuntu:22.04'
    dockerfile_template: |
      FROM {{base_image}}
      RUN apt-get update && apt-get install -y gfortran build-essential openmpi-bin libopenmpi-dev
      COPY . /app/
      WORKDIR /app/NPB3.4-MPI
      RUN make cg FFLAGS="-Ofast"
    build_args: {}
```

**Usage**:
```bash
# Run MPI variant with 4 processes
launch.py -b mpi --mpl 4 cg-mpi-w 1.0

# Run with profiling
launch.py -b mpi --mpl 8 -b mpip cg-mpi-a 2.0
```

---

## Suite Configuration Patterns

### Pattern 1: Single Source for All Benchmarks (Rodinia, NPB)

Use when all benchmarks come from one repository with multiple entry points:

```yaml
# benchmarks/suite/_shared.yaml
sources:
  - type: git
    url: https://github.com/...
    # Optional:
    branch: main
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
