# SHARP Profiling Framework

The Profile tab in SHARP's GUI enables root-cause analysis of performance variation through a systematic workflow that connects high-level performance behaviors to low-level system metrics and actionable mitigation strategies.

## Overview

### The Profile Tab Workflow

The Profile tab implements a four-phase methodology for understanding and addressing performance issues:

**1. Identify Performance Classes of Interest**

The first step is classifying benchmark runs into meaningful performance categories based on outcome metrics (e.g., execution time, throughput). SHARP provides multiple labeling strategies:

- **Binary**: Fast vs Slow (e.g., cache hit vs miss behavior)
- **Tertile/Quartile**: Equal-sized performance groups for statistical analysis
- **Auto**: Automatic discovery of natural performance modes, temporal phases (warmup/cooldown), and tail latency

These labels define the dependent variable (Y) for subsequent analysis: "What causes a run to be SLOW vs FAST?"

**2. Find Associated Low-Level Metrics**

Once performance classes are identified, SHARP examines low-level profiling metrics (cache misses, context switches, page faults, etc.) to find statistical associations with the classes.

Using profiling backends like `perf`, `strace`, or `bintime`, SHARP collects hundreds of system-level metrics. The Profile tab's decision tree training reveals which metrics best predict class membership. For example:
- "SLOW runs have >50K cache misses"
- "TAIL latency correlates with >100 context switches"

**3. Identify Mitigating Factors**

After discovering predictive metrics, the next step is identifying experimental factors (configuration parameters, input sizes, environment variables) that could alleviate these issues.

Decision tree analysis uses factor values (X variables) to predict performance classes (Y variable), revealing rules like:
- "Thread count > 8 → SLOW (due to lock contention, high context switches)"
- "Cache size < 512MB → MODE_3 (cache thrashing, high LLC misses)"

These rules suggest concrete mitigations: reduce thread count, increase cache allocation, etc.

**4. Evaluate Empirical Effect**

The final step validates proposed mitigations through targeted experiments. SHARP's sweep functionality tests hypotheses:
- Change identified factors (reduce threads, increase memory)
- Re-run benchmarks under new conditions
- Compare outcome metrics and profiling data

This closes the analysis loop: hypothesis (from decision tree) → intervention (factor sweep) → validation (outcome measurement).

### Why This Approach Works

Traditional profiling shows "what happened" (e.g., 100K cache misses). SHARP's Profile tab answers "why it happened" (threading policy) and "how to fix it" (reduce thread count). By connecting three data layers—**outcomes** (time), **mechanisms** (cache misses), and **controls** (thread count)—the workflow transforms observation into actionable understanding.

### Key Concepts

**Performance Classes (Labels):**
Discrete categories assigned to runs based on outcome metrics. These become the target variable for decision tree training.

**Profiling Metrics:**
Low-level system measurements (CPU counters, syscall times, resource usage) collected via profiling backends. These provide mechanistic explanations for performance differences.

**Factors:**
Experimental parameters (input size, thread count, algorithm choice) that can be manipulated. Decision trees identify which factors cause performance class transitions.

**Decision Trees:**
Interpretable classifiers that reveal factor → class relationships. Each leaf node represents a rule linking factor values to performance outcomes.

## Performance Labeling Strategies

The Profile tab in the GUI provides multiple strategies for labeling performance measurements into distinct classes. This classification enables statistical analysis, decision-tree training, and root-cause identification.

### Overview of Labeling

**Why Label Performance Data?**

Performance measurements are continuous values (e.g., execution time in seconds), but analysis often requires discrete categories:
- **Statistical comparison**: "FAST vs SLOW" groups for hypothesis testing
- **Machine learning**: Training decision trees requires labeled classes
- **Root cause analysis**: Identifying factors that cause specific performance behaviors
- **Visualization**: Color-coded plots by performance class

**Design Philosophy:**

SHARP's labelers are **rule-based classifiers**, not ML models:
- They assign labels based on **thresholds**, **quantiles**, or **natural groupings**
- They are **deterministic** and **interpretable**
- They serve as **ground truth** for training ML classifiers (decision trees)

### Available Labeling Strategies

#### 1. Binary Labeling (`binary`)

**Description:** Divides samples into two classes (FAST/SLOW) using a single cutoff threshold.

**How it works:**
1. Automatically determines cutoff using distribution analysis (mode detection, valley finding, or median)
2. If `lower_is_better=True`: samples ≤ cutoff are FAST, samples > cutoff are SLOW
3. If `lower_is_better=False`: samples ≤ cutoff are SLOW, samples > cutoff are FAST

**Class names:**
- `FAST` - Better performing samples
- `SLOW` - Worse performing samples

**When to use:**
- Simple "good vs bad" performance analysis
- Clear bimodal distributions (e.g., cache hit vs cache miss)
- Debugging specific performance regressions
- When you want manual cutoff adjustment (binary labeler is mutable)

**Interactive features:**
- **Click on plot**: Move cutoff to clicked location
- **Search for cutoff**: Exhaustive search to minimize AIC (Akaike Information Criterion)

