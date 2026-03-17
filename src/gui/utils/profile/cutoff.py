"""
Cutoff computation and management utilities for profile workflow.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Callable, Tuple
import numpy as np
from scipy import stats
import polars as pl

from src.core.stats.distribution import _is_unimodal, _is_amodal, _find_modes
from .tree import search_for_cutoff


def suggest_cutoff(x: np.ndarray) -> float:
    """
    Suggest an initial cutoff point for classification based on distribution shape.

    Logic mirrors R implementation:
    - Very small samples (<=5): return median
    - Unimodal or amodal:
      - If left-skewed (skew <= -0.5): return 25th percentile
      - If right-skewed (skew >= 0.5): return 75th percentile
      - If symmetric: return first mode
    - Multimodal: return midpoint between two largest modes

    Args:
        x: 1D array of numeric values

    Returns:
        Suggested cutoff value
    """
    x_clean = x[~np.isnan(x)]

    if len(x_clean) <= 5:
        return float(np.median(x_clean))

    # Determine distribution shape
    if _is_unimodal(x_clean) or _is_amodal(x_clean):
        try:
            skewness = stats.skew(x_clean)
        except Exception:
            return float(np.median(x_clean))

        if np.isnan(skewness):
            return float(np.median(x_clean))

        if skewness <= -0.5:  # Left-tailed
            return float(np.percentile(x_clean, 25))
        elif skewness >= 0.5:  # Right-tailed
            return float(np.percentile(x_clean, 75))
        else:  # Symmetric distribution
            modes = _find_modes(x_clean)
            return float(modes[0]) if modes else float(np.median(x_clean))
    else:  # Multimodal: midpoint between two largest modes
        modes = _find_modes(x_clean)
        if len(modes) >= 2:
            return (modes[0] + modes[1]) / 2
        else:
            return float(np.median(x_clean))


def compute_cutoff_from_data(data: pl.DataFrame, metric_col: str | None = None) -> float | None:
    """
    Compute suggested cutoff for a given metric in profiling data.

    Args:
        data: Polars dataframe with profiling data
        metric_col: Column name to use. Must be provided and valid.

    Returns:
        Suggested cutoff value, or None if unable to compute
    """
    if data is None or data.is_empty():
        return None

    # Require metric_col to be explicitly provided and non-empty
    if not metric_col or metric_col.strip() == "":
        return None

    # Verify metric_col exists in data
    if metric_col not in data.columns:
        return None

    values = data[metric_col].drop_nulls().to_numpy()
    if len(values) < 2:
        return None

    try:
        return suggest_cutoff(values)
    except Exception:
        return None


def compute_suggested_cutoff(data: pl.DataFrame, metric_col: str) -> float | None:
    """
    Compute suggested cutoff from data distribution.

    Args:
        data: Polars DataFrame with metric data
        metric_col: Name of the metric column

    Returns:
        Suggested cutoff value, or None if cannot be computed
    """
    if data is None or data.is_empty():
        return None

    if not metric_col or metric_col.strip() == "":
        return None

    if metric_col not in data.columns:
        return None

    try:
        cutoff = compute_cutoff_from_data(data, metric_col)
        return cutoff
    except Exception:
        return None


def validate_cutoff_range(
    data: pl.DataFrame,
    metric_col: str,
    cutoff: float
) -> tuple[int, int]:
    """
    Check how many points fall below and above the cutoff.

    Args:
        data: Polars DataFrame with metric data
        metric_col: Name of the metric column
        cutoff: Cutoff value to validate

    Returns:
        Tuple of (n_below, n_above) where:
        - n_below: number of points <= cutoff
        - n_above: number of points > cutoff
        Returns (0, 0) if data is invalid
    """
    if data is None or data.is_empty():
        return (0, 0)

    if not metric_col or metric_col not in data.columns:
        return (0, 0)

    if cutoff is None:
        return (0, 0)

    try:
        metric_values = data[metric_col].drop_nulls()
        if len(metric_values) == 0:
            return (0, 0)

        n_below = int((metric_values <= cutoff).sum())
        n_above = int((metric_values > cutoff).sum())

        return (n_below, n_above)

    except Exception:
        return (0, 0)


def search_optimal_cutoff(
    data: pl.DataFrame,
    metric_col: str,
    exclusions: list[str],
    max_search_points: int = 100,
    progress_callback: Callable[[float, str], None] | None = None
) -> float | None:
    """
    Search for optimal cutoff point that minimizes decision tree AIC.

    Args:
        data: Polars DataFrame containing the data
        metric_col: Name of the metric column to use for classification
        exclusions: List of predictor names to exclude from the tree
        max_search_points: Maximum number of cutoff points to search
        progress_callback: Optional callback function(progress_pct: float, detail: str)

    Returns:
        Optimal cutoff value, or None if no valid trees found
    """
    if data is None or data.is_empty():
        return None

    if not metric_col or metric_col.strip() == "":
        return None

    if metric_col not in data.columns:
        return None

    if exclusions is None:
        exclusions = []

    try:
        return search_for_cutoff(
            data,
            metric_col,
            exclusions,
            max_search_points=max_search_points,
            progress_callback=progress_callback
        )
    except Exception:
        import traceback
        traceback.print_exc()
        return None
