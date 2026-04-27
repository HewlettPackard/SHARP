# Benchmark Comparison Tool

The `compare` command performs statistical analysis and metadata comparison between two benchmark runs. It generates comprehensive comparison reports showing performance differences, statistical significance, and configuration changes, along with natural language interpretation of the results.

## Usage

```bash
compare [OPTIONS] BASELINE TREATMENT
```

The baseline run represents the reference or control condition, while the treatment run represents the modified or experimental condition being evaluated.

### Basic Examples

Compare two runs in the same experiment:
```bash
compare -e myexp run1 run2
```

Compare runs using full paths (extension optional):
```bash
compare runlogs/exp1/matmul runlogs/exp2/matmul
```

Compare multiple metrics:
```bash
compare -e myexp -m inner_time,outer_time,cycles run1 run2
```

Output as CSV for downstream analysis:
```bash
compare --format csv run1 run2
```

Show all metadata differences (not just significant ones):
```bash
compare --show-all run1 run2
```

Compare specific launch IDs within a multi-launch file:
```bash
compare -e myexp --baseline-launch-id abc123 --treatment-launch-id def456 sweep.csv sweep.csv
```

## Command-Line Options

| Option | Description |
|--------|-------------|
| `BASELINE` | Baseline (reference) run CSV file (or filename if `-e` specified) |
| `TREATMENT` | Treatment (experimental) run CSV file (or filename if `-e` specified) |
| `-e, --experiment NAME` | Experiment directory (searches in `runlogs/<experiment>/`) |
| `--baseline-launch-id ID` | Launch ID for baseline run (required if CSV has multiple launch IDs) |
| `--treatment-launch-id ID` | Launch ID for treatment run (required if CSV has multiple launch IDs) |
| `-m, --metrics LIST` | Comma-separated metrics to compare (default: `inner_time`) |
| `--format {md,csv,plaintext}` | Output format (default: `md`) |
| `--show-all` | Show all metadata fields, not just differences |
| `-v, --verbose` | Verbose output (include debug info) |
| `-h, --help` | Show help message |

**Note**: The `.csv` extension is optional. If omitted, it will be added automatically:
```bash
# Both are equivalent
compare -e myexp baseline treatment
compare -e myexp baseline.csv treatment.csv
```

## Statistical Comparison

The tool performs rigorous statistical analysis on metric distributions using the same calculations as the GUI:

### Statistical Tests

1. **Mann-Whitney U Test**: Non-parametric test for distribution differences
   - Used when distributions may not be normal
   - Tests whether medians differ significantly
   - Reports U statistic and p-value

2. **Kolmogorov-Smirnov Test**: Tests overall distribution similarity
   - Measures maximum distance between ECDFs
   - Detects shape differences beyond central tendency