**Example use case:**
```
# Scenario: Database query performance
# Bimodal distribution: queries that hit index (5ms) vs full table scan (500ms)
# Binary labeling: Cutoff at 50ms separates fast (indexed) from slow (unindexed)
```

#### 2. Tertile Labeling (`tertile`)

**Description:** Divides samples into three equal-sized groups based on 33rd and 67th percentiles.

**How it works:**
1. Computes 33rd percentile (P33) and 67th percentile (P67)
2. Assigns labels based on value ranges:
   - If `lower_is_better=True`:
     - values ≤ P33 → `FAST`
     - P33 < values ≤ P67 → `MIDDLE-THIRD`
     - values > P67 → `SLOW`
   - If `lower_is_better=False`: order is reversed

**Class names:**
- `FAST` - Bottom third (best performing)
- `MIDDLE-THIRD` - Middle third
- `SLOW` - Top third (worst performing)

**When to use:**
- Uniform or approximately symmetric distributions
- When you want equal sample sizes in each class for statistical power
- Exploring gradual performance degradation patterns
- No clear natural groupings in the data

**Characteristics:**
- **Immutable**: Cutoffs are quantile-based and not manually adjustable
- **Balanced classes**: Each class has ~33% of samples
- **Order-preserving**: Monotonic relationship with performance

**Example use case:**
```
# Scenario: Network latency measurements
# Approximately uniform distribution: 10ms to 100ms
# Tertile labeling: FAST (10-40ms), MIDDLE (40-70ms), SLOW (70-100ms)
```

#### 3. Quartile Labeling (`quartile`)

**Description:** Divides samples into four equal-sized groups based on 25th, 50th, and 75th percentiles.

**How it works:**
1. Computes quartile boundaries: P25, P50 (median), P75
2. Assigns labels based on value ranges:
   - If `lower_is_better=True`:
     - values ≤ P25 → `FAST`
     - P25 < values ≤ P50 → `SECOND-QUARTILE`
     - P50 < values ≤ P75 → `THIRD-QUARTILE`
     - values > P75 → `SLOW`
   - If `lower_is_better=False`: order is reversed

**Class names:**
- `FAST` - First quartile (best performing)
- `SECOND-QUARTILE` - Second quartile
- `THIRD-QUARTILE` - Third quartile
- `SLOW` - Fourth quartile (worst performing)

**When to use:**
- Fine-grained performance analysis
- Identifying subtle performance variations
- Statistical studies requiring quartile-based groupings
- When you need balanced classes with more granularity than tertiles

**Characteristics:**
- **Immutable**: Cutoffs are quantile-based
- **Balanced classes**: Each class has ~25% of samples
- **Finer granularity**: More classes than tertile for detailed analysis

**Example use case:**
```
# Scenario: Compiler optimization levels
# Distribution: Gradual performance improvement across optimization flags
# Quartile labeling: Separates O0, O1, O2, O3 performance ranges
```

#### 5. Manual Labeling (`manual`) - User-Controlled Multi-Class

**Description:** Flexible multi-class labeling with user-specified number of cutoffs (1-9), supporting both manual adjustment and automated optimization.

**How it works:**
1. User selects number of cutoffs (1-9) from dropdown menu
2. Initial cutoffs determined automatically:
   - For 1 cutoff: Uses `suggest_cutoff()` (mode detection or median)
   - For multiple cutoffs: Uses evenly-spaced quantiles
3. User can adjust:
   - **Click on plot**: Move nearest cutoff to clicked location
   - **Change cutoff count**: Add/remove cutoffs (preserves existing values when possible)
   - **Search for cutoffs**: Automated optimization using Jenks + AIC

**Class names:**
- `GROUP_1` - First group (lowest values if `lower_is_better=True`)
- `GROUP_2` - Second group
- `GROUP_3` - Third group
- ... continues up to `GROUP_N`

**When to use:**
- You know the expected number of performance modes (e.g., 3 cache levels)
- Debugging specific performance behaviors requiring custom boundaries
- Iterative analysis where you refine cutoffs based on tree results
- When Auto's heuristics don't match your domain knowledge

**Interactive features:**
- **Change # cutoffs**: Dropdown selector (1-9) dynamically adjusts grouping
- **Click on plot**: Move nearest cutoff to clicked location
- **Find Cutoffs**: Automated search using Jenks natural breaks + AIC optimization
  - Tries all cutoff counts (1-9)
  - For each count, uses Jenks algorithm to find optimal placement
  - Trains decision tree and computes AIC
  - Selects configuration with minimum AIC

**Characteristics:**
- **Mutable**: Fully adjustable cutoffs and count
- **Preserves state**: When adding cutoffs, existing values are retained
- **Order-preserving**: GROUP_1 < GROUP_2 < GROUP_3, etc.
- **Flexible granularity**: From binary (1 cutoff) to fine-grained (9 cutoffs)

**Automated search algorithm:**
```
For num_cutoffs = 1 to 9:
    1. Use Jenks natural breaks to find optimal cutoff locations
    2. Create ManualLabeler with these cutoffs
    3. Train decision tree on labeled data
    4. Compute AIC = -2×log_likelihood + 2×n_nodes
    5. Track best configuration
Return cutoffs with minimum AIC
```

