# Custom Backend Configurations Overview

## YAML-based Backends

### `docker.yaml`
- **Docker**: Manages Docker containers for function execution, including commands for restarting containers and making HTTP requests to container IP addresses.

### `fission.yaml`
- **Fission**: Uses Fission functions, with support for pod management and testing function endpoints in a Kubernetes environment.

### `inner_time.yaml`
- **Inner Time**: Extracts runtime metrics reported directly by the function using the "@@@ Time" marker in output.

### `knative.yaml`
- **Knative**: Focuses on managing serverless Knative services, including commands for interacting with pods and services in a Kubernetes cluster.

### `memory.yaml`
- **Memory**: Measures the memory usage of commands, using `/usr/bin/time` to report various statistics such as maximum resident set size.

### `perf.yaml`
- **Performance**: Utilizes the `perf` tool to measure and report performance metrics such as:
  - Cache misses
  - Context switches
  - Branch misses
  - CPU migrations
  - Page faults
  - TLB misses
  - Various cache level misses

### `power_iLO.yaml`
- **Power iLO**: Measures power consumption metrics using HPE's iLO (Integrated Lights-Out) interface:
  - Average power consumption
  - Maximum power consumption
  - Minimum power consumption
  - Total energy consumed

### `uname.yaml`
- **Uname**: Provides basic system information using the `uname` command, useful for fetching UNIX hostname and kernel version.

## Python-based Backends

### `mpi.py`
- **MPI Launcher**: Executes tasks using MPI (Message Passing Interface):
  - Supports parallel execution across multiple nodes
  - Configurable MPI flags
  - Automatic detection of mpirun executable
  - System specification collection through MPI environment

### `ssh.py`
- **SSH Launcher**: Runs tasks remotely using SSH:
  - Supports multiple remote hosts
  - Host list can be specified directly or via a hostfile
  - Automatic SSH command detection
  - Round-robin distribution of tasks across hosts

## Usage Examples

1. Combining performance monitoring with MPI:
```bash
./launcher.py -f backends/perf.yaml -f backends/mpi.py -b perf -b mpi my_function
```

2. Measuring memory usage on remote hosts:
```bash
./launcher.py -f backends/memory.yaml -f backends/ssh.py -b ssh -b memory my_function
```

3. Power monitoring with system information:
```bash
./launcher.py -f backends/power_iLO.yaml -f backends/uname.yaml -b power -b uname my_function
```

Remember that backend order matters as each backend wraps around the next one in the command line order.
