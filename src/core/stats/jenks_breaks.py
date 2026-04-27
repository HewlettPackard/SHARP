"""
Jenks natural breaks optimization for 1D clustering.

Provides the Fisher-Jenks algorithm and Goodness of Variance Fit metrics
for identifying natural groupings in performance data.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
from typing import List, Tuple


def jenks_breaks(data: np.ndarray, n_classes: int) -> List[float]:
    """
    Calculate Jenks natural breaks (Fisher-Jenks algorithm) for 1D data.

    Jenks natural breaks optimization minimizes within-class variance and
    maximizes between-class variance, making it ideal for finding natural
    groupings in performance data.

    Args:
        data: 1D array of numeric values
        n_classes: Number of classes to create (2-10 recommended)

    Returns:
        List of n_classes-1 break points that optimally separate the data

    Raises:
        ValueError: If n_classes < 2 or n_classes > len(unique values)

    Example:
        >>> data = np.array([1, 2, 3, 10, 11, 12, 50, 51, 52])
        >>> breaks = jenks_breaks(data, 3)
        >>> # Returns breaks that separate [1,2,3], [10,11,12], [50,51,52]
    """
    # Clean and sort data
    data_clean = data[~np.isnan(data)]
    data_sorted = np.sort(data_clean)
    n = len(data_sorted)

    if n_classes < 2:
        raise ValueError("n_classes must be at least 2")

    unique_vals = np.unique(data_sorted)
    if len(unique_vals) < n_classes:
        raise ValueError(
            f"Cannot create {n_classes} classes with only {len(unique_vals)} unique values"
        )

    # For small datasets, use simple quantile-based approach
    if n < n_classes * 2:
        percentiles = [100 * (i + 1) / n_classes for i in range(n_classes - 1)]
        result: List[float] = np.percentile(data_sorted, percentiles).tolist()
        return result

    # Fisher-Jenks algorithm using dynamic programming
    # Based on the algorithm described in:
    # Fisher, W. D. (1958). On grouping for maximum homogeneity.

    # Create matrices for sum of squared deviations (SSD) and class limits
    # mat1[i][j] = minimum SSD for values 0..i classified into j classes
    # mat2[i][j] = lower class limit for optimal classification

    mat1 = np.full((n, n_classes), np.inf)
    mat2 = np.zeros((n, n_classes), dtype=int)

    # Initialize: one class for first i values
    for i in range(n):
        mat1[i, 0] = _ssd(data_sorted[:i + 1])
        mat2[i, 0] = 0

    # Fill matrices using dynamic programming
    for j in range(1, n_classes):
        for i in range(j, n):
            for k in range(j - 1, i):
                # SSD if we put values k+1..i in class j
                ssd_k = _ssd(data_sorted[k + 1:i + 1])
                cost = mat1[k, j - 1] + ssd_k

                if cost < mat1[i, j]:
                    mat1[i, j] = cost
                    mat2[i, j] = k + 1

    # Backtrack to find break points
    breaks: List[float] = []
    k = n
    for j in range(n_classes - 1, 0, -1):
        break_idx = mat2[k - 1, j]
        # Break point is between data_sorted[break_idx-1] and data_sorted[break_idx]
        if break_idx > 0 and break_idx < n:
            # Use midpoint between adjacent values as the break
            break_val = (data_sorted[break_idx - 1] + data_sorted[break_idx]) / 2
            breaks.insert(0, break_val)
        k = break_idx

    return breaks


def _ssd(data: np.ndarray) -> float:
    """
    Calculate sum of squared deviations from mean.

    Args:
        data: Array of values

    Returns:
        Sum of squared deviations from mean
    """
    if len(data) == 0:
        return 0.0
    mean = np.mean(data)
    return float(np.sum((data - mean) ** 2))


def goodness_of_variance_fit(data: np.ndarray, breaks: List[float]) -> float:
    """
    Calculate Goodness of Variance Fit (GVF) for a set of breaks.

    GVF measures how well the breaks explain the variance in the data.
    Values range from 0 to 1, with 1 being a perfect fit.

    Args:
        data: 1D array of numeric values
        breaks: List of break points

    Returns:
        GVF value between 0 and 1
    """
    data_clean = data[~np.isnan(data)]
    data_sorted = np.sort(data_clean)

    # Total sum of squared deviations
    ssd_total = _ssd(data_sorted)
    if ssd_total == 0:
        return 1.0

    # Sum of squared deviations within classes
    all_breaks = [-np.inf] + list(breaks) + [np.inf]
    ssd_within = 0.0

    for i in range(len(all_breaks) - 1):
        lower, upper = all_breaks[i], all_breaks[i + 1]
        mask = (data_sorted > lower) & (data_sorted <= upper)
        ssd_within += _ssd(data_sorted[mask])

    return 1.0 - (ssd_within / ssd_total)


def optimal_jenks_classes(data: np.ndarray, min_classes: int = 2,
                          max_classes: int = 5, gvf_threshold: float = 0.8,
                          min_gvf_improvement: float = 0.10) -> Tuple[int, List[float]]:
    """
    Find optimal number of Jenks classes using Goodness of Variance Fit.

    Starts with min_classes and increases until GVF exceeds threshold
    or max_classes is reached. Also stops if adding more classes doesn't
    improve GVF by at least min_gvf_improvement.

    Args:
        data: 1D array of numeric values
        min_classes: Minimum number of classes to try
        max_classes: Maximum number of classes to try
        gvf_threshold: GVF threshold to stop searching (target quality)
        min_gvf_improvement: Minimum GVF improvement to justify more classes

    Returns:
        Tuple of (optimal_n_classes, break_points)
    """
    data_clean = data[~np.isnan(data)]
    unique_vals = np.unique(data_clean)

    # Limit max_classes to available unique values
    max_classes = min(max_classes, len(unique_vals))

    best_breaks = []
    best_n = min_classes
    prev_gvf = 0.0

    for n in range(min_classes, max_classes + 1):
        try:
            breaks = jenks_breaks(data_clean, n)
            gvf = goodness_of_variance_fit(data_clean, breaks)

            # Check if we've reached the quality threshold
            if gvf >= gvf_threshold:
                return n, breaks

            # Check if improvement justifies added complexity
            if n > min_classes and (gvf - prev_gvf) < min_gvf_improvement:
                # Diminishing returns - stick with previous n
                return best_n, best_breaks

            best_breaks = breaks
            best_n = n
            prev_gvf = gvf
        except ValueError:
            break

    return best_n, best_breaks