**Example use cases:**
```
# Scenario 1: Memory hierarchy analysis
# 3 distinct cache levels (L1, L2, L3 misses)
# Manual labeling: 2 cutoffs separate 3 performance groups
#   GROUP_1: L1 hits (fastest)
#   GROUP_2: L2 hits (medium)
#   GROUP_3: L3 misses (slowest)

# Scenario 2: Thread scaling behavior
# Performance plateaus at 4, 8, 16 threads
# Manual labeling: 3 cutoffs separate scaling regimes
#   GROUP_1: Excellent scaling (1-4 threads)
#   GROUP_2: Good scaling (5-8 threads)
#   GROUP_3: Poor scaling (9-16 threads)
#   GROUP_4: Degradation (>16 threads, contention)

# Scenario 3: Unknown structure with automated search
# "Find Cutoffs" discovers 5 distinct modes
# Decision tree reveals: GROUP_1-3 → input size, GROUP_4-5 → memory exhaustion
```

**Comparison with other strategies:**

| Aspect | Binary | Tertile/Quartile | Auto | Manual |
|--------|--------|------------------|------|--------|
| **Number of classes** | 2 | 3 or 4 | 2-7 (auto) | 2-10 (user choice) |
| **Cutoff placement** | Auto | Quantile | Jenks + temporal | Jenks + manual |
| **Mutability** | Yes (1 cutoff) | No | No | Yes (all cutoffs) |
| **User control** | Medium | None | None | Full |
| **Automated search** | Yes | No | N/A | Yes (all counts) |
| **Best for** | Simple analysis | Statistical | Discovery | Iterative/domain-driven |

**Why Manual is useful:**

1. **Domain knowledge**: You know performance has 3 modes (cache levels) but Auto finds 2
2. **Iterative refinement**: Start with Auto, then switch to Manual to adjust boundaries
3. **Custom granularity**: Need 5 groups for detailed SLO analysis (P50, P75, P90, P95, P99)
4. **Debugging**: Narrow down issue by adjusting cutoffs while watching tree structure

#### 4. Auto Labeling (`auto`) - Hybrid Strategy

**Description:** Sophisticated multi-phase approach combining temporal analysis, tail detection, and natural clustering.

**How it works (3-phase pipeline):**

**Phase 1: Temporal Detection**
- Uses **changepoint detection** (PELT algorithm) to identify performance shifts over time
- Detects `WARMUP`: Initial transient period (first 30% of samples with changepoint)
  - Example: JIT compilation, cache warming, connection pooling
- Detects `SLOWDOWN`: Final degradation period (last 30% of samples with changepoint)
  - Example: Memory leaks, resource exhaustion, thermal throttling
- **Why this matters**: Warmup slowness has different root causes than steady-state slowness

**Phase 2: Tail Isolation**
- Applies **IQR-based outlier detection** to remaining steady-state samples
- Computes Q1 (25th percentile) and Q3 (75th percentile)
- If `lower_is_better=True`: outliers are values > Q3 + 1.5×IQR (high tail)
- If `lower_is_better=False`: outliers are values < Q1 - 1.5×IQR (low tail)
- **Classification logic**:
  - If ≥ 5 samples AND ≥ 2% of data → labeled as `TAIL` (meaningful tail latency)
  - If < 5 samples → labeled as `OUTLIERS` (sparse anomalies, not analyzable)
- **Why this matters**: Tail latency (P95, P99) requires separate analysis from median behavior

**Phase 3: Body Clustering**
- Applies **Jenks Natural Breaks** optimization to remaining body samples
- Jenks algorithm: Minimizes within-class variance, maximizes between-class variance
- **Finds natural groupings** in the data (valleys between modes)
- **Adaptive class naming**:
  - If 2 modes detected: `FAST_PATH` and `SLOW_PATH`
  - If 3+ modes detected: `MODE_1`, `MODE_2`, `MODE_3`, etc.
- Uses **Goodness of Variance Fit (GVF)** to determine optimal number of classes (2-4)

**Class names (dynamic):**
- `WARMUP` - Startup transient phase
- `FAST_PATH` or `MODE_1` - Fastest body mode
- `SLOW_PATH` or `MODE_2` - Slower body mode
- `MODE_3`, `MODE_4` - Additional modes if detected
- `TAIL` - Tail latency samples (if sufficient)
- `OUTLIERS` - Sparse extreme values (if present)
- `SLOWDOWN` - Degradation phase

**When to use:**
- Complex performance distributions with multiple behaviors
- Time-series data where temporal phases matter
- Systems with distinct operational modes (e.g., cache hit/miss, fast/slow paths)
- SLO-focused analysis (isolating tail latency)
- When you want SHARP to automatically discover structure

**Characteristics:**
- **Immutable**: Automatically determined from data structure
- **Unbalanced classes**: Class sizes vary based on natural groupings
- **Temporal awareness**: Respects time-series order
- **Physics-informed**: Separates startup, steady-state, tail, and degradation

