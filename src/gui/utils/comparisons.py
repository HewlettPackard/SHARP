"""
Comparison utilities for GUI.

Provides reusable functions for comparing two datasets with plots and tables.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any

from src.core.stats.distribution import compute_summary
from src.core.stats.comparisons import density_comparison, ecdf_comparison
from src.core.stats.narrative import format_sig_figs


def _compute_pct_change(baseline_val: float, treatment_val: float) -> tuple:
    """
    Compute percentage change, handling special cases.

    Args:
        baseline_val: Baseline measurement
        treatment_val: Treatment measurement

    Returns:
        Tuple of (pct_change_str, raw_pct_change_or_none)
    """
    if baseline_val == 0:
        # Avoid division by zero
        pct_str = '∞' if treatment_val != 0 else '0%'
        return (pct_str, None)
    else:
        pct_change = ((treatment_val - baseline_val) / baseline_val) * 100
        return (f"{pct_change:+.1f}%", pct_change)


def compute_comparison_summary(baseline: np.ndarray, treatment: np.ndarray,
                               digits: int = 10, sig_figs: int = 3) -> Dict[str, Any]:
    """
    Compute summary statistics for baseline and treatment datasets.

    Args:
        baseline: Baseline measurements
        treatment: Treatment measurements
        digits: Number of decimal places for rounding
        sig_figs: Number of significant figures for display (default: 3)

    Returns:
        Dictionary with 'statistic_names', 'baseline', 'treatment', and 'pct_change' arrays
    """
    b_summary = compute_summary(baseline, digits=digits)
    t_summary = compute_summary(treatment, digits=digits)

    # Return in a format ready for table display
    statistic_names = [
        'n', 'min', 'median', 'mode', 'mean',
        'CI95_low', 'CI95_high', 'p95', 'p99', 'max',
        'stddev', 'stderr', 'cv'
    ]

    # Compute coefficient of variance (CV = stddev / mean)
    b_cv = b_summary['stddev'] / b_summary['mean'] if b_summary['mean'] != 0 else np.nan
    t_cv = t_summary['stddev'] / t_summary['mean'] if t_summary['mean'] != 0 else np.nan

    # Calculate percentage change for each statistic
    baseline_vals = []
    treatment_vals = []
    pct_changes = []

    for name in statistic_names:
        if name == 'cv':
            b_val = b_cv
            t_val = t_cv
        else:
            b_val = b_summary[name]
            t_val = t_summary[name]

        # 'n' should be displayed as integer
        is_int = (name == 'n')
        baseline_vals.append(format_sig_figs(b_val, sig_figs, is_integer=is_int))
        treatment_vals.append(format_sig_figs(t_val, sig_figs, is_integer=is_int))

        # Compute percentage change
        if name == 'n':
            # For sample size, show dash instead of percentage
            pct_changes.append('-')
        elif name == 'cv' and (np.isnan(b_cv) or np.isnan(t_cv)):
            # CV may be NaN if mean is zero
            pct_changes.append('NA')
        else:
            pct_str, _ = _compute_pct_change(b_val, t_val)
            pct_changes.append(pct_str)

    return {
        'statistic_names': statistic_names,
        'baseline': baseline_vals,
        'treatment': treatment_vals,
        'pct_change': pct_changes
    }


def render_density_comparison_plot(baseline: np.ndarray, treatment: np.ndarray,
                                   metric: str):
    """
    Create matplotlib figure comparing density distributions.

    Args:
        baseline: Baseline measurements
        treatment: Treatment measurements
        metric: Name of metric being compared

    Returns:
        Matplotlib figure or None if error
    """
    try:
        result = density_comparison(baseline, treatment, metric=metric)

        if 'error' in result:
            return None

        # Create matplotlib figure from dict data
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(result['baseline_kde']['x'], result['baseline_kde']['density'],
               label='Baseline', linewidth=2)
        ax.plot(result['treatment_kde']['x'], result['treatment_kde']['density'],
               label='Treatment', linewidth=2)
        ax.set_xlabel('Value')
        ax.set_ylabel('Density')
        ax.set_title(f'Density Comparison: {metric}')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout(pad=1.0)
        fig.subplots_adjust(left=0.12, right=0.95, top=0.92, bottom=0.12)
        return fig
    except Exception as e:
        print(f'Error creating density plot: {e}')
        import traceback
        traceback.print_exc()
        return None


def render_ecdf_comparison_plot(baseline: np.ndarray, treatment: np.ndarray,
                                metric: str):
    """
    Create matplotlib figure comparing ECDF distributions.

    Args:
        baseline: Baseline measurements
        treatment: Treatment measurements
        metric: Name of metric being compared

    Returns:
        Matplotlib figure or None if error
    """
    try:
        result = ecdf_comparison(baseline, treatment, metric=metric)

        if 'error' in result:
            return None

        # Create matplotlib figure from dict data
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.step(result['baseline_ecdf']['values'], result['baseline_ecdf']['cumprob'],
               label='Baseline', where='post', linewidth=2)
        ax.step(result['treatment_ecdf']['values'], result['treatment_ecdf']['cumprob'],
               label='Treatment', where='post', linewidth=2)
        ax.set_xlabel('Value')
        ax.set_ylabel('Cumulative Probability')
        ax.set_title(f'ECDF Comparison: {metric}')
        if result.get('ks_p_value') is not None:
            ax.text(0.05, 0.95, f"KS p-value: {result['ks_p_value']:.4f}",
                   transform=ax.transAxes, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout(pad=1.0)
        fig.subplots_adjust(left=0.12, right=0.95, top=0.92, bottom=0.12)
        return fig
    except Exception as e:
        print(f'Error creating ECDF plot: {e}')
        import traceback
        traceback.print_exc()
        return None
