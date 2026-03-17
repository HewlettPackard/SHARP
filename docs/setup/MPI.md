# Setup MPI

SHARP supports MPI benchmarks through the `mpi` backend and through benchmark definitions such as `mpi-pingpong-single` in `benchmarks/micro/mpi/benchmark.yaml`.

## Basic host setup

Install OpenMPI on the systems that will launch and run MPI jobs:

```sh
sudo apt update
sudo apt install openmpi-bin libopenmpi-dev -y
```

Verify the installation:

```sh
mpirun --version
```

## Running an MPI benchmark

Run the shipped microbenchmark with two ranks:

```sh
uv run launch -b mpi --mpl 2 mpi-pingpong-single 10
```

If you need to pin execution to specific hosts, pass MPI backend options with `-j`, for example:

```sh
uv run launch -b mpi --mpl 2 \
	-j '{"backend_options": {"mpi": {"mpiflags": "--host host1:2,host2:2"}}}' \
	mpi-pingpong-single 10
```

## Notes on multi-service MPI workflows

Earlier SHARP versions included repo-managed examples for MPI across multiple services. Those examples are no longer shipped. If you need a multi-service MPI deployment, provide your own benchmark definition and deployment artifacts, then use the MPI backend with the appropriate host and launch configuration.
