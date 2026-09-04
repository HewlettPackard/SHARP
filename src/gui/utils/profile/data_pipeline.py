"""Data pipeline computations for the Profile module.

Contains the metric-independent and metric-dependent data reduction logic
that powers the reactive pipeline in profile.py:

    base_data → cleaned_columns (C1+C2) → reduced_data (C3)

These are pure computation functions. The reactive wiring (Shiny
``@reactive.Calc``) stays in ``profile.py`` and calls into this module.
"""

from typing import Any

import polars as pl

from src.core.profile.data_reduction import (
    reduce_columns_dependent,
    reduce_columns_independent,
)
from src.core.profile import predictor_selection
from src.gui.utils.profile.predictor_stats import get_auto_excluded_predictors


def compute_cleaned_columns(data: pl.DataFrame, settings: Any | None = None) -> list[str]:
    """Metric-independent column cleaning (C1 + C2).

    Wrapper around ``reduce_columns_independent`` for the reactive pipeline.
    Preserves timestamp column if configured in settings.
    """
    cleaned = reduce_columns_independent(data)

    # Ensure timestamp column from settings is preserved if present in data
    if settings is not None:
        timestamp_col = settings.get("profiling.lag_detection.timestamp_column", None)
        if isinstance(timestamp_col, str) and timestamp_col in data.columns:
            if timestamp_col not in cleaned:
                cleaned = list(cleaned) + [timestamp_col]

    return cleaned


def compute_reduced_columns(
    data: pl.DataFrame,
    metric: str,
    cleaned_cols: list[str],
    outcome_correlations: dict[str, float],
) -> list[str]:
    """Metric-dependent column reduction (C3).

    Args:
        data: Active (possibly filtered) DataFrame
        metric: Outcome metric column name
        cleaned_cols: C1+C2 survivor column names
        outcome_correlations: ``{col: |corr_with_metric|}``

    Returns:
        List of surviving column names after C3
    """
    candidate_cols = [c for c in cleaned_cols if c != metric and c in outcome_correlations]
    return reduce_columns_dependent(
        data, metric, candidate_cols, outcome_correlations,
    )


def compute_outcome_correlations(
    data: pl.DataFrame,
    metric_col: str,
    cleaned_cols: list[str],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Compute outcome correlations for the predictor exclusion pipeline.

    Returns the correlations dict and the stats rows list.

    Args:
        data: Active DataFrame
        metric_col: Outcome metric column name
        cleaned_cols: C1+C2 survivor columns

    Returns:
        (correlations, stats_rows) where correlations maps column names to
        ``|correlation|`` and stats_rows is a list of dicts suitable for the
        predictor exclusion table.
    """
    exclude_cols = {metric_col, "start", "task"}
    if cleaned_cols:
        candidate_cols = [c for c in cleaned_cols if c not in exclude_cols]
    else:
        candidate_cols = [c for c in data.columns if c not in exclude_cols]

    # Batch compute n_unique for candidates only
    n_unique_expr = [pl.col(c).n_unique().alias(c) for c in candidate_cols]
    n_unique_counts = data.select(n_unique_expr).row(0)

    # Filter to columns with n_unique > 1
    potential_predictors = [
        col for col, n_uniq in zip(candidate_cols, n_unique_counts) if n_uniq > 1
    ]

    # Pre-filter DataFrame to only cleaned columns + metric to avoid
    # variance filter scanning all 28K columns
    keep_cols = [metric_col] + potential_predictors
    filtered_data = data.select([c for c in data.columns if c in keep_cols])

    # Only exclude special columns (start, task) since we've already filtered
    # to potential predictors
    exclude_for_correlations = ["start", "task"]

    correlations = predictor_selection.compute_predictor_correlations(
        filtered_data, metric_col, exclude_for_correlations
    )

    stats_rows = [
        {
            "name": pred_name,
            "non_na_count": data[pred_name].drop_nulls().len(),
            "correlation": float(correlation),
        }
        for pred_name, correlation in correlations.items()
    ]

    return correlations, stats_rows


def apply_auto_exclusions(
    stats_rows: list[dict[str, Any]],
    current_exclusions: set[str],
    modal_filters: dict[str, Any] | None,
    settings: Any | None = None,
) -> set[str] | None:
    """Compute auto-exclusions from predictor stats.

    Returns the updated exclusion set if it changed, or None if no update
    is needed (e.g. user has already applied manual filters).
    """
    user_has_applied = (modal_filters or {}).get("user_has_applied", False)
    if user_has_applied:
        return None

    max_correlation = (modal_filters or {}).get("max_corr")
    if max_correlation is None:
        if settings is None:
            from src.core.config.settings import Settings
            settings = Settings()
        max_correlation = settings.get("profiling.max_correlation", 0.99)

    auto_excluded = get_auto_excluded_predictors(stats_rows, max_correlation)
    new_exclusions = current_exclusions | auto_excluded

    if new_exclusions != current_exclusions:
        return new_exclusions
    return None
