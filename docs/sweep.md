---
title: Parameter Sweep Support
description: Running parameter sweep experiments with combinatorial expansion
---

# Parameter Sweep Support

SHARP v4.0 supports parameter sweep experiments, allowing you to run multiple configurations of a benchmark with systematically varied parameters. This is useful for performance analysis across different problem sizes, thread counts, or runtime options.

## Overview

Parameter sweeps define variations in:
- **args**: Benchmark command-line arguments
- **env**: Environment variables
- **options**: SHARP runtime options (mpl, start, etc.)

Array values in `env` and `options` trigger **Cartesian product expansion**, automatically generating all combinations.

## Sweep Format

Sweeps are defined in YAML with a `sweep:` key containing three optional sections:

```yaml
sweep:
  args: [...]      # List of argument lists
  env: {...}       # Environment variables
  options: {...}   # SHARP options
```

| Section | Type | Purpose | Example |
|---------|------|---------|---------|
| `args` | list of lists | Benchmark arguments | `[["--size", "1024"], ["--size", "2048"]]` |
| `env` | dict | Environment variables | `{"OMP_NUM_THREADS": ["1", "4"]}` |
| `options` | dict | SHARP runtime options | `{"mpl": [1, 2], "start": "warm"}` |

All sections are optional.

## Basic Examples

### Fixed Parameters (Single Configuration)

```yaml
sweep:
  args:
    - ["--size", "1024", "--iterations", "100"]
  env:
    OMP_NUM_THREADS: "4"
  options:
    mpl: 1
```

Produces **1 configuration**.

### Multiple Argument Sets

```yaml
sweep:
  args:
    - ["--size", "1024"]
    - ["--size", "2048"]
    - ["--size", "4096"]
```

Produces **3 configurations**, one per argument list. Args use list-of-lists format with no Cartesian product.

## Combinatorial Expansion

### Array Values = Cartesian Product

Arrays in `env` or `options` generate all combinations:

```yaml
sweep:
  env:
    OMP_NUM_THREADS: ["1", "2", "4"]
  options:
    mpl: [1, 2]
```

Produces: 3 thread counts × 2 mpl values = **6 configurations**

### Mixed Scalars and Arrays

```yaml
sweep:
  env:
    OMP_NUM_THREADS: ["1", "4", "8"]  # Swept
    MKL_NUM_THREADS: "1"              # Fixed
```

Produces **3 configurations**, all with `MKL_NUM_THREADS=1`.

### Multi-Dimensional Sweeps

```yaml
sweep:
  args:
    - ["--size", "1024"]
    - ["--size", "2048"]
  env:
    OMP_NUM_THREADS: ["2", "4"]
  options:
    mpl: [1, 2]
```

Produces: 2 sizes × 2 threads × 2 mpl = **8 configurations**

## Running Sweeps

### Inline Sweep Definition

Include sweep directly in experiment config or a separate file via `include`:

```yaml
# experiment.yaml
include:
  - benchmark.yaml
  - backends/local.yaml
  - sweep_params.yaml  # Contains sweep: {...}
```

### Execution

```bash
uv run launch my_exp -c experiment.yaml -v
```

All configurations run sequentially, writing to the same output files.

### Launch IDs

Each configuration gets a unique identifier:

```
sweep_0001_a3f29c
sweep_0002_a3f29c
sweep_0003_a3f29c
```

Format: `sweep_NNNN_HHHHHH` where:
- `NNNN` = sequential number (zero-padded)
- `HHHHHH` = 6-character session hash (groups related runs)

Launch IDs appear in CSV output and link to parameters in markdown.

## Output Format

### CSV Output

Includes `launch_id` column linking rows to their configuration:

```csv
launch_id,task,repeat,rank,walltime
sweep_0001_a3f29c,matmul,1,0,1.234
sweep_0002_a3f29c,matmul,1,0,0.654
sweep_0003_a3f29c,matmul,1,0,0.387
```

### Markdown Output

#### Invariant Parameters (per launch_id)

```json
{
  "sweep_0001_a3f29c": {
    "args": ["--size", "1000"],
    "env.OMP_NUM_THREADS": "1",
    "mpl": 1
  },
  "sweep_0002_a3f29c": {
    "args": ["--size", "1000"],
    "env.OMP_NUM_THREADS": "2",
    "mpl": 1
  }
}
```

#### Sweep Parameters (overall ranges)

```json
{
  "args": "2 combinations",
  "env.OMP_NUM_THREADS": ["1", "2"],
  "mpl": [1, 2]
}
```



## Best Practices

1. **Start small**: Test with 2-3 values before large sweeps
2. **Consider runtime**: N × M × P parameters = N×M×P configurations
3. **Use repeaters**: Combine with RSE/CI for statistical rigor

