"""
Tests for confounding utilities (partial correlation, pruning, CI pre-screening).

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import polars as pl

from src.core.profile.confounding import (
    partial_correlation,
    prune_confounded,
    ci_pre_screening,
)


def test_partial_correlation_reduces_spurious_association():
    rng = np.random.default_rng(123)
    n = 200

    x1 = rng.normal(size=n)
    y = 0.9 * x1 + rng.normal(scale=0.1, size=n)
    x2 = x1 + rng.normal(scale=0.05, size=n)

    r_raw, _ = partial_correlation(x2, y)
    r_partial, p_partial = partial_correlation(x2, y, z=x1)

    assert abs(r_raw) > 0.7
    assert abs(r_partial) < 0.2
    assert p_partial > 0.05


def test_prune_confounded_removes_redundant_predictor():
    rng = np.random.default_rng(456)
    n = 300

    x1 = rng.normal(size=n)
    y = 1.5 * x1 + rng.normal(scale=0.2, size=n)
    x2 = x1 + rng.normal(scale=0.05, size=n)

    data = pl.DataFrame({
        "x1": x1,
        "x2": x2,
        "y": y,
    })

    survivors = prune_confounded(
        data,
        outcome_col="y",
        predictors=["x1", "x2"],
        max_conditioning_size=1,
        significance_level=0.05,
    )

    assert "x1" in survivors
    assert "x2" not in survivors


def test_ci_pre_screening_keeps_top_predictors():
    rng = np.random.default_rng(789)
    n = 250

    x1 = rng.normal(size=n)
    y = 1.2 * x1 + rng.normal(scale=0.3, size=n)
    x2 = x1 + rng.normal(scale=0.1, size=n)
    noise_a = rng.normal(size=n)
    noise_b = rng.normal(size=n)

    data = pl.DataFrame({
        "x1": x1,
        "x2": x2,
        "noise_a": noise_a,
        "noise_b": noise_b,
        "y": y,
    })

    predictors = ["x1", "x2", "noise_a", "noise_b"]
    filtered = ci_pre_screening(
        data,
        outcome_col="y",
        predictors=predictors,
        max_keep=2,
        max_conditioning_size=1,
        significance_level=0.05,
    )

    assert len(filtered) <= 2
    assert "x1" in filtered
