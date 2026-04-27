"""
Predictor selection utilities for classification models.

Provides hybrid predictor selection using variance filtering, correlation analysis,
and semantic grouping for diversity.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from collections import defaultdict
import re

import numpy as np
import polars as pl
import scipy.stats as ss

from src.core.config.settings import Settings


def compute_predictor_correlations(
    data: pl.DataFrame,
    metric_col: str,
    exclude: list[str] | None = None
) -> dict[str, float]:
    """Compute correlations for all viable predictors.

    This is the single source of truth for predictor correlations.
    Used by both model training (predictor selection) and GUI (exclusion dialog).

    Args:
        data: DataFrame containing potential predictors
        metric_col: Target metric column name
        exclude: Columns to exclude from consideration

    Returns:
        Dictionary mapping predictor names to absolute correlation values
    """
    if exclude is None:
        exclude = []

    try:
        # Filter by variance first (fast, eliminates useless predictors)
        numeric_cols, categorical_cols = _filter_by_variance(data, exclude, metric_col)

        # Compute correlations for all viable predictors
        correlations = _compute_correlations(
            data, metric_col, numeric_cols, categorical_cols
        )

        return correlations

    except Exception:
        import traceback
        traceback.print_exc()
        return {}


def select_predictors(
    data: pl.DataFrame,
    metric_col: str,
    exclude: list[str] | None = None,
    max_predictors: int = 100,
    max_correlation: float = 0.99
) -> list[str]:
    """Select best predictors using hybrid approach (vectorized + semantic grouping).

    Args:
        data: DataFrame containing potential predictors
        metric_col: Target metric column name
        exclude: Columns to exclude
        max_predictors: Maximum number to select
        max_correlation: Correlation threshold

    Returns:
        List of selected predictor column names
    """
    if exclude is None:
        exclude = []

    try:
        # Phase 1: Vectorized variance filter (separates numeric and categorical)
        numeric_cols, categorical_cols = _filter_by_variance(data, exclude, metric_col)

        total_cols = len(numeric_cols) + len(categorical_cols)
        if total_cols <= max_predictors:
            return numeric_cols + categorical_cols

        # Phase 2: Vectorized correlation computation
        correlations = _compute_correlations(
            data, metric_col, numeric_cols, categorical_cols
        )

        # Phase 3: Semantic grouping and representative selection
        return _select_top_predictors(correlations, max_predictors, max_correlation)

    except Exception:
        import traceback
        traceback.print_exc()
        return []


def select_predictors_from_labels(
    data: pl.DataFrame,
    labels: np.ndarray,
    exclude: list[str],
    max_predictors: int,
    max_correlation: float
) -> list[str]:
    """Select best predictors for predicting class labels (for classification training).

    When training a decision tree classifier, the target is a class label (e.g., 'FAST' or 'SLOW'),
    not a numeric outcome. This function converts those string labels to numeric proxies and uses
    them as a virtual "outcome metric" for predictor selection, allowing the same correlation-based
    selection logic to work for classification tasks.

    Use case: After classifying performance data into performance classes (via ClassSelector),
    use this function to select which predictors (e.g., CPU, memory metrics) best explain
    the difference between classes. The selected predictors then train the classifier.

    Args:
        data: DataFrame containing potential predictors
        labels: Array of class labels (strings like 'FAST'/'SLOW' or numeric)
        exclude: Columns to exclude from consideration
        max_predictors: Maximum number of predictors to return
        max_correlation: Correlation threshold for filtering

    Returns:
        List of selected predictor column names that best explain class membership
    """
    # Convert string labels to numeric for correlation computation
    if labels.dtype.kind in ('U', 'S', 'O'):  # Unicode, byte string, or object
        unique_labels = np.unique(labels)
        label_map = {label: i for i, label in enumerate(unique_labels)}
        numeric_labels = np.array([label_map[label] for label in labels], dtype=float)
    else:
        numeric_labels = labels.astype(float)

    # Create temporary metric column from numeric labels
    temp_data = data.with_columns([pl.Series("_temp_target", numeric_labels)])
    predictors = select_predictors(
        temp_data, "_temp_target", exclude, max_predictors, max_correlation
    )
    return [p for p in predictors if p != "_temp_target"]


def encode_features(
    data: pl.DataFrame,
    feature_cols: list[str]
) -> tuple[np.ndarray | None, list[str]]:
    """Encode features with one-hot encoding for categorical columns.

    Args:
        data: DataFrame containing features
        feature_cols: List of column names to encode

    Returns:
        Tuple of (encoded array, feature names)
    """
    try:
        X_parts = []
        feature_names = []

        for col in feature_cols:
            col_data = data[col]

            if col_data.dtype in [pl.Utf8, pl.Categorical]:
                # One-hot encode
                unique_cats = col_data.unique().drop_nulls().to_list()
                for cat in sorted(unique_cats):
                    indicator = (col_data == cat).cast(pl.Int32).to_numpy()
                    X_parts.append(indicator.reshape(-1, 1))
                    feature_names.append(f"{col}={cat}")
            elif col_data.dtype in [pl.Float64, pl.Int64, pl.Int32, pl.Int16, pl.Int8]:
                numeric_array = col_data.to_numpy().astype(np.float64)
                X_parts.append(numeric_array.reshape(-1, 1))
                feature_names.append(col)

        if not X_parts:
            return None, []

        result = np.hstack(X_parts) if len(X_parts) > 1 else X_parts[0]
        return result, feature_names

    except Exception:
        import traceback
        traceback.print_exc()
        return None, []


def _filter_by_variance(
    data: pl.DataFrame,
    exclude: list[str],
    metric_col: str
) -> tuple[list[str], list[str]]:
    """Filter columns to find predictors with variance.

    Returns:
        Tuple of (numeric_columns, categorical_columns) that have variance
    """
    max_categorical_unique = Settings().get(
        'profiling.predictor_selection.max_categorical_unique', 100
    )

    numeric_types = {
        pl.Float64, pl.Float32, pl.Int64, pl.Int32, pl.Int16, pl.Int8,
        pl.UInt64, pl.UInt32, pl.UInt16, pl.UInt8, pl.Boolean
    }

    numeric_cols = []
    categorical_cols = []

    for col in data.columns:
        if col in exclude or col == metric_col:
            continue

        if data[col].dtype in numeric_types:
            numeric_cols.append(col)
        elif data[col].dtype == pl.Utf8:
            try:
                n_unique = data[col].drop_nulls().n_unique()
                if 2 <= n_unique <= max_categorical_unique:
                    categorical_cols.append(col)
            except Exception:
                pass

    # Vectorized variance filter for numeric columns
    if numeric_cols:
        stds = data.select([pl.col(c).std().alias(c) for c in numeric_cols]).row(0)
        numeric_with_var = [
            col for col, std in zip(numeric_cols, stds)
            if std is not None and std > 0
        ]
    else:
        numeric_with_var = []

    return numeric_with_var, categorical_cols


def _compute_correlations(
    data: pl.DataFrame,
    metric_col: str,
    numeric_predictors: list[str],
    categorical_predictors: list[str]
) -> dict[str, float]:
    """Compute correlations using vectorized operations."""
    settings = Settings()
    chunk_size = settings.get('profiling.predictor_selection.chunk_size', 5000)
    min_eta = settings.get('profiling.predictor_selection.min_eta', 0.01)

    correlations = {}

    # Vectorized correlation for numeric predictors
    if numeric_predictors:
        for i in range(0, len(numeric_predictors), chunk_size):
            chunk = numeric_predictors[i:i+chunk_size]
            try:
                result = data.select([pl.corr(metric_col, c).alias(c) for c in chunk]).row(0)
                for col, corr in zip(chunk, result):
                    if corr is not None and not np.isnan(corr):
                        correlations[col] = abs(corr)
            except Exception:
                continue

    # Eta-squared for categorical predictors
    if categorical_predictors:
        metric_values = data[metric_col].to_numpy()

        for col in categorical_predictors:
            try:
                categories = data[col].drop_nulls().to_numpy()
                if len(categories) < 2:
                    continue

                unique_cats = np.unique(categories)
                if len(unique_cats) < 2:
                    continue

                groups = [metric_values[data[col].to_numpy() == cat] for cat in unique_cats]
                groups = [g for g in groups if len(g) > 0]

                if len(groups) >= 2:
                    f_stat, _ = ss.f_oneway(*groups)
                    if not np.isnan(f_stat) and f_stat > 0:
                        n_total = len(metric_values)
                        n_groups = len(groups)
                        denominator = f_stat * (n_groups - 1) + n_total - n_groups
                        if denominator > 0:
                            eta_squared = (f_stat * (n_groups - 1)) / denominator
                            if eta_squared >= min_eta:
                                correlations[col] = eta_squared
            except Exception:
                continue

    return correlations


def _extract_metric_type(col: str) -> str:
    """Extract semantic metric type from column name.

    Splits on underscores, dots, brackets, and dollar signs.
    Stops at numeric tokens (assumed to be instance/location identifiers).

    Examples:
        LD_Qlen_tp_0_sd_0_377 → LD_Qlen_tp
        PROC_nice_nd0_28 → PROC_nice_nd0
        system.cpu.usage.node0 → system_cpu_usage_node0
        cpu.utilization.5 → cpu_utilization
    """
    parts = re.split(r'[_.\[\]\(\)$]+', col)
    parts = [p for p in parts if p]

    if not parts:
        return col

    prefix = parts[0]

    # Stop at numeric tokens or after 2 additional parts (limit depth)
    for i, part in enumerate(parts[1:], 1):
        if re.match(r'^\d+$', part):
            break
        prefix += '_' + part
        if i >= 2:
            break

    return prefix


def _select_representatives_per_group(
    correlations: dict[str, float],
    max_per_group: int,
    max_correlation: float
) -> list[tuple[str, float, str]]:
    """Select representative predictors from each metric group.

    Returns:
        List of (column, correlation, metric_type) tuples
    """
    groups = defaultdict(list)
    for col, corr in correlations.items():
        if corr < max_correlation:
            metric_type = _extract_metric_type(col)
            groups[metric_type].append((col, corr))

    selected = []
    for metric_type, members in groups.items():
        members.sort(key=lambda x: -x[1])
        for col, corr in members[:max_per_group]:
            selected.append((col, corr, metric_type))

    return selected


def _select_top_predictors(
    correlations: dict[str, float],
    max_predictors: int,
    max_correlation: float
) -> list[str]:
    """Select top predictors using semantic grouping for diversity."""
    max_per_group = Settings().get('profiling.predictor_selection.max_per_group', 3)

    # Get representatives from each group
    candidates = _select_representatives_per_group(
        correlations, max_per_group, max_correlation
    )

    if candidates:
        candidates.sort(key=lambda x: -x[1])
        return [col for col, _, _ in candidates[:max_predictors]]

    # Fallback to simple filtering if no candidates
    filtered = {k: v for k, v in correlations.items() if v < max_correlation}
    if not filtered:
        filtered = {k: v for k, v in correlations.items() if v < 1.0}
    if not filtered:
        filtered = correlations

    n_select = min(max_predictors, len(filtered))
    sorted_preds = sorted(filtered.keys(), key=lambda p: filtered[p], reverse=True)
    return sorted_preds[:n_select]
