"""
Tests for lag detection utilities.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import numpy as np

from src.core.profile.lag_detection import auto_max_lag, max_lag_correlation, sparse_lag_screening


def _build_shifted_series(seed: int, n: int, lag: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    base = rng.normal(0, 1, n)
    outcome = np.roll(base, lag)
    outcome[:lag] = 0.0
    return outcome, base


def test_max_lag_correlation_detects_forward_lag():
    outcome, predictor = _build_shifted_series(seed=42, n=200, lag=5)
    max_corr, best_lag, _ = max_lag_correlation(outcome, predictor, max_lag=10)

    assert best_lag == 5
    assert max_corr > 0.5


def test_max_lag_correlation_detects_reverse_lag():
    predictor, outcome = _build_shifted_series(seed=123, n=200, lag=4)
    max_corr, best_lag, _ = max_lag_correlation(outcome, predictor, max_lag=10)

    assert best_lag == -4
    assert max_corr > 0.5


def test_auto_max_lag_with_timestamps():
    rng = np.random.default_rng(7)
    outcome = rng.normal(0, 1, 100)
    timestamps = np.arange(0, 100, dtype=float)

    max_lag = auto_max_lag(outcome, timestamps=timestamps)

    assert 1 <= max_lag <= 5


def test_sparse_lag_screening():
    lags = sparse_lag_screening(50)
    assert lags == [0, 1, 2, 3, 5, 8, 13, 21, 34]


def test_max_lag_correlation_timestamp_seconds():
    outcome, predictor = _build_shifted_series(seed=99, n=120, lag=3)
    timestamps = np.arange(0, 240, 2, dtype=float)

    _, best_lag, lag_seconds = max_lag_correlation(
        outcome,
        predictor,
        max_lag=10,
        timestamps=timestamps,
    )

    assert best_lag == 3
    assert lag_seconds == 6.0