```yaml
sweep:
  env:
    OMP_NUM_THREADS: ["1", "4"]
repeater: RSE
repeater_options:
  confidence: 0.95
```

## Troubleshooting

**Invalid YAML**: Validate with `yamllint`

**Wrong expansion size**: All arrays in `env`/`options` multiply:
```yaml
env:
  VAR1: ["a", "b"]       # 2 values
  VAR2: ["x", "y", "z"]  # 3 values
# = 2 × 3 = 6 configurations
```

**Validation errors**: Ensure `args` is list-of-lists, `env`/`options` are dicts

## Complete Working Example

This example creates a minimal sweep from scratch that you can reproduce.

### Step 1: Create Demo Script

```bash
#!/bin/bash
# demo.sh - Simulates computation with configurable parameters

SIZE=${1:-1000}
THREADS=${OMP_NUM_THREADS:-1}

echo "Running demo with size=$SIZE, threads=$THREADS"
echo "Simulating computation..."

# Simulate work that scales with size and parallelism
WORK_TIME=$(echo "scale=3; $SIZE / (1000 * $THREADS)" | bc)
sleep "$WORK_TIME"

echo "Work completed in ${WORK_TIME}s"
echo "METRIC: size=$SIZE"
echo "METRIC: threads=$THREADS"
echo "METRIC: walltime=$WORK_TIME"
```

Save as `demo.sh` and make executable: `chmod +x demo.sh`

### Step 2: Create Benchmark Definition

`benchmark.yaml`:

```yaml
version: "4.0"
name: demo
description: Simple demo benchmark for sweep testing
entry_point: ./demo.sh

metrics:
  size:
    description: Problem size parameter
    extract: 'grep "METRIC: size=" | cut -d= -f2'
    type: numeric
  threads:
    description: Number of threads used
    extract: 'grep "METRIC: threads=" | cut -d= -f2'
    type: numeric
  walltime:
    description: Simulated work time
    extract: 'grep "METRIC: walltime=" | cut -d= -f2'
    type: numeric
    lower_is_better: true
```

### Step 3: Create Sweep Definition

`scaling_sweep.yaml`:

```yaml
# Parameter sweep: 2 sizes × 2 thread counts = 4 configurations
sweep:
  args:
    - ["1000"]
    - ["2000"]
  env:
    OMP_NUM_THREADS: ["1", "2"]
```

### Step 4: Create Experiment Config

`experiment.yaml`:

```yaml
version: "4.0"
include:
  - benchmark.yaml
  - backends/local.yaml
  - scaling_sweep.yaml
options:
  directory: runlogs/sweep_demo
```

### Step 5: Run the Sweep

```bash
uv run src/cli/launch.py sweep_demo -c experiment.yaml -v
```

**Output:**
```
=== Parameter Sweep ===
Total configurations: 4

--- Running sweep_0001_a3f29c ---
--- Running sweep_0002_a3f29c ---
--- Running sweep_0003_a3f29c ---
--- Running sweep_0004_a3f29c ---

=== Sweep Complete ===
Status: ✓ All succeeded
```

### Results

**CSV** (`runlogs/sweep_demo/demo.csv`):
```csv
launch_id,repeat,rank,outer_time,size,threads,walltime
sweep_0001_a3f29c,1,0,1.025,1000.0,1.0,1.0
sweep_0002_a3f29c,1,0,0.518,1000.0,2.0,0.5
sweep_0003_a3f29c,1,0,2.019,2000.0,1.0,2.0
sweep_0004_a3f29c,1,0,1.024,2000.0,2.0,1.0
```

**Markdown** (`runlogs/sweep_demo/demo.md`) contains per-launch parameters:
```json
{
  "sweep_0001_a3f29c": {"args": ["1000"], "env.OMP_NUM_THREADS": "1"},
  "sweep_0002_a3f29c": {"args": ["1000"], "env.OMP_NUM_THREADS": "2"},
  "sweep_0003_a3f29c": {"args": ["2000"], "env.OMP_NUM_THREADS": "1"},
  "sweep_0004_a3f29c": {"args": ["2000"], "env.OMP_NUM_THREADS": "2"}
}
```

### Analysis

```bash
# Extract walltime for each configuration
cut -d, -f1,7 runlogs/sweep_demo/demo.csv
```

Or with Python/pandas:
```python
import pandas as pd
df = pd.read_csv('runlogs/sweep_demo/demo.csv')
print(df.groupby(['size', 'threads'])['walltime'].mean())
```

## See Also

- [Launch Command](launch.md): Running experiments
- [Metrics](metrics.md): Understanding output
- [Repeaters](../src/core/repeaters/README.md): Statistical convergence
- [Workflows](workflows.md): Sequential experiment pipelines
- [Full Config Schema Test](../tests/integration/test_full_config_schema.py): Reference for all config options