**Example use case:**
```
# Scenario: Microservice request latency (100,000 samples)
# Auto labeling discovers:
#   - WARMUP (first 5,000 samples): Cold start, JIT compilation
#   - FAST_PATH (60,000 samples): In-memory cache hits
#   - SLOW_PATH (30,000 samples): Database queries
#   - TAIL (4,000 samples): Network contention, GC pauses
#   - OUTLIERS (1,000 samples): Rare timeout events
```

**Comparison with quantile-based approaches:**

| Aspect | Quantile (Tertile/Quartile) | Auto (Hybrid) |
|--------|------------------------------|---------------|
| **Temporal awareness** | None - mixes startup and steady-state | Separates warmup/cooldown from body |
| **Tail handling** | Outliers grouped with top quantile | Tails explicitly isolated if meaningful |
| **Mode detection** | Arbitrary splits | Finds natural valleys in distribution |
| **Class balance** | Always balanced (equal sizes) | Unbalanced (follows natural structure) |
| **Interpretability** | "Top 25%" vs "Bottom 25%" | "Cache hits" vs "Cache misses" |

**Why Auto is better for root cause analysis:**

1. **Time matters**: Warmup slowness (code loading) ≠ steady-state slowness (lock contention)
2. **Tails are special**: P99 latency has different causes than P50 latency
3. **Natural groupings**: System behaviors often cluster (binary state machines: locked/unlocked)
4. **Avoids arbitrary splits**: Jenks finds valleys, not arbitrary percentiles

### Labeling Workflow in GUI

1. **Load experiment**: Select experiment and task in Profile tab
2. **Choose outcome metric**: Select the performance metric to analyze (e.g., `time`, `cpu_time`)
3. **Select labeling strategy**: Choose from binary, tertile, quartile, or auto
4. **Interactive adjustment** (binary only):
   - Click on distribution plot to move cutoff
   - Use "Search for Cutoff" button to optimize AIC
5. **Exclude predictors**: Remove correlated or invariant features
6. **Train decision tree**: Use labeled classes to identify root causes

### Technical Details

#### Jenks Natural Breaks Algorithm

The Jenks algorithm (Fisher-Jenks optimization) is a 1D clustering technique:

**Algorithm:**
1. Sort data: $x_1 \leq x_2 \leq \cdots \leq x_n$
2. Use dynamic programming to minimize sum of squared deviations (SSD) within classes
3. Maximize SSD between classes

**Objective function:**
$$\text{GVF} = 1 - \frac{\sum_{k=1}^{K} \text{SSD}_{\text{within class } k}}{\text{SSD}_{\text{total}}}$$

**Why it works:** Natural "breaks" occur at valleys in the distribution where density is low.

**Computational complexity:** $O(n^2 K)$ where $n$ = samples, $K$ = classes

**SHARP's optimization:** For small datasets ($n < 2K$), falls back to quantiles

#### Changepoint Detection (PELT Algorithm)

SHARP uses the PELT (Pruned Exact Linear Time) algorithm from the `ruptures` library:

**Algorithm:**
1. Model: Detects changes in mean/variance using cost function
2. Penalty: $\lambda = 3 \log(n)$ (BIC-like penalty to avoid over-segmentation)
3. Minimum segment size: $\max(3, 0.05n)$ to ensure statistical validity

**Model selection:**
- $n \leq 500$: RBF kernel (more accurate, $O(n^2)$)
- $n > 500$: L2 norm (faster, $O(n \log n)$)

**Output:** List of changepoint indices where distribution shifts

#### IQR-Based Tail Detection

**Standard outlier detection:**
- Interquartile range: $\text{IQR} = Q_3 - Q_1$
- Lower fence: $Q_1 - 1.5 \times \text{IQR}$
- Upper fence: $Q_3 + 1.5 \times \text{IQR}$

**SHARP's adaptation:**
- Respects `lower_is_better` semantics (only upper tail for latency, only lower tail for throughput)
- Requires minimum tail size (5 samples AND 2% of data) to avoid labeling sparse noise
- Distinguishes `TAIL` (analyzable) from `OUTLIERS` (too sparse)

### Best Practices

1. **Start with Auto**: Let SHARP discover structure, then refine if needed
2. **Use Binary for A/B testing**: When you have clear hypothesis about a change
3. **Use Quantiles for balanced classes**: When statistical power matters more than interpretability
4. **Check for warmup**: Always inspect the first few samples - Auto labeling catches this automatically
5. **Tail latency matters**: If analyzing SLOs, Auto or manual P95/P99 cutoffs are essential
6. **Validate with plots**: Visual inspection of colored scatter plots confirms labeling makes sense

## Profiling Backends and Data Collection

### What Are Profiling Backends?

Profiling backends are composable tools that collect low-level system metrics during benchmark execution. Unlike outcome metrics (time, throughput) which measure overall performance, profiling metrics capture mechanistic details:

- **Hardware counters**: CPU cycles, cache misses, branch mispredictions (via `perf`)
- **System calls**: Time spent in kernel operations, I/O patterns (via `strace`)
- **Resource usage**: Memory consumption, context switches, page faults (via `bintime`)
- **Thermal behavior**: CPU temperatures during sustained load (via `temps`)

These metrics provide the explanatory variables for understanding *why* performance varies.

### Backend Composition

Profiling backends can be **composed** with execution backends to create flexible analysis pipelines:

