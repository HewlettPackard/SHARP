"""
Tests for influence analyzer implementations.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import polars as pl
import pytest

from src.core.profile.analyzers import (
    TrainedModelInfluenceAnalyzer,
    TreeInfluenceAnalyzer,
)
from src.core.profile.base import InfluenceFactor


def test_tree_analyzer_with_numeric_features():
    """TreeInfluenceAnalyzer trains tree and extracts factors from numeric predictors."""
    data = pl.DataFrame({
        "predictor1": [1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0, 3.0],
        "predictor2": [10.0, 20.0, 30.0, 40.0, 50.0, 10.0, 20.0, 30.0],
        "outcome": [0.1, 0.2, 0.3, 0.4, 0.5, 0.1, 0.2, 0.3],
    })
    labels = np.array([0, 0, 1, 1, 1, 0, 0, 1])

    analyzer = TreeInfluenceAnalyzer()
    factors = analyzer.analyze(data, labels, exclude_cols=[], outcome_col="outcome")

    assert factors, "Analyzer should return at least one factor"
    # Should only have predictor columns, not the outcome column
    assert all(f.name != "outcome" for f in factors), "Outcome column should not be in factors"
    assert all(isinstance(f, InfluenceFactor) for f in factors)
    assert all(0 <= f.strength <= 1 for f in factors), "Strength (importance) should be in [0, 1]"
    # Verify ranks are sequential starting from 1
    assert [f.rank for f in factors] == list(range(1, len(factors) + 1))


def test_tree_analyzer_ranked_by_importance():
    """TreeInfluenceAnalyzer returns factors ranked by importance (descending)."""
    data = pl.DataFrame({
        "strong_pred": [1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0, 3.0],
        "weak_pred": [0.1, 0.2, 0.1, 0.2, 0.1, 0.2, 0.1, 0.2],
        "outcome": [0.1, 0.2, 0.3, 0.4, 0.5, 0.1, 0.2, 0.3],
    })
    labels = np.array([0, 0, 1, 1, 1, 0, 0, 1])

    analyzer = TreeInfluenceAnalyzer()
    factors = analyzer.analyze(data, labels, exclude_cols=[], outcome_col="outcome")

    if len(factors) > 1:
        # First factor should have higher importance than second
        assert factors[0].strength >= factors[1].strength, "Factors should be ranked descending by strength"


def test_tree_analyzer_with_categorical_features():
    """TreeInfluenceAnalyzer handles categorical predictors."""
    data = pl.DataFrame({
        "cat_pred": ["A", "B", "A", "B", "A", "B", "A", "B"],
        "num_pred": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        "outcome": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    })
    labels = np.array([0, 0, 1, 1, 1, 1, 0, 0])

    analyzer = TreeInfluenceAnalyzer()
    factors = analyzer.analyze(data, labels, exclude_cols=[], outcome_col="outcome")

    assert factors, "Analyzer should handle mixed numeric + categorical data"
    assert all(isinstance(f.name, str) for f in factors), "All factor names should be strings"


def test_tree_analyzer_excludes_columns():
    """TreeInfluenceAnalyzer respects exclude_cols parameter."""
    data = pl.DataFrame({
        "predictor1": [1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0, 3.0],
        "predictor2": [10.0, 20.0, 30.0, 40.0, 50.0, 10.0, 20.0, 30.0],
        "outcome": [0.1, 0.2, 0.3, 0.4, 0.5, 0.1, 0.2, 0.3],
    })
    labels = np.array([0, 0, 1, 1, 1, 0, 0, 1])

    analyzer = TreeInfluenceAnalyzer()
    factors = analyzer.analyze(data, labels, exclude_cols=["predictor2"], outcome_col="outcome")

    # All returned factors should NOT be from excluded columns
    assert all(f.name != "predictor2" for f in factors), "Excluded columns should not appear in factors"


def test_tree_analyzer_insufficient_data():
    """TreeInfluenceAnalyzer returns empty factors on insufficient data."""
    data = pl.DataFrame({
        "predictor": [1.0, 2.0],
        "outcome": [0.1, 0.2],
    })
    labels = np.array([0, 1])

    analyzer = TreeInfluenceAnalyzer()
    factors = analyzer.analyze(data, labels, exclude_cols=[], outcome_col="outcome")

    # With only 2 samples, tree training may fail or return empty
    assert isinstance(factors, list), "Should return a list even on failure"


def test_tree_analyzer_trained_model_accessible():
    """TreeInfluenceAnalyzer.trained_model is accessible after analyze()."""
    data = pl.DataFrame({
        "predictor": [1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0, 3.0],
        "outcome": [0.1, 0.2, 0.3, 0.4, 0.5, 0.1, 0.2, 0.3],
    })
    labels = np.array([0, 0, 1, 1, 1, 0, 0, 1])

    analyzer = TreeInfluenceAnalyzer()
    analyzer.analyze(data, labels, exclude_cols=[], outcome_col="outcome")

    assert analyzer.trained_model is not None, "trained_model should be set after analyze()"
    assert analyzer.trained_model.model is not None, "trained_model.model should be a DecisionTreeClassifier"
    assert hasattr(analyzer.trained_model.model, 'feature_importances_')


def test_tree_analyzer_ignores_eager_bootstrap_setting():
    """TreeInfluenceAnalyzer no longer computes bootstrap CI during analyze()."""
    data = pl.DataFrame({
        "predictor1": [1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0, 3.0],
        "predictor2": [10.0, 20.0, 30.0, 40.0, 50.0, 10.0, 20.0, 30.0],
        "outcome": [0.1, 0.2, 0.3, 0.4, 0.5, 0.1, 0.2, 0.3],
    })
    labels = np.array([0, 0, 1, 1, 1, 0, 0, 1])
    settings = {
        "profiling.model.bootstrap_ci_samples": 3,
    }

    analyzer = TreeInfluenceAnalyzer()
    factors = analyzer.analyze(
        data,
        labels,
        exclude_cols=[],
        outcome_col="outcome",
        settings=settings,
        max_predictors=10,
        max_correlation=0.99,
    )

    assert factors, "Analyzer should still return factors"
    assert all(
        not bool((f.metadata or {}).get("bootstrap_ci_enabled", False)) for f in factors
    )


def test_tree_bootstrap_ci_calculates_interval_tuples():
    """Bootstrap CI calculation returns valid interval tuples for trained features."""
    data = pl.DataFrame({
        "predictor1": [1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0, 3.0],
        "predictor2": [10.0, 20.0, 30.0, 40.0, 50.0, 10.0, 20.0, 30.0],
        "outcome": [0.1, 0.2, 0.3, 0.4, 0.5, 0.1, 0.2, 0.3],
    })
    labels = np.array([0, 0, 1, 1, 1, 0, 0, 1])

    analyzer = TreeInfluenceAnalyzer()
    analyzer.analyze(
        data,
        labels,
        exclude_cols=[],
        outcome_col="outcome",
        max_predictors=10,
        max_correlation=0.99,
    )
    assert analyzer.trained_model is not None

    ci_map = analyzer._bootstrap_ci(
        data,
        labels,
        analyzer.trained_model,
        exclude_cols=[],
        max_predictors=10,
        max_correlation=0.99,
        n_samples=5,
    )

    assert isinstance(ci_map, dict)
    for interval in ci_map.values():
        assert isinstance(interval, tuple)
        assert len(interval) == 2
        low, high = interval
        assert low <= high


def test_tree_bootstrap_ci_preserves_minority_class_via_stratification(monkeypatch):
    """Bootstrap sampling should retain minority-class representation in each sample."""
    data = pl.DataFrame({
        "predictor": list(range(20)),
        "outcome": [0.0] * 18 + [1.0, 1.0],
    })
    labels = np.array([0] * 18 + [1, 1])

    analyzer = TreeInfluenceAnalyzer()
    analyzer.analyze(
        data,
        labels,
        exclude_cols=[],
        outcome_col="outcome",
        max_predictors=10,
        max_correlation=0.99,
    )
    assert analyzer.trained_model is not None

    original_choice = np.random.choice

    def fake_choice(a, size=None, replace=True, p=None):
        # If bootstrap is unstratified and draws from range(n_rows), force all-majority.
        # Stratified bootstrap draws from class index arrays and bypasses this trap.
        if isinstance(a, (int, np.integer)):
            return np.zeros(size, dtype=int)
        return original_choice(a, size=size, replace=replace, p=p)

    monkeypatch.setattr(np.random, "choice", fake_choice)

    original_train = analyzer._trainer.train

    def train_and_assert(sample_data, sample_labels, **kwargs):
        assert set(np.unique(sample_labels)) == {0, 1}
        return original_train(sample_data, sample_labels, **kwargs)

    monkeypatch.setattr(analyzer._trainer, "train", train_and_assert)

    ci_map = analyzer._bootstrap_ci(
        data,
        labels,
        analyzer.trained_model,
        exclude_cols=[],
        max_predictors=10,
        max_correlation=0.99,
        n_samples=3,
    )

    assert isinstance(ci_map, dict)


def test_tree_analyze_keeps_factor_ci_none_until_requested():
    """Tree analyze keeps confidence_interval=None until on-demand bootstrap is run."""
    data = pl.DataFrame({
        "predictor1": [1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0, 3.0],
        "predictor2": [10.0, 20.0, 30.0, 40.0, 50.0, 10.0, 20.0, 30.0],
        "outcome": [0.1, 0.2, 0.3, 0.4, 0.5, 0.1, 0.2, 0.3],
    })
    labels = np.array([0, 0, 1, 1, 1, 0, 0, 1])

    analyzer = TreeInfluenceAnalyzer()
    factors = analyzer.analyze(
        data,
        labels,
        exclude_cols=[],
        outcome_col="outcome",
        max_predictors=10,
        max_correlation=0.99,
    )

    assert factors
    assert all(f.confidence_interval is None for f in factors)


def test_trained_model_analyzer_is_abstract():
    """TrainedModelInfluenceAnalyzer cannot be instantiated directly."""
    with pytest.raises(TypeError):
        TrainedModelInfluenceAnalyzer()


# ============================================================================
# Tree downsampling tests
# ============================================================================

def _make_large_dataframe(n_rows: int = 2000) -> tuple[pl.DataFrame, np.ndarray]:
    """Build a synthetic DataFrame with a predictable signal."""
    rng = np.random.default_rng(42)
    predictor = rng.normal(0, 1, n_rows)
    noise = rng.normal(0, 0.1, n_rows)
    outcome = predictor + noise
    labels = (outcome > np.median(outcome)).astype(int)
    return pl.DataFrame({"predictor": predictor, "outcome": outcome}), labels


def test_tree_downsamples_when_exceeding_target_rows(monkeypatch):
    """TreeInfluenceAnalyzer trains on at most target_rows rows when data is large."""
    data, labels = _make_large_dataframe(2000)
    settings = {"profiling.tree_training.target_rows": 100}

    captured: list[int] = []
    analyzer = TreeInfluenceAnalyzer()
    original_train = analyzer._trainer.train

    def capturing_train(d, lbl, **kwargs):
        captured.append(len(d))
        return original_train(d, lbl, **kwargs)

    monkeypatch.setattr(analyzer._trainer, "train", capturing_train)

    factors = analyzer.analyze(
        data, labels, exclude_cols=[], outcome_col="outcome", settings=settings
    )

    assert captured, "trainer.train should have been called"
    assert captured[0] <= 100, (
        f"Tree was trained on {captured[0]} rows; expected ≤100 (target_rows=100)"
    )
    assert isinstance(factors, list), "analyze() should return a list"


def test_tree_no_downsampling_when_below_target(monkeypatch):
    """TreeInfluenceAnalyzer trains on all rows when data is below target_rows."""
    data, labels = _make_large_dataframe(50)
    settings = {"profiling.tree_training.target_rows": 200}

    captured: list[int] = []
    analyzer = TreeInfluenceAnalyzer()
    original_train = analyzer._trainer.train

    def capturing_train(d, lbl, **kwargs):
        captured.append(len(d))
        return original_train(d, lbl, **kwargs)

    monkeypatch.setattr(analyzer._trainer, "train", capturing_train)

    analyzer.analyze(
        data, labels, exclude_cols=[], outcome_col="outcome", settings=settings
    )

    assert captured, "trainer.train should have been called"
    assert captured[0] == 50, (
        f"Tree was trained on {captured[0]} rows; all 50 should be used (no downsampling)"
    )


def test_tree_downsampling_is_deterministic():
    """TreeInfluenceAnalyzer produces identical factors when called twice on the same data."""
    data, labels = _make_large_dataframe(2000)
    settings = {"profiling.tree_training.target_rows": 100}

    analyzer1 = TreeInfluenceAnalyzer()
    factors1 = analyzer1.analyze(
        data, labels, exclude_cols=[], outcome_col="outcome", settings=settings
    )

    analyzer2 = TreeInfluenceAnalyzer()
    factors2 = analyzer2.analyze(
        data, labels, exclude_cols=[], outcome_col="outcome", settings=settings
    )

    assert len(factors1) == len(factors2), "Same data must yield the same number of factors"
    for f1, f2 in zip(factors1, factors2):
        assert f1.name == f2.name, f"Factor names diverged: {f1.name} vs {f2.name}"
        assert f1.strength == pytest.approx(f2.strength, rel=1e-6), (
            f"Factor strengths diverged for {f1.name}: {f1.strength} vs {f2.strength}"
        )


def test_tree_downsampling_respects_custom_target_rows(monkeypatch):
    """profiling.tree_training.target_rows setting controls the row cap."""
    data, labels = _make_large_dataframe(2000)

    captured: list[int] = []
    analyzer = TreeInfluenceAnalyzer()
    original_train = analyzer._trainer.train

    def capturing_train(d, lbl, **kwargs):
        captured.append(len(d))
        return original_train(d, lbl, **kwargs)

    monkeypatch.setattr(analyzer._trainer, "train", capturing_train)

    # Use a non-default cap of 150
    settings = {"profiling.tree_training.target_rows": 150}
    analyzer.analyze(
        data, labels, exclude_cols=[], outcome_col="outcome", settings=settings
    )

    assert captured, "trainer.train should have been called"
    assert captured[0] <= 150, (
        f"Tree was trained on {captured[0]} rows; expected ≤150"
    )
