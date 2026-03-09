"""
Distribution analysis utilities.

Provides functions for computing summary statistics, detecting change points,
estimating autocorrelation, and characterizing distributions.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
from scipy import stats
from typing import Dict, Optional, Tuple, Any
import warnings
import matplotlib.pyplot as plt

# Threshold for automatic model selection in change point detection.
# Below this sample size, use RBF (more accurate); above, use L2 (faster).
AUTO_MODEL_THRESHOLD = 500


def compute_summary(x: np.ndarray, digits: int = 5) -> Dict[str, float]:
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
                        pen: Optional[float] = None,
                        min_size: Optional[int] = None,
                        auto_threshold: int = AUTO_MODEL_THRESHOLD) -> Dict[str, Any]:
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

    if n < 10:
        return {'cps': [], 'n': n}

    # Adaptive model selection: RBF for small samples (more accurate),
    # L2 for large samples (much faster, O(n log n) vs O(n²))
    if model == "auto":
        model = "rbf" if n <= auto_threshold else "l2"

    # Set defaults
    if min_size is None:
        min_size = max(3, int(0.05 * n))
    if pen is None:
        pen = 3 * np.log(n)

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


def estimate_acf_lag(x: np.ndarray, threshold: float = 0.2,
                    max_lag: Optional[int] = None) -> Dict[str, Any]:
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

    if n < 10:
        return {'lag': 0, 'max_acf': np.nan}

    if max_lag is None:
        max_lag = min(int(n / 4), 50)

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
                return abs(skewness) >= 0.5
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
        return (abs(mode_val - median_val) / (value_range + 1e-10)) < 0.05
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


def _test_normality(x_clean: np.ndarray) -> Optional[str]:
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
                              pen: Optional[float] = None,
                              min_size: Optional[int] = None) -> str:
    """
    Characterize the distribution of a numeric vector with narrative text.

    Args:
        x: Numeric array
        skew_thresh: Threshold for considering distribution skewed
        model: Change point model ("auto" adapts based on sample size)
        pen: Penalty for change point detection
        min_size: Minimum segment size for change points

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
    from .narrative import characterize_changepoints
    cp_narrative = characterize_changepoints(x_clean, model=model, pen=pen, min_size=min_size)
    if cp_narrative:
        narrative.append(cp_narrative)

    return " ".join(narrative)


def _compute_histogram_bins(values: np.ndarray) -> Tuple[int, float]:
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


def _render_histogram(ax, values: np.ndarray, n_bins: int):
    """Render histogram and return counts for downstream use."""
    hist_counts, bin_edges_hist, patches = ax.hist(
        values, bins=n_bins, color='deeppink', alpha=0.5,
        edgecolor='black', density=False, label='Distribution'
    )
    return hist_counts


def _render_intervals(ax, values: np.ndarray):
    """Render 95% and 67% quantile intervals."""
    q95_low, q95_high = np.quantile(values, [0.025, 0.975])
    q67_low, q67_high = np.quantile(values, [0.165, 0.835])
    ax.axvspan(q95_low, q95_high, color='purple', alpha=0.08, label='95% interval')
    ax.axvspan(q67_low, q67_high, color='purple', alpha=0.18, label='67% interval')


def _render_mode_marker(ax, values: np.ndarray, n_bins: int):
    """Render mode marker at the peak of the histogram."""
    counts, bin_edges = np.histogram(values, bins=n_bins)
    mode_bin = np.argmax(counts)
    mode_x = (bin_edges[mode_bin] + bin_edges[mode_bin + 1]) / 2
    ax.axvline(mode_x, color='orange', linestyle='--', linewidth=1.5, label='Mode')


def _prepare_scatter_data(values: np.ndarray, max_scatter_points: int):
    """Downsample scatter data if needed for performance."""
    n = len(values)
    if n > max_scatter_points:
        rng = np.random.default_rng(43)
        scatter_indices = rng.choice(n, size=max_scatter_points, replace=False)
        return values[scatter_indices]
    return values