```bash
# Collect CPU counters during local execution
uv run launch -b perf -b local benchmark

# Profile MPI communication with system call tracing
uv run launch -b strace -b mpi benchmark

# Stack multiple profiling tools for comprehensive data
uv run launch -b temps -b strace -b perf -b local benchmark
```

**Composition rules:**
- **Composable backends** (`perf`, `strace`, `bintime`, `temps`, `local`, `ssh`): Can appear anywhere in the chain
- **Non-composable backends** (`mpip`, `docker`, `knative`): Must be used alone or as leftmost backend
- Backends are applied **right-to-left** (first specified wraps all others)

### Profiling Output Files

When profiling backends are used, SHARP generates `-prof` suffixed files:

```
runlogs/experiment/
  benchmark.csv          # Outcome metrics (time, throughput)
  benchmark-prof.csv     # Profiling metrics (cache misses, context switches)
  benchmark.md           # Outcome metadata
  benchmark-prof.md      # Profiling metadata
```

All profiling metrics from multiple backends are merged into a single `*-prof.csv` file for integrated analysis in the Profile tab.

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
task,start,repeat,concurrency,rank,outer_time,perf_time,cache_misses,context_switches,...
hotspot-prof,normal,1,1,0,1.234,1.230,45678,23,...
hotspot-prof,normal,2,1,0,1.245,1.241,45123,25,...
```

Contains one row per benchmark run with all collected profiling metrics.

**Markdown format (`benchmark-prof.md`):**

Contains experiment metadata and field descriptions (not per-run results):

```markdown
Experiment completed at 2025-03-01 01:15:08+00:00

This file describes the fields in benchmark-prof.csv.
The measurements were run on etc1, starting at 2025-03-01 01:07:23+00:00.
The source code version used was from git hash: af206b7

## Runtime options

{
  "function": "/path/to/benchmark",
  "arguments": "...",
  "backends": ["local", "perf"],
  "repeats": "KS",
  ...
}

## Field description

  * `task` (string): Task name.
  * `start` (string): Warm, cold, or normal start.
  * `repeat` (int): Batch number (iteration) when a task is repeated.
  * `concurrency` (int): No. of concurrent runs.
  * `rank` (int): Concurrent run number.
  * `outer_time` (numeric): External measured run time (s); lower is better.
  * `perf_time` (numeric): Wall-clock duration as measured by perf (seconds); lower is better.
  * `cache_misses` (numeric): overall cache misses (count); lower is better.
  * `context_switches` (numeric): context switches (count); lower is better.
  ...
