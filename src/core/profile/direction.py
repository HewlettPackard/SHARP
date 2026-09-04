"""
Direction testing for causal influence analysis.

Implements bidirectional Granger causality testing to determine the direction
of causal influence between predictors and outcomes. Includes stationarity
checks (ADF test) to warn when assumptions may be violated.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from dataclasses import dataclass
import warnings

import numpy as np
import polars as pl
from statsmodels.tsa.stattools import grangercausalitytests, adfuller

try:
    from statsmodels.tools.sm_exceptions import ValueWarning as StatsmodelsValueWarning
except Exception:  # pragma: no cover - statsmodels internals may vary
    StatsmodelsValueWarning = Warning

from src.core.profile.base import CausalDirection
from src.core.stats.arrays import to_numpy


@dataclass
class DirectionResult:
    """Result of bidirectional Granger causality test."""

    direction: CausalDirection
    """Overall direction of causality"""

    forward_f_stat: float
    """F-statistic for X → Y (predictor causes outcome)"""

    forward_p_value: float
    """P-value for X → Y"""

    reverse_f_stat: float
    """F-statistic for Y → X (outcome causes predictor)"""

    reverse_p_value: float
    """P-value for Y → X"""

    max_lag: int
    """Maximum lag tested"""

    x_stationary: bool
    """Whether predictor series is stationary (ADF test)"""

    y_stationary: bool
    """Whether outcome series is stationary (ADF test)"""

    x_adf_p_value: float
    """ADF test p-value for predictor (< 0.05 = stationary)"""

    y_adf_p_value: float
    """ADF test p-value for outcome (< 0.05 = stationary)"""

    warning: str | None = None
    """Warning message if assumptions violated"""


def detect_direction(
    predictor: np.ndarray | pl.Series,
    outcome: np.ndarray | pl.Series,
    max_lag: int = 5,
    significance_level: float = 0.05,
    check_stationarity: bool = True,
) -> DirectionResult:
    """
    Detect the direction of causal influence using bidirectional Granger causality.

    Performs two Granger tests:
    - Forward: Does X Granger-cause Y? (actionable if significant)
    - Reverse: Does Y Granger-cause X? (effect, not cause, if significant)

    Direction classification:
    - FORWARD: forward significant, reverse not significant
    - REVERSE: reverse significant, forward not significant
    - BIDIRECTIONAL: both significant (feedback loop or common cause)
    - INDETERMINATE: neither significant

    Args:
        predictor: Time series of predictor variable (X)
        outcome: Time series of outcome variable (Y)
        max_lag: Maximum lag to test (default: 5)
        significance_level: Significance threshold for tests (default: 0.05)
        check_stationarity: Whether to run ADF test and warn if non-stationary

    Returns:
        DirectionResult with F-statistics, p-values, and direction classification

    Raises:
        ValueError: If series lengths don't match or are too short
    """
    # Convert to numpy arrays
    predictor = to_numpy(predictor)
    outcome = to_numpy(outcome)

    # Remove NaN values
    valid_mask = ~(np.isnan(predictor) | np.isnan(outcome))
    predictor = predictor[valid_mask]
    outcome = outcome[valid_mask]

    if len(predictor) != len(outcome):
        raise ValueError("Predictor and outcome must have same length")

    if len(predictor) < max_lag + 10:
        raise ValueError(
            f"Series too short: need at least {max_lag + 10} samples, got {len(predictor)}"
        )

    # Check stationarity with ADF test
    x_stationary = True
    y_stationary = True
    x_adf_p = 1.0
    y_adf_p = 1.0
    warning_msg = None

    if check_stationarity:
        try:
            x_adf_result = adfuller(predictor, autolag="AIC")
            x_adf_p = x_adf_result[1]
            x_stationary = x_adf_p < 0.05

            y_adf_result = adfuller(outcome, autolag="AIC")
            y_adf_p = y_adf_result[1]
            y_stationary = y_adf_p < 0.05

            if not x_stationary or not y_stationary:
                non_stationary = []
                if not x_stationary:
                    non_stationary.append("predictor")
                if not y_stationary:
                    non_stationary.append("outcome")
                warning_msg = (
                    f"Non-stationary series detected ({', '.join(non_stationary)}). "
                    f"Granger test assumes stationarity. Consider first-differencing."
                )
        except Exception as e:
            warnings.warn(f"ADF test failed: {e}", UserWarning)
            x_stationary = False
            y_stationary = False
            warning_msg = "Stationarity check failed"

    # Perform bidirectional Granger causality tests
    # Forward: X → Y (does predictor Granger-cause outcome?)
    forward_f, forward_p = _granger_test_single_direction(
        cause=predictor,
        effect=outcome,
        max_lag=max_lag,
    )

    # Reverse: Y → X (does outcome Granger-cause predictor?)
    reverse_f, reverse_p = _granger_test_single_direction(
        cause=outcome,
        effect=predictor,
        max_lag=max_lag,
    )

    # Classify direction based on significance
    forward_sig = forward_p < significance_level
    reverse_sig = reverse_p < significance_level

    if forward_sig and not reverse_sig:
        direction = CausalDirection.FORWARD
    elif reverse_sig and not forward_sig:
        direction = CausalDirection.REVERSE
    elif forward_sig and reverse_sig:
        direction = CausalDirection.BIDIRECTIONAL
    else:
        direction = CausalDirection.INDETERMINATE

    return DirectionResult(
        direction=direction,
        forward_f_stat=forward_f,
        forward_p_value=forward_p,
        reverse_f_stat=reverse_f,
        reverse_p_value=reverse_p,
        max_lag=max_lag,
        x_stationary=bool(x_stationary),
        y_stationary=bool(y_stationary),
        x_adf_p_value=float(x_adf_p),
        y_adf_p_value=float(y_adf_p),
        warning=warning_msg,
    )


def _granger_test_single_direction(
    cause: np.ndarray,
    effect: np.ndarray,
    max_lag: int,
) -> tuple[float, float]:
    """
    Run Granger causality test in one direction.

    Args:
        cause: Hypothesized cause time series
        effect: Hypothesized effect time series
        max_lag: Maximum lag to test

    Returns:
        Tuple of (F-statistic, p-value) for the best lag
    """
    try:
        # Prepare data: statsmodels expects (effect, cause) order
        data = np.column_stack([effect, cause])

        # Run Granger test for lags 1 to max_lag
        # Returns dict: {lag: {test_name: (statistic, p_value, df)}}
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r".*verbose is deprecated since functions should not print results.*",
                category=FutureWarning,
            )
            warnings.filterwarnings(
                "ignore",
                message=r".*covariance of constraints does not have full rank.*",
                category=StatsmodelsValueWarning,
            )
            results = grangercausalitytests(
                data,
                maxlag=max_lag,
                verbose=False,
            )

        # Extract F-test results (ssr_ftest is the standard F-test)
        # Use the lag with the smallest p-value (most significant)
        best_f_stat = 0.0
        best_p_value = 1.0

        for lag in range(1, max_lag + 1):
            lag_results = results[lag]
            # ssr_ftest returns (F-stat, p-value, df_denom, df_num)
            f_stat = lag_results[0]["ssr_ftest"][0]
            p_value = lag_results[0]["ssr_ftest"][1]

            if p_value < best_p_value:
                best_f_stat = f_stat
                best_p_value = p_value

        return float(best_f_stat), float(best_p_value)

    except Exception as e:
        warnings.warn(f"Granger test failed: {e}", UserWarning)
        return 0.0, 1.0
