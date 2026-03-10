# SHARP Profiling Framework

SHARP provides a flexible profiling framework that enables performance analysis through composable profiling tools. Profiling backends can be combined with execution backends to collect detailed performance metrics without modifying benchmark code.

## Overview

### What is Profiling?

Profiling in SHARP refers to collecting detailed performance data during benchmark execution using external tools like `perf`, `strace`, or `mpiP`. Profiling backends:

- Wrap benchmark execution with profiling tools
- Collect metrics beyond basic runtime (CPU cycles, cache misses, syscalls, etc.)
- Generate detailed performance reports
- Can be combined with execution backends (local, MPI, SSH, Docker)

### Key Concepts

**Profiling vs Execution Backends:**
- **Execution backends** (`local`, `mpi`, `ssh`, `docker`): Define *where* and *how* benchmarks run
- **Profiling backends** (`perf`, `strace`, `mpip`, `bintime`): Define *what* performance data to collect

**Backend Composition:**
Profiling backends can be composed with execution backends to create powerful analysis pipelines:

```bash
# Profile local execution with perf
uv run launch -b perf -b local benchmark

# Profile MPI execution with strace
uv run launch -b strace -b mpi benchmark

# Stack multiple profiling tools
uv run launch -b strace -b perf -b local benchmark
```

## Available Profiling Backends

### `perf` - CPU Performance Counters

Uses Linux `perf stat` to collect hardware performance counters.

**Metrics collected:**
- `cache_misses`: Overall cache misses
- `context_switches`: Context switches during execution
- `branch_misses`: Branch prediction misses
- `cpu_migrations`: CPU migrations
- `page_faults`: Total page faults
- `dTLB_misses`: Data TLB load misses
- `iTLB_misses`: Instruction TLB load misses
- `L1_icache_misses`: L1 instruction cache load misses
- `L1_dcache_misses`: L1 data cache load misses
- `LLC_misses`: Last level cache load misses
- `cpu_clock`: CPU clock time
- `cycles`: CPU cycles
- `instructions`: Instructions retired

**Example usage:**
```bash
# Basic perf profiling
uv run launch -b perf matmul 1000

# Perf with MPI
uv run launch -b perf -b mpi --mpl 4 matmul 1000

# Multiple runs with repeater
uv run launch -b perf -j '{"repeater": {"target": "time", "target_rsd": 0.05}}' matmul 1000
```

**When to use:**
- CPU-intensive benchmarks
- Cache behavior analysis
- Branch prediction analysis
- Low-level hardware performance investigation

### `strace` - System Call Tracing

Uses `/usr/bin/strace -c` to measure time spent in system calls.

**Metrics collected:**
- `auto`: Auto-detected metrics for each system call (time spent per syscall)
- Reports percentage of time, number of calls, and errors per syscall

**Example usage:**
```bash
# System call profiling
uv run launch -b strace io_benchmark

# Combine with perf for comprehensive analysis
uv run launch -b strace -b perf io_benchmark
```

**When to use:**
- I/O intensive workloads
- Kernel interaction analysis
- Identifying syscall bottlenecks
- Debugging unexpected kernel calls

### `bintime` - Resource Usage

Uses `/usr/bin/time` to collect comprehensive resource usage metrics.

**Metrics collected:**
- `wall_time`: Elapsed wall-clock time
- `sys_time`: System (kernel) time
- `user_time`: User time
- `major_page_faults`: Major page faults
- `minor_page_faults`: Minor page faults
- `max_rss`: Maximum resident set size (memory)
- `percent_cpu`: Percent of CPU this job got
- `involuntary_context_switches`: Involuntary context switches
- `voluntary_context_switches`: Voluntary context switches

**Example usage:**
```bash
# Memory and resource profiling
uv run launch -b bintime memory_test

# Resource usage with remote execution
uv run launch -b bintime -b ssh memory_test
```

**When to use:**
- Memory usage analysis
- Context switch investigation
- Overall resource consumption monitoring
- Quick resource profiling without perf overhead

### `mpip` - MPI Profiling (Non-Composable)

Uses the mpiP library to profile MPI communication patterns.

**Special characteristics:**
- **Non-composable**: Must be used alone or as the leftmost (outermost) backend
- Replaces the standard `mpi` backend
- Requires mpiP library installation

**Metrics collected:**
- MPI communication time
- MPI call counts
- Message size distributions
- Rank-specific performance data

**Example usage:**
```bash
# MPI profiling (mpip alone)
uv run launch -b mpip --mpl 4 mpi_app

# ERROR: Cannot compose with other backends
# uv run launch -b perf -b mpip mpi_app  # INVALID!
```

**When to use:**
- MPI communication analysis
- Identifying MPI bottlenecks
- Load imbalance detection
- Message passing optimization

### `temps` - Temperature Monitoring

Uses `/usr/bin/sensors` to monitor CPU temperatures during execution.