```

The markdown file serves as a **data dictionary** for the CSV, documenting:
- Experiment configuration and runtime options
- Git hash for reproducibility
- Field names, types, descriptions, and units
- Metric extraction patterns (how each metric was computed)

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
    run: "vtune -collect hotspots -result-dir vtune_results -- $CMD $ARGS"
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
- `run`: Shell command with `$CMD` and `$ARGS` placeholders
- `reset`: Optional cleanup command
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

### Decision Trees Missing Important Factors

**Problem:** Decision trees seem incomplete or miss factors you know are important. Trees show weak splits or fail to identify known relationships.

**Cause:** Predictor selection picks only top-3 correlated metrics per family. Factors with **weak overall correlation but strong conditional correlation** may be excluded. For example:
- Predictor X has correlation 0.4 with outcome (ranks 5th in its family, excluded)
- But X splits data into two groups where other predictors correlate at 0.8+ in each group
- Decision tree could benefit from X as top-level split, but it's excluded

**Solution (in order of effectiveness):**

1. **Lower `max_correlation` threshold** in `settings.yaml`:
   ```yaml
   profiling:
     max_correlation: 0.90  # or 0.95, down from default 0.99
   ```
   - Includes more predictors with moderate correlations
   - These may be the ones that split well despite weak overall association
   - Trade-off: More predictors = larger trees, but more comprehensive analysis
   - **Most effective approach for capturing non-linear relationships**

2. **Increase `max_per_group`**:
   ```yaml
   profiling:
     predictor_selection:
       max_per_group: 5  # or 10, up from default 3
   ```
   - Includes more representatives from each metric family
   - Captures predictors that may have interaction effects
   - Trade-off: Less diversity across families, but more depth within families

3. **Increase `max_predictors`**:
   ```yaml
   profiling:
     max_predictors: 300  # or 500, up from default 200
   ```
   - Allows more predictors from more families
   - With 10-16x speedup, this is feasible
   - Trade-off: Minimal performance impact, comprehensive coverage

**Recommendation:** Start by lowering `max_correlation` to 0.90-0.95. This is the most effective way to include predictors with non-linear or interaction effects.

## Performance Optimizations

SHARP includes two major optimizations for large-scale profiling data: **predictor selection for wide datasets** and **decision tree training for tall datasets**. These optimizations work together to handle datasets with tens of thousands of columns and rows efficiently.

### Predictor Selection Optimization (Wide Data)

When analyzing datasets with tens of thousands of columns (e.g., storage arrays with 39,000+ metrics), SHARP uses a **hybrid approach** combining vectorized operations, categorical variable support, and semantic grouping for efficient and accurate predictor selection.

#### Algorithm: 5-Phase Pipeline

SHARP's predictor selection combines multiple strategies:

**Phase 1: Vectorized Type Detection & Variance Filtering**
- Uses Polars `std()` to compute standard deviations for all columns in single operation
- Separates numeric columns (correlation via Pearson) and categorical columns (correlation via eta-squared)
- Identifies categorical columns: 2-100 unique values (flags, states, configuration parameters)
- **Performance**: 1.9s for 39,570 columns (vs 45s with loops)

**Phase 2A: Vectorized Numeric Correlation**
- Uses Polars `pl.corr(metric, predictor)` on **full dataset** (no sampling)
- Processes columns in chunks of 5,000 to manage memory
- **Performance**: 1.0s for 32,000 numeric columns
- **Reliability**: Full-data correlations eliminate sampling artifacts

**Phase 2B: Categorical Correlation (Eta-Squared)**
- Computes effect size via ANOVA for categorical predictors
- Formula: `η² = SS_between / SS_total` (proportion of variance explained by groups)
- Filters weak associations (eta < 0.01 threshold)
- **Performance**: 0.9s for 367 valid categorical predictors
- **Coverage**: Captures categorical factors missed by numeric-only approaches

**Phase 3: Automatic Semantic Grouping**
- Extracts metric type from column names without requiring naming policy
- Pattern: `PREFIX_metric_location_instance` → group by `PREFIX_metric`
  - Examples: `LD_Qlen_tp_0_sd_0_377` → `LD_Qlen`, `PROC_nice_nd0_28` → `PROC_nice`
- Stops at location indicators: `nd0-3`, `tp`, `sd`, `sa`, or digit sequences
- **Result**: Discovers 300+ metric families automatically

**Phase 4: Representative Selection**
- Selects top-k predictors **per metric family** (default: 3)
- Ensures diversity: avoids over-representation of any single metric type
- Within each family, ranks by correlation strength
- **Result**: 100 predictors spanning 50+ metric families

**Phase 5: Final Ranking**
- Sorts all selected representatives by correlation
- Returns top max_predictors (default: 200)
- Filters perfect correlations (>0.99) to avoid redundancy

#### Configuration Parameters

Settings are defined in `settings.yaml` under `profiling` and `profiling.predictor_selection`:

| Parameter | Default | Purpose | Impact |
|-----------|---------|---------|--------|
| `max_predictors` | 200 | Maximum predictors to select | Higher values provide more comprehensive analysis but increase tree complexity. Set to 200 (up from 100) due to 10-16x speedup in selection. |
| `max_correlation` | 0.99 | Maximum correlation threshold | Filters highly correlated predictors to reduce redundancy. Lower values (e.g., 0.95, 0.90) select more diverse but potentially weaker predictors. **Important**: Lowering this can capture non-linear relationships by including predictors that split well even with modest overall correlation. |
| `max_categorical_unique` | 100 | Maximum unique values for categorical treatment | String columns with 2-100 unique values are treated as categorical. Higher values → more categoricals, but slower. |
| `min_eta` | 0.01 | Minimum eta-squared for categorical predictors | Filters weak categorical associations. Lower values → more predictors, but may include noise. |
| `max_per_group` | 3 | Representatives per metric family | Controls diversity vs specificity trade-off. Higher values → more similar metrics from same family. **Limitation**: Picking only top-3 per family may miss predictors that split well despite lower correlation. Consider lowering `max_correlation` to include more candidates. |
| `chunk_size` | 5000 | Chunk size for vectorized correlation | Balances memory usage and performance. Larger chunks → faster but more memory. |

**Tuning guidelines:**

- **For high-cardinality data** (100K+ columns): Reduce `max_per_group` to 1-2, increase `min_eta` to 0.02
- **For categorical-heavy data**: Increase `max_categorical_unique` to 200, reduce `min_eta` to 0.005
- **For limited diversity**: Increase `max_per_group` to 5-10
- **For memory-constrained systems**: Reduce `chunk_size` to 1000-2000

#### Performance Characteristics

**Key characteristics:**

1. **Scales to ultra-wide data**: 40k+ columns processed in 3-5 seconds
2. **Handles tall datasets efficiently**: 90k rows with minimal overhead
3. **High diversity**: 45-52 metric families represented in wide datasets
4. **Reliable correlations**: Full-data computation eliminates sampling artifacts
5. **Categorical support**: Identifies 300+ categorical predictors via eta-squared

#### VGO (Variability Guided Optimization) Benefits

The hybrid approach directly supports SHARP's VGO mission:

**1. Reliable Correlations**
- Uses full data → correlations are ground truth, not sampling artifacts
- Statistical power from complete dataset (n=14,400 vs small samples)

**2. Comprehensive Factor Discovery**
- 50+ metric families → comprehensive view including CPU, network, memory, cache, storage
- Representative selection ensures no single metric type dominates

**3. Categorical Factor Support**
- Eta-squared captures categorical predictors (configuration flags, states)
- Example: "CMP_metavv_wHit_TPVV_7" (cache hit pattern) has strong association
- Identifies 300+ valid categorical predictors from 800+ columns

**4. Actionable Insights**
- Diverse predictors lead to more comprehensive root cause analysis
- Semantic grouping reveals system-wide patterns, not just local metrics

#### Performance Scaling

The hybrid predictor selection is **always active** with performance scaling based on dataset characteristics:

- **Wide data (>10k columns)**: 3-5 seconds for 40k columns via vectorized operations
- **Moderate width (1k-10k columns)**: Sub-second to few seconds
- **Narrow data (<1k columns)**: Milliseconds with minimal overhead
- **Categorical-heavy data**: Automatic eta-squared computation for categorical predictors

All dataset sizes benefit from full-data correlations and semantic grouping.

#### Semantic Grouping: No Naming Policy Required

A key advantage: **automatic context inference** without enforcing naming conventions.

**How it works:**
- Identifies common patterns in existing column names using **underscore separators only**
- Recognizes location indicators: `nd0-3` (nodes), `tp` (time period), `sd` (standard deviation)
- Stops at digit sequences (instance IDs)
- Falls back gracefully for non-standard names (uses first 2 parts)
- **Limitation**: Only recognizes underscore-separated names (e.g., `metric_subtype_location`). Dots, hyphens, or camelCase are treated as single tokens.

**Examples:**
- `LD_Qlen_tp_0_sd_0_377` → `LD_Qlen` (load queue length)
- `PD_Qlen_54_0_2_1` → `PD_Qlen` (port queue length)
- `PROC_nice_nd0_28` → `PROC_nice` (process niceness)
- `VVLogCons_hit_blks_TPVV_30` → `VVLogCons_hit_blks` (volume log consistency hits)
- `system.cpu.usage` → `system.cpu.usage` (no grouping, treated as single type)
- `cpu-usage-node0` → `cpu-usage-node0` (no grouping, treated as single type)

**Why this matters:**
- No need to rename 39,000 columns in existing datasets
- Works with legacy data collection systems using underscore conventions
- Adapts to new metric types automatically
- Users don't need to learn/enforce naming policies (as long as underscores are used)

#### Correctness Guarantees

**Statistical validity:**
- Pearson correlation: Valid for linear relationships (most performance metrics)
- Eta-squared: Valid for categorical → continuous associations (ANOVA-based)
- Full-data computation: Eliminates sampling bias

**Semantic grouping:**
- Worst-case: Treats each column as unique family (reverts to top-200 by correlation)
- Common case: Discovers 50-300 families, selects 3 representatives each
- No information loss: Top correlations from each family are preserved

**Diversity guarantee:**
- At least `min(max_predictors / max_per_group, n_families)` families represented
- Example: 200 predictors, 3 per group → at least 66 families
- Prevents over-representation of any single metric type

#### Tuning the Algorithm

**Disable semantic grouping (use correlation-only):**
```yaml
profiling:
  predictor_selection:
    max_per_group: 100  # Effectively disables grouping
