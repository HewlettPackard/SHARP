"""
Distribution analysis utilities.

Provides functions for computing summary statistics, detecting change points,
estimating autocorrelation, and characterizing distributions.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
from scipy import stats
from typing import Any
import warnings
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.figure import Figure

# Threshold for automatic model selection in change point detection.
# Below this sample size, use RBF (more accurate); above, use L2 (faster).
AUTO_MODEL_THRESHOLD = 500

# Require at least this many samples before running changepoint/ACF analysis.
# Smaller series are too short for stable PELT segmentation or lag estimates.
MIN_CHANGEPOINT_ANALYSIS_SAMPLES = 10

# PELT needs a minimum segment length. Three points is the smallest segment that
# still supports median-based comparisons on both sides of a changepoint.
DEFAULT_MIN_CHANGEPOINT_SEGMENT_SIZE = 3

# Also scale the minimum segment length with the dataset size so large traces do
# not get split into unrealistically short phases.
DEFAULT_MIN_SEGMENT_FRACTION = 0.05

# Use a moderate default penalty that grows with series length. The multiplier of
# 3 keeps the detector from over-segmenting noisy benchmark traces.
DEFAULT_CHANGEPOINT_PENALTY_MULTIPLIER = 3.0

# Only inspect the first quarter of the series for the ACF estimate, but never
# more than 50 lags, to keep the calculation inexpensive on long traces.
DEFAULT_ACF_MAX_LAG_FRACTION = 0.25
DEFAULT_ACF_MAX_LAG_CAP = 50

# Treat autocorrelation below 0.2 as negligible for narrative purposes.
DEFAULT_ACF_THRESHOLD = 0.2

# Warmup is expected near the front of the run, so search the first 30%.
DEFAULT_WARMUP_FRACTION = 0.3

# Cooldown or slowdown is expected near the tail, so search after 70%, which
# effectively reserves the last 30% of the series for late-phase detection.
DEFAULT_COOLDOWN_FRACTION = 0.7

# Mann-Whitney comparisons need at least a few samples in each partition to avoid
# unstable p-values and misleading medians.
MIN_PERIOD_COMPARISON_SAMPLES = 3

# Use the standard 5% significance level when deciding whether a detected phase
# transition is statistically distinct from the rest of the series.
DEFAULT_PHASE_SIGNIFICANCE_THRESHOLD = 0.05

# Cap changepoint analysis at 5000 samples because PELT is one of the more
# expensive parts of the narrative pipeline and the GUI does not need full-rate
# traces to describe large-scale temporal shifts.
DEFAULT_MAX_CHANGEPOINT_POINTS = 5000


def compute_summary(x: np.ndarray, digits: int = 5) -> dict[str, float]:
    """
    Compute summary statistics for a given vector.

    Args:
        x: Numeric array
        digits: Number of decimal places for rounding

    Returns:
        Dictionary with summary statistics (n, min, median, mode, mean, CI95_low,
        CI95_high, p95, p99, max, stddev, stderr)
    """
    x_clean = x[~np.isnan(x)]
    n = len(x_clean)

    if n == 0:
        return {k: np.nan for k in ['n', 'min', 'median', 'mode', 'mean',
                                     'CI95_low', 'CI95_high', 'p95', 'p99',
                                     'max', 'stddev', 'stderr']}

    # Compute mode (most frequent value)
    mode_result = stats.mode(x_clean, keepdims=True)
    mode_val = mode_result.mode[0] if len(mode_result.mode) > 0 else np.median(x_clean)

    # Compute 95% confidence interval
    t_score = stats.t.ppf(0.975, df=n-1)  # 0.975 for two-tailed 95% CI
    se = np.std(x_clean, ddof=1) / np.sqrt(n)
    mean_val = np.mean(x_clean)

    summary = {
        'n': n,
        'min': np.min(x_clean),
        'median': np.median(x_clean),
        'mode': mode_val,
        'mean': mean_val,
        'CI95_low': mean_val - t_score * se,
        'CI95_high': mean_val + t_score * se,
        'p95': np.percentile(x_clean, 95),
        'p99': np.percentile(x_clean, 99),
        'max': np.max(x_clean),
        'stddev': np.std(x_clean, ddof=1),
        'stderr': se,
        'cv': (np.std(x_clean, ddof=1) / mean_val) if mean_val != 0 else np.nan
    }

    # Round all values except 'n'
    return {k: (round(v, digits) if k != 'n' else int(v)) for k, v in summary.items()}


def detect_change_points(x: np.ndarray, model: str = "auto",
                        pen: float | None = None,
                        min_size: int | None = None,
                        auto_threshold: int = AUTO_MODEL_THRESHOLD) -> dict[str, Any]:
    """
    Detect change points using PELT algorithm.

    Args:
        x: Numeric array
        model: Change point model - "auto" (default), "l2", "l1", or "rbf"
               "auto" uses RBF for n ≤ auto_threshold (more accurate),
               L2 for larger samples (faster)
        pen: Penalty value (default: 3 * log(n))
        min_size: Minimum segment size (default: max(3, 5% of n))
        auto_threshold: Sample size threshold for automatic model selection
                        (default: AUTO_MODEL_THRESHOLD = 500)

    Returns:
        Dictionary with 'cps' (change point indices), 'n' (sample size),
        'min_size', 'pen', and optionally 'error'
    """
    try:
        from ruptures import Pelt
    except ImportError:
        warnings.warn("ruptures package not available; change point detection disabled")
        return {'cps': [], 'n': len(x), 'error': 'ruptures not installed'}

    x_clean = x[~np.isnan(x)]
    n = len(x_clean)

    if n < MIN_CHANGEPOINT_ANALYSIS_SAMPLES:
        return {'cps': [], 'n': n}

    # Adaptive model selection: RBF for small samples (more accurate),
    # L2 for large samples (much faster, O(n log n) vs O(n²))
    if model == "auto":
        model = "rbf" if n <= auto_threshold else "l2"

    # Set defaults
    if min_size is None:
        min_size = max(DEFAULT_MIN_CHANGEPOINT_SEGMENT_SIZE, int(DEFAULT_MIN_SEGMENT_FRACTION * n))
    if pen is None:
        pen = DEFAULT_CHANGEPOINT_PENALTY_MULTIPLIER * np.log(n)

    try:
        # Use ruptures library for change point detection
        algo = Pelt(model=model, min_size=min_size).fit(x_clean.reshape(-1, 1))
        cps = algo.predict(pen=pen)

        # Remove the final breakpoint (n) which is always included
        if len(cps) > 0 and cps[-1] == n:
            cps = cps[:-1]

        return {
            'cps': cps,
            'n': n,
            'min_size': min_size,
            'pen': pen
        }
    except Exception as e:
        return {
            'cps': [],
            'n': n,
            'error': str(e)
        }


def estimate_acf_lag(x: np.ndarray, threshold: float = DEFAULT_ACF_THRESHOLD,
                    max_lag: int | None = None) -> dict[str, Any]:
    """
    Estimate autocorrelation lag (where ACF drops below threshold).

    Args:
        x: Numeric array
        threshold: ACF threshold for significance
        max_lag: Maximum lag to check (default: min(n/4, 50))

    Returns:
        Dictionary with 'lag' (first lag below threshold), 'max_acf'
        (maximum ACF value), and optionally 'error'
    """
    x_clean = x[~np.isnan(x)]
    n = len(x_clean)

    if n < MIN_CHANGEPOINT_ANALYSIS_SAMPLES:
        return {'lag': 0, 'max_acf': np.nan}

    if max_lag is None:
        max_lag = min(int(n * DEFAULT_ACF_MAX_LAG_FRACTION), DEFAULT_ACF_MAX_LAG_CAP)

    try:
        from statsmodels.tsa.stattools import acf

        # Compute ACF
        acf_vals = acf(x_clean, nlags=max_lag, fft=True)[1:]  # Exclude lag 0

        # Find first lag where |ACF| < threshold
        below_thresh = np.where(np.abs(acf_vals) < threshold)[0]
        lag = below_thresh[0] + 1 if len(below_thresh) > 0 else max_lag

        return {
            'lag': int(lag),
            'max_acf': float(np.max(np.abs(acf_vals)))
        }
    except ImportError:
        warnings.warn("statsmodels not available; ACF estimation disabled")
        return {'lag': 0, 'max_acf': np.nan, 'error': 'statsmodels not installed'}
    except Exception as e:
        return {'lag': 0, 'max_acf': np.nan, 'error': str(e)}


def _detect_period_boundaries(x_clean: np.ndarray, cps: list[int], n: int,
                              min_seg_size: int, threshold_pct: float,
                              period_type: str) -> dict[str, Any] | None:
    """
    Detect boundaries and statistics for a performance period (warmup or cooldown).

    Args:
        x_clean: Clean numeric array
        cps: List of change points
        n: Total length
        min_seg_size: Minimum segment size
        threshold_pct: Percentage threshold for period detection (0-1)
        period_type: 'warmup' or 'cooldown'

    Returns:
        Dictionary with period info, or None if no period detected:
        - 'type': 'warmup' or 'cooldown'
        - 'end_idx': Index where the period ends (for warmup) or starts (for cooldown)
        - 'indices': Range of indices belonging to this period
        - 'p_value': Statistical significance of the period
        - 'median_diff': Difference in median between period and rest
    """
    if period_type == "warmup":
        threshold = int(threshold_pct * n)
        matched_cps = [cp for cp in cps if cp <= threshold and cp >= min_seg_size]
        period_idx = matched_cps[0] if matched_cps else None
    else:  # cooldown
        threshold = int(threshold_pct * n)
        matched_cps = [cp for cp in cps if cp >= threshold]
        period_idx = matched_cps[-1] if matched_cps else None

    if period_idx is None:
        return None

    if period_type == "warmup":
        period_data = x_clean[:period_idx]
        other_data = x_clean[period_idx:]
        indices = list(range(period_idx))
    else:
        period_data = x_clean[period_idx:]
        other_data = x_clean[:period_idx]
        indices = list(range(period_idx, n))

    if len(period_data) < MIN_PERIOD_COMPARISON_SAMPLES or len(other_data) < MIN_PERIOD_COMPARISON_SAMPLES:
        return None

    period_median = np.median(period_data)
    other_median = np.median(other_data)
    _, p_value = stats.mannwhitneyu(period_data, other_data, alternative='two-sided')

    return {
        'type': period_type,
        'end_idx': period_idx if period_type == 'warmup' else None,
        'start_idx': period_idx if period_type == 'cooldown' else None,
        'indices': indices,
        'p_value': p_value,
        'median_diff': period_median - other_median,
        'period_median': period_median,
        'other_median': other_median,
        'n_samples': len(period_data)
    }


def detect_temporal_phases(x: np.ndarray, warmup_pct: float = DEFAULT_WARMUP_FRACTION,
                           cooldown_pct: float = DEFAULT_COOLDOWN_FRACTION,
                           min_samples: int = MIN_CHANGEPOINT_ANALYSIS_SAMPLES,
                           p_threshold: float = DEFAULT_PHASE_SIGNIFICANCE_THRESHOLD) -> dict[str, Any]:
    """
    Detect warmup and cooldown phases in a time series.

    This function analyzes the time series for changepoints and identifies
    any warmup (initial transient) or cooldown (final degradation) phases.

    Args:
        x: Numeric array (time series of performance measurements)
        warmup_pct: Look for warmup changepoints in first N% of data (default: 30%)
        cooldown_pct: Look for cooldown changepoints after N% of data (default: 70%)
        min_samples: Minimum samples required for analysis
        p_threshold: P-value threshold for significant phase detection

    Returns:
        Dictionary with:
        - 'warmup': dict with warmup phase info, or None if not detected
        - 'cooldown': dict with cooldown phase info, or None if not detected
        - 'steady_state_indices': list of indices considered steady state
        - 'changepoints': list of all detected changepoints
    """
    x_clean = x[~np.isnan(x)]
    n = len(x_clean)

    result: dict[str, Any] = {
        'warmup': None,
        'cooldown': None,
        'steady_state_indices': list(range(n)),
        'changepoints': []
    }

    if n < min_samples:
        return result

    # Detect changepoints
    cp_result = detect_change_points(x_clean)
    if 'error' in cp_result:
        return result

    cps = cp_result.get('cps', [])
    min_seg_size = cp_result.get('min_size', DEFAULT_MIN_CHANGEPOINT_SEGMENT_SIZE)
    result['changepoints'] = cps

    if not cps:
        return result

    # Detect warmup
    warmup = _detect_period_boundaries(x_clean, cps, n, min_seg_size, warmup_pct, 'warmup')
    if warmup and warmup['p_value'] < p_threshold:
        result['warmup'] = warmup

    # Detect cooldown
    cooldown = _detect_period_boundaries(x_clean, cps, n, min_seg_size, cooldown_pct, 'cooldown')
    if cooldown and cooldown['p_value'] < p_threshold:
        result['cooldown'] = cooldown

    # Compute steady state indices (excluding warmup and cooldown)
    excluded_indices: set[int] = set()
    if warmup is not None and warmup['p_value'] < p_threshold:
        excluded_indices.update(warmup['indices'])
    if cooldown is not None and cooldown['p_value'] < p_threshold:
        excluded_indices.update(cooldown['indices'])

    result['steady_state_indices'] = [i for i in range(n) if i not in excluded_indices]

    return result


def _is_unimodal(x: np.ndarray, bins: int = 20) -> bool:
    """
    Heuristic to detect if distribution is unimodal.

    Counts peaks in histogram. If ≤2 peaks detected AND distribution is skewed
    (|skewness| >= 0.5), treat as unimodal (peaks are noise from skewness).
    Only 1 peak counts as unimodal for symmetric distributions.

    Args:
        x: Numeric array
        bins: Number of histogram bins

    Returns:
        True if distribution appears unimodal, False otherwise
    """
    if len(x) <= 5:
        return True

    try:
        counts, _ = np.histogram(x, bins=bins)
        # Count local maxima (peaks)
        peaks = 0
        for i in range(1, len(counts) - 1):
            if counts[i] > counts[i-1] and counts[i] > counts[i+1]:
                peaks += 1

        # If only 1 peak, it's unimodal
        if peaks <= 1:
            return True

        # If 2 peaks, check if distribution is skewed
        # (skewed distributions naturally have multiple histogram peaks)
        if peaks == 2:
            try:
                skewness = stats.skew(x[~np.isnan(x)])
                # If significantly skewed, treat 2 peaks as unimodal with noise
                return bool(abs(skewness) >= 0.5)
            except Exception:
                return False

        # 3+ peaks: multimodal
        return False
    except Exception:
        return True


def _is_amodal(x: np.ndarray) -> bool:
    """
    Detect if distribution appears to have no clear mode (flat).

    Checks if the mode and median are within 5% of the range.

    Args:
        x: Numeric array

    Returns:
        True if distribution appears amodal, False otherwise
    """
    try:
        x_clean = x[~np.isnan(x)]
        if len(x_clean) <= 5:
            return False

        mode_result = stats.mode(x_clean, keepdims=True)
        mode_val = mode_result.mode[0] if len(mode_result.mode) > 0 else np.median(x_clean)
        median_val = np.median(x_clean)
        value_range = np.max(x_clean) - np.min(x_clean)

        # If mode and median are close and value range is large, likely amodal
        return bool((abs(mode_val - median_val) / (value_range + 1e-10)) < 0.05)
    except Exception:
        return False


def _find_modes(x: np.ndarray, bins: int = 20) -> list[float]:
    """
    Find the locations of modes in the distribution.

    Args:
        x: Numeric array
        bins: Number of histogram bins

    Returns:
        List of up to 3 most prominent mode locations
    """
    try:
        x_clean = x[~np.isnan(x)]
        if len(x_clean) <= 1:
            return [np.median(x_clean)]

        counts, edges = np.histogram(x_clean, bins=bins)

        # Find bin centers (midpoints)
        bin_centers = (edges[:-1] + edges[1:]) / 2

        # Sort by count (descending) and get top modes
        sorted_indices = np.argsort(counts)[::-1]
        modes = [bin_centers[i] for i in sorted_indices[:3] if i < len(bin_centers)]

        return sorted(modes) if modes else [np.median(x_clean)]
    except Exception:
        return [np.median(x_clean)]


def _test_normality(x_clean: np.ndarray) -> str | None:
    """
    Test for normality and log-normality, returning narrative text.

    Args:
        x_clean: Clean numeric array (no NaNs)

    Returns:
        Narrative string describing normality test results, or None if test cannot be performed
    """
    n = len(x_clean)
    if n < 20:
        return None

    try:
        _, p_value = stats.shapiro(x_clean)

        if p_value >= 0.05:
            return f"Distribution is consistent with normality (Shapiro-Wilk p={p_value:.4f})."

        # Not normal - check for log-normality
        if np.all(x_clean > 0):
            log_x = np.log(x_clean)
            _, p_value_log = stats.shapiro(log_x)

            if p_value_log >= 0.05:
                return (f"Distribution deviates from normality (Shapiro-Wilk p={p_value:.4f}) "
                       f"but is consistent with log-normality (log-transformed p={p_value_log:.4f}).")
            else:
                return (f"Distribution deviates significantly from normality (Shapiro-Wilk p={p_value:.4f}) "
                       f"and from log-normality (log-transformed p={p_value_log:.4f}).")
        else:
            # Cannot test log-normality with non-positive values
            return (f"Distribution deviates significantly from normality (Shapiro-Wilk p={p_value:.4f}). "
                   f"Log-normality test not applicable (data contains non-positive values).")
    except Exception:
        return None


def characterize_distribution(x: np.ndarray, skew_thresh: float = 0.5,
                              model: str = "auto",
                              pen: float | None = None,
                              min_size: int | None = None,
                              max_changepoint_points: int = DEFAULT_MAX_CHANGEPOINT_POINTS) -> str:
    """
    Characterize the distribution of a numeric vector with narrative text.

    Args:
        x: Numeric array
        skew_thresh: Threshold for considering distribution skewed
        model: Change point model ("auto" adapts based on sample size)
        pen: Penalty for change point detection
        min_size: Minimum segment size for change points
        max_changepoint_points: Maximum number of points to use for changepoint detection.
                                Larger datasets will be downsampled.

    Returns:
        Narrative string describing the distribution
    """
    x_clean = x[~np.isnan(x)]
    n = len(x_clean)

    if n < 3:
        return "Insufficient data for distribution characterization."

    narrative = []

    # Compute skewness and kurtosis on full dataset (fast operations)
    skewness = stats.skew(x_clean)
    kurtosis = stats.kurtosis(x_clean)

    # Characterize skewness
    if abs(skewness) < skew_thresh:
        narrative.append(f"Distribution is approximately symmetric (skewness={skewness:.2f}).")
    elif skewness > 0:
        narrative.append(f"Distribution is right-skewed (skewness={skewness:.2f}), with a long tail of high values.")
    else:
        narrative.append(f"Distribution is left-skewed (skewness={skewness:.2f}), with a long tail of low values.")

    # Characterize kurtosis
    if kurtosis > 1:
        narrative.append(f"Distribution has heavy tails (kurtosis={kurtosis:.2f}), indicating outliers or extreme values are common.")
    elif kurtosis < -1:
        narrative.append(f"Distribution has light tails (kurtosis={kurtosis:.2f}), indicating fewer outliers than a normal distribution.")

    # Test normality and log-normality
    normality_result = _test_normality(x_clean)
    if normality_result:
        narrative.append(normality_result)

    # Changepoint analysis - model selection is adaptive (RBF for ≤500, L2 for larger)
    from .narrative import describe_changepoints

    # Downsample for expensive temporal analysis if needed
    if len(x_clean) > max_changepoint_points:
        # Use simple uniform sampling
        indices = np.linspace(0, len(x_clean) - 1, max_changepoint_points, dtype=int)
        x_cp = x_clean[indices]
    else:
        x_cp = x_clean

    # Pre-calculate stats to avoid circular dependency in narrative module
    acf_info = estimate_acf_lag(x_cp)
    cp_result = detect_change_points(x_cp, model=model, pen=pen, min_size=min_size)

    if 'error' not in cp_result:
        cps = cp_result.get('cps', [])
        min_seg_size = cp_result.get('min_size', DEFAULT_MIN_CHANGEPOINT_SEGMENT_SIZE)

        cp_narrative = describe_changepoints(x_cp, cps, acf_info, min_seg_size=min_seg_size)
        if cp_narrative:
            narrative.append(cp_narrative)

    return " ".join(narrative)


def _compute_histogram_bins(values: np.ndarray) -> tuple[int, float]:
    """
    Compute adaptive histogram binning using Freedman-Diaconis rule.

    The Freedman-Diaconis rule is robust to outliers and adapts well to multimodal data:
    bin_width = 2 * IQR * n^(-1/3)

    Args:
        values: 1D numeric array (should already be cleaned of NaNs)

    Returns:
        Tuple of (n_bins, bin_width)
    """
    n = len(values)
    iqr = np.percentile(values, 75) - np.percentile(values, 25)

    if iqr > 0:
        bin_width = 2 * iqr / (n ** (1/3))
        n_bins = int((values.max() - values.min()) / bin_width)
        # Clamp bins between 10 and 100 for reasonable visualization
        n_bins = max(10, min(n_bins, 100))
    else:
        # Fallback if IQR is zero (all values very similar)
        n_bins = 30
        bin_width = (values.max() - values.min()) / n_bins if values.max() > values.min() else 1.0

    return n_bins, bin_width


def _render_histogram(ax: Any, values: np.ndarray, n_bins: int) -> Any:
    """Render histogram and return counts for downstream use."""
    hist_counts, bin_edges_hist, patches = ax.hist(
        values, bins=n_bins, color='deeppink', alpha=0.5,
        edgecolor='black', density=False, label='Distribution'
    )
    return hist_counts


def _render_intervals(ax: Any, values: np.ndarray) -> None:
    """Render 95% and 67% quantile intervals."""
    q95_low, q95_high = np.quantile(values, [0.025, 0.975])
    q67_low, q67_high = np.quantile(values, [0.165, 0.835])
    ax.axvspan(q95_low, q95_high, color='purple', alpha=0.08, label='95% interval')
    ax.axvspan(q67_low, q67_high, color='purple', alpha=0.18, label='67% interval')


def _render_mode_marker(ax: Any, values: np.ndarray, n_bins: int) -> None:
    """Render mode marker at the peak of the histogram."""
    counts, bin_edges = np.histogram(values, bins=n_bins)
    mode_bin = np.argmax(counts)
    mode_x = (bin_edges[mode_bin] + bin_edges[mode_bin + 1]) / 2
    ax.axvline(mode_x, color='orange', linestyle='--', linewidth=1.5, label='Mode')


def _prepare_scatter_data(values: np.ndarray, max_scatter_points: int) -> np.ndarray:
    """Downsample scatter data if needed for performance."""
    n = len(values)
    if n > max_scatter_points:
        rng = np.random.default_rng(43)
        scatter_indices = rng.choice(n, size=max_scatter_points, replace=False)
        return values[scatter_indices]
    return values


def _render_scatter(ax: Any, values: np.ndarray, jitter: np.ndarray,
                    class_labels: np.ndarray | None = None,
                    class_colors: dict[str, str] | None = None,
                    class_names_order: list[str] | None = None,
                    cutoffs: list[float] | None = None,
                    divider_color: str = '#1f77b4', alpha: float = 0.4) -> None:
    """Render jittered scatter plot with optional classification coloring.

    Args:
        ax: Matplotlib axes
        values: Data values for scatter plot
        jitter: Y-axis jitter values
        class_labels: Array of class labels for each point (optional)
        class_colors: Dictionary mapping class labels to colors (optional)
        class_names_order: Ordered list of class names for legend (optional)
        cutoffs: List of cutoff values to draw vertical lines (optional)
        divider_color: Color for cutoff lines and labels (default: blue)
        alpha: Alpha transparency for scatter points (default: 0.4)
    """
    # Render with class labels if provided
    if class_labels is not None and class_colors is not None:
        # Use provided order if available, otherwise sort alphabetically
        if class_names_order is not None:
            labels_to_plot = class_names_order
        else:
            labels_to_plot = np.unique(class_labels)

        for label in labels_to_plot:
            mask = class_labels == label
            color = class_colors.get(str(label), 'black')
            ax.scatter(values[mask], jitter[mask], s=26, alpha=alpha,
                      color=color, label=str(label), rasterized=True)

        # Draw cutoffs if provided
        if cutoffs:
            for cutoff in cutoffs:
                ax.axvline(cutoff, color=divider_color, linestyle='--', linewidth=1.6)
                ax.text(cutoff, ax.get_ylim()[1], f'{cutoff:.2f}', rotation=90,
                       ha='right', va='top', color=divider_color, fontsize=10)
        return

    # Default fallback (no classification)
    ax.scatter(values, jitter, s=24, alpha=alpha, color='black', rasterized=True)


def _render_boxplot(ax: Any, values: np.ndarray, jitter_height: float, boxplot_y: float) -> None:
    """Render boxplot overlay on scatter plot."""
    bp = ax.boxplot(values, orientation='horizontal', widths=jitter_height * 0.6,
                   positions=[boxplot_y], patch_artist=True, showfliers=False)
    for patch in bp['boxes']:
        patch.set_facecolor('lightblue')
        patch.set_alpha(0.5)
    for median in bp['medians']:
        median.set_color('navy')
        median.set_linewidth(2)


def _choose_legend_location(values: np.ndarray) -> str:
    """Choose optimal legend location based on data skewness.

    For right-skewed data (bulk on left), place legend on the right.
    For left-skewed data (bulk on right), place legend on the left.
    For symmetric data, use default upper left.

    Args:
        values: Data array to analyze

    Returns:
        Matplotlib legend location string
    """
    try:
        skewness = float(stats.skew(values))
        if skewness > 0.5:  # Right-skewed: bulk on left, place legend on right
            return 'upper right'
        elif skewness < -0.5:  # Left-skewed: bulk on right, place legend on left
            return 'upper left'
        else:  # Symmetric or mildly skewed: default
            return 'upper left'
    except Exception:
        return 'upper left'  # Fallback to default


def _add_plot_annotations(ax: Any, n: int, bin_width: float, hist_counts_max: float, jitter_height: float,
                          legend_loc: str = 'upper left') -> None:
    """Add sample size, binning, and axis information to the plot.

    Args:
        ax: Matplotlib axes object
        n: Number of samples
        bin_width: Histogram bin width
        hist_counts_max: Maximum histogram count
        jitter_height: Height of jitter strip
        legend_loc: Location for the class legend (default: 'upper left')
    """
    # Sample size and binning annotation - position complementary to legend
    # If legend is on the left, put info box on right (and vice versa)
    if 'left' in legend_loc:
        info_x, info_ha = 0.98, 'right'
    else:
        info_x, info_ha = 0.02, 'left'

    info_text = f'n={n}\nbinwidth={bin_width:.2g}'
    ax.text(info_x, 0.97, info_text, transform=ax.transAxes,
            ha=info_ha, va='top', fontsize=11,
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.6, pad=0.4))

    ax.set_xlabel('Metric', fontsize=14)
    ax.set_ylabel('Count', fontsize=14)

    # Set y-axis limits with fixed proportional spacing for jitter/boxplot
    y_bottom = -jitter_height * 1.2
    y_top = hist_counts_max * 1.05
    ax.set_ylim(bottom=y_bottom, top=y_top)

    # Enable y-axis with numeric labels
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True, nbins=6))
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'{int(x)}' if x == int(x) else ''))
    ax.grid(alpha=0.3, axis='both')

    # Manage legend with dynamic placement
    try:
        ax.legend(loc=legend_loc, fontsize=9, framealpha=0.4)
    except Exception:
        pass


def create_distribution_plot(values: np.ndarray, metric: str,
                            class_labels: np.ndarray | None = None,
                            class_colors: dict[str, str] | None = None,
                            class_names_order: list[str] | None = None,
                            cutoffs: list[float] | None = None,
                            max_scatter_points: int = 2000,
                            divider_color: str = '#1f77b4', alpha: float = 0.4) -> Figure:

    """Create enriched distribution plot approximating R half-eye + boxplot.

    Features:
      - Histogram with adaptive binning (Freedman-Diaconis rule)
      - 95% and 67% intervals (quantile approximation of HDI)
      - Mode marker (density peak)
      - Boxplot overlay near baseline
      - Jittered raw samples (higher visibility) - downsampled for speed if n > max_scatter_points
      - Optional classification coloring (via class_labels/colors)

    Args:
        values: 1D numeric array
        metric: Metric name for axis label
        class_labels: Array of class labels for each point (optional)
        class_colors: Dictionary mapping class labels to colors (optional)
        class_names_order: Ordered list of class names for legend (optional)
        cutoffs: List of cutoff values to draw vertical lines (optional)
        max_scatter_points: Maximum points to draw in scatter jitter (for speed)
        divider_color: Color for divider line and label (default: blue)
        alpha: Alpha transparency for scatter points (default: 0.4)

    Returns:
        Matplotlib Figure
    """
    # Filter NaNs from values AND class_labels if present
    mask = ~np.isnan(values)
    clean = values[mask]

    clean_labels = None
    if class_labels is not None:
        if len(class_labels) == len(values):
            clean_labels = class_labels[mask]
        else:
            # If lengths mismatch, ignore labels to prevent crash
            clean_labels = None

    n = len(clean)

    if n == 0:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, 'No data', ha='center', va='center')
        ax.axis('off')
        return fig

    fig, ax = plt.subplots(figsize=(10, 6))

    # Compute histogram bins using adaptive Freedman-Diaconis rule
    n_bins, bin_width = _compute_histogram_bins(clean)

    # Render main plot components
    hist_counts = _render_histogram(ax, clean, n_bins)
    _render_intervals(ax, clean)
    _render_mode_marker(ax, clean, n_bins)

    # Prepare and render scatter plot
    # Note: _prepare_scatter_data downsamples. We need to downsample labels too if we do that.
    # For now, let's skip downsampling if labels are present to keep it simple and correct,
    # or implement synchronized downsampling.

    if clean_labels is not None:
        # Synchronized downsampling
        if n > max_scatter_points:
            rng = np.random.default_rng(43)
            scatter_indices = rng.choice(n, size=max_scatter_points, replace=False)
            scatter_clean = clean[scatter_indices]
            scatter_labels = clean_labels[scatter_indices]
        else:
            scatter_clean = clean
            scatter_labels = clean_labels
    else:
        scatter_clean = _prepare_scatter_data(clean, max_scatter_points)
        scatter_labels = None

    rng_jitter = np.random.default_rng(42)
    jitter_height = hist_counts.max() * 0.25
    jitter = rng_jitter.uniform(-jitter_height, -jitter_height * 0.2, len(scatter_clean))

    _render_scatter(ax, scatter_clean, jitter,
                   class_labels=scatter_labels,
                   class_colors=class_colors,
                   class_names_order=class_names_order,
                   cutoffs=cutoffs,
                   divider_color=divider_color,
                   alpha=alpha)

    # Render boxplot overlay
    boxplot_y = (-jitter_height - jitter_height * 0.2) / 2
    _render_boxplot(ax, clean, jitter_height, boxplot_y)

    # Choose optimal legend location based on data distribution
    legend_loc = _choose_legend_location(clean)

    # Add annotations and finalize plot
    _add_plot_annotations(ax, n, bin_width, hist_counts.max(), jitter_height, legend_loc)
    ax.set_xlabel(metric, fontsize=14)

    # Adjust layout to prevent xlabel and ylabel cutoff
    plt.tight_layout(pad=1.5)
    plt.subplots_adjust(bottom=0.12, left=0.12)
    return fig
