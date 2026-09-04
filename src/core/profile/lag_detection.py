"""
Lag detection utilities for causal analysis.

Provides cross-correlation-based lag detection with automatic search bounds
and sparse lag screening for large-scale predictor scans.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""


import numpy as np
from scipy.signal import correlate

from src.core.stats.distribution import estimate_acf_lag


def auto_max_lag(
    outcome: np.ndarray,
    timestamps: np.ndarray | None = None,
    acf_threshold: float = 1.0 / np.e,
    max_lag_cap: int = 200,
) -> int:
    """Determine the maximum lag to search based on ACF decay and timestamps.

    Uses the first lag where the outcome's ACF drops below `acf_threshold`.
    When timestamps are provided, also computes a time-based cap using
    5% of the total time range divided by the median time step, and
    returns the smaller of the two for conservative bounds.

    Args:
        outcome: Outcome time series (Y).
        timestamps: Optional timestamps aligned to outcome.
        acf_threshold: ACF magnitude threshold (default: 1/e).
        max_lag_cap: Hard cap on lag search.

    Returns:
        Integer maximum lag to search (>= 1).
    """
    x = np.asarray(outcome, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)

    if n < 3:
        return 1

    max_lag = min(int(np.sqrt(n)), max_lag_cap)
    if max_lag < 1:
        return 1

    try:
        acf_result = estimate_acf_lag(x, threshold=acf_threshold, max_lag=max_lag)
        acf_lag = int(acf_result.get("lag", max_lag))
    except Exception:
        acf_lag = max_lag

    acf_lag = max(1, min(acf_lag, max_lag))

    if timestamps is None:
        return acf_lag

    ts = np.asarray(timestamps, dtype=float)
    ts = ts[~np.isnan(ts)]
    if len(ts) < 2:
        return acf_lag

    diffs = np.diff(np.sort(ts))
    diffs = diffs[diffs > 0]
    if len(diffs) == 0:
        return acf_lag

    median_step = float(np.median(diffs))
    if median_step <= 0:
        return acf_lag

    time_range = float(np.max(ts) - np.min(ts))
    time_lag = int(max(1, (0.05 * time_range) / median_step))
    return max(1, min(acf_lag, time_lag))


def sparse_lag_screening(max_lag: int) -> list[int]:
    """Return Fibonacci-like lag offsets up to max_lag.

    Args:
        max_lag: Maximum lag (inclusive).

    Returns:
        Sorted list of lag offsets starting at 0.
    """
    if max_lag <= 0:
        return [0]

    lags = [0, 1, 2]
    while True:
        next_lag = lags[-1] + lags[-2]
        if next_lag > max_lag:
            break
        lags.append(next_lag)

    return [lag for lag in lags if lag <= max_lag]


def max_lag_correlation(
    outcome: np.ndarray,
    predictor: np.ndarray,
    max_lag: int | None = None,
    timestamps: np.ndarray | None = None,
) -> tuple[float, int, float | None]:
    """Find the lag with maximum absolute cross-correlation.

    Args:
        outcome: Outcome time series (Y).
        predictor: Predictor time series (X).
        max_lag: Maximum lag to search. Auto-detected if None.
        timestamps: Optional timestamps aligned to outcome/predictor.

    Returns:
        Tuple of (max_abs_correlation, optimal_lag_rows, optimal_lag_seconds).
        optimal_lag_seconds is None when timestamps are unavailable.
        Positive lag means predictor leads outcome.
    """
    x = np.asarray(outcome, dtype=float)
    y = np.asarray(predictor, dtype=float)

    if x.shape != y.shape:
        raise ValueError("Outcome and predictor must have the same length")

    mask = ~np.isnan(x) & ~np.isnan(y)
    x = x[mask]
    y = y[mask]

    if len(x) < 3:
        return 0.0, 0, None

    if max_lag is None:
        max_lag = auto_max_lag(x, timestamps=timestamps)

    max_lag = max(1, min(int(max_lag), len(x) - 1))

    x = x - np.mean(x)
    y = y - np.mean(y)

    x_std = float(np.std(x))
    y_std = float(np.std(y))
    if x_std == 0.0 or y_std == 0.0:
        return 0.0, 0, None

    corr = correlate(x, y, mode="full", method="fft")
    corr = corr / (len(x) * x_std * y_std)
    lags = np.arange(-len(x) + 1, len(x))

    lag_mask = (lags >= -max_lag) & (lags <= max_lag)
    corr = corr[lag_mask]
    lags = lags[lag_mask]

    idx = int(np.argmax(np.abs(corr)))
    best_lag = int(lags[idx])
    best_corr = float(np.abs(corr[idx]))

    lag_seconds = None
    if timestamps is not None:
        ts = np.asarray(timestamps, dtype=float)
        ts = ts[~np.isnan(ts)]
        if len(ts) >= 2:
            diffs = np.diff(np.sort(ts))
            diffs = diffs[diffs > 0]
            if len(diffs) > 0:
                median_step = float(np.median(diffs))
                if median_step > 0:
                    lag_seconds = float(best_lag * median_step)

    return best_corr, best_lag, lag_seconds
