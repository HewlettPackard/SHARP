# Metric Definition Schema

**Used In**: Benchmark YAML and Backend YAML

**Purpose**: Define how to extract, classify, and display performance metrics from benchmark outputs.

## Schema

```python
class MetricDefinition(BaseModel):
    """Single metric definition."""

    description: str
    """Human-readable metric name and purpose"""

    extract: str
    """Shell command to extract metric value from output"""

    lower_is_better: bool
    """Performance direction: True for time/latency, False for throughput"""

    type: str
    """Value type: float, int, string"""

    units: str | None = None
    """Units: seconds, ms, ops/sec, MOPS, instructions, cycles, etc."""
```

## Field Semantics

### `description` (required)

Human-readable description of the metric.

**Examples**:
- "CPU cycle count"
- "Inference latency in milliseconds"
- "Memory bandwidth (GB/s)"
- "Cache misses per second"

### `extract` (required)

Shell one-liner to extract metric value from benchmark output.

Executed in the **output directory** after benchmark completes. Should output a single numeric (or string) value.

**Extract Command Patterns**:

#### Simple grep + awk
```yaml
extract: 'grep "time:" output.txt | awk "{print $2}"'
```

#### CSV parsing
```yaml
extract: 'tail -1 results.csv | cut -d, -f3'
```

#### Multiple extraction steps
```yaml
extract: 'cat perf.out | grep "cycles" | head -1 | awk "{print $1}"'
```

#### Math operations (using bc or similar)
```yaml
extract: 'grep "bytes:" metrics.txt | awk "{print $2 / 1e9}"'
# Output: 2.5 GB
```

#### JSON parsing (using jq if available)
```yaml
extract: 'cat metrics.json | jq ".throughput"'
```

### `lower_is_better` (required)

Boolean flag indicating performance direction.

**true**: Lower values are better
- Time-based metrics: seconds, milliseconds, latency
- Error rates, cache misses, exceptions
- Power consumption (watts, wattage)

**false**: Higher values are better
- Throughput: ops/sec, requests/sec, MOPS, GB/s
- Speedup, efficiency, utilization %
- Accuracy, precision

**Example**:
```yaml
metrics:
  execution_time:
    lower_is_better: true   # Smaller time is better

  throughput:
    lower_is_better: false  # Larger throughput is better

  cache_misses:
    lower_is_better: true   # Fewer misses is better
```

### `type` (required)

Value type returned by extract command.

Options:
- **float**: Decimal numbers (most common)
  - Example: 1.23, 45.6, 0.001
  - Used for: latency, throughput, ratios
- **int**: Integers only
  - Example: 1000, 500000, 256
  - Used for: cycle counts, instruction counts, event counts
- **string**: Text values (rarely used)
  - Example: "optimal", "failed", "timeout"
  - Used for: status, classification

**Example**:
```yaml
metrics:
  latency_ms:
    type: float      # 1.234, 5.678

  instructions:
    type: int        # 1000000, 2000000

  status:
    type: string     # "success", "timeout"
```

### `units` (optional)

Unit of measurement for the metric. Used in display and comparison reports.

**Time Units**:
- `seconds`, `ms`, `microseconds`, `nanoseconds`, `ns`, `us`

**Throughput Units**:
- `ops/sec`, `ops/s`, `requests/sec`, `MOPS`, `GOPS`
- `GB/s`, `MB/s`, `KB/s`
- `transactions/sec`

**Hardware Counters**:
- `cycles`, `instructions`, `cache-misses`, `LLC-loads`
- `page-faults`, `context-switches`

**Power/Energy**:
- `watts`, `mW`, `joules`, `mJ`

**Other**:
- `percent`, `ratio`, `count`

**Example**:
```yaml
metrics:
  execution_time:
    units: ms

  throughput:
    units: ops/sec

  memory_bandwidth:
    units: GB/s

  instruction_count:
    units: instructions
```

## Examples

### Time-Based Metrics

```yaml
metrics:
  inner_time:
    description: Time to execute benchmark
    extract: 'grep "time:" output.txt | awk "{print $2}"'
    lower_is_better: true
    type: float
    units: seconds

  latency_ms:
    description: Inference latency
    extract: 'cat metrics.json | jq ".latency_ms"'
    lower_is_better: true
    type: float
    units: ms

  initialization_time:
    description: Model initialization time
    extract: 'grep "init:" output.txt | awk "{print $2}"'
    lower_is_better: true
    type: float
    units: seconds
```

### Throughput Metrics

```yaml
metrics:
  throughput:
    description: Operations per second
    extract: 'tail -1 results.txt | awk "{print $1}"'
    lower_is_better: false
    type: float
    units: ops/sec

  bandwidth_gb_s:
    description: Memory bandwidth
    extract: 'grep "bandwidth:" perf.out | awk "{print $2}"'
    lower_is_better: false
    type: float
    units: GB/s

  tokens_per_second:
    description: LLM inference throughput
    extract: 'cat metrics.json | jq ".tokens_per_sec"'
    lower_is_better: false
    type: float
    units: tokens/sec
```

### Hardware Counter Metrics