def _render_scatter(ax, values: np.ndarray, jitter: np.ndarray, divider: Optional[float] = None,
                    left_color: str = '#2ca02c', right_color: str = '#ff7f0e',
                    divider_color: str = '#1f77b4', alpha: float = 0.4):
    """Render jittered scatter plot with optional divider coloring.

    Args:
        ax: Matplotlib axes
        values: Data values for scatter plot
        jitter: Y-axis jitter values
        divider: Optional cutoff value to split points into left/right groups
        left_color: Color for points <= divider (default: dark green)
        right_color: Color for points > divider (default: orange)
        divider_color: Color for divider line and label (default: blue)
        alpha: Alpha transparency for scatter points (default: 0.4)
    """
    if divider is not None:
        left_mask = values <= divider
        right_mask = ~left_mask
        ax.scatter(values[left_mask], jitter[left_mask], s=26, alpha=alpha,
                  color=left_color, label='≤ cutoff', rasterized=True)
        ax.scatter(values[right_mask], jitter[right_mask], s=26, alpha=alpha,
                  color=right_color, label='> cutoff', rasterized=True)
        ax.axvline(divider, color=divider_color, linestyle='--', linewidth=1.6)
        ax.text(divider, ax.get_ylim()[1], f'{divider:.2f}', rotation=90,
               ha='right', va='top', color=divider_color, fontsize=10)
    else:
        ax.scatter(values, jitter, s=24, alpha=alpha, color='black', rasterized=True)


def _render_boxplot(ax, values: np.ndarray, jitter_height: float, boxplot_y: float):
    """Render boxplot overlay on scatter plot."""
    bp = ax.boxplot(values, vert=False, widths=jitter_height * 0.6,
                   positions=[boxplot_y], patch_artist=True, showfliers=False)
    for patch in bp['boxes']:
        patch.set_facecolor('lightblue')
        patch.set_alpha(0.5)
    for median in bp['medians']:
        median.set_color('navy')
        median.set_linewidth(2)


def _add_plot_annotations(ax, n: int, bin_width: float, hist_counts_max: float, jitter_height: float):
    """Add sample size, binning, and axis information to the plot."""
    # Sample size and binning annotation
    info_text = f'n={n}\nbinwidth={bin_width:.2g}'
    ax.text(0.98, 0.97, info_text, transform=ax.transAxes,
            ha='right', va='top', fontsize=11,
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.6, pad=0.4))

    ax.set_xlabel('Metric', fontsize=14)
    ax.set_ylabel('Count', fontsize=14)

    # Set y-axis limits with fixed proportional spacing for jitter/boxplot
    y_bottom = -jitter_height * 1.2
    y_top = hist_counts_max * 1.05
    ax.set_ylim(bottom=y_bottom, top=y_top)

    # Enable y-axis with numeric labels
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True, nbins=6))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x)}' if x == int(x) else ''))
    ax.grid(alpha=0.3, axis='both')

    # Manage legend
    try:
        ax.legend(loc='upper left', fontsize=9, framealpha=0.4)
    except Exception:
        pass


def create_distribution_plot(values: np.ndarray, metric: str, divider: Optional[float] = None,
                            max_scatter_points: int = 2000,
                            left_color: str = '#2ca02c', right_color: str = '#ff7f0e',
                            divider_color: str = '#1f77b4', alpha: float = 0.4):
    """Create enriched distribution plot approximating R half-eye + boxplot.

    Features:
      - Histogram with adaptive binning (Freedman-Diaconis rule)
      - 95% and 67% intervals (quantile approximation of HDI)
      - Mode marker (density peak)
      - Boxplot overlay near baseline
      - Jittered raw samples (higher visibility) - downsampled for speed if n > max_scatter_points
      - Optional divider vertical line splitting points (color groups)

    Args:
        values: 1D numeric array
        metric: Metric name for axis label
        divider: Optional cutoff value visually separating samples
        max_scatter_points: Maximum points to draw in scatter jitter (for speed)
        left_color: Color for points <= divider (default: dark green)
        right_color: Color for points > divider (default: orange)
        divider_color: Color for divider line and label (default: blue)
        alpha: Alpha transparency for scatter points (default: 0.4)

    Returns:
        Matplotlib Figure
    """
    clean = values[~np.isnan(values)]
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
    scatter_clean = _prepare_scatter_data(clean, max_scatter_points)
    rng_jitter = np.random.default_rng(42)
    jitter_height = hist_counts.max() * 0.25
    jitter = rng_jitter.uniform(-jitter_height, -jitter_height * 0.2, len(scatter_clean))
    _render_scatter(ax, scatter_clean, jitter, divider, left_color, right_color, divider_color, alpha)

    # Render boxplot overlay
    boxplot_y = (-jitter_height - jitter_height * 0.2) / 2
    _render_boxplot(ax, clean, jitter_height, boxplot_y)

    # Add annotations and finalize plot
    _add_plot_annotations(ax, n, bin_width, hist_counts.max(), jitter_height)
    ax.set_xlabel(metric, fontsize=14)

    # Adjust layout to prevent xlabel and ylabel cutoff
    plt.tight_layout(pad=1.5)
    plt.subplots_adjust(bottom=0.12, left=0.12)
    return fig
