"""
Data reduction utilities for profiling analysis.

Implements column and row filtering strategies to reduce dataset size
and focus analysis on relevant, non-redundant predictors.

Strategies:
- C1: Adaptive column completeness gate
- C2: Near-zero variance filter
- C3: Outcome-relevance gate
- C4: Conditional mutual information screening
- R1-R3: Row filtering strategies

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from typing import Optional

import polars as pl
from sklearn.feature_selection import mutual_info_regression

from src.core.config.settings import Settings


# ============================================================================
# Column Reduction Strategies (C1-C4)
# ============================================================================

def filter_by_completeness_adaptive(
    data: pl.DataFrame,
    outcome_col: str,
    min_absolute_non_null: int = 30,
    max_null_percentile: float = 0.05,
    preserve_outcome_aligned_sparse: bool = True,
) -> list[str]:
    """C1: Drop columns that are too sparse to be useful.

    Uses absolute minimum + percentile-based approach:
    - Any column with <min_absolute_non_null observations → drop.
    - Columns in the bottom max_null_percentile by null % → drop.
    - Exception: columns aligned with outcome are preserved.

    This adapts automatically to multi-host vs single-host data
    without requiring source metadata.

    Args:
        data: DataFrame to filter
        outcome_col: Name of outcome column
        min_absolute_non_null: Minimum non-null values required in a column
        max_null_percentile: Drop columns in bottom N% by null fraction
        preserve_outcome_aligned_sparse: Preserve sparse columns that appear with outcome

    Returns:
        List of column names to keep
    """
    survivors: list[str] = []
    n_rows = data.height

    if n_rows == 0:
        return survivors

    # Compute null counts in a single pass
    null_counts = data.null_count().row(0)
    null_fracs = [null_count / n_rows for null_count in null_counts]

    # Percentile-based threshold
    fracs = sorted(null_fracs)
    threshold_idx = max(0, int(len(fracs) * max_null_percentile))
    threshold = fracs[threshold_idx] if threshold_idx < len(fracs) else 1.0

    # Identify columns needing outcome-aligned check
    columns_for_alignment = []
    if preserve_outcome_aligned_sparse and outcome_col in data.columns:
        outcome_valid = pl.col(outcome_col).is_not_null()

    # Filter columns
    for col, null_count, null_frac in zip(data.columns, null_counts, null_fracs):
        n_non_null = n_rows - null_count

        # Absolute minimum check
        if n_non_null < min_absolute_non_null:
            continue

        # Percentile gate
        if null_frac <= threshold:
            survivors.append(col)
            continue

        # Exception: sparse but outcome-aligned
        if preserve_outcome_aligned_sparse and outcome_col in data.columns:
            columns_for_alignment.append(col)

    if preserve_outcome_aligned_sparse and outcome_col in data.columns and columns_for_alignment:
        aligned_expr = [
            (pl.col(col).is_not_null() & outcome_valid).sum().alias(col)
            for col in columns_for_alignment
        ]
        aligned_counts = data.select(aligned_expr).row(0)
        for col, count in zip(columns_for_alignment, aligned_counts):
            if count > 0:
                survivors.append(col)

    return survivors


def filter_near_zero_variance(
    data: pl.DataFrame,
    columns: list[str],
    max_constant_fraction: float = 0.95,
) -> list[str]:
    """C2: Remove columns where >95% of non-null values are identical.

    These are effectively constant and cannot be informative predictors.
    Handles both numeric and categorical columns.

    Args:
        data: DataFrame containing the columns
        columns: Column names to evaluate
        max_constant_fraction: Drop columns where mode fraction >= this

    Returns:
        List of column names to keep
    """
    survivors = []
    for col in columns:
        # Get non-null values
        non_null = data[col].drop_nulls()
        if non_null.len() == 0:
            continue

        # Compute mode (most frequent value)
        value_counts = non_null.value_counts().sort("count", descending=True)
        if value_counts.height == 0:
            continue
        mode_count = value_counts["count"][0]
        mode_frac = mode_count / non_null.len()

        # Keep if not too constant
        if mode_frac < max_constant_fraction:
            survivors.append(col)

    return survivors


def filter_by_outcome_relevance(
    correlations: dict[str, float],
    min_abs_correlation: float = 0.05,
) -> list[str]:
    """C3: Drop columns with negligible outcome association.

    If |r| < 0.05, the column explains <0.25% of outcome variance
    and cannot be a meaningful causal factor.

    Args:
        correlations: Dictionary mapping column names to outcome correlations
        min_abs_correlation: Drop columns with |r| < this threshold

    Returns:
        List of column names to keep
    """
    return [
        col for col, corr in correlations.items()
        if abs(corr) >= min_abs_correlation
    ]


def select_by_mutual_information(
    data: pl.DataFrame,
    outcome_col: str,
    candidates: list[str],
    n_select: int = 300,
    n_neighbors: int = 5,
) -> list[str]:
    """C4: Select top-N columns by mutual information with outcome.

    Uses sklearn's mutual_info_regression (Kraskov k-NN estimator).
    Name-free: works regardless of column naming conventions.
    Captures non-linear associations better than correlation.

    Args:
        data: DataFrame containing the columns
        outcome_col: Name of outcome column
        candidates: Column names to evaluate
        n_select: Number of top columns to return
        n_neighbors: Number of neighbors for MI estimation

    Returns:
        List of top-N column names by mutual information
    """
    try:
        # Extract outcomes
        y = data[outcome_col].drop_nulls().to_numpy()
        if len(y) == 0:
            return candidates[:n_select]

        # Extract features for candidates, keeping rows aligned with non-null outcomes
        outcome_mask = data[outcome_col].is_not_null()
        X_list = []
        for col in candidates:
            col_data = data[col]
            # Align with outcome non-nulls
            aligned = col_data.filter(outcome_mask)
            X_list.append(aligned.to_numpy().reshape(-1, 1))

        # Stack features
        if not X_list:
            return candidates[:n_select]

        X = pl.concat([pl.DataFrame({})] + [
            pl.DataFrame({col: X_list[i][:, 0]})
            for i, col in enumerate(candidates)
        ]).drop_nulls().to_numpy()

        # Compute mutual information
        mi_scores = mutual_info_regression(
            X, y[:len(X)], n_neighbors=min(n_neighbors, len(X) - 1), random_state=42
        )

        # Rank by MI
        ranked = sorted(zip(candidates, mi_scores), key=lambda x: -x[1])
        return [col for col, _ in ranked[:n_select]]

    except Exception:
        # Fallback if MI estimation fails
        return candidates[:n_select]


# ============================================================================
# Staged Column Reduction (for reactive GUI pipeline)
# ============================================================================

def reduce_columns_independent(
    data: pl.DataFrame,
    settings: Optional[Settings] = None,
) -> list[str]:
    """Apply metric-independent column reduction (C1 + C2).

    Suitable for one-time cleaning at data load time. Does not require
    knowledge of the outcome metric.

    Strategies applied:
    - C1: Adaptive completeness gate (without outcome-aligned sparse preservation)
    - C2: Near-zero variance filter

    Args:
        data: Raw DataFrame with many columns
        settings: Settings object for configuration

    Returns:
        List of surviving column names after C1 + C2
    """
    if settings is None:
        settings = Settings()

    if not settings.get("profiling.data_reduction.enabled", True):
        return list(data.columns)

    max_cols_without_reduction = settings.get(
        "profiling.data_reduction.max_columns_without_reduction", 500
    )
    if data.width <= max_cols_without_reduction:
        return list(data.columns)

    min_absolute_non_null = settings.get(
        "profiling.data_reduction.c1_min_absolute_non_null", 30
    )
    max_null_percentile = settings.get(
        "profiling.data_reduction.c1_max_null_percentile", 0.05
    )
    max_constant_fraction = settings.get(
        "profiling.data_reduction.c2_max_constant_fraction", 0.95
    )

    # C1: Completeness gate (metric-independent — no outcome alignment)
    cols_after_c1 = filter_by_completeness_adaptive(
        data, outcome_col="",
        min_absolute_non_null=min_absolute_non_null,
        max_null_percentile=max_null_percentile,
        preserve_outcome_aligned_sparse=False,
    )

    # C2: Near-zero variance
    cols_after_c2 = filter_near_zero_variance(
        data, cols_after_c1,
        max_constant_fraction=max_constant_fraction,
    )

    return cols_after_c2


def reduce_columns_dependent(
    data: pl.DataFrame,
    outcome_col: str,
    candidate_cols: list[str],
    correlations: dict[str, float],
    settings: Optional[Settings] = None,
) -> list[str]:
    """Apply metric-dependent column reduction (C3, optional C4).

    Requires outcome metric and precomputed correlations. Suitable for
    re-running when the outcome metric or filter changes.

    Strategies applied:
    - C3: Outcome-relevance gate (drop columns with negligible correlation)
    - C4: (Optional) Mutual information screening

    Args:
        data: DataFrame (may be pre-cleaned by reduce_columns_independent)
        outcome_col: Name of outcome column
        candidate_cols: Column names to evaluate (typically C1+C2 survivors)
        correlations: Precomputed correlations {col_name: abs_correlation}
        settings: Settings object for configuration

    Returns:
        List of surviving column names after C3 (+ optional C4)
    """
    if settings is None:
        settings = Settings()

    if not settings.get("profiling.data_reduction.enabled", True):
        return list(candidate_cols)

    min_outcome_correlation = settings.get(
        "profiling.data_reduction.c3_min_abs_correlation", 0.05
    )
    use_mi_screening = settings.get(
        "profiling.data_reduction.c4_use_mutual_information", False
    )
    mi_n_select = settings.get(
        "profiling.data_reduction.c4_n_select", 300
    )

    # C3: Outcome relevance
    relevant_correlations = {c: correlations[c] for c in candidate_cols if c in correlations}
    cols_after_c3 = filter_by_outcome_relevance(
        relevant_correlations, min_abs_correlation=min_outcome_correlation
    )

    # C4: Mutual information screening (optional)
    if use_mi_screening:
        cols_final = select_by_mutual_information(
            data, outcome_col, cols_after_c3,
            n_select=mi_n_select,
        )
    else:
        cols_final = cols_after_c3

    return cols_final


def reduce_columns(
    data: pl.DataFrame,
    outcome_col: str,
    settings: Optional[Settings] = None,
) -> list[str]:
    """Pipeline: Apply C1-C4 column reduction strategies in order.

    Reduces from 40K raw columns to ~30-80 outcome-relevant predictors.

    Args:
        data: Raw DataFrame with many columns
        outcome_col: Name of outcome column (must exist in data)
        settings: Settings object for configuration

    Returns:
        List of surviving column names after all reductions
    """
    if settings is None:
        settings = Settings()

    if not settings.get("profiling.data_reduction.enabled", True):
        return [c for c in data.columns if c != outcome_col]

    max_cols_without_reduction = settings.get(
        "profiling.data_reduction.max_columns_without_reduction", 500
    )
    if data.width <= max_cols_without_reduction:
        return [c for c in data.columns if c != outcome_col]

    # Phase 1: metric-independent (C1 + C2)
    cols_after_c2 = reduce_columns_independent(data, settings)

    # Exclude outcome from predictor candidates
    predictor_cols = [c for c in cols_after_c2 if c != outcome_col]

    # Compute correlations for metric-dependent reduction
    correlations = {}
    for col in predictor_cols:
        try:
            corr = data.select(pl.corr(col, outcome_col)).item()
            if corr is not None and corr == corr:  # NaN != NaN
                correlations[col] = abs(corr)
            else:
                correlations[col] = 0.0
        except Exception:
            correlations[col] = 0.0

    # Phase 2: metric-dependent (C3 + optional C4)
    cols_final = reduce_columns_dependent(
        data, outcome_col, predictor_cols, correlations, settings
    )
    return cols_final


# ============================================================================
# Row Reduction Strategies (R1-R3)
# ============================================================================

def filter_relevant_rows(
    data: pl.DataFrame,
    outcome_col: str,
    predictor_cols: list[str],
) -> pl.DataFrame:
    """R3: Drop rows with neither outcome nor any predictor values.

    Allow rows with:
    - Outcome but no predictors (predictors may appear at earlier lags)
    - Predictors but no outcome (outcome may appear at later lags)
    Only drop rows where you have no relevant data whatsoever.

    This preserves time-lagged associations: X(t) → Y(t+lag).

    Args:
        data: DataFrame to filter
        outcome_col: Name of outcome column
        predictor_cols: Names of predictor columns that survived column reduction (C1-C4)

    Returns:
        Filtered DataFrame (rows with at least outcome or any predictor)
    """
    if not predictor_cols:
        # No predictors to check, keep rows with outcome
        return data.filter(pl.col(outcome_col).is_not_null())

    # Keep rows where: outcome is non-null OR at least one predictor is non-null
    has_outcome = pl.col(outcome_col).is_not_null()
    has_any_predictor = pl.any_horizontal(
        pl.col(c).is_not_null() for c in predictor_cols
    )
    return data.filter(has_outcome | has_any_predictor)


def filter_uninformative_rows(
    data: pl.DataFrame,
    outcome_col: str | None = None,
    predictor_cols: list[str] | None = None,
) -> pl.DataFrame:
    """R1: Drop rows that are completely empty across all columns.

    Removes rows where every single column is null. This is outcome-agnostic
    and can be applied at load time before the user chooses an outcome metric.

    Args:
        data: DataFrame to filter
        outcome_col: Ignored (kept for API compatibility during pipeline calls)
        predictor_cols: Ignored (kept for API compatibility during pipeline calls)

    Returns:
        Filtered DataFrame with at least one non-null value per row
    """
    # Use sum_horizontal for efficient row-wise sum (optimized for many columns)
    non_null_counts = data.select(
        pl.sum_horizontal([pl.col(c).is_not_null() for c in data.columns]).alias("non_null_count")
    )["non_null_count"]
    return data.filter(non_null_counts > 0)


def filter_steady_state(
    data: pl.DataFrame,
    outcome_col: str,
    warmup_fraction: Optional[float] = None,
    use_changepoints: bool = False,
) -> pl.DataFrame:
    """R2: Exclude warmup/cooldown rows from causal analysis.

    Warmup and cooldown rows exhibit transient behavior that follows
    different causal mechanisms than steady-state.

    Args:
        data: DataFrame to filter
        outcome_col: Name of outcome column (used for changepoint detection)
        warmup_fraction: Fraction of rows to skip (0.0-1.0). If None, use changepoint detection.
        use_changepoints: If True, auto-detect warmup via changepoint detection

    Returns:
        Filtered DataFrame (steady-state rows only)
    """
    if warmup_fraction is not None:
        n_skip = int(len(data) * warmup_fraction)
        if n_skip >= len(data):
            return data
        return data.slice(n_skip)

    if use_changepoints:
        try:
            # Simple changepoint detection: look for largest drop in outcome metric
            # This is a placeholder; real implementation would use ruptures or similar
            outcome_vals = data[outcome_col].drop_nulls().to_numpy()
            if len(outcome_vals) < 10:
                return data
            # For now, just skip first 10% if changepoints is requested
            n_skip = len(outcome_vals) // 10
            return data.slice(n_skip)
        except Exception:
            return data

    return data


def reduce_rows(
    data: pl.DataFrame,
    outcome_col: str,
    predictor_cols: list[str],
    settings: Optional[Settings] = None,
) -> pl.DataFrame:
    """Pipeline: Apply R1, R2, then R3 row reduction strategies in order.

    R1 (completely empty rows): outcome-agnostic, always safe
    R2 (warmup/cooldown): independent of outcome selection
    R3 (row relevance): uses the actual predictor set from the analyzer

    Args:
        data: DataFrame to filter
        outcome_col: Name of outcome column
        predictor_cols: Names of predictor columns that will be used in analysis.
                       Should be the final selected set after correlation filtering,
                       max_predictors limits, exclusions, etc. from the factor analyzer.
        settings: Settings object for configuration

    Returns:
        Filtered DataFrame after row reduction
    """
    if settings is None:
        settings = Settings()

    if not settings.get("profiling.data_reduction.enabled", True):
        return data

    # R1: Completely empty rows (outcome-agnostic, always safe, fast)
    # Always run this regardless of dataset size
    data = filter_uninformative_rows(data)

    # Skip remaining reduction (R2, R3) if data is small
    max_rows_without_reduction = settings.get(
        "profiling.data_reduction.max_rows_without_reduction", 50000
    )
    if data.height <= max_rows_without_reduction:
        return data

    # R2: Warmup/cooldown (optional, independent of outcome/predictors)
    use_warmup_filter = settings.get(
        "profiling.data_reduction.r2_exclude_warmup", False
    )
    if use_warmup_filter:
        warmup_fraction = settings.get(
            "profiling.data_reduction.r2_warmup_fraction", None
        )
        use_changepoints = settings.get(
            "profiling.data_reduction.r2_use_changepoints", False
        )
        data = filter_steady_state(
            data, outcome_col,
            warmup_fraction=warmup_fraction,
            use_changepoints=use_changepoints,
        )

    # R3: Keep rows with outcome or selected predictor values (supports lag detection)
    # Uses only the predictors that will actually be in the analysis, not all columns
    if predictor_cols:
        data = filter_relevant_rows(data, outcome_col, predictor_cols)

    return data
