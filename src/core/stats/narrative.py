"""
Narrative text generation utilities.

Provides functions for generating human-readable descriptions of statistical
analyses (changepoints, test results, etc.).

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
from typing import Optional, Dict, Any, List
from scipy import stats


def format_sig_figs(value: float, sig_figs: int = 3, is_integer: bool = False) -> str:
    """
    Format a number to N significant figures, stripping trailing zeros.

    Provides consistent number formatting across CLI and GUI components.
    Uses scientific notation for very large (>= 1e6) or very small (<= 1e-4)
    numbers to improve readability. Uses regular notation with significant
    figures for all other values.

    Args:
        value: Number to format
        sig_figs: Number of significant figures (default: 3)
        is_integer: If True, format as integer without decimals

    Returns:
        Formatted string representation

    Examples:
        >>> format_sig_figs(24140962, sig_figs=3)
        '2.41e+07'
        >>> format_sig_figs(123.456, sig_figs=3)
        '123'
        >>> format_sig_figs(0.0001234, sig_figs=3)
        '1.23e-04'
        >>> format_sig_figs(1.234, sig_figs=3)
        '1.23'
    """
    if np.isnan(value):
        return "NA"
    if is_integer:
        return str(int(value))

    if value == 0:
        return "0"

    abs_value = abs(value)

    # Use scientific notation for very large or very small numbers
    if abs_value >= 1e6 or (abs_value < 1e-4 and abs_value > 0):
        return f"{value:.{sig_figs-1}e}"

    # Calculate significant figures for regular notation
    magnitude = np.floor(np.log10(abs_value))
    rounded = np.round(value, -int(magnitude) + (sig_figs - 1))

    # Format and strip trailing zeros
    if magnitude >= sig_figs - 1:
        return str(int(rounded))
    else:
        decimals = int(-magnitude + sig_figs - 1)
        formatted = f"{rounded:.{decimals}f}"
        # Strip trailing zeros and decimal point if not needed
        formatted = formatted.rstrip('0').rstrip('.')
        return formatted


def _characterize_acf(x_clean: np.ndarray, acf_threshold: float) -> List[str]:
    """
    Generate narrative about autocorrelation in the time series.

    Args:
        x_clean: Clean numeric array (no NaNs)
        acf_threshold: Threshold for ACF significance

    Returns:
        List of narrative strings about ACF
    """
    from .distribution import estimate_acf_lag

    narrative = []
    acf_info = estimate_acf_lag(x_clean, threshold=acf_threshold)

    if 'max_acf' in acf_info and not np.isnan(acf_info['max_acf']):
        max_acf = acf_info['max_acf']
        lag = acf_info.get('lag', 0)

        if max_acf > 0.5:
            narrative.append(
                f"Strong autocorrelation detected (max ACF={max_acf:.2f} at lag ~{lag}), "
                "suggesting performance samples are not truly independent or the system "
                "preserves state between runs."
            )
        elif max_acf > 0.2:
            narrative.append(
                f"Moderate autocorrelation present (max ACF={max_acf:.2f}), "
                "indicating some temporal dependency in measurements."
            )

    return narrative


def _characterize_period(x_clean: np.ndarray, cps: List[int], n: int,
                         min_seg_size: int, threshold_pct: float,
                         period_type: str) -> tuple[List[str], List[int]]:
    """
    Detect and characterize a performance period (warmup or cooldown).

    Args:
        x_clean: Clean numeric array
        cps: List of change points
        n: Total length
        min_seg_size: Minimum segment size
        threshold_pct: Percentage threshold for period detection (0-1)
        period_type: 'warmup' or 'cooldown'

    Returns:
        Tuple of (narrative list, matched change points list)
    """
    narrative = []

    if period_type == "warmup":
        threshold = int(threshold_pct * n)
        matched_cps = [cp for cp in cps if cp <= threshold and cp >= min_seg_size]
        idx_selector = lambda lst: lst[0] if lst else None
        position_label = lambda pct: f"first {pct}%"
        period_label = "Warmup period"
    else:  # cooldown
        threshold = int(threshold_pct * n)
        matched_cps = [cp for cp in cps if cp >= threshold]
        idx_selector = lambda lst: lst[-1] if lst else None
        position_label = lambda pct: f"after {pct}%"
        period_label = "Cooldown/degradation"

    if not matched_cps:
        return narrative, []

    period_idx = idx_selector(matched_cps)
    if period_idx is None:
        return narrative, []

    period_pct_actual = round(100 * period_idx / n)

    before_data = x_clean[:period_idx]
    after_data = x_clean[period_idx:]

    if len(before_data) >= 3 and len(after_data) >= 3:
        before_median = np.median(before_data)
        after_median = np.median(after_data)
        _, p_value = stats.mannwhitneyu(before_data, after_data, alternative='two-sided')

        direction = "higher" if after_median > before_median else "lower"
        median_diff = abs(after_median - before_median)

        narrative.append(
            f"{period_label} detected in {position_label(period_pct_actual)} of samples "
            f"(median {direction} by {median_diff:.2f}, p={p_value:.4f})."
        )

    return narrative, matched_cps


def characterize_changepoints(x: np.ndarray, model: str = "auto",
                              pen: Optional[float] = None,
                              min_size: Optional[int] = None,
                              acf_threshold: float = 0.2,
                              warmup_pct: float = 0.3,
                              cooldown_pct: float = 0.7) -> str:
    """
    Characterize warmup, cooldown, and change points in a time series.

    Args:
        x: Numeric array (time series)
        model: Change point model ("auto" adapts based on sample size)
        pen: Penalty for change point detection
        min_size: Minimum segment size
        acf_threshold: Threshold for ACF significance
        warmup_pct: Percentage threshold for warmup detection (0-1)
        cooldown_pct: Percentage threshold for cooldown detection (0-1)

    Returns:
        Narrative string describing temporal patterns
    """
    from .distribution import detect_change_points

    x_clean = x[~np.isnan(x)]
    n = len(x_clean)

    if n < 10:
        return ""

    narrative = []

    # ACF analysis
    narrative.extend(_characterize_acf(x_clean, acf_threshold))

    # Change point detection
    cp_result = detect_change_points(x_clean, model=model, pen=pen, min_size=min_size)

    if 'error' in cp_result:
        return " ".join(narrative)

    cps = cp_result.get('cps', [])
    if len(cps) == 0:
        narrative.append("No significant change points detected; series appears stationary.")
        return " ".join(narrative)

    min_seg_size = cp_result.get('min_size', 3)

    # Detect warmup
    warmup_narrative, early_cps = _characterize_period(x_clean, cps, n, min_seg_size, warmup_pct, "warmup")
    narrative.extend(warmup_narrative)

    # Detect cooldown
    cooldown_narrative, late_cps = _characterize_period(x_clean, cps, n, min_seg_size, cooldown_pct, "cooldown")
    narrative.extend(cooldown_narrative)

    # Report other change points
    middle_cps = [cp for cp in cps if cp not in early_cps and cp not in late_cps]
    if len(middle_cps) > 0:
        narrative.append(
            f"{len(middle_cps)} additional change point(s) detected in the middle of the series, "
            f"suggesting non-stationary behavior or external disturbances."
        )

    return " ".join(narrative)


def format_p_value(p: float, rounding: int = 2, p_option: str = "rounded") -> str:
    """
    Format p-value for display.

    Args:
        p: P-value to format
        rounding: Number of decimal places
        p_option: 'rounded', 'scientific', or 'exact'

    Returns:
        Formatted p-value string
    """
    if np.isnan(p):
        return "NA"

    match p_option:
        case "scientific":
            return f"{p:.2e}" if p < 0.001 else f"{p:.{rounding}f}"
        case "exact":
            return f"{p:.{rounding}f}"
        case _:  # rounded (default)
            match True:
                case _ if p < 0.001:
                    return "< 0.001"
                case _ if p < 0.01:
                    return f"{p:.3f}"
                case _:
                    return f"{p:.{rounding}f}"


def report_test(test_result: Dict[str, Any], rounding: int = 2,
               p_option: str = "rounded") -> str:
    """
    Generate a formatted report of a statistical test result.

    Args:
        test_result: Dictionary with 'statistic', 'p_value', and optionally 'effect_size'
        rounding: Number of decimal places
        p_option: P-value formatting option

    Returns:
        Formatted test result string
    """
    if 'error' in test_result:
        return f"Test failed: {test_result['error']}"

    stat = test_result.get('statistic', np.nan)
    p_val = test_result.get('p_value', np.nan)
    effect = test_result.get('effect_size', None)

    if np.isnan(stat) or np.isnan(p_val):
        return "Test result unavailable"

    p_str = format_p_value(p_val, rounding=rounding, p_option=p_option)

    report = f"U = {stat:.{rounding}f}, p = {p_str}"

    if effect is not None and not np.isnan(effect):
        report += f", effect size = {effect:.{rounding}f}"

    return report


def generate_comparison_narrative(baseline: np.ndarray, treatment: np.ndarray,
                                  p_thresh: float = 0.01) -> str:
    """
    Generate narrative comparison between baseline and treatment distributions.

    Performs multiple statistical tests and generates human-readable LaTeX-formatted
    narrative describing the relationship between two performance distributions.

    Args:
        baseline: Baseline performance measurements
        treatment: Treatment performance measurements
        p_thresh: P-value threshold for significance (default: 0.01)

    Returns:
        HTML with separate LaTeX blocks for each line
    """
    lines = []

    # Compare means (t-test)
    t_result = stats.ttest_ind(treatment, baseline)
    sig = "significantly" if t_result.pvalue < p_thresh else ""

    if t_result.pvalue >= 0.3:
        higher = "about the same as"
    else:
        higher = "higher than" if np.mean(treatment) > np.mean(baseline) else "lower than"

    lines.append(f"$$\\text{{Treatment mean is {sig} {higher} baseline}}$$")
    lines.append(f"$${_format_test_latex('t-test', t_result.statistic, t_result.pvalue)}$$")

    # Compare medians (Wilcoxon/Mann-Whitney)
    w_result = stats.mannwhitneyu(treatment, baseline, alternative='two-sided')
    sig = "significantly" if w_result.pvalue < p_thresh else ""

    if w_result.pvalue >= 0.3:
        higher = "about the same as"
    else:
        higher = "higher than" if np.median(treatment) > np.median(baseline) else "lower than"

    lines.append(f"$$\\text{{Treatment median is {sig} {higher} baseline}}$$")
    lines.append(f"$${_format_test_latex('Wilcoxon', w_result.statistic, w_result.pvalue)}$$")

    # Kolmogorov-Smirnov test
    ks_result = stats.ks_2samp(treatment, baseline)
    dist_description = "very similar" if ks_result.statistic <= 0.1 else (
        "similar" if ks_result.statistic <= 0.3 else "dissimilar"
    )
    lines.append(f"$$\\text{{Distributions appear to be {dist_description}}}$$")
    lines.append(f"$${_format_test_latex('KS', ks_result.statistic, ks_result.pvalue)}$$")

    # Correlation (only if same length)
    if len(baseline) == len(treatment):
        c_result = stats.pearsonr(treatment, baseline)
        if abs(c_result[0]) <= 0.3:
            corr_description = "uncorrelated"
        else:
            strength = "strongly" if abs(c_result[0]) > 0.7 else "somewhat"
            direction = "correlated" if c_result[0] > 0 else "anti-correlated"
            corr_description = f"{strength} {direction}"

        lines.append(f"$$\\text{{Samples appear to be {corr_description}}}$$")
        lines.append(f"$${_format_test_latex('correlation', c_result[0], c_result[1])}$$")

    # Kalman filter fusion
    var_baseline = np.var(baseline, ddof=1)
    var_treatment = np.var(treatment, ddof=1)
    sumv = var_baseline + var_treatment

    if sumv > 0:
        fused = (var_treatment * np.mean(baseline) + var_baseline * np.mean(treatment)) / sumv
        lines.append(f"$$\\text{{Mean performance fused with Kalman Filter}}$$")
        lines.append(f"$$\\mu={fused:.4f}$$")

    # Join lines with paragraph breaks
    narrative = "<p>" + "</p><p>".join(lines) + "</p>"
    return narrative


def _format_test_latex(test_name: str, statistic: float, p_value: float) -> str:
    """Format statistical test result as LaTeX."""
    p_str = format_p_value(p_value, rounding=4, p_option="rounded")
    return f"\\text{{{test_name}: stat={statistic:.4f}, p={p_str}}}"
