# Custom Backend Configurations Overview

## Backend Auto-loading

SHARP automatically loads backend configuration files when you specify a backend with `-b <backend>`. This means you typically don't need to explicitly include backend config files with `-f`.

**How it works:**
1. When you use `-b <backend>`, SHARP checks if that backend already has options defined
2. If not, it searches for `backends/<backend>.yaml` (or `.json`)
3. If found, the config is automatically loaded and merged

**Examples:**
```bash
# Auto-loads backends/docker.yaml
./launcher.py -b docker my_function

# Auto-loads backends/perf.yaml and backends/mpi.yaml in that order
./launcher.py -b perf -b mpi my_function

# Explicit -f still works (and takes precedence over auto-loading)
./launcher.py -f backends/docker.yaml -b docker my_function
```

**Configuration Merge Order:**
1. All `-f` config files (in order of appearance)
2. Auto-loaded backend configs (in order of `-b` appearance)

This means if you specify `-f backends/docker.yaml -b docker`, the file is loaded once (not twice), and the explicit `-f` version takes precedence.

## List of backends

### `local.yaml` (Built-in)
- **Local**: Executes tasks directly on the local machine
  - Default backend when no other backend is specified
  - Auto-loaded when using `-b local` or when no backends specified
  - Supports filesystem cache flushing for cold-start measurements
  - Usage: `-b local` or simply omit the `-b` flag

### `docker.yaml`
- **Docker**: Manages Docker containers for function execution, including commands for restarting containers and making HTTP requests to container IP addresses.

### `fission.yaml`
- **Fission**: Uses Fission functions, with support for pod management and testing function endpoints in a Kubernetes environment.

### `inner_time.yaml`
- **Inner Time**: Extracts runtime metrics reported directly by the function using the "@@@ Time" marker in output.

### `knative.yaml`
- **Knative**: Focuses on managing serverless Knative services, including commands for interacting with pods and services in a Kubernetes cluster.

### `bintime.yaml`
- **BinTime**: Measures a wide range of resource usage metrics using `/usr/bin/time`:
  - Elapsed wall-clock time (`wall_time`)
  - System (kernel) time (`sys_time`)
  - Major page faults (`major_page_faults`)
  - Minor page faults (`minor_page_faults`)
  - Maximum resident set size (`max_rss`)
  - Percent of CPU this job got (`percent_cpu`)
  - Involuntary context switches (`involuntary_context_switches`)
  - Voluntary context switches (`voluntary_context_switches`)

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

### `mpi.yaml`
- **MPI Launcher**: Executes tasks using MPI (Message Passing Interface):
  - Supports parallel execution across multiple nodes
  - Configurable MPI flags via YAML
  - System specification collection through MPI environment
  - Usage: `-f backends/mpi.yaml -b mpi`

### `mpip.yaml`
- **MPI Profiling (mpiP)**: Executes MPI tasks with comprehensive performance profiling using the mpiP library:
  - Automatic mpiP library preloading and environment setup
  - Generates detailed MPI performance profiles and call statistics
  - Rank-specific output collection with hostname and CPU affinity reporting
  - Automated processing of mpiP output files for metric extraction
  - Configurable MPI flags for multi-host and network settings
  - Automatic cleanup of temporary and profiling files after execution
  - Requires mpiP library installation and Python processing script
  - Usage: `-f backends/mpip.yaml -b mpip`

### `ssh.yaml`
- **SSH Launcher**: Runs tasks remotely using SSH:
  - Supports multiple remote hosts
  - Host list can be specified directly or via a hostfile in YAML
  - Round-robin distribution of tasks across hosts
  - Usage: `-f backends/ssh.yaml -b ssh`

### `strace.yaml`
- **Strace**: Measures time spent in various system calls using `/usr/bin/strace -c`.
  - Reports time spent per system call (auto-detected)
  - Useful for profiling syscall-level performance bottlenecks

### `temps.yaml`
- **Temps**: Measures CPU package and core temperatures using `/usr/bin/sensors`.
  - Reports temperature for each CPU package and core (auto-detected)
  - Useful for thermal profiling and hardware monitoring


## Usage Examples

1. Local execution (auto-loaded):
```bash
./launcher.py my_function
# or explicitly:
./launcher.py -b local my_function
```

2. Combining performance monitoring with MPI (auto-loaded):
```bash
./launcher.py -b perf -b mpi my_function
# Equivalent to the old way:
# ./launcher.py -f backends/perf.yaml -f backends/mpi.yaml -b perf -b mpi my_function
```

3. Measuring resource usage on remote hosts (auto-loaded):
```bash
./launcher.py -b ssh -b bintime my_function
```

4. Power monitoring with system information (auto-loaded):
```bash
./launcher.py -b power_iLO -b uname my_function
```

5. Mixing explicit config files with auto-loading:
```bash
# Custom config overrides auto-loaded defaults
./launcher.py -f my_custom_docker.yaml -b docker my_function
```

Remember that backend order matters as each backend wraps around the next one in the command line order and the arguments are only included for the innermost(rightmost) backend.
