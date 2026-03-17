"""
Statistical comparison utilities.

Provides functions for comparing distributions (ECDF, density plots, statistical tests).

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
from scipy import stats
from typing import Any


def mann_whitney_test(baseline: np.ndarray, treatment: np.ndarray,
                     alternative: str = 'two-sided') -> dict[str, Any]:
    """
    Perform Mann-Whitney U test (non-parametric comparison of two distributions).

    Args:
        baseline: Baseline measurements
        treatment: Treatment measurements
        alternative: 'two-sided', 'less', or 'greater'

    Returns:
        Dictionary with 'statistic', 'p_value', and 'effect_size' (rank-biserial correlation)
    """
    baseline_clean = baseline[~np.isnan(baseline)]
    treatment_clean = treatment[~np.isnan(treatment)]

    if len(baseline_clean) < 3 or len(treatment_clean) < 3:
        return {'statistic': np.nan, 'p_value': np.nan, 'effect_size': np.nan,
                'error': 'Insufficient data'}

    try:
        statistic, p_value = stats.mannwhitneyu(
            baseline_clean, treatment_clean, alternative=alternative
        )

        # Compute effect size (rank-biserial correlation)
        n1, n2 = len(baseline_clean), len(treatment_clean)
        u1 = statistic
        # For mannwhitneyu, rank-biserial = 1 - (2*U)/(n1*n2)
        # But we need to normalize: r = (2*U)/(n1*n2) - 1
        effect_size = 1 - (2 * u1) / (n1 * n2)

        return {
            'statistic': float(statistic),
            'p_value': float(p_value),
            'effect_size': float(effect_size)
        }
    except Exception as e:
        return {'statistic': np.nan, 'p_value': np.nan, 'effect_size': np.nan,
                'error': str(e)}


def ecdf_comparison(baseline: np.ndarray, treatment: np.ndarray,
                   metric: str) -> dict[str, Any]:
    """
    Generate ECDF (Empirical Cumulative Distribution Function) comparison data.

    Args:
        baseline: Baseline measurements
        treatment: Treatment measurements
        metric: Name of metric being compared

    Returns:
        Dictionary with 'baseline_ecdf', 'treatment_ecdf' (sorted data with cumulative probabilities),
        'ks_statistic', 'ks_p_value', 'metric'
    """
    baseline_clean = baseline[~np.isnan(baseline)]
    treatment_clean = treatment[~np.isnan(treatment)]

    if len(baseline_clean) == 0 or len(treatment_clean) == 0:
        return {'error': 'Empty data', 'metric': metric}

    # Sort data for ECDF
    baseline_sorted = np.sort(baseline_clean)
    treatment_sorted = np.sort(treatment_clean)

    # Compute cumulative probabilities
    baseline_ecdf = {
        'values': baseline_sorted.tolist(),
        'cumprob': (np.arange(1, len(baseline_sorted) + 1) / len(baseline_sorted)).tolist()
    }
    treatment_ecdf = {
        'values': treatment_sorted.tolist(),
        'cumprob': (np.arange(1, len(treatment_sorted) + 1) / len(treatment_sorted)).tolist()
    }

    # Kolmogorov-Smirnov test
    try:
        ks_stat, ks_p = stats.ks_2samp(baseline_clean, treatment_clean)
    except Exception:
        ks_stat, ks_p = np.nan, np.nan

    return {
        'baseline_ecdf': baseline_ecdf,
        'treatment_ecdf': treatment_ecdf,
        'ks_statistic': float(ks_stat) if not np.isnan(ks_stat) else None,
        'ks_p_value': float(ks_p) if not np.isnan(ks_p) else None,
        'metric': metric
    }


def density_comparison(baseline: np.ndarray, treatment: np.ndarray,
                      metric: str, bw_method: str | None = None) -> dict[str, Any]:
    """
    Generate kernel density estimation comparison data.

    Args:
        baseline: Baseline measurements
        treatment: Treatment measurements
        metric: Name of metric being compared
        bw_method: Bandwidth method ('scott', 'silverman', or float)

    Returns:
        Dictionary with 'baseline_kde', 'treatment_kde' (x/y values for density curves),
        'metric'
    """
    baseline_clean = baseline[~np.isnan(baseline)]
    treatment_clean = treatment[~np.isnan(treatment)]

    if len(baseline_clean) < 3 or len(treatment_clean) < 3:
        return {'error': 'Insufficient data for KDE', 'metric': metric}

    try:
        from scipy.stats import gaussian_kde

        # Compute KDE
        baseline_kde_obj = gaussian_kde(baseline_clean, bw_method=bw_method)
        treatment_kde_obj = gaussian_kde(treatment_clean, bw_method=bw_method)

        # Generate evaluation points (common range for both)
        x_min = min(baseline_clean.min(), treatment_clean.min())
        x_max = max(baseline_clean.max(), treatment_clean.max())
        x_range = np.linspace(x_min, x_max, 200)

        baseline_density = baseline_kde_obj(x_range)
        treatment_density = treatment_kde_obj(x_range)

        return {
            'baseline_kde': {
                'x': x_range.tolist(),
                'density': baseline_density.tolist()
            },
            'treatment_kde': {
                'x': x_range.tolist(),
                'density': treatment_density.tolist()
            },
            'metric': metric
        }
    except Exception as e:
        return {'error': str(e), 'metric': metric}


def comparison_table(baseline: np.ndarray, treatment: np.ndarray,
                    metric: str, better: str = 'lower',
                    digits: int = 5) -> dict[str, Any]:
    """
    Generate a comparison table with summary statistics and statistical tests.

    Args:
        baseline: Baseline measurements
        treatment: Treatment measurements
        metric: Name of metric being compared
        better: 'lower' or 'higher' (which direction is improvement)
        digits: Number of decimal places for rounding

    Returns:
        Dictionary with comparison statistics
    """
    from .distribution import compute_summary

    baseline_clean = baseline[~np.isnan(baseline)]
    treatment_clean = treatment[~np.isnan(treatment)]

    # Compute summary statistics
    baseline_summary = compute_summary(baseline_clean, digits=digits)
    treatment_summary = compute_summary(treatment_clean, digits=digits)

    # Perform Mann-Whitney test
    mw_result = mann_whitney_test(baseline_clean, treatment_clean)

    # Compute median difference and percent change
    baseline_median = baseline_summary['median']
    treatment_median = treatment_summary['median']
    median_diff = treatment_median - baseline_median
    pct_change = (median_diff / baseline_median * 100) if baseline_median != 0 else np.nan

    # Determine if improvement
    if better == 'lower':
        improved = median_diff < 0
    else:
        improved = median_diff > 0

    # Create comparison table
    data = {
        'metric': metric,
        'baseline_n': baseline_summary['n'],
        'baseline_median': baseline_summary['median'],
        'baseline_mean': baseline_summary['mean'],
        'baseline_stddev': baseline_summary['stddev'],
        'treatment_n': treatment_summary['n'],
        'treatment_median': treatment_summary['median'],
        'treatment_mean': treatment_summary['mean'],
        'treatment_stddev': treatment_summary['stddev'],
        'median_diff': round(median_diff, digits),
        'pct_change': round(pct_change, 2) if not np.isnan(pct_change) else np.nan,
        'improved': improved,
        'mann_whitney_u': mw_result.get('statistic', np.nan),
        'p_value': mw_result.get('p_value', np.nan),
        'effect_size': mw_result.get('effect_size', np.nan)
    }

    return data
