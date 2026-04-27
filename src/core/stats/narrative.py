"""
Narrative text generation utilities.

Provides functions for generating human-readable descriptions of statistical
analyses (changepoints, test results, etc.).

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
from typing import Any, Callable
from scipy import stats

# Below this ACF magnitude, temporal dependence is mild enough that it does not
# usually dominate the changepoint narrative.
MODERATE_AUTOCORRELATION_THRESHOLD = 0.2

# Above this ACF magnitude, neighboring samples are strongly coupled and the
# narrative should explicitly warn that runs may not be independent.
STRONG_AUTOCORRELATION_THRESHOLD = 0.5

# Changepoint narratives only make sense once the series is long enough to have
# at least a few points in multiple candidate segments.
MIN_CHANGEPOINT_NARRATIVE_SAMPLES = 10

# Three samples per side is the smallest partition that still gives a sensible
# median comparison and a stable Mann-Whitney test.
MIN_PERIOD_COMPARISON_SAMPLES = 3

# Match the detector's minimum segment size default so narrative logic and PELT
# use the same lower bound for what counts as a meaningful phase.
DEFAULT_MIN_CHANGEPOINT_SEGMENT_SIZE = 3

# By default, treat the first 30% of the series as the warmup search window.
DEFAULT_WARMUP_FRACTION = 0.3

# By default, treat the final 30% of the series as the cooldown search window,
# which corresponds to changepoints after the 70% mark.
DEFAULT_COOLDOWN_FRACTION = 0.7


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


def describe_acf(acf_info: dict[str, Any]) -> list[str]:
    """
    Generate narrative about autocorrelation in the time series.

    Args:
        acf_info: Dictionary with 'max_acf' and 'lag' keys

    Returns:
        List of narrative strings about ACF
    """
    narrative = []

    if 'max_acf' in acf_info and not np.isnan(acf_info['max_acf']):
        max_acf = acf_info['max_acf']
        lag = acf_info.get('lag', 0)

        if max_acf > STRONG_AUTOCORRELATION_THRESHOLD:
            narrative.append(
                f"Strong autocorrelation detected (max ACF={max_acf:.2f} at lag ~{lag}), "
                "suggesting performance samples are not truly independent or the system "
                "preserves state between runs."
            )
        elif max_acf > MODERATE_AUTOCORRELATION_THRESHOLD:
            narrative.append(
                f"Moderate autocorrelation present (max ACF={max_acf:.2f}), "
                "indicating some temporal dependency in measurements."
            )

    return narrative


def _characterize_period(x_clean: np.ndarray, cps: list[int], n: int,
                         min_seg_size: int, threshold_pct: float,
                         period_type: str) -> tuple[list[str], list[int]]:
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
    narrative: list[str] = []

    idx_selector: Callable[[list[int]], int | None]
    position_label: Callable[[int], str]

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

    if len(before_data) >= MIN_PERIOD_COMPARISON_SAMPLES and len(after_data) >= MIN_PERIOD_COMPARISON_SAMPLES:
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


def describe_changepoints(x: np.ndarray, cps: list[int], acf_info: dict[str, Any],
                          min_seg_size: int = DEFAULT_MIN_CHANGEPOINT_SEGMENT_SIZE,
                          warmup_pct: float = DEFAULT_WARMUP_FRACTION,
                          cooldown_pct: float = DEFAULT_COOLDOWN_FRACTION) -> str:
    """
    Characterize warmup, cooldown, and change points in a time series.

    Args:
        x: Numeric array (time series)
        cps: List of detected change points
        acf_info: Dictionary with ACF analysis results
        min_seg_size: Minimum segment size used in detection
        warmup_pct: Percentage threshold for warmup detection (0-1)
        cooldown_pct: Percentage threshold for cooldown detection (0-1)

    Returns:
        Narrative string describing temporal patterns
    """
    x_clean = x[~np.isnan(x)]
    n = len(x_clean)

    if n < MIN_CHANGEPOINT_NARRATIVE_SAMPLES:
        return ""

    narrative = []

    # ACF analysis
    narrative.extend(describe_acf(acf_info))

    if len(cps) == 0:
        narrative.append("No significant change points detected; series appears stationary.")
        return " ".join(narrative)

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


def format_p_value_table(p: float, sig_figs: int = 4, stars: bool = True) -> str:
    """
    Format p-value for table display with up to N significant figures.

    Uses scientific notation for very small values (< 1e-4).
    Optionally adds significance stars.

    Args:
        p: P-value to format
        sig_figs: Number of significant figures (default: 4)
        stars: Whether to append significance stars (default: True)

    Returns:
        Formatted p-value string with optional stars
    """
    if np.isnan(p) or p is None:
        return "NA"

    # Use format_sig_figs for consistent formatting
    formatted = format_sig_figs(p, sig_figs=sig_figs)

    if stars:
        if p < 0.001:
            formatted += " ***"
        elif p < 0.01:
            formatted += " **"
        elif p < 0.05:
            formatted += " *"

    return formatted


def report_test(test_result: dict[str, Any], rounding: int = 2,
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


def _format_test_latex(test_name: str, statistic: float, p_value: float) -> str:
    """Format statistical test result as LaTeX."""
    p_str = format_p_value(p_value, rounding=4, p_option="rounded")
    return f"\\text{{{test_name}: stat={statistic:.4f}, p={p_str}}}"


def generate_comparison_narrative(baseline: np.ndarray, treatment: np.ndarray,
                                 lower_is_better: bool | None = None,
                                 p_thresh: float = 0.01) -> str:
    """
    Generate HTML-formatted narrative comparison with color coding.

    Provides plain text description styled with HTML colors:
    - Improvements (better performance, lower dispersion): bold/green
    - Degradations (worse performance, higher dispersion): underline/red
    - If lower_is_better is None, no color coding is applied (neutral styling)

    Args:
        baseline: Baseline performance measurements
        treatment: Treatment performance measurements
        lower_is_better: If True, lower values are better; if False, higher is better;
                        if None, no color coding applied (neutral)
        p_thresh: P-value threshold for significance (default: 0.01)

    Returns:
        HTML-formatted narrative with color-coded adjectives/adverbs (or neutral if lower_is_better=None)
    """
    def style_good(text: str) -> str:
        """Style text as improvement (bold/green)."""
        return f'<b style="color: green;">{text}</b>'

    def style_bad(text: str) -> str:
        """Style text as degradation (underline/red)."""
        return f'<u style="color: red;">{text}</u>'

    lines = []

    # Compare means (t-test)
    t_result = stats.ttest_ind(treatment, baseline)
    sig = "significantly " if t_result.pvalue < p_thresh else ""

    if t_result.pvalue >= 0.3:
        change_word = "remained about the same"
    else:
        mean_increased = np.mean(treatment) > np.mean(baseline)

        if lower_is_better is None:
            # Neutral styling - no color coding
            change_word = "increased" if mean_increased else "decreased"
        else:
            # If lower is better: increase is bad, decrease is good
            # If higher is better: increase is good, decrease is bad
            if mean_increased:
                change_word = style_good("increased") if not lower_is_better else style_bad("increased")
            else:
                change_word = style_good("decreased") if lower_is_better else style_bad("decreased")

    lines.append(f"Treatment mean {sig}{change_word} compared to baseline.")

    # Compare medians
    if t_result.pvalue >= 0.3:
        change_word = "remained about the same"
    else:
        median_increased = np.median(treatment) > np.median(baseline)
        if lower_is_better is None:
            change_word = "increased" if median_increased else "decreased"
        else:
            if median_increased:
                change_word = style_good("increased") if not lower_is_better else style_bad("increased")
            else:
                change_word = style_good("decreased") if lower_is_better else style_bad("decreased")

    lines.append(f"Treatment median {sig}{change_word}.")

    # Analyze dispersion changes
    baseline_std = np.std(baseline, ddof=1)
    treatment_std = np.std(treatment, ddof=1)
    baseline_cv = baseline_std / np.mean(baseline) if np.mean(baseline) != 0 else np.nan
    treatment_cv = treatment_std / np.mean(treatment) if np.mean(treatment) != 0 else np.nan

    # Standard deviation (lower dispersion is always better)
    std_ratio = treatment_std / baseline_std if baseline_std > 0 else np.nan
    if not np.isnan(std_ratio):
        if std_ratio > 1.2:
            text = "increased notably"
            lines.append(f"Dispersion (standard deviation) {style_bad(text) if lower_is_better is not None else text}.")
        elif std_ratio < 0.8:
            text = "decreased notably"
            lines.append(f"Dispersion (standard deviation) {style_good(text) if lower_is_better is not None else text}.")
        else:
            lines.append("Dispersion (standard deviation) remained similar.")

    # Coefficient of variation (lower is better)
    if not np.isnan(baseline_cv) and not np.isnan(treatment_cv):
        cv_ratio = treatment_cv / baseline_cv if baseline_cv > 0 else np.nan
        if not np.isnan(cv_ratio):
            if cv_ratio > 1.2:
                text = "increased"
                lines.append(f"Relative variability (CV) {style_bad(text) if lower_is_better is not None else text}.")
            elif cv_ratio < 0.8:
                text = "decreased"
                lines.append(f"Relative variability (CV) {style_good(text) if lower_is_better is not None else text}.")

    # IQR analysis (lower is better)
    baseline_q25, baseline_q75 = np.percentile(baseline, [25, 75])
    treatment_q25, treatment_q75 = np.percentile(treatment, [25, 75])
    baseline_iqr = baseline_q75 - baseline_q25
    treatment_iqr = treatment_q75 - treatment_q25

    iqr_ratio = treatment_iqr / baseline_iqr if baseline_iqr > 0 else np.nan
    if not np.isnan(iqr_ratio):
        if iqr_ratio > 1.2:
            text = "widened"
            lines.append(f"Interquartile range (IQR) {style_bad(text) if lower_is_better is not None else text}.")
        elif iqr_ratio < 0.8:
            text = "narrowed"
            lines.append(f"Interquartile range (IQR) {style_good(text) if lower_is_better is not None else text}.")

    # Range analysis (lower is better)
    baseline_range = np.max(baseline) - np.min(baseline)
    treatment_range = np.max(treatment) - np.min(treatment)
    range_ratio = treatment_range / baseline_range if baseline_range > 0 else np.nan
    if not np.isnan(range_ratio):
        if range_ratio > 1.2:
            text = "expanded"
            lines.append(f"Overall range {style_bad(text) if lower_is_better is not None else text}.")
        elif range_ratio < 0.8:
            text = "contracted"
            lines.append(f"Overall range {style_good(text) if lower_is_better is not None else text}.")

    # Tail behavior (p95, p99) - depends on lower_is_better
    baseline_p95 = np.percentile(baseline, 95)
    treatment_p95 = np.percentile(treatment, 95)
    baseline_p99 = np.percentile(baseline, 99)
    treatment_p99 = np.percentile(treatment, 99)

    p99_ratio = treatment_p99 / baseline_p99 if baseline_p99 > 0 else np.nan
    if not np.isnan(p99_ratio):
        # For tail latency, check if it got worse or better based on lower_is_better
        tail_increased = p99_ratio > 1.1
        tail_decreased = p99_ratio < 0.9

        if tail_increased:
            if lower_is_better is None:
                lines.append("Tail latency (p99) increased.")
            elif lower_is_better:
                lines.append(f"Tail latency (p99) {style_bad('worsened')}.")
            else:
                lines.append(f"Tail latency (p99) {style_good('improved')}.")
        elif tail_decreased:
            if lower_is_better is None:
                lines.append("Tail latency (p99) decreased.")
            elif lower_is_better:
                lines.append(f"Tail latency (p99) {style_good('improved')}.")
            else:
                lines.append(f"Tail latency (p99) {style_bad('worsened')}.")

    # Distribution similarity (KS test)
    ks_result = stats.ks_2samp(treatment, baseline)
    if ks_result.pvalue < p_thresh:
        lines.append("Distributions are statistically different.")
    else:
        lines.append("Distributions are statistically similar.")

    # Kalman filter fusion
    var_baseline = np.var(baseline, ddof=1)
    var_treatment = np.var(treatment, ddof=1)
    sumv = var_baseline + var_treatment

    if sumv > 0:
        fused = (var_treatment * np.mean(baseline) + var_baseline * np.mean(treatment)) / sumv
        fused_str = format_sig_figs(fused, sig_figs=4)
        lines.append(f"Kalman-filtered mean performance: {fused_str}.")

    return " ".join(lines)