```yaml
metrics:
  cycles:
    description: CPU cycles
    extract: 'grep "cycles" perf.txt | head -1 | awk "{print $1}"'
    lower_is_better: true
    type: int
    units: cycles

  instructions:
    description: Instructions executed
    extract: 'grep "instructions" perf.txt | head -1 | awk "{print $1}"'
    lower_is_better: false  # More instructions might be ok if time is same
    type: int
    units: instructions

  cache_misses:
    description: L1 cache misses
    extract: 'grep "cache-misses" perf.txt | awk "{print $1}"'
    lower_is_better: true
    type: int
    units: cache-misses

  branch_misses:
    description: Branch prediction misses
    extract: 'grep "branch-misses" perf.txt | head -1 | awk "{print $1}"'
    lower_is_better: true
    type: int
    units: misses
```

### Mixed Metrics

```yaml
metrics:
  kernel_time:
    description: GPU kernel execution time
    extract: 'grep "kernel:" output.txt | awk "{print $2}"'
    lower_is_better: true
    type: float
    units: ms

  memory_throughput:
    description: Memory throughput during kernel
    extract: 'grep "mem_throughput:" output.txt | awk "{print $2}"'
    lower_is_better: false
    type: float
    units: GB/s

  occupancy:
    description: GPU occupancy percentage
    extract: 'grep "occupancy:" output.txt | awk "{print $2}"'
    lower_is_better: false
    type: float
    units: percent

  memory_usage_mb:
    description: Peak memory usage
    extract: 'grep "peak_mem:" output.txt | awk "{print $2}"'
    lower_is_better: true
    type: float
    units: MB
```

## Backend Metrics Example

```yaml
# backends/perf.yaml

backend_options:
  perf:
    profiling: true
    command_template: "perf stat -e cycles,instructions,cache-misses,LLC-loads -j $CMD $ARGS"

# Metrics extracted from perf output
metrics:
  cycles:
    description: CPU cycles
    extract: 'grep -oP "cycles.*?value["\s]*:?\s*\K[^,}"]*' output.json | head -1'
    lower_is_better: true
    type: int
    units: cycles

  instructions:
    description: Instructions retired
    extract: 'grep -oP "instructions.*?value["\s]*:?\s*\K[^,}"]*' output.json | head -1'
    lower_is_better: false
    type: int
    units: instructions

  cache_misses:
    description: Cache misses
    extract: 'grep -oP "cache-misses.*?value["\s]*:?\s*\K[^,}"]*' output.json | head -1'
    lower_is_better: true
    type: int
    units: cache-misses

  llc_loads:
    description: Last-level cache loads
    extract: 'grep -oP "LLC-loads.*?value["\s]*:?\s*\K[^,}"]*' output.json | head -1'
    lower_is_better: false
    type: int
    units: LLC-loads
```

## Benchmark Metrics Example

```yaml
# benchmarks/ollama/benchmark.yaml

benchmarks:
  ollama-mistral:
    command: python ollama.py
    args: '{"model": "mistral:latest"}'

metrics:
  inference_latency:
    description: Inference latency in milliseconds
    extract: 'grep "latency:" output.txt | awk "{print $2}"'
    lower_is_better: true
    type: float
    units: ms

  tokens_per_second:
    description: Inference throughput
    extract: 'grep "throughput:" output.txt | awk "{print $2}"'
    lower_is_better: false
    type: float
    units: tokens/sec

  memory_usage_mb:
    description: Peak GPU memory usage
    extract: 'grep "gpu_mem:" output.txt | awk "{print $2}"'
    lower_is_better: true
    type: float
    units: MB
```

## Metric Extraction Tips

### Output Format Considerations

**Extract from plain text**:
```yaml
extract: 'grep "time:" output.txt | awk "{print $2}"'
# Works if output contains: "time: 1.234"
```

**Extract from CSV**:
```yaml
extract: 'tail -1 results.csv | cut -d, -f3'
# Works if last line of CSV has metric in column 3
```

**Extract from JSON**:
```yaml
extract: 'cat metrics.json | jq ".benchmark.execution_time"'
# Works if metrics.json has structure: {"benchmark": {"execution_time": 1.234}}
```

**Extract multiple lines, use first**:
```yaml
extract: 'grep "cycles" perf.txt | head -1 | awk "{print $1}"'
```

**Debug extract commands**:
```bash
# Test extract command locally
cd output_directory
grep "time:" output.txt | awk "{print $2}"
# Should output: 1.234
```

## Validation

Metric definitions are validated during config loading:

```python
from src.core.config.schema import MetricDefinition

metric = MetricDefinition(
    description="Execution time",
    extract='grep "time:" output.txt | awk "{print $2}"',
    lower_is_better=True,
    type="float",
    units="seconds"
)
# Raises ValidationError if invalid
```

Validation checks:
- `description` is non-empty string
- `extract` is non-empty string (valid shell one-liner)
- `lower_is_better` is boolean
- `type` is one of: float, int, string
- `units` is optional string

## See Also

- [Benchmark Configuration Schema](benchmark.md)
- [Backend Configuration Schema](backend.md)
- [Metrics Extraction Guide](../metrics.md)
