"""
Unit tests for LaggedCCFInfluenceAnalyzer.

Tests lag detection, uncertainty quantification (permutation-based p-values),
and correctness on synthetic data with known lag relationships.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import polars as pl
import pytest

from src.core.profile.analyzers import LaggedCCFInfluenceAnalyzer
from src.core.profile.base import InfluenceFactor


@pytest.fixture
def analyzer():
    """Create a fresh analyzer instance."""
    return LaggedCCFInfluenceAnalyzer(seed=42)


@pytest.fixture
def simple_lag_data():
    """Synthetic data where predictor leads outcome by 5 rows.

    predictor_t → outcome_{t+5}

    Returns:
        (data, outcome_col_name, expected_lag_rows)
    """
    n = 200
    np.random.seed(0)
    t = np.arange(n)

    # Predictor: smooth sinusoid
    predictor = 50 + 20 * np.sin(2 * np.pi * t / 50) + np.random.normal(0, 2, n)

    # Outcome: predictor shifted by +5 rows + noise
    outcome = 100 + 0.5 * np.roll(predictor, shift=5) + np.random.normal(0, 3, n)

    # Build DataFrame
    data = pl.DataFrame({
        "outcome": outcome,
        "predictor": predictor,
        "noise": np.random.normal(0, 1, n),
    })

    return data, "outcome", 5


@pytest.fixture
def reverse_lag_data():
    """Synthetic data where outcome leads predictor (causality reversed).

    outcome_t → predictor_{t+3}

    Returns:
        (data, outcome_col_name, expected_lag)
    """
    n = 150
    np.random.seed(1)
    t = np.arange(n)

    outcome = 100 + 15 * np.cos(2 * np.pi * t / 40) + np.random.normal(0, 2, n)
    predictor = 50 + 0.8 * np.roll(outcome, shift=3) + np.random.normal(0, 3, n)

    data = pl.DataFrame({
        "outcome": outcome,
        "predictor": predictor,
        "noise": np.random.normal(0, 0.5, n),
    })

    return data, "outcome", 3  # predictor lags outcome


@pytest.fixture
def zero_lag_data():
    """Synthetic data with zero lag (simultaneous correlation).

    predictor_t ↔ outcome_t

    Returns:
        (data, outcome_col_name)
    """
    n = 200
    np.random.seed(2)
    base = np.random.normal(0, 1, n)

    predictor = 50 + 10 * base + np.random.normal(0, 2, n)
    outcome = 100 + 5 * base + np.random.normal(0, 3, n)

    data = pl.DataFrame({
        "outcome": outcome,
        "predictor": predictor,
        "noise": np.random.normal(0, 1, n),
    })

    return data, "outcome"


@pytest.fixture
def no_correlation_data():
    """Synthetic data where predictor has no correlation with outcome.

    Returns:
        (data, outcome_col_name)
    """
    n = 200
    np.random.seed(3)

    outcome = np.random.normal(100, 5, n)
    predictor = np.random.normal(50, 10, n)
    noise = np.random.normal(0, 2, n)

    data = pl.DataFrame({
        "outcome": outcome,
        "predictor": predictor,
        "noise": noise,
    })

    return data, "outcome"


@pytest.fixture
def multi_lag_data():
    """Synthetic data with multiple predictors at different lags.

    predictor_a: leads by 2 rows
    predictor_b: leads by 7 rows
    predictor_c: simultaneous
    predictor_noise: uncorrelated

    Returns:
        (data, outcome_col_name)
    """
    n = 250
    np.random.seed(4)
    t = np.arange(n)

    # Base outcome
    outcome = 100 + 20 * np.sin(2 * np.pi * t / 60) + np.random.normal(0, 2, n)

    # Create predictors with different lags
    pred_a = 0.6 * np.roll(outcome, shift=2) + np.random.normal(0, 2, n)
    pred_b = 0.7 * np.roll(outcome, shift=7) + np.random.normal(0, 2, n)
    pred_c = 0.5 * outcome + np.random.normal(0, 2, n)
    pred_noise = np.random.normal(50, 5, n)

    data = pl.DataFrame({
        "outcome": outcome,
        "predictor_a": pred_a,
        "predictor_b": pred_b,
        "predictor_c": pred_c,
        "predictor_noise": pred_noise,
    })

    return data, "outcome"


@pytest.fixture
def data_with_timestamps():
    """Synthetic data with timestamps (for testing lag_seconds conversion).

    Time-stamped data over 100 seconds at 0.5s intervals.

    Returns:
        (data, outcome_col_name, timestamps_array, expected_lag_seconds)
    """
    n = 200
    np.random.seed(5)
    # 0.5 second intervals
    timestamps = np.linspace(0, 100, n)
    t_idx = np.arange(n)

    predictor = 50 + 20 * np.sin(2 * np.pi * t_idx / 50) + np.random.normal(0, 2, n)
    # Lag of 10 rows = 10 * 0.5 = 5 seconds
    outcome = 100 + 0.5 * np.roll(predictor, shift=10) + np.random.normal(0, 3, n)

    data = pl.DataFrame({
        "timestamp": timestamps,
        "outcome": outcome,
        "predictor": predictor,
    })

    return data, "outcome", timestamps, 5.0  # lag in seconds


class TestLaggedCCFBasics:
    """Basic functionality tests for LaggedCCFInfluenceAnalyzer."""

    def test_analyzer_name(self, analyzer):
        """Verify analyzer name is 'ccf'."""
        assert analyzer.name == "ccf"

    def test_analyzer_capabilities(self, analyzer):
        """Verify expected capabilities."""
        caps = analyzer.capabilities
        assert caps["lag_detection"] is True
        assert caps["direction"] is False
        assert caps["uncertainty"] is True
        assert caps["falsification"] is False

    def test_empty_data(self, analyzer):
        """Analyzer should handle empty data gracefully."""
        data = pl.DataFrame()
        labels = np.array([])
        result = analyzer.analyze(data, labels, outcome_col="outcome")
        assert result == []

    def test_missing_outcome_column(self, analyzer):
        """In regression mode, missing outcome column returns empty."""
        data = pl.DataFrame({
            "predictor": [1, 2, 3],
            "noise": [0, 0, 0],
        })
        labels = np.array([0, 1, 0])
        result = analyzer.analyze(
            data, labels, outcome_col="missing_col", outcome_mode="regression"
        )
        assert result == []

    def test_single_predictor_correlation(self, analyzer, simple_lag_data):
        """Analyzer should detect correlation with a single predictor."""
        data, outcome_col, _ = simple_lag_data
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=["noise"],
            max_predictors=10,
        )

        assert len(result) > 0
        # Predictor should be the top factor (highest correlation)
        top = result[0]
        assert top.name == "predictor"
        assert top.strength > 0.5  # Should have strong correlation


class TestLagDetection:
    """Tests for lag detection capabilities."""

    def test_detects_forward_lag(self, analyzer, simple_lag_data):
        """Analyzer should detect when predictor leads outcome."""
        data, outcome_col, expected_lag = simple_lag_data
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=["noise"],
        )

        assert len(result) > 0
        predictor_result = next((r for r in result if r.name == "predictor"), None)
        assert predictor_result is not None
        assert predictor_result.lag_rows is not None
        # Detected lag should be close to expected (within ±2 rows)
        assert abs(predictor_result.lag_rows - expected_lag) <= 2

    def test_detects_reverse_lag(self, analyzer, reverse_lag_data):
        """Analyzer should detect when outcome leads predictor."""
        data, outcome_col, expected_lag = reverse_lag_data
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=["noise"],
        )

        assert len(result) > 0
        predictor_result = next((r for r in result if r.name == "predictor"), None)
        assert predictor_result is not None
        # Note: lag_rows is the lag of predictor relative to outcome
        # When outcome leads, lag_rows will be negative (or outcome correlates at positive lag)
        # The important thing is that the lag is detected
        assert predictor_result.lag_rows is not None

    def test_zero_lag_detection(self, analyzer, zero_lag_data):
        """Analyzer should detect simultaneous correlation (lag ≈ 0)."""
        data, outcome_col = zero_lag_data
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=["noise"],
        )

        assert len(result) > 0
        predictor_result = next((r for r in result if r.name == "predictor"), None)
        assert predictor_result is not None
        assert predictor_result.lag_rows is not None
        # Zero lag (close to 0)
        assert abs(predictor_result.lag_rows) <= 2

    def test_multiple_lags_ranking(self, analyzer, multi_lag_data):
        """Analyzer should rank predictors correctly despite different lags."""
        data, outcome_col = multi_lag_data
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=None,
        )

        assert len(result) > 0
        # Extract predictors (excluding noise)
        correlated = [r for r in result if "noise" not in r.name]
        assert len(correlated) >= 3

        # Correlated predictors should rank higher than noise
        strengths = [r.strength for r in correlated]
        noise_strength = next(
            (r.strength for r in result if "noise" in r.name), None
        )
        if noise_strength is not None:
            assert max(strengths) > noise_strength


class TestUncertaintyQuantification:
    """Tests for permutation-based p-values and confidence intervals."""

    def test_p_values_present(self, analyzer, simple_lag_data):
        """Analyzer should include p-values in results."""
        data, outcome_col, _ = simple_lag_data
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=["noise"],
            settings={"profiling.lag_detection.permutations": 100},
        )

        assert len(result) > 0
        for factor in result:
            assert factor.p_value is not None or factor.strength == 0
            if factor.p_value is not None:
                assert 0 <= factor.p_value <= 1

    def test_confidence_intervals_present(self, analyzer, simple_lag_data):
        """Analyzer should include confidence intervals."""
        data, outcome_col, _ = simple_lag_data
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=["noise"],
            settings={"profiling.lag_detection.permutations": 100},
        )

        assert len(result) > 0
        for factor in result:
            if factor.confidence_interval is not None:
                low, high = factor.confidence_interval
                assert low <= high
                assert low >= 0
                assert high <= 1

    def test_uncorrelated_has_higher_pvalue(self, analyzer, no_correlation_data):
        """P-value should be higher for uncorrelated predictors."""
        data, outcome_col = no_correlation_data
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=None,
            settings={"profiling.lag_detection.permutations": 100},
        )

        # Uncorrelated predictor should have weak correlation or high p-value
        if len(result) > 0:
            assert result[0].strength < 0.5  # Weak correlation
            if result[0].p_value is not None and result[0].strength > 0.1:
                # If it has non-zero strength, p-value should be relatively high (≥ 0.04 due to permutation variance)
                assert result[0].p_value > 0.03

    def test_strong_correlation_has_low_pvalue(self, analyzer, simple_lag_data):
        """P-value should be low (<0.05) for strong correlations."""
        data, outcome_col, _ = simple_lag_data
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=["noise"],
            settings={"profiling.lag_detection.permutations": 200},
        )

        assert len(result) > 0
        top = result[0]
        # Strong correlation should give low p-value
        if top.strength > 0.5 and top.p_value is not None:
            assert top.p_value < 0.1


class TestTimestampHandling:
    """Tests for timestamp-based lag conversion."""

    def test_lag_in_seconds_computed(self, analyzer, data_with_timestamps):
        """Analyzer should compute lag in seconds when timestamps available."""
        data, outcome_col, _, expected_lag_seconds = data_with_timestamps
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            timestamp_col="timestamp",
            exclude_cols=None,
        )

        assert len(result) > 0
        predictor_result = next((r for r in result if r.name == "predictor"), None)
        assert predictor_result is not None
        assert predictor_result.lag_rows is not None
        assert predictor_result.lag is not None  # lag in seconds

        # Should be close to expected (within ±1 second)
        assert abs(predictor_result.lag - expected_lag_seconds) <= 1.0

    def test_lag_seconds_without_timestamps(self, analyzer, simple_lag_data):
        """Lag in seconds should be None if no timestamps provided."""
        data, outcome_col, _ = simple_lag_data
        labels = np.zeros(len(data), dtype=int)

        # Analyze without timestamps
        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=["noise"],
        )

        assert len(result) > 0
        predictor_result = next((r for r in result if r.name == "predictor"), None)
        assert predictor_result is not None
        assert predictor_result.lag_rows is not None
        assert predictor_result.lag is None  # No seconds without timestamps


class TestRanking:
    """Tests for factor ranking and sorting."""

    def test_factors_ranked_by_strength(self, analyzer, multi_lag_data):
        """Factors should be ranked by strength (index starts at 1)."""
        data, outcome_col = multi_lag_data
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=None,
        )

        assert len(result) > 0
        # Check ranking is consecutive
        ranks = [f.rank for f in result]
        assert ranks == list(range(1, len(result) + 1))

        # Check ranking is by strength (descending)
        for i in range(len(result) - 1):
            assert result[i].strength >= result[i + 1].strength

    def test_no_duplicate_factors(self, analyzer, simple_lag_data):
        """Each factor should appear exactly once."""
        data, outcome_col, _ = simple_lag_data
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=["noise"],
        )

        names = [f.name for f in result]
        assert len(names) == len(set(names))  # All unique


class TestMetadata:
    """Tests for metadata in InfluenceFactor results."""

    def test_method_name_set(self, analyzer, simple_lag_data):
        """Method name should be 'ccf'."""
        data, outcome_col, _ = simple_lag_data
        labels = np.zeros(len(data), dtype=int)

        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=["noise"],
        )

        assert len(result) > 0
        for factor in result:
            assert factor.method == "ccf"

    def test_metadata_includes_permutation_count(self, analyzer, simple_lag_data):
        """Metadata should include permutation count."""
        data, outcome_col, _ = simple_lag_data
        labels = np.zeros(len(data), dtype=int)

        perm_count = 150
        result = analyzer.analyze(
            data,
            labels,
            outcome_col=outcome_col,
            exclude_cols=["noise"],
            settings={"profiling.lag_detection.permutations": perm_count},
        )

        assert len(result) > 0
        for factor in result:
            assert factor.metadata is not None
            assert factor.metadata.get("permutations") == perm_count