**Metrics collected:**
- CPU package temperatures (auto-detected)
- Core temperatures (auto-detected)
- Temperature readings per CPU package

**Example usage:**
```bash
# Temperature monitoring
uv run launch -b temps cpu_intensive

# Temperature + perf analysis
uv run launch -b temps -b perf cpu_intensive
```

**When to use:**
- Thermal behavior analysis
- Cooling system evaluation
- Sustained load testing
- Hardware monitoring

## Backend Composition Rules

### Composability

Backends have a `composable` flag that determines how they can be combined:

**Composable backends** (`composable: true`):
- Can appear anywhere in the backend chain
- Wrap other backends in the command line
- Examples: `perf`, `strace`, `bintime`, `temps`, `local`, `ssh`

**Non-composable backends** (`composable: false`):
- Must be used alone OR as the leftmost (outermost) backend
- Cannot be wrapped by other backends
- Examples: `mpip`, `docker`, `knative`, `fission`

### Valid Compositions

```bash
# ✅ Valid: Single backend
uv run launch -b local app
uv run launch -b perf app

# ✅ Valid: Composable profiling + execution
uv run launch -b perf -b local app
uv run launch -b strace -b mpi app

# ✅ Valid: Multiple composable profiling
uv run launch -b strace -b perf -b local app

# ✅ Valid: Non-composable alone
uv run launch -b mpip app

# ❌ Invalid: Non-composable not leftmost
# uv run launch -b perf -b mpip app

# ❌ Invalid: Multiple non-composable
# uv run launch -b mpip -b docker app
```

### Execution Order

Backends are composed **right-to-left** (first backend is outermost, last is innermost):

```bash
uv run launch -b strace -b perf -b local sleep 1.5
```

Results in command composition:
```
strace -c (wraps perf (wraps local (wraps benchmark)))
→ strace -c perf stat -- ./sleep 1.5
```

## Profiling Output Files

### Filename Convention

When profiling backends are used, SHARP generates files with the `-prof` suffix:

```
runlogs/
  experiment/
    benchmark.csv          # Regular execution metrics
    benchmark.md           # Regular execution metadata
    benchmark-prof.csv     # Profiling metrics
    benchmark-prof.md      # Profiling metadata
```

**Important notes:**
- Single `-prof` suffix regardless of number of profiling tools
- Both `perf` alone and `perf + strace` produce `benchmark-prof.csv`
- Profiling metrics from all tools are merged into single CSV

### Output Structure

**CSV format (`benchmark-prof.csv`):**
```csv
launch_id,time,cache_misses,context_switches,branch_misses,...
1,1.234,45678,23,1234,...
2,1.245,45123,25,1189,...
```

**Markdown format (`benchmark-prof.md`):**
```markdown
# Profiling Results: benchmark

## Run 1
- **time**: 1.234 seconds
- **cache_misses**: 45678 count
- **context_switches**: 23 count
...

## System Specification
...
```

## Common Profiling Workflows

### 1. CPU-Bound Performance Analysis

Goal: Understand CPU behavior and cache performance

```bash
# Collect CPU metrics with perf
uv run launch -b perf -j '{"repeater": {"target": "time", "target_rsd": 0.05}}' matmul 1000

# View results
cat runlogs/default/matmul-prof.csv
```

**Key metrics to examine:**
- `cycles` and `instructions`: IPC (instructions per cycle)
- `cache_misses`: Memory hierarchy efficiency
- `branch_misses`: Control flow prediction

### 2. I/O and System Call Analysis

Goal: Identify I/O bottlenecks and syscall patterns

```bash
# Trace system calls
uv run launch -b strace io_test

# Combine with resource monitoring
uv run launch -b bintime -b strace io_test
```

**Key metrics to examine:**
- Time spent in `read`, `write`, `open`, `close`
- Major vs minor page faults
- Context switches

### 3. MPI Communication Profiling

Goal: Analyze MPI communication patterns and load balance

```bash
# MPI profiling with mpiP
uv run launch -b mpip --mpl 8 mpi_app

# Review MPI metrics
cat runlogs/default/mpi_app-prof.csv
```

**Key metrics to examine:**
- MPI communication time vs computation time
- Message size distributions
- Load imbalance across ranks

### 4. Multi-Tool Comprehensive Profiling

Goal: Get complete performance picture

```bash
# Stack multiple profiling tools
uv run launch -b temps -b strace -b perf -b local \
  -j '{"repeater": {"target": "time", "target_rsd": 0.05}}' complex_app
```

**Combined analysis:**
- CPU behavior from `perf`
- Syscall patterns from `strace`
- Thermal behavior from `temps`
- Statistical stability from repeater

### 5. Remote System Profiling

Goal: Profile benchmarks on remote systems