3. **Effect Size (Cohen's d)**: Standardized mean difference
   - Small effect: |d| < 0.5
   - Medium effect: 0.5 <= |d| < 0.8
   - Large effect: |d| >= 0.8

### Output Metrics

For each compared metric, the report shows:

- **Baseline/Treatment**: Median ± standard deviation, sample size
- **Change**: Percent change in median (negative = improvement for time metrics)
- **p-value**: Statistical significance (typically < 0.05 is significant)
- **Effect**: Cohen's d effect size
- **Improved**: Whether performance improved (based on metric's `lower_is_better` setting)

### Example Output (Markdown)

```markdown
## Statistical Comparison

| Metric | Baseline | Treatment | Change | p-value | Effect | Improved |
|--------|----------|-----------|--------|---------|--------|----------|
| inner_time | 1.456 ± 0.052 | 1.234 ± 0.045 | -15.2% | 0.0001 | -0.89 | Yes |
| cycles | 2.3e6 ± 1.1e5 | 2.5e6 ± 1.2e5 | +8.7% | 0.0023 | 0.54 | No |
```

## Narrative Comparison

In addition to statistical tables, the tool generates natural language interpretations of the results. This narrative section provides human-readable summaries of:

- **Mean/median changes**: Whether treatment improved or degraded relative to baseline
- **Statistical significance**: Whether changes are statistically meaningful
- **Dispersion analysis**: How variability (standard deviation, CV, IQR) changed
- **Tail behavior**: Changes in tail latency characteristics

The narrative uses color coding (in markdown/HTML output) to highlight:
- **Green (bold)**: Improvements in performance or reduced variability
- **Red (underlined)**: Degradations in performance or increased variability

### Example Narrative Output

```markdown
## Narrative Comparison

**inner_time:**
Treatment mean significantly decreased compared to baseline.
Treatment median significantly decreased.
Dispersion (standard deviation) decreased notably.
Relative variability (CV) decreased.
```

This natural language interpretation complements the statistical tables by explaining what the numbers mean in practical terms.

## Metadata Comparison

The tool compares metadata from `.md` files to identify configuration differences that might explain performance changes.

### Compared Sections

1. **Initial runtime options**: Command-line arguments, entry points, backend configuration
2. **Initial system configuration**: CPU, memory, GPU, load average, kernel settings
3. **Invariant parameters**: Task name, start mode, concurrency settings

### Significance Filtering

By default, only performance-relevant differences are shown. The tool intelligently filters out noise:

**Always Ignored** (timing artifacts that don't affect performance):
- `timestamp`, `date`, `launch_id`
- `download_timestamp`, `build_timestamp`
- `uptime_seconds`, `running_processes`

**Ignored in Runtime Options Only** (but significant in Invariant parameters):
- `experiment`, `directory`, `mode`
- `verbose`, `skip_sys_specs`
- `repeats`, `repeater_options`

**Always Significant** (not ignored):
- `task`, `start`, `concurrency` - What benchmark and how it ran
- `git_hash`, `timeout` - Version and execution limits

**Numeric Thresholds** (configurable in `settings.yaml`):
- **Load average**: Must differ by > `load_avg_threshold_factor * core_count`
  - Example: 128 cores × 0.1 = 12.8 threshold
  - Small fluctuations (< threshold) are ignored
- **CPU frequency**: Must differ by > `cpu_freq_threshold_pct`% (default: 5%)
- **Memory**: Must differ by > `memory_threshold_pct`% (default: 1%)
- **Temperature/fan speed**: Always ignored (not performance-relevant)

**Version Strings**:
- Minor version differences ignored (e.g., 3.10.12 vs 3.10.13)
- Major version differences reported (e.g., 3.10.x vs 3.11.x)

**Discrete Values**:
- Always reported if different (task names, arguments, backend choices)

### Launch ID Alignment

When comparing runs with single launch IDs in each file, the tool automatically extracts and aligns the invariant parameters for direct comparison:

**Before (nested by launch ID)**:
```markdown
| Field | Baseline | Treatment |
|-------|----------|----------|
| 80ff640f.task | ls | N/A |
| ecfbcee0.task | N/A | matmul |
```

**After (aligned)**:
```markdown
| Field | Baseline | Treatment |
|-------|----------|----------|
| task | ls | matmul |
```

This makes it clear that you're comparing `ls` vs `matmul`, not dealing with separate launch IDs.

### Nested Structure Flattening

System configuration is hierarchical (JSON/YAML). The tool flattens it using dot notation:

```json
{
  "cpu": {
    "processor_count": "128",
    "scaling_cur_freq_khz": "2400000"
  }
}
```

Becomes:
- `cpu.processor_count: 128`
- `cpu.scaling_cur_freq_khz: 2400000`

This allows field-by-field comparison with appropriate thresholds.

**Value Truncation**: Long values (>30 characters) are truncated with ellipsis (`...`) for readability. Field names are truncated at 50 characters.

### Example Output (Markdown)

```markdown
## Metadata Comparison

### Initial runtime options

| Field | Baseline | Treatment |
|-------|----------|----------|
| args | ['-n', '500'] | ['-n', '1000'] |
| entry_point | /path/to/v1.AppImage | /path/to/v2.AppImage |

### Initial system configuration

| Field | Baseline | Treatment |
|-------|----------|----------|
| cpu.scaling_cur_freq_khz | 2200000 | 2400000 |
```

**Note**: The "Significant" column is automatically omitted when all differences are significant (default behavior). Use `--show-all` to see non-significant differences, which will include the "Significant" column.

### Show All Metadata

Use `--show-all` to include non-significant differences:

```bash
compare --show-all run1 run2
```

This displays all fields that differ, including those below significance thresholds. Useful for detailed environment audits.

## Output Formats

### Markdown (default)

Human-readable tables with clear headers, including narrative interpretation. Suitable for documentation, reports, or viewing in terminals with markdown support.

```bash
compare baseline treatment
```

### CSV

Machine-readable format for downstream analysis (spreadsheets, scripting):

```bash
compare --format csv baseline treatment > comparison.csv
```

CSV includes statistical comparison data but excludes narrative interpretation:
- Statistical comparison: `metric,baseline_median,baseline_std,treatment_median,...`

**Note**: CSV format does not include narrative comparison. Use markdown or plaintext for narrative output.

### Plaintext

Plain text tables without markdown formatting, including narrative interpretation. Good for terminals or log files:

```bash
compare --format plaintext baseline treatment
```

Example:
```
STATISTICAL COMPARISON
============================================================

inner_time:
  Baseline:  1.456 ± 0.052 (n=100)
  Treatment: 1.234 ± 0.045 (n=100)
  Change:    -15.2%
  p-value:   0.0001
  Effect:    -0.89
  Improved:  YES

============================================================
Narrative Comparison
============================================================

inner_time:
Treatment mean significantly decreased compared to baseline.
Treatment median significantly decreased.
Dispersion (standard deviation) decreased notably.
```

## Configuration

Comparison thresholds are configured in `settings.yaml`:

```yaml
comparisons:
  cpu_freq_threshold_pct: 5        # CPU frequency % difference threshold
  load_avg_threshold_factor: 0.1   # Load avg threshold as fraction of cores
  memory_threshold_pct: 1          # Memory % difference threshold
```

### Adjusting Sensitivity

**More sensitive** (detect smaller differences):
```yaml
comparisons:
  cpu_freq_threshold_pct: 2
  memory_threshold_pct: 0.5
```

**Less sensitive** (ignore minor fluctuations):
```yaml
comparisons:
  cpu_freq_threshold_pct: 10
  memory_threshold_pct: 5
```

### Load Average Threshold

The load average threshold adapts to system size:

- **128-core system**: 0.1 × 128 = 12.8 threshold
- **8-core system**: 0.1 × 8 = 0.8 threshold

Core count is automatically extracted from the metadata's `processor_count` or `cpu_cores` field, so the threshold scales appropriately.

## Integration with Workflows

Compare runs as part of automated workflows:

```bash
# Run experiment twice
uv run launch -e exp1 -t baseline benchmark args
uv run launch -e exp1 -t treatment benchmark args

# Compare results
uv run compare -e exp1 baseline treatment --format csv > results.csv

# Check for regression
if grep -q "Improved,No" results.csv; then
    echo "Performance regression detected!"
    exit 1
fi
```

## Troubleshooting

### "File not found" Error

Ensure files exist and paths are correct:
```bash
# List files in experiment
ls runlogs/myexp/

# Use full paths if -e doesn't work
compare runlogs/myexp/baseline runlogs/myexp/treatment

# Note: .csv extension is optional
compare runlogs/myexp/baseline.csv runlogs/myexp/treatment.csv
```

### "Metric not found" Error

Check available metrics in CSV:
```bash
head -1 runlogs/myexp/run1.csv
```

Then specify existing metrics:
```bash
compare -m inner_time,outer_time run1.csv run2.csv
```

### No Metadata Comparison

Metadata comparison requires `.md` files alongside `.csv` files. If missing, only statistical comparison is performed.

### Too Many/Few Differences

Adjust thresholds in `settings.yaml` or use `--show-all` to see filtered differences.

## Implementation Details

### Statistical Functions

Comparison reuses GUI calculation functions from `src/core/stats/comparisons.py`:

- `comparison_table()`: Computes summary statistics and statistical tests
- `mann_whitney_test()`: Non-parametric distribution comparison
- `ecdf_comparison()`: ECDF and KS test

### Metadata Parsing

Metadata parsing in `src/core/runlogs/metadata_compare.py`:

- `load_metadata()`: Parses JSON/YAML code blocks from markdown
- `flatten_dict()`: Converts nested structures to dot notation
- `is_significant_difference()`: Applies threshold rules
- `extract_core_count()`: Reads processor count from system configuration

### File Resolution

Files are resolved in order:
1. If `-e` specified: search `runlogs/<experiment>/<filename>`
2. Try adding `.csv` extension if missing
3. Otherwise: treat as relative/absolute path from current directory

## See Also

- [Launch Documentation](launch.md) - Running benchmarks
- [Metrics Documentation](metrics.md) - Available metrics and extraction
- [GUI Documentation](gui.md) - Interactive comparison in web interface
