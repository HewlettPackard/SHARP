# SHARP GUI Documentation

The SHARP GUI is a Python Shiny application for interactive benchmarking analysis. It helps answer questions like: "Why is my application slow sometimes?", "What system factors correlate with poor performance?", and "Did my optimization actually help?"

## Running the GUI

```bash
# From the project root
uv run shiny run src/gui/app.py

# Or with specific options
uv run shiny run src/gui/app.py --port 8080 --host 0.0.0.0
```

The GUI will be available at `http://localhost:8000` by default.

## Tabs Overview

### Overview Tab

**Purpose**: Entry point showing recent experiments and providing navigation to analysis tools.

**When to use**: Start here to see what data is available and jump to specific analyses (rerun an experiment or explore its results).

### Measure Tab

**Purpose**: Launch new benchmark experiments with configurable repeater strategies.

**When to use**: When you need to collect new performance data.

**Key capabilities**:
- Configure adaptive stopping criteria
- Select profiling backends to collect system metrics alongside timing
- Monitor real-time progress during execution

### Explore Tab

**Purpose**: Understand the distribution of a single metric, detect non-stationarity, and identify correlations between metrics.

**Questions it answers**:
- What does the performance distribution look like? (Normal, bimodal, heavy-tailed?)
- Is the time series stationary, or are there changepoints (shifts in behavior over time)?
- Are there outliers that might indicate measurement problems?
- How do different metrics correlate with each other?
- How does performance vary when filtered by a specific factor (e.g., only runs on node A)?

**Workflow**:
1. Select an experiment and task
2. Choose a metric (e.g., `perf_time`, `inner_time`)
3. Examine the density plot for distribution shape
4. Check the **distribution characterization** panel for:
   - Stationarity assessment (is performance stable over time?)
   - Changepoint detection (did something change mid-experiment?)
   - Autocorrelation analysis (are consecutive measurements correlated?)
5. Optionally filter by a categorical or numeric column to isolate subsets
6. Use the **correlation plot** to see pairwise relationships between numeric columns

**Key features**:
- **Changepoint detection**: Identifies points where the distribution shifts significantly (e.g., a system update mid-experiment, thermal throttling kicking in)
- **Stationarity check**: Warns if measurements are trending or have structural breaks
- **Metric correlations**: Scatter plot matrix showing how metrics relate (useful for identifying redundant measurements or unexpected relationships)

**Scenarios**:
- **Bimodal distribution**: Suggests two distinct performance regimes—filter by system factors to identify the cause
- **Changepoint detected**: The experiment may have been affected by an external event; consider splitting data at the changepoint
- **Long tail**: A few very slow runs may indicate interference or resource contention
- **High metric correlation**: Two metrics measuring essentially the same thing; one may be redundant

### Compare Tab

**Purpose**: Statistically compare two benchmark runs to determine if there's a real performance difference.

**Questions it answers**:
- Is the performance difference between baseline and treatment statistically significant?
- What is the effect size (how much faster/slower)?
- Can we confidently say one version is better than the other?

**Workflow**:
1. Select baseline experiment/task (e.g., original code)
2. Select treatment experiment/task (e.g., optimized code)
3. Choose the metric to compare
4. Review the statistical results

