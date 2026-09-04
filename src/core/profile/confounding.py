"""
Conditional independence utilities for causal analysis.

Implements partial correlation, confounding pruning, and CI pre-screening
used by Granger and Hybrid analyzers.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import polars as pl
from scipy import stats

from src.core.stats.arrays import to_numpy


def partial_correlation(
    x: np.ndarray | pl.Series,
    y: np.ndarray | pl.Series,
    z: np.ndarray | pl.Series | None = None,
) -> tuple[float, float]:
    """
    Compute partial correlation between x and y given conditioning variables z.

    Args:
        x: Predictor array
        y: Outcome array
        z: Conditioning array(s), shape (n,) or (n, k)

    Returns:
        Tuple of (partial_correlation, p_value)
    """
    x_vals = to_numpy(x)
    y_vals = to_numpy(y)
    z_vals = to_numpy(z) if z is not None else None

    if z_vals is None or z_vals.size == 0:
        return _pearson_with_p_value(x_vals, y_vals)

    if z_vals.ndim == 1:
        z_vals = z_vals.reshape(-1, 1)

    mask = ~np.isnan(x_vals) & ~np.isnan(y_vals)
    if z_vals is not None:
        mask &= ~np.isnan(z_vals).any(axis=1)

    x_vals = x_vals[mask]
    y_vals = y_vals[mask]
    z_vals = z_vals[mask]

    n_rows = len(x_vals)
    if n_rows < 5:
        return 0.0, 1.0

    x_resid = _regress_out(x_vals, z_vals)
    y_resid = _regress_out(y_vals, z_vals)

    r, p = _pearson_with_p_value(x_resid, y_resid, df_adjust=z_vals.shape[1])
    return r, p


def prune_confounded(
    data: pl.DataFrame,
    outcome_col: str,
    predictors: list[str],
    max_conditioning_size: int = 3,
    significance_level: float = 0.05,
    min_abs_partial: float | None = None,
    outcome_correlations: dict[str, float] | None = None,
) -> list[str]:
    """
    Remove predictors whose partial correlation vanishes after conditioning.

    Args:
        data: Input DataFrame
        outcome_col: Outcome column name
        predictors: Predictor column names
        max_conditioning_size: Max number of conditioning predictors
        significance_level: P-value threshold for significance
        min_abs_partial: Optional absolute partial correlation threshold

    Returns:
        List of predictors that retain independent association with outcome
    """
    if not predictors or outcome_col not in data.columns:
        return []

    outcome = data[outcome_col].to_numpy()
    corr_map = _compute_correlations(data, outcome, predictors, outcome_correlations)
    ordered = sorted(predictors, key=lambda p: abs(corr_map.get(p, 0.0)), reverse=True)
    survivors = ordered[:]

    for predictor in reversed(ordered):
        if predictor not in survivors:
            continue

        conditioning = [p for p in survivors if p != predictor][:max_conditioning_size]
        if not conditioning:
            continue

        predictor_vals = data[predictor].to_numpy()
        z_vals = data.select(conditioning).to_numpy()

        r_partial, p_value = partial_correlation(predictor_vals, outcome, z_vals)

        if min_abs_partial is not None and abs(r_partial) < min_abs_partial:
            survivors.remove(predictor)
            continue

        if p_value > significance_level:
            survivors.remove(predictor)

    return survivors


def ci_pre_screening(
    data: pl.DataFrame,
    outcome_col: str,
    predictors: list[str],
    max_keep: int = 30,
    max_conditioning_size: int = 3,
    significance_level: float = 0.05,
    min_abs_partial: float | None = None,
    outcome_correlations: dict[str, float] | None = None,
) -> list[str]:
    """
    Conditional independence pre-screening to reduce predictor count.

    Applies partial correlation pruning, then keeps top max_keep by
    marginal correlation strength.

    Args:
        data: Input DataFrame
        outcome_col: Outcome column name
        predictors: Predictor column names
        max_keep: Maximum predictors to keep
        max_conditioning_size: Max conditioning predictors
        significance_level: P-value threshold for partial correlation
        min_abs_partial: Optional absolute partial correlation threshold

    Returns:
        Filtered list of predictors
    """
    if len(predictors) <= max_keep:
        return predictors

    survivors = prune_confounded(
        data,
        outcome_col,
        predictors,
        max_conditioning_size=max_conditioning_size,
        significance_level=significance_level,
        min_abs_partial=min_abs_partial,
        outcome_correlations=outcome_correlations,
    )

    if len(survivors) <= max_keep:
        return survivors

    outcome = data[outcome_col].to_numpy()
    corr_map = _compute_correlations(data, outcome, survivors, outcome_correlations)
    ranked = sorted(survivors, key=lambda p: abs(corr_map.get(p, 0.0)), reverse=True)
    return ranked[:max_keep]


def _compute_correlations(
    data: pl.DataFrame,
    outcome: np.ndarray,
    predictors: Iterable[str],
    outcome_correlations: dict[str, float] | None = None,
) -> dict[str, float]:
    correlations: dict[str, float] = dict(outcome_correlations or {})
    for predictor in predictors:
        if predictor in correlations:
            continue
        pred_vals = data[predictor].to_numpy()
        r, _ = _pearson_with_p_value(outcome, pred_vals)
        correlations[predictor] = r
    return correlations


def _regress_out(target: np.ndarray, predictors: np.ndarray) -> np.ndarray:
    if predictors.size == 0:
        return target

    predictors = np.asarray(predictors)
    target = np.asarray(target)

    if predictors.ndim == 1:
        predictors = predictors.reshape(-1, 1)

    intercept = np.ones((predictors.shape[0], 1))
    design = np.hstack([intercept, predictors])
    coeffs, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
    fitted = design @ coeffs
    return target - fitted


def _pearson_with_p_value(
    x_vals: np.ndarray,
    y_vals: np.ndarray,
    df_adjust: int = 0,
) -> tuple[float, float]:
    mask = ~np.isnan(x_vals) & ~np.isnan(y_vals)
    x_vals = x_vals[mask]
    y_vals = y_vals[mask]

    n_rows = len(x_vals)
    if n_rows < 3:
        return 0.0, 1.0

    r = float(np.corrcoef(x_vals, y_vals)[0, 1])
    if not np.isfinite(r):
        return 0.0, 1.0

    df = n_rows - 2 - df_adjust
    if df <= 0:
        return r, 1.0

    t_stat = r * np.sqrt(df / max(1e-12, 1.0 - r * r))
    p_value = float(2.0 * stats.t.sf(abs(t_stat), df))
    return r, p_value