```

**Disable categorical support:**
```yaml
profiling:
  predictor_selection:
    max_categorical_unique: 0  # Treat all non-numeric as excluded
```

**Increase diversity:**
```yaml
profiling:
  predictor_selection:
    max_per_group: 1  # Only best predictor from each family
```

### Decision Tree Training Optimization (Tall Data)

SHARP employs **class-aware downsampling** to accelerate decision tree training on large datasets without sacrificing accuracy. This optimization intelligently reduces the training set size based on the characteristics of each performance class.

#### How It Works

The optimization is based on a key insight: **samples within a concentrated performance class are redundant from the tree's perspective**—they will all end up in the same leaf node regardless. Therefore, we can safely downsample large, homogeneous classes while preserving smaller or more heterogeneous classes.

**Algorithm:**
1. **Analyze each class independently:**
   - Calculate class size (number of samples)
   - Compute coefficient of variation (CV) across all features: `CV = std / mean`
   - CV measures concentration: low CV → tightly clustered, high CV → spread out

2. **Apply class-specific sampling rules:**
   - **Small classes** (< `min_class_size`): Keep ALL samples
     - Rare performance modes (e.g., tail latency) must be preserved
     - Example: 50 "EXTREMELY_SLOW" runs in 50,000 total

   - **Large + concentrated** (≥ `min_class_size` AND CV < `cv_threshold`): Aggressive downsampling
     - Apply `base_sample_ratio` (e.g., keep 20% → 5x reduction)
     - Example: 40,000 "NORMAL" runs with similar characteristics → sample 8,000

   - **Large + spread** (≥ `min_class_size` AND CV ≥ `cv_threshold`): Conservative downsampling
     - Keep `base_sample_ratio × (1 + CV)` samples
     - Higher CV → more samples retained
     - Example: 10,000 "VARIABLE" runs with CV=0.5 → keep 20% × 1.5 = 30% = 3,000

3. **Random sampling within each class** to reach target size

#### Configuration Parameters

Settings are defined in `settings.yaml` under `profiling.tree_training`:

| Parameter | Default | Purpose | Justification |
|-----------|---------|---------|---------------|
| `target_rows` | 5000 | Target training set size | Number of rows to select for tree training after filtering for completeness and applying class-aware downsampling. Increased from 1000 to 5000 due to combined speedups (predictor selection + downsampling). More data → more robust trees. |
| `completeness_threshold` | 0.95 | Minimum data completeness ratio | Fraction of non-null values required across selected predictors for a row to be included in training. Adaptive: starts at 0.95, lowers to 0.75, 0.5, 0.25 if insufficient rows found. Ensures training data has minimal missing values while maintaining adequate sample size. |
| `min_class_size` | 300 | Minimum samples to consider downsampling | Rare classes (<300) are often the most interesting (outliers, tail latencies). Preserving them entirely is critical for profiling. |
| `cv_threshold` | 0.15 | CV below which a class is "concentrated" | CV < 0.15 means standard deviation is <15% of mean—indicates tight clustering. Such classes are safe to downsample aggressively. Based on empirical testing with performance data. |
| `base_sample_ratio` | 0.20 | Fraction to keep for concentrated classes | 20% sampling (5x reduction) maintains tree structure while significantly reducing training time. For 50k samples → 10k, provides ~3-4x speedup. |

**Why These Defaults?**

- **`min_class_size = 300`**: Statistical rule of thumb for reliable estimates. Classes <300 may represent rare but critical performance modes.
- **`cv_threshold = 0.15`**: Empirically determined from performance profiling data. Performance metrics typically show CV=0.05-0.10 for normal operation, CV=0.2-0.5 for variable workloads.
- **`base_sample_ratio = 0.20`**: Balances speedup (5x reduction) with accuracy. Decision trees need enough samples to identify splits; 20% maintains sufficient density.

#### Performance Results

Benchmarked on large-scale profiling datasets:

| Dataset | Size | Before (avg) | After (avg) | Speedup | Samples Reduced |
|---------|------|--------------|-------------|---------|-----------------|
| Slingshot 1000-node | 45,976 × 32 | 0.077s | 0.049s | **1.57x** | 45,976 → 14,396 (69%) |
| Slingshot 2000-node | 90,668 × 32 | 0.130s | 0.102s | **1.27x** | 90,668 → 39,798 (56%) |
| Storage 2hr (wide) | 14,400 × 39,570 | 4.037s | 4.120s | 0.98x | 2,288 → 2,288 (0%) |

**Key Observations:**

1. **Tall datasets benefit most**: 45k-90k rows see 1.3-1.6x speedup from reduced `tree.fit()` time
2. **Wide datasets unaffected**: Bottleneck is predictor selection (39k columns), not tree training
3. **No accuracy loss**: Tree depth and structure remain identical (same number of leaves)
4. **Adaptive behavior**: Storage dataset had small initial sample (2,288), below downsampling threshold

#### Combined Optimization Impact

For datasets that are both tall and wide, **both optimizations work together**:

| Scenario | Example | Predictor Selection | Tree Training | Total Time |
|----------|---------|---------------------|---------------|------------|
| **Tall + Wide** | 50k rows × 40k cols | ~5s | ~0.2s | **~5s** |
| **Wide only** | 15k rows × 40k cols | ~5s | ~0.1s | **~5s** |
| **Tall only** | 90k rows × 30 cols | <0.1s | ~0.3s | **~0.4s** |

Real example: **2hrStorageData** (14,400 × 39,570)
- Predictor selection: 5.1s
- Tree training: ~0.1s
- **Total workflow: ~5s**

#### When Optimizations Apply

**Predictor selection optimization (always active):**
- Biggest benefit: >10k columns
- Moderate benefit: 1k-10k columns
- Minimal overhead: <1k columns

**Tree training optimization (conditional):**
- Active when: >10k samples AND >2 classes AND at least one concentrated class
- Biggest benefit: 50k-100k rows
- Moderate benefit: 10k-50k rows
- Inactive: <10k rows (overhead exceeds benefit)

#### Correctness Guarantees

**Predictor selection:**
- Full-data correlations provide ground truth without sampling bias
- Semantic grouping preserves top predictors from each family
- Categorical support via ANOVA is statistically valid
- Representative selection ensures diversity without information loss

**Tree training:**
- Decision trees split based on class boundaries, not individual samples
- Concentrated classes (low CV) are safely downsampled—no internal structure to lose
- Minority classes preserved entirely for accurate tail latency analysis
- Random sampling within classes is unbiased

**Validation:**
- Feature importance rankings consistent across training runs
- Tree depth and structure reproducible
- Prediction accuracy maintained through intelligent sampling

#### Tuning the Optimizations

**Adjust predictor selection:**
```yaml
profiling:
  predictor_selection:
    max_per_group: 100  # Increase for more same-family predictors (less diversity)
    chunk_size: 1000    # Reduce for memory-constrained systems
```

**Adjust tree training downsampling:**
```yaml
profiling:
  tree_training:
    min_class_size: 999999999  # Disable downsampling (use full data)
    base_sample_ratio: 1.0      # Or keep 100% of samples even for large classes
```

## See Also

- [Backend Configuration Schema](schemas/backend.md) - Backend YAML structure
- [Launch Documentation](launch.md) - Command-line options
- [Metrics Documentation](metrics.md) - Metric extraction and analysis
- [Backends Overview](backends.md) - All available backends
