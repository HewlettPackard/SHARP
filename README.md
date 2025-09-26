
<p align=center>
<img src="docs/img/sharp.png">
</p>

# Scalable Heterogeneous Architecture for Reproducible Performance

A simple synthetic performance benchmark for heterogeneous and serverless architectures.


## Prerequisites

Hardware and software setup instructions found [here](./docs/setup/README.md).

## Quick start

After [setting up](./docs/setup/README.md) the software and hardware, check if you can run functions correctly on your chosen backend, say, `fission`:

```sh
launcher/launch.py -v -b local sleep 1
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

## Functions

* bounce: Request-bound, time to read request.
* swapbytes: I/O-bound, cache-oblivious byte-swap.
* inc: Memory-bound, single-threaded array incrementer.
* cuda-inc: GPU-parallel version (CUDA) of `inc`.
* matmul: CPU-bound, multithreaded matrix multiply.
* cuda-matmul: GPU-parallel version (CUDA) of `matmul`.
* mpi-pingpong-single: Simple MPI Python application entirely executed within a single function.
* nope: No-op, for latency measurements.
* sleep: Sleep for a given number of seconds, for cooling down.
* distributions: A set of synthetic distributions for debugging purposes.

You can find detailed documentation for all these functions [here](./docs/fns/index.html).
If you want to add a function/application, please follow [these](./docs/app-guidelines.md) guidelines.


## Applications

* [rodinia-omp](./docs/fns/rodinia-omp): The Rodinia HPC benchmarking suite, CPU-based using OpenMP.
* [rodinia-cuda](./docs/fns/rodinia-cuda): The Rodinia HPC benchmarking suite, GPU-based using CUDA.


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

 * `fns`: Individual functions that can be used and composed in benchmarks (overviewed in the Functions section above).
 * `examples`: Top-level benchmark Makefile and individual benchmarks using workflows of these functions (overviewed [here](./examples/README.md)).
 * `launcher`: An abstraction layer to launch any function on any backend (described [here](./docs/launcher.md)).
 * `backends`: Config files to run custom backends (described [here](./docs/backends.md)).
 * `workflows`: A description of workflow formats and a conversion script from CNCF format to Makefiles (described [here](./workflows/README.md).
 * `runlogs`: Output top-level directory for log files from individual function runs, organized by experiment subdirectories.
 * `reports`: Output top-level directory for complete benchmark results and analyses, organized by experiment subdirectories.
 * `docs`: Contains general setup instructions, as well as instructions specific to each backend, function, and benchmark.
 * `test`: Contains test implementations and mock launchers for testing the launcher framework with different configurations.