```bash
# SSH with profiling
uv run launch -b perf -b ssh benchmark

# Multiple hosts with profiling
uv run launch -b strace -b ssh \
  -j '{"backend_options": {"ssh": {"hosts": ["host1", "host2", "host3"]}}}' benchmark
```

## Profiling Best Practices

### 1. Choose Appropriate Tools

- **CPU-bound**: Use `perf` for hardware counters
- **I/O-bound**: Use `strace` for syscall analysis
- **Memory-intensive**: Use `bintime` for resource usage
- **MPI apps**: Use `mpip` for communication profiling
- **Thermal concerns**: Add `temps` for temperature monitoring

### 2. Use Statistical Repeaters

Profiling overhead can affect measurement stability. Use repeaters for reliable results:

```bash
# Target relative standard deviation
uv run launch -b perf -j '{"repeater": {"target": "time", "target_rsd": 0.05}}' app

# Fixed number of runs
uv run launch -b perf -j '{"repeater": {"count": 10}}' app
```

### 3. Combine Tools Judiciously

More profiling tools = more overhead. Start simple and add tools as needed:

```bash
# Start with one tool
uv run launch -b perf app

# Add more if needed
uv run launch -b strace -b perf app

# Comprehensive (high overhead)
uv run launch -b temps -b bintime -b strace -b perf app
```

### 4. Understand Overhead

Different profiling tools have different overhead:
- **Low overhead**: `bintime`, `temps`
- **Medium overhead**: `perf` (depends on counters)
- **High overhead**: `strace` (traces every syscall)

### 5. Check Profiling Tool Availability

Ensure profiling tools are installed before use:

```bash
# Check perf
which perf

# Check strace
which strace

# Check sensors (for temps)
which sensors

# Check mpiP library
ldconfig -p | grep mpiP
```

## Adding Custom Profiling Backends

You can add new profiling tools without modifying Python code. Just create a YAML backend definition:

### Example: VTune Backend

```yaml
# backends/vtune.yaml
version: 1.0.0
description: Intel VTune Profiler

backend_options:
  vtune:
    version: 1.0.0
    description: Intel VTune CPU profiling
    profiling: true           # Mark as profiling backend
    composable: true          # Can wrap other backends
    command_template: "vtune -collect hotspots -result-dir vtune_results -- $CMD $ARGS"
    reset: ""

metrics:
  vtune_cpu_time:
    description: CPU time from VTune
    extract: 'grep "CPU Time" vtune_results/*.csv | awk "{print $3}"'
    lower_is_better: true
    type: float
    units: seconds
```

**Usage:**
```bash
# Use the new backend (auto-loaded)
uv run launch -b vtune app

# Compose with other backends
uv run launch -b vtune -b perf -b local app
```

**Key fields for profiling backends:**
- `profiling: true`: Required - identifies this as a profiling backend
- `composable: true/false`: Can it wrap other backends?
- `command_template`: Shell command with `$CMD` and `$ARGS` placeholders
- `metrics`: Metric definitions with extraction patterns

## Troubleshooting

### Permission Errors (perf)

**Problem:** `perf` requires kernel access for hardware counters

**Solution:**
```bash
# Temporary (until reboot)
sudo sysctl -w kernel.perf_event_paranoid=-1

# Permanent
echo 'kernel.perf_event_paranoid = -1' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Missing Profiling Tools

**Problem:** Tool not found in PATH

**Solution:**
```bash
# Install perf (Ubuntu/Debian)
sudo apt-get install linux-tools-common linux-tools-generic

# Install strace
sudo apt-get install strace

# Install sensors (temps backend)
sudo apt-get install lm-sensors
sudo sensors-detect  # Configure sensors
```

### High Profiling Overhead

**Problem:** Profiling slows down benchmark significantly

**Solution:**
1. Use lower-overhead tools (`bintime` instead of `strace`)
2. Reduce perf counters (custom backend with fewer events)
3. Profile longer-running benchmarks
4. Accept overhead and adjust target metrics accordingly

### Empty Profiling Metrics

**Problem:** Profiling output file exists but metrics are NA or missing

**Solution:**
1. Check if benchmark runs too quickly (perf needs minimum time)
2. Verify metric extraction patterns in backend YAML
3. Check profiling tool output format hasn't changed
4. Run with `-v` for verbose output to see raw profiling data

### Backend Composition Errors

**Problem:** `Non-composable backends can only be in position 1 (leftmost)`

**Solution:**
- Non-composable backends (`mpip`, `docker`, `knative`) must be alone or leftmost
- Correct: `-b mpip` or `-b local -b mpip`
- Incorrect: `-b perf -b mpip`

## See Also

- [Backend Configuration Schema](schemas/backend.md) - Backend YAML structure
- [Launch Documentation](launch.md) - Command-line options
- [Metrics Documentation](metrics.md) - Metric extraction and analysis
- [Backends Overview](backends.md) - All available backends
