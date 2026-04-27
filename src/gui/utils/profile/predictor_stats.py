"""
Predictor statistics utilities for performance profiling.

Provides functions for computing statistics about potential predictors,
including correlation with outcome metrics and non-null counts.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any
import numpy as np
import polars as pl

from src.core.profile import predictor_selection


# Default predictors to exclude from tree training
DEFAULT_EXCLUDED_PREDICTORS = ["repeat", "inner_time", "outer_time", "perf_time"]


def compute_predictor_stats(
    data: pl.DataFrame,
    metric_col: str,
    predictor_list: list[str] | None = None
) -> list[dict[str, Any]]:
    """
    Compute statistics for potential predictors.

    Reuses correlation computation from core predictor_selection module.
    This ensures correlations are computed once and consistently.

    Args:
        data: Polars DataFrame containing the data
        metric_col: Name of the outcome metric column
        predictor_list: Optional list of predictor names. If None, uses all columns.

    Returns:
        List of dicts with keys: name, non_na_count, correlation
    """
    if data is None or data.is_empty() or metric_col not in data.columns:
        return []

    # Build exclude list from all columns not in predictor_list
    if predictor_list is not None:
        exclude = [c for c in data.columns if c != metric_col and c not in predictor_list]
    else:
        exclude = []

    # Compute correlations using core module (single source of truth)
    correlations = predictor_selection.compute_predictor_correlations(
        data, metric_col, exclude
    )

    # Format as stats rows for GUI
    stats_rows = []
    for pred_name, correlation in correlations.items():
        stats_rows.append({
            "name": pred_name,
            "non_na_count": data[pred_name].drop_nulls().len(),
            "correlation": float(correlation),
        })

    return stats_rows


def filter_predictors_by_correlation(
    stats_rows: list[dict[str, Any]],
    max_correlation: float = 0.99,
    max_predictors: int = 100,
    search: str = ""
) -> list[dict[str, Any]]:
    """
    Filter and sort predictor stats by correlation and other criteria.

    Args:
        stats_rows: List of predictor statistics dictionaries
        max_correlation: Maximum correlation threshold (exclude >= this)
        max_predictors: Maximum number of predictors to return
        search: Search term to filter predictor names

    Returns:
        Filtered and sorted list of predictor stats
    """
    filtered = list(stats_rows)

    # Sort by absolute correlation, descending, with NAs last
    filtered.sort(
        key=lambda r: abs(r["correlation"]) if r["correlation"] is not None and not np.isnan(r["correlation"]) else -1,
        reverse=True
    )

    # Apply search filter
    if search:
        search_lower = search.lower()
        filtered = [r for r in filtered if search_lower in r["name"].lower()]

    # Apply max_correlation filter
    def _filter_by_max_corr(r: dict[str, Any]) -> bool:
        corr = r.get("correlation")
        if corr is None or np.isnan(corr):
            return True
        return float(abs(corr)) < max_correlation

    filtered = [r for r in filtered if _filter_by_max_corr(r)]

    # Limit number
    if len(filtered) > max_predictors:
        filtered = filtered[:max_predictors]

    return filtered


def get_auto_excluded_predictors(
    stats_rows: list[dict[str, Any]],
    max_correlation: float = 0.99
) -> set[str]:
    """
    Get predictors that should be auto-excluded based on correlation threshold.

    Args:
        stats_rows: List of predictor statistics
        max_correlation: Maximum correlation threshold

    Returns:
        Set of predictor names to auto-exclude
    """
    auto_excluded = set()
    for stat in stats_rows:
        correlation = stat.get("correlation")
        if correlation is not None and not np.isnan(correlation) and abs(correlation) >= max_correlation:
            auto_excluded.add(stat["name"])
    return auto_excluded
