# Change Point Detection in SHARP GUI

## Overview

The SHARP GUI includes automatic change point detection to identify warm-up periods, cool-down periods, and regime changes in performance data. This helps identify when measurements may not represent steady-state behavior.

## Implementation

### Algorithm: PELT (Pruned Exact Linear Time)

- **Method**: PELT change point detection from the R `changepoint` package
- **Cost function**: Mean and variance changes (`cpt.meanvar`) by default
- **Penalty**: Conservative penalty of `3 * log(n)` to avoid over-segmentation
- **Minimum segment size**: 5% of total samples (minimum 3)

### Features

1. **Warm-up Detection**: Identifies if the first change point occurs in the first 30% of data
   - Reports median difference and percentage change
   - Includes Wilcoxon rank-sum test p-value for statistical significance
2. **Cool-down Detection**: Identifies if the last change point occurs in the final 30% of data
   - Reports median difference and percentage change
   - Includes Wilcoxon rank-sum test p-value for statistical significance
3. **Regime Changes**: Reports any change points in the middle "steady-state" region
4. **Autocorrelation Analysis**: Computes ACF to detect temporal dependencies
   - Reports implications when high autocorrelation is detected

### Integration

The change point analysis is integrated into `characterize_distribution()` and appears automatically in:

- **Explore Tab**: Displays distribution characteristics including change points
- **Profile Tab**: Shows characteristics below the distribution plot

### API

```r
# Main function (called automatically by characterize_distribution)
characterize_changepoints(x, model="rbf", pen=NULL, min_size=NULL,
                         acf_threshold=0.2, warmup_pct=0.3, cooldown_pct=0.7)

# Helper functions
detect_change_points(x, model="rbf", pen=NULL, min_size=NULL)
estimate_acf_lag(x, threshold=0.2, max_lag=NULL)
```

### Parameters

- `x`: Numeric vector (time series data)
- `model`: Cost function - "rbf" or "meanvar" for distributional changes, "mean" for mean-only
- `pen`: Penalty value (default: `3 * log(n)` for conservative detection)
- `min_size`: Minimum segment length (default: 5% of sample size)
- `acf_threshold`: Threshold for ACF analysis (default: 0.2)
- `warmup_pct`: Threshold for early change points (default: 0.3 = first 30%)
- `cooldown_pct`: Threshold for late change points (default: 0.7 = last 30%)

### Example Output

```
### Example Output

```
Distribution appears to be bimodal, unskewed. Strong autocorrelation detected
(max ACF=0.58 at lag ~13), suggesting performance samples are not truly independent
or the system preserves state between runs. Potential warm-up period detected:
first 20 samples (20% of data); median difference = 4.86 (94.9%), p<10^{-9}.
Single change point suggests a phase transition in the data.
```
```

## Interpretation

- **Warm-up period**: Initial samples may not represent steady-state; consider excluding from analysis
  - Median difference shows how much performance changed after warm-up
  - P-value indicates statistical significance of the difference
- **Cool-down period**: Final samples show different behavior; may indicate system shutdown effects
  - Median difference shows how much performance changed during cool-down
  - P-value indicates statistical significance of the difference
- **Regime changes**: Multiple operational modes detected; consider analyzing segments separately
- **Autocorrelation**: Strong correlation suggests non-independent samples; affects statistical tests
  - High ACF indicates system state preservation or temporal dependencies

## Tuning

To adjust sensitivity:

- **More conservative** (fewer change points): Increase `pen` parameter
- **More sensitive** (more change points): Decrease `pen` parameter or `min_size`
- **Focus on mean shifts only**: Use `model="mean"` instead of "rbf"/"meanvar"

## Dependencies

Requires R package: `changepoint` (automatically installed if missing)
