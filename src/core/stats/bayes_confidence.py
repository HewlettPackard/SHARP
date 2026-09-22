# © Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""Bayesian confidence utilities for factor columns.

Adds approximate Bayesian effect summaries for each requested column:
- Regression mode: BayesianRidge posterior for each factor.
- Classification mode: Laplace-approximate Bayesian logistic posterior
    with Gaussian prior.
"""

from typing import Any

import numpy as np
import polars as pl
from scipy.stats import norm
from sklearn.linear_model import BayesianRidge, LogisticRegression

from src.core.stats.arrays import is_numeric_polars_dtype

def estimate_bayes_confidence_for_columns(
    data: pl.DataFrame,
    outcome: np.ndarray,
    outcome_mode: str,
    columns: list[str],
    max_columns: int = 20,
) -> dict[str, dict[str, Any]]:
    """Estimate Bayesian confidence stats for the requested columns.

    Returns:
        Mapping of column name -> bayes confidence stats.
    """
    if not columns or data is None or data.is_empty() or outcome is None:
        return {}

    capped = min(max_columns, len(columns))
    results: dict[str, dict[str, Any]] = {}

    for column_name in columns[:capped]:
        if column_name not in data.columns:
            continue

        effect = _estimate_factor_effect(
            data=data,
            column_name=column_name,
            outcome=outcome,
            outcome_mode=outcome_mode,
        )
        if effect is None:
            continue

        results[column_name] = effect

    return results


def _estimate_factor_effect(
    data: pl.DataFrame,
    column_name: str,
    outcome: np.ndarray,
    outcome_mode: str,
) -> dict[str, Any] | None:
    series = data[column_name]

    # Keep numeric types only for now (categoricals can be one-hot expanded later)
    if not is_numeric_polars_dtype(series.dtype):
        return None

    x_raw = series.cast(pl.Float64).to_numpy()
    y_raw = np.asarray(outcome)

    if len(x_raw) != len(y_raw):
        return None

    mask = np.isfinite(x_raw) & np.isfinite(y_raw)
    if mask.sum() < 10:
        return None

    x = x_raw[mask]
    y = y_raw[mask]

    # Standardize feature so coefficients are comparable across factors
    x_mean = float(np.mean(x))
    x_std = float(np.std(x))
    if x_std < 1e-12:
        return None

    xz = ((x - x_mean) / x_std).reshape(-1, 1)

    if outcome_mode == "regression":
        return _bayes_regression_effect(xz, y)

    return _bayes_logistic_effect(xz, y)


def _bayes_regression_effect(x: np.ndarray, y: np.ndarray) -> dict[str, Any] | None:
    try:
        model = BayesianRidge(fit_intercept=True)
        model.fit(x, y)

        coef = float(model.coef_[0])
        if model.sigma_ is None or model.sigma_.shape[0] < 1:
            return None

        sd = float(np.sqrt(max(model.sigma_[0, 0], 0.0)))
        if sd <= 0 or not np.isfinite(sd):
            return None

        ci_low = coef - 1.96 * sd
        ci_high = coef + 1.96 * sd
        prob_positive = float(1.0 - norm.cdf(0.0, loc=coef, scale=sd))

        return {
            "model": "bayesian_ridge",
            "mode": "regression",
            "coef_std": coef,
            "sd": sd,
            "ci95": (float(ci_low), float(ci_high)),
            "prob_positive": prob_positive,
        }
    except Exception:
        return None


def _bayes_logistic_effect(x: np.ndarray, y: np.ndarray) -> dict[str, Any] | None:
    unique = np.unique(y)
    if len(unique) < 2:
        return None

    def fit_binary(y_binary: np.ndarray) -> tuple[float, float, float, float, float] | None:
        try:
            tau2 = 4.0
            model = LogisticRegression(
                C=tau2,
                fit_intercept=True,
                solver="lbfgs",
                max_iter=1000,
            )
            model.fit(x, y_binary.astype(int))

            coef = float(model.coef_[0, 0])
            intercept = float(model.intercept_[0])

            design = np.column_stack([np.ones(len(x)), x[:, 0]])
            logits = intercept + coef * x[:, 0]
            probs = 1.0 / (1.0 + np.exp(-logits))
            weights = probs * (1.0 - probs)

            xtwx = design.T @ (design * weights[:, None])
            prior_precision = np.diag([1e-6, 1.0 / tau2])
            hessian = xtwx + prior_precision
            cov = np.linalg.pinv(hessian)

            sd = float(np.sqrt(max(cov[1, 1], 0.0)))
            if sd <= 0 or not np.isfinite(sd):
                return None

            ci_low = coef - 1.96 * sd
            ci_high = coef + 1.96 * sd
            prob_positive = float(1.0 - norm.cdf(0.0, loc=coef, scale=sd))
            return coef, sd, ci_low, ci_high, prob_positive
        except Exception:
            return None

    if len(unique) == 2:
        fit = fit_binary(y == unique[1])
        if fit is None:
            return None
        coef, sd, ci_low, ci_high, prob_positive = fit
        return {
            "model": "bayes_logistic_laplace",
            "mode": "classification",
            "target_class": str(unique[1]),
            "coef_std": coef,
            "sd": sd,
            "ci95": (float(ci_low), float(ci_high)),
            "prob_positive": prob_positive,
        }

    best: dict[str, Any] | None = None
    for cls in unique:
        y_binary = (y == cls)
        if y_binary.sum() == 0 or y_binary.sum() == len(y_binary):
            continue
        fit = fit_binary(y_binary)
        if fit is None:
            continue
        coef, sd, ci_low, ci_high, prob_positive = fit
        candidate = {
            "model": "bayes_logistic_laplace_ovr",
            "mode": "classification",
            "target_class": str(cls),
            "coef_std": coef,
            "sd": sd,
            "ci95": (float(ci_low), float(ci_high)),
            "prob_positive": prob_positive,
        }
        if best is None or abs(float(candidate["coef_std"])) > abs(float(best["coef_std"])):
            best = candidate

    return best


__all__ = ["estimate_bayes_confidence_for_columns"]
