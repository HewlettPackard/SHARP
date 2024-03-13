# Setup MPI

We have two approaches to running MPI applications as functions:

1. Running all MPI ranks in a single function (see example in [mpi-pingpong-single](./fns/mpi-pingpong-single.md))
1. Running MPI ranks across multiple functions (see example in [mpi-pingpong-multi](./fns/mpi-pingpong-multi.md))

## Execution as a Single Function

No further setup is required to run in a single function as `mpirun` is executed within the function and the functions are invoked using the standard invocation mechanism, e.g., HTTP triggers for Fission.

## Execution as Multiple Functions

Some setup is required for running MPI applications across multiple functions, as that requires running `mpirun` outside the function environment.

### Fission

For Fission, we use a custom agent script that executes commands normally sent over SSH/RSH within a Fission function.
This requires OpenMPI (MPICH does not offer this feature) and matching OpenMPI versions on the host and functions.
The easiest way to achieve this is to install OpenMPI from `apt` and making sure that both environments match.
We therefore use Ubuntu 20.04 both on our host and as a base image for Fission functions.
Then, we install OpenMPI as:

```sh
apt update
apt install libopenmpi-dev -y
```

Also make sure that the agent script is executable.
While this is the default when cloning this repository, this is a common pitfall and the error output from OpenMPI does not explicitly mention this:

```sh
chmod +x ./fns/mpi-pingpong-multi/fission-agent
```