**Key outputs**:
- **Density comparison plot**: Visual overlay of both distributions
- **Mann-Whitney U test**: Non-parametric test for distribution differences (doesn't assume normality)
- **Kolmogorov-Smirnov test**: Tests if distributions have the same shape
- **Effect size (rank-biserial correlation)**: Magnitude of difference (-1 to +1 scale, similar to Cliff's delta)
- **Narrative summary**: Plain-English interpretation of results

**Interpreting results**:
- **p < 0.05 with |effect size| > 0.33**: Likely a meaningful difference
- **p < 0.05 with |effect size| < 0.15**: Statistically significant but practically small
- **p > 0.05**: Cannot conclude there's a difference (need more samples or difference is too small)

**Scenarios**:
- **A/B testing**: Compare before/after an optimization
- **Configuration comparison**: Test different compiler flags, JIT settings, etc.
- **Environment comparison**: Same code on different hardware or OS versions

### Profile Tab

**Purpose**: Identify which system factors explain performance variation using decision tree classification.

**Questions it answers**:
- What system characteristics correlate with slow runs?
- Which factors best predict whether a run will be "fast" or "slow"?
- If I mitigate a factor (e.g., pin to specific CPUs), does performance improve?

**Workflow**:

#### Step 1: Load Data
1. Select experiment and task
2. If profiling data (`*-prof.csv`) exists, choose whether to use it or run new profiling

#### Step 2: Understand the Distribution
1. Select the outcome metric (what you're trying to explain)
2. View the density plot showing the full distribution
3. The suggested cutoff separates "fast" (left/green) from "slow" (right/orange) runs

#### Step 3: Set a Cutoff
The cutoff defines what counts as "slow". Three options:
- **Click on the plot**: Set a custom threshold interactively
- **Search for Cutoff**: Automatically find the cutoff that produces the best-fitting tree (minimizes AIC)
- **Use default**: Accept the suggested cutoff based on distribution analysis

#### Step 4: Train the Decision Tree
The tree shows which factors best separate fast from slow runs:
- **Internal nodes**: Show the splitting criterion (e.g., `cpu_freq < 2.5`)
- **Leaf nodes**: Show sample counts, colored by majority class
- **Tree depth**: Deeper trees capture more complex interactions but may overfit

#### Step 5: Analyze Factors
The Factor Details panel shows:
- Which predictors the tree selected and their importance
- Correlation between each predictor and the outcome metric

#### Step 6: Exclude Irrelevant Predictors
Click "Exclude Predictors" to:
- Remove columns that are just identifiers (timestamps, run IDs)
- Remove columns with correlation ≥ threshold (likely measuring the same thing as the outcome)
- Focus on actionable system factors

#### Step 7: Compare with Mitigation (Optional)
If you've run the benchmark again after mitigating an identified factor:
1. Click "Load Mitigation Data"
2. Select the mitigation run
3. Compare distributions to verify improvement

**Interpreting the tree**:
- **Single-factor dominance**: If one factor appears at the root and explains most variance, focus mitigation efforts there
- **Complex interactions**: Multiple factors at different levels suggest the problem depends on combinations of conditions
- **No clear tree**: If no tree forms (or AIC doesn't improve), the performance variation may be random or require different profiling backends

**Scenarios**:
- **NUMA effects**: Tree splits on memory node or CPU socket → consider memory placement
- **Frequency scaling**: Tree splits on CPU frequency → consider pinning governor or using performance mode
- **Thermal throttling**: Tree splits on temperature readings → check cooling or reduce load
- **Resource contention**: Tree splits on other process counts → isolate the benchmark environment

## Data Organization

```
runlogs/
├── <experiment>/
│   ├── <task>.csv          # Raw benchmark timing data
│   ├── <task>.md           # Metadata (command, backends, settings)
│   ├── <task>-prof.csv     # Profiling data with system metrics (optional)
│   └── <task>-prof.md      # Profiling metadata (optional)
```

## Configuration

GUI settings in `settings.yaml`:

```yaml
gui:
  distribution:
    left_color: "#2ca02c"   # "Better" class color (fast runs)
    right_color: "#ff7f0e"  # "Worse" class color (slow runs)
  default_experiment: "misc"

profiling:
  max_predictors: 100       # Maximum predictors for tree training
  max_correlation: 0.99     # Exclude predictors with higher correlation to outcome
```

## Troubleshooting

### "No tree available"
- The data may not have enough variance in the outcome metric
- Try a different cutoff value
- Check that predictors aren't all excluded

### "Metrics not loading"
- Ensure the CSV has numeric columns
- Check for file permissions or corrupted data

### Slow performance
- Large datasets: Filter data before heavy computations
- Many predictors: Use the exclusion modal to reduce predictor count
- Complex trees: Reduce `max_predictors` in settings
