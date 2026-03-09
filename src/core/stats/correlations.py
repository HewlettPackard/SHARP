"""
Correlation and association measure utilities.

Functions for computing correlation between variables of various types
(numeric, categorical, mixed). Used in feature selection and analysis.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np


def compute_numeric_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """
    Compute Pearson correlation between two numeric variables.

    Args:
        x: Numeric predictor values (1D array)
        y: Numeric outcome values (1D array)

    Returns:
        Correlation value in [-1, 1], or np.nan if cannot compute
    """
    try:
        if np.std(x) > 0 and np.std(y) > 0:
            return float(np.corrcoef(x, y)[0, 1])
        return np.nan
    except Exception:
        return np.nan


def compute_categorical_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """
    Compute eta-squared effect size (correlation-like) for categorical predictor vs numeric outcome.

    Uses ANOVA to compute effect size and converts to correlation scale [-1, 1]
    with sign based on direction of mean difference.

    Args:
        x: Categorical predictor values (1D array, can be strings or numeric)
        y: Numeric outcome values (1D array)

    Returns:
        Correlation value in [-1, 1], or np.nan if cannot compute
    """
    try:
        from scipy.stats import f_oneway

        # Convert to categorical and get unique groups
        unique_vals = np.unique(x)
        if len(unique_vals) < 2:
            return np.nan

        # Compute ANOVA
        groups = [y[x == val] for val in unique_vals]
        f_stat, p_val = f_oneway(*groups)

        # Calculate eta-squared (effect size)
        # eta^2 = SS_between / SS_total
        grand_mean = np.mean(y)
        ss_total = np.sum((y - grand_mean) ** 2)
        ss_between = sum(len(group) * (np.mean(group) - grand_mean) ** 2 for group in groups)
        eta_squared = ss_between / ss_total if ss_total > 0 else 0

        # Convert to correlation scale (take square root)
        eta = np.sqrt(eta_squared)

        # Determine sign based on whether first level has higher or lower mean
        level_means = [np.mean(y[x == val]) for val in unique_vals]
        sign_direction = 1.0 if level_means[0] < level_means[-1] else -1.0

        return float(eta * sign_direction)
    except Exception:
        return np.nan


def _clean_data_pair(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Clean paired data by removing NaN/None values.

    Handles both numeric arrays (NaN) and object arrays (None).

    Args:
        x: First array
        y: Second array

    Returns:
        Tuple of (x_clean, y_clean) with NaN/None removed
    """
    try:
        if np.issubdtype(x.dtype, np.number):
            mask_x = ~np.isnan(x)
        else:
            mask_x = np.array([v is not None for v in x])

        if np.issubdtype(y.dtype, np.number):
            mask_y = ~np.isnan(y)
        else:
            mask_y = np.array([v is not None for v in y])
    except Exception:
        return np.array([]), np.array([])

    mask = mask_x & mask_y
    return x[mask], y[mask]


def compute_generalized_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """
    Compute correlation between any predictor and numeric outcome.

    Automatically detects predictor type and applies appropriate correlation measure:
    - Numeric-numeric: Pearson correlation
    - Categorical-numeric: Eta-squared effect size (ANOVA)

    Returns value in range [-1, 1] for both numeric and categorical predictors.

    Args:
        x: Predictor values (1D array, numeric or categorical)
        y: Outcome values (1D array, numeric)

    Returns:
        Correlation value in [-1, 1], or np.nan if cannot compute
    """
    # Clean data first
    x_clean, y_clean = _clean_data_pair(x, y)

    # Need at least 2 observations
    if len(x_clean) < 2 or len(y_clean) < 2:
        return np.nan

    # Check if predictor and outcome have variance
    unique_x = np.unique(x_clean)
    unique_y = np.unique(y_clean)

    if len(unique_x) <= 1 or len(unique_y) <= 1:
        return np.nan

    # Determine if predictor is numeric
    x_is_numeric = np.issubdtype(x_clean.dtype, np.number)
    y_is_numeric = np.issubdtype(y_clean.dtype, np.number)

    if x_is_numeric and y_is_numeric:
        # Both numeric: use Pearson correlation
        return compute_numeric_correlation(x_clean, y_clean)
    elif not x_is_numeric and y_is_numeric:
        # Categorical predictor, numeric outcome: use eta-squared
        return compute_categorical_correlation(x_clean, y_clean)
    else:
        # Other cases not supported
        return np.nan


def safe_correlation(x: np.ndarray, y: np.ndarray, min_pairs: int = 3) -> float:
    """
    Safely compute correlation on valid pairs with minimum pair requirement.

    Useful for robustness when dealing with sparse or heavily missing data.

    Args:
        x: Predictor values
        y: Outcome values
        min_pairs: Minimum number of valid pairs required

    Returns:
        Correlation value, or np.nan if insufficient data
    """
    x_clean, y_clean = _clean_data_pair(x, y)

    if len(x_clean) <= min_pairs:
        return np.nan

    if len(np.unique(x_clean)) <= 1 or len(np.unique(y_clean)) <= 1:
        return np.nan

    try:
        return compute_generalized_correlation(x_clean, y_clean)
    except Exception:
        return np.nan
