
<p align=center>
<img src="docs/img/sharp.png">
</p>

# Scalable Heterogeneous Architecture for Reproducible Performance

A simple synthetic performance benchmark for heterogeneous and serverless architectures.


## Prerequisites

Hardware and software setup instructions found [here](./docs/setup/README.md).

## Configuration

Default settings (backends, repeaters, output directories, GUI options) are configured in [`settings.yaml`](./settings.yaml). Each setting is documented with inline comments.

## Quick start

After [setting up](./docs/setup/README.md) the software and hardware, check if you can run functions correctly on your chosen backend, say, `fission`:

```sh
uv run launch -v -b local sleep 1
```

This should take about one second and produce some output.
If there are no errors, proceed to run a single benchmark:

```sh
cd examples
rm -rf reports/misc-local
make backend=local benchmarks="parallel_sleep"
cd ..
```

This should produce a PDF report file (and various other formats) as `reports/misc-local/report.df`. Inspect the file and ensure it shows no error messages.

## Graphical user interface

Alternatively, you can try out SHARP with a GUI that lets your run measurements, visualize the results, and compare different runs. Setup and run instructions can be found [here](docs/setup/GUI.md).

## Hardware support

Currently supports the following architectures:

* CPU
* GPU using CUDA (see [setup notes](./docs/setup/CUDA.md))

## FaaS framework support

Currently supports (using Kubernetes):

* Fission
* Knative

## Metrics

All benchmarks collect a metric called `outer_time` that measures how long (in seconds) each run took from the perspective of the launcher, i.e., including both benchmark execution and all setup and overhead time.
In addition, any benchmark can have any arbitrary metric logged in the CSV files and reported in the PDF file, as long as it outputs it to stdout.
Complete documentation on how to add or customize metrics can be found [here](./docs/metrics.md).

## Benchmark Suites

SHARP includes several benchmark suites organized by category. All benchmarks can be listed with:

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


## Example workflows / benchmarks

A small library of simple benchmarks and workflows is prebuilt with SHARP:

 * [parallel sleep](./docs/examples/psleep.md): Evaluate the scaling of the backend as the number of jobs increases.
 * [start latency](./docs/examples/start-latency.md): Measure cold- and hot-start latencies.
 * [performance prediction](./docs/examples/perfpred.md): Measure variability in the input metrics and performance predictions of AUB's benchmark suites.

The last [benchmark]((./docs/exanples/perfpred.md) has a generic reporting mechanism that only visualizes the distributions of all the collected metrics.
In can be used as a template for any other benchmark where this visualization is enough (or a good starting point).
To adapt it to your needs, simply copy the `perfpred` directory under `examples/` and edit the files to use your own metrics and descriptions.

---

## Directory structure

The code is organized into these subdirectories:

 * `src/` - Core framework implementation (config, execution, metrics, stats, etc.)
 * `benchmarks/` - Benchmark suite definitions and sources (organized by suite)
 * `backends/` - Backend configuration files (local, docker, ssh, mpi, profiling tools)
 * `runlogs/` - Experiment output directory (CSV data + markdown metadata)
 * `docs/` - Documentation (setup, backends, metrics, packaging, etc.)
 * `tests/` - Test suite (unit, integration, smoke tests)
 * `build/` - (optional) Build artifacts (AppImages, Docker images)

For detailed architecture documentation, see [DESIGN.md](./DESIGN.md).
