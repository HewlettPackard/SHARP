
<p align=center>
<img src="docs/img/sharp.png">
</p>

# Scalable Heterogeneous Architecture for Reproducible Performance

A framework for collecting, organizing, and analyzing reproducible performance measurements across heterogeneous and serverless environments.

## Purpose

SHARP helps you run repeatable performance experiments across local binaries, containers, MPI jobs, and FaaS platforms while keeping collection and analysis decoupled. It records each run as structured CSV data plus Markdown metadata so measurements can be launched on one system and explored later from the CLI or the GUI.

## Main features and capabilities

* Launch benchmarks from the command line or web-based GUI.
* Inspect completed runs in the web GUI or generate comparisons in the CLI.
* Collect measurements independently from analysis so raw run logs can be archived, shared, and revisited later.
* Run direct scripts and binaries, or package benchmarks as Docker images and AppImages when the backend requires self-contained artifacts.
* Compose execution backends with profiling and instrumentation backends, then compare runs with built-in statistics and visualization tools.
* Use profiling backends and GUI-driven variability-guided optimization (VGO) workflows to identify sources of performance variation; see [the profiling framework guide](./docs/profiling.md).

## Prerequisites

Hardware and software setup instructions found [here](./docs/setup/README.md).

## Configuration

Default settings (backends, repeaters, output directories, GUI options) are configured in [`settings.yaml`](./settings.yaml). Each setting is documented with inline comments.

## Quick start

After [setting up](./docs/setup/README.md) the software and hardware, create the project environment and list the shipped benchmarks:

```sh
uv sync --extra dev
uv run launch --list-benchmarks
```

Then run a simple local benchmark:

```sh
uv run launch -v -b local micro/sleep 1
```

This should take about one second and write a CSV file plus accompanying Markdown metadata under `runlogs/`. You can inspect those files directly, compare runs with `uv run compare`, or open the GUI with `uv run gui`.

## Graphical user interface

SHARP includes a Shiny-based GUI for browsing run logs, visualizing distributions, and comparing experiments. Start it with `uv run gui` and open the configured address in your browser. Background on the analysis workflow is documented [here](./docs/gui.md).

## Hardware support

Currently supports the following architectures:

* CPU
* GPU using CUDA (see [setup notes](./docs/setup/CUDA.md))

## FaaS framework support

Currently supports (using Kubernetes):

* Fission
* Knative

## Metrics

Every run records an `outer_time` metric in the CSV output. This is the end-to-end wall-clock time seen by the launcher, including benchmark execution and orchestration overhead.

The accompanying Markdown metadata records when the experiment started, which benchmark and backends were used, the runtime options, host information, SHARP version information, and an executable checksum when one is available.

Benchmarks and profiling backends can emit additional metrics through stdout extraction, including multi-metric `auto` backends such as `perf`, `strace`, or `bintime`.
Complete documentation on how to add or customize metrics can be found [here](./docs/metrics.md).

## Benchmark Suites

SHARP ships benchmark definitions under `benchmarks/`. All available benchmarks can be listed with:

```sh
uv run launch --list-benchmarks
```

### Microbenchmarks (micro/)

Simple, focused benchmarks for basic performance testing:

**CPU Suite** (`micro/cpu/`):
* `sleep` - Busy-wait for specified duration (baseline variability control)
* `nope` - No-op loop (instruction count validation)
* `inc` - Increment counter (memory bandwidth)
* `matmul` - Small matrix multiplication (compute-bound)
* `bounce` - Pointer chasing (cache behavior)

**GPU Suite** (`micro/gpu/`):
* `cuda-inc` - GPU counter increment (CUDA memory bandwidth)
* `cuda-matmul` - GPU matrix multiplication (CUDA compute)

**MPI Suite** (`micro/mpi/`):
* `mpi-pingpong-single` - MPI communication benchmark

**I/O Suite** (`micro/io/`):
* `swapbytes` - Cache-oblivious byte-swap (I/O performance)

### Rodinia Benchmark Suite

The Rodinia HPC benchmark suite (29 benchmarks total):

**CUDA GPU Benchmarks** (`rodinia/cuda/` - 15 benchmarks):
* Scientific computing: backprop, gaussian, heartwall, hotspot, lud, needle, srad-v1, srad-v2
* Molecular dynamics: lavamd
* Graph algorithms: bfs, pathfinder
* Machine learning: nn
* Clustering: sc (streamcluster)
* Monte Carlo: particle-filter-naive, particle-filter-float

**OpenMP CPU Benchmarks** (`rodinia/omp/` - 14 benchmarks):
* Similar set to CUDA with OpenMP parallelization
* See `benchmarks/rodinia/README.md` for complete details

For complete documentation and usage examples, see the [benchmark guide](./benchmarks/README.md).

---

## Directory structure

The code is organized into these subdirectories:

 * `settings.yaml` - Default launcher, backend, repeater, and GUI settings
 * `src/` - Core framework implementation (config, execution, metrics, stats, etc.)
 * `benchmarks/` - Benchmark suite definitions and shared sources
 * `backends/` - Backend configuration files (local, docker, ssh, mpi, profiling tools)
 * `runlogs/` - Experiment output directory (CSV data plus Markdown metadata)
 * `docs/` - User-facing documentation, setup notes, and schema references
 * `tests/` - Test suite (unit, integration, smoke tests)
 * `build/` - Optional build artifacts such as AppImages and Docker context output

For detailed architecture documentation, see [docs/DESIGN_V4.md](./docs/DESIGN_V4.md).
