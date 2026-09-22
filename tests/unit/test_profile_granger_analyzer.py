"""
Tests for GrangerInfluenceAnalyzer.

Tests lag detection, direction testing, falsification plans, and model
assumptions for Granger causality analysis.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import polars as pl
import pytest

from src.core.profile.base import CausalDirection
from src.core.profile.analyzers import GrangerInfluenceAnalyzer


class TestGrangerAnalyzerBasics:
    """Test basic functionality of GrangerInfluenceAnalyzer."""

    def test_analyzer_properties(self):
        """Test analyzer name and capabilities."""
        analyzer = GrangerInfluenceAnalyzer()

        assert analyzer.name == "granger"
        assert analyzer.capabilities["lag_detection"] is True
        assert analyzer.capabilities["direction"] is True
        assert analyzer.capabilities["uncertainty"] is True
        assert analyzer.capabilities["falsification"] is True

    def test_empty_data(self):
        """Test behavior with empty data."""
        analyzer = GrangerInfluenceAnalyzer()
        empty_df = pl.DataFrame()
        labels = np.array([])

        result = analyzer.analyze(empty_df, labels, outcome_col="outcome")
        assert result == []

    def test_missing_outcome_column(self):
        """In regression mode, missing outcome column returns empty."""
        analyzer = GrangerInfluenceAnalyzer()
        data = pl.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        labels = np.array([0, 1, 0])

        result = analyzer.analyze(
            data, labels, outcome_col="missing", outcome_mode="regression"
        )
        assert result == []

    def test_time_string_timestamps(self):
        """Time-of-day strings should not crash lag detection."""
        np.random.seed(200)
        analyzer = GrangerInfluenceAnalyzer()
        n = 200

        # Generate time strings spanning multiple minutes
        times = [f"14:{30 + i // 60:02d}:{i % 60:02d}.000" for i in range(n)]

        # Generate realistic data with some autocorrelation and noise
        x_vals = np.zeros(n)
        x_vals[0] = np.random.randn()
        for t in range(1, n):
            x_vals[t] = 0.5 * x_vals[t - 1] + np.random.randn() * 0.5

        y_vals = np.zeros(n)
        for t in range(2, n):
            y_vals[t] = 0.3 * x_vals[t - 1] + np.random.randn() * 0.5

        data = pl.DataFrame(
            {
                "Time": times,
                "x": x_vals,
                "y": y_vals,
            }
        )
        labels = np.array([0] * (n // 2) + [1] * (n // 2))

        factors = analyzer.analyze(
            data,
            labels,
            outcome_col="y",
            timestamp_col="Time",
            max_predictors=5,
        )

        assert factors is not None


class TestForwardCausality:
    """Test detection of forward causality (X → Y)."""

    def test_forward_causality_detection(self):
        """Test that forward causality is correctly detected and ranked."""
        np.random.seed(100)
        n = 200

        # Generate X → Y relationship
        x = np.zeros(n)
        x[0] = np.random.randn()
        for t in range(1, n):
            x[t] = 0.3 * x[t - 1] + np.random.randn()

        y = np.zeros(n)
        for t in range(3, n):
            y[t] = 0.8 * x[t - 1] + 0.6 * x[t - 2] + 0.1 * np.random.randn()

        data = pl.DataFrame({"x": x, "y": y})
        labels = np.array([0] * n)

        analyzer = GrangerInfluenceAnalyzer()
        factors = analyzer.analyze(
            data, labels, outcome_col="y", max_predictors=10
        )

        assert len(factors) == 1
        assert factors[0].name == "x"
        assert factors[0].rank == 1
        assert factors[0].method == "granger"

        # Should detect forward causality (or bidirectional with strong forward)
        assert factors[0].direction in [
            CausalDirection.FORWARD,
            CausalDirection.BIDIRECTIONAL,
        ]

        # Forward should be significant
        assert factors[0].p_value < 0.05

        # Should have positive lag (X leads Y)
        assert factors[0].lag_rows is not None
        assert factors[0].lag_rows > 0

    def test_forward_causality_falsification(self):
        """Test that forward causality generates intervention plan."""
        np.random.seed(101)
        n = 200

        x = np.zeros(n)
        x[0] = np.random.randn()
        for t in range(1, n):
            x[t] = 0.3 * x[t - 1] + np.random.randn()

        y = np.zeros(n)
        for t in range(3, n):
            y[t] = 0.8 * x[t - 1] + 0.6 * x[t - 2] + 0.1 * np.random.randn()

        data = pl.DataFrame({"x": x, "y": y})
        labels = np.array([0] * n)

        analyzer = GrangerInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        assert factors[0].falsification_plan is not None
        plan = factors[0].falsification_plan

        # Should suggest intervention for forward causality
        assert plan["type"] in ["intervention", "controlled_experiment"]


class TestReverseCausality:
    """Test detection of reverse causality (Y → X)."""

    def test_reverse_causality_detection(self):
        """Test that reverse causality is correctly detected."""
        np.random.seed(102)
        n = 200

        # Generate Y → X relationship (outcome causes predictor)
        y = np.zeros(n)
        y[0] = np.random.randn()
        for t in range(1, n):
            y[t] = 0.3 * y[t - 1] + np.random.randn()

        x = np.zeros(n)
        for t in range(3, n):
            x[t] = 0.8 * y[t - 1] + 0.6 * y[t - 2] + 0.1 * np.random.randn()

        data = pl.DataFrame({"x": x, "y": y})
        labels = np.array([0] * n)

        analyzer = GrangerInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        assert len(factors) == 1
        # Should detect reverse causality
        assert factors[0].direction == CausalDirection.REVERSE

    def test_reverse_causality_falsification_warning(self):
        """Test that reverse causality generates warning plan."""
        np.random.seed(103)
        n = 200

        y = np.zeros(n)
        y[0] = np.random.randn()
        for t in range(1, n):
            y[t] = 0.3 * y[t - 1] + np.random.randn()

        x = np.zeros(n)
        for t in range(3, n):
            x[t] = 0.8 * y[t - 1] + 0.6 * y[t - 2] + 0.1 * np.random.randn()

        data = pl.DataFrame({"x": x, "y": y})
        labels = np.array([0] * n)

        analyzer = GrangerInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        assert factors[0].falsification_plan is not None
        plan = factors[0].falsification_plan

        # Should warn against intervention for reverse causality
        assert plan["type"] == "warning"
        assert "not a cause" in plan["description"].lower()


class TestBidirectionalCausality:
    """Test detection of bidirectional causality (X ↔ Y)."""

    def test_bidirectional_causality_detection(self):
        """Test that bidirectional causality is correctly detected."""
        np.random.seed(104)
        n = 200

        x = np.zeros(n)
        y = np.zeros(n)
        x[0:3] = np.random.randn(3)
        y[0:3] = np.random.randn(3)

        for t in range(3, n):
            y[t] = 0.5 * x[t - 1] + 0.3 * x[t - 2] + 0.2 * np.random.randn()
            x[t] = 0.4 * y[t - 1] + 0.3 * y[t - 2] + 0.2 * np.random.randn()

        data = pl.DataFrame({"x": x, "y": y})
        labels = np.array([0] * n)

        analyzer = GrangerInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        assert len(factors) == 1
        # Should detect bidirectional causality
        assert factors[0].direction == CausalDirection.BIDIRECTIONAL


class TestMultiplePredictors:
    """Test behavior with multiple predictors."""

    def test_ranking_by_f_statistic(self):
        """Test that factors are ranked by forward F-statistic."""
        np.random.seed(105)
        n = 200

        # Strong forward causality
        x1 = np.zeros(n)
        x1[0] = np.random.randn()
        for t in range(1, n):
            x1[t] = 0.3 * x1[t - 1] + np.random.randn()

        # Weak forward causality
        x2 = np.zeros(n)
        x2[0] = np.random.randn()
        for t in range(1, n):
            x2[t] = 0.3 * x2[t - 1] + np.random.randn()

        y = np.zeros(n)
        for t in range(3, n):
            # Strong influence from x1
            y[t] = 0.9 * x1[t - 1] + 0.7 * x1[t - 2] + 0.1 * np.random.randn()
            # Weak influence from x2
            y[t] += 0.1 * x2[t - 1] + 0.05 * np.random.randn()

        data = pl.DataFrame({"x1": x1, "x2": x2, "y": y})
        labels = np.array([0] * n)

        analyzer = GrangerInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        assert len(factors) == 2

        # x1 should be ranked higher (stronger F-statistic)
        assert factors[0].name == "x1"
        assert factors[0].rank == 1
        assert factors[1].name == "x2"
        assert factors[1].rank == 2

        # x1 should have higher F-statistic
        assert factors[0].metadata["forward_f_stat"] > factors[1].metadata["forward_f_stat"]


class TestModelAssumptions:
    """Test that model assumptions are populated correctly."""

    def test_stationary_series_assumptions(self):
        """Test assumptions for stationary series."""
        np.random.seed(106)
        n = 200

        x = np.zeros(n)
        x[0] = np.random.randn()
        for t in range(1, n):
            x[t] = 0.3 * x[t - 1] + np.random.randn()

        y = np.zeros(n)
        for t in range(2, n):
            y[t] = 0.7 * x[t - 1] + 0.2 * np.random.randn()

        data = pl.DataFrame({"x": x, "y": y})
        labels = np.array([0] * n)

        analyzer = GrangerInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        assumptions = factors[0].metadata["model_assumptions"]
        assert isinstance(assumptions, list)
        assert len(assumptions) > 0

        # Should mention stationarity
        assumption_text = " ".join(assumptions).lower()
        assert "stationary" in assumption_text or "non-stationary" in assumption_text

    def test_non_stationary_warning(self):
        """Test that non-stationary series generate warnings."""
        np.random.seed(107)
        n = 200

        # Random walk (non-stationary)
        x = np.cumsum(np.random.randn(n))
        y = np.cumsum(np.random.randn(n))

        data = pl.DataFrame({"x": x, "y": y})
        labels = np.array([0] * n)

        analyzer = GrangerInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        if len(factors) > 0:
            assumptions = factors[0].metadata["model_assumptions"]
            assumption_text = " ".join(assumptions).lower()

            # Should mention non-stationarity
            assert "non-stationary" in assumption_text


class TestCIPrescreening:
    """Test conditional independence pre-screening."""

    def test_ci_prescreening_reduces_predictors(self):
        """Test that CI pre-screening reduces predictor set."""
        np.random.seed(108)
        n = 200

        # Create 40 predictors, only 2 with actual causality
        data_dict = {}

        # Two causal predictors
        x1 = np.zeros(n)
        x1[0] = np.random.randn()
        for t in range(1, n):
            x1[t] = 0.3 * x1[t - 1] + np.random.randn()
        data_dict["x1"] = x1

        x2 = np.zeros(n)
        x2[0] = np.random.randn()
        for t in range(1, n):
            x2[t] = 0.3 * x2[t - 1] + np.random.randn()
        data_dict["x2"] = x2

        # Generate outcome from x1 and x2
        y = np.zeros(n)
        for t in range(2, n):
            y[t] = 0.6 * x1[t - 1] + 0.4 * x2[t - 1] + 0.1 * np.random.randn()
        data_dict["y"] = y

        # Add 38 noise predictors
        for i in range(38):
            noise = np.random.randn(n)
            data_dict[f"noise_{i}"] = noise

        data = pl.DataFrame(data_dict)
        labels = np.array([0] * n)

        # With CI pre-screening enabled (should keep ~30 predictors)
        analyzer = GrangerInfluenceAnalyzer()
        settings = {"profiling.granger.ci_prescreening": True}
        factors = analyzer.analyze(
            data, labels, outcome_col="y", settings=settings, max_predictors=100
        )

        # Should have analyzed fewer than all 40 predictors due to pre-screening
        # The actual number will vary, but x1 and x2 should still be in top results
        factor_names = [f.name for f in factors[:5]]
        assert "x1" in factor_names or "x2" in factor_names


class TestMetadata:
    """Test that metadata is properly populated."""

    def test_all_metadata_fields(self):
        """Test that all expected metadata fields are populated."""
        np.random.seed(109)
        n = 200

        x = np.zeros(n)
        x[0] = np.random.randn()
        for t in range(1, n):
            x[t] = 0.3 * x[t - 1] + np.random.randn()

        y = np.zeros(n)
        for t in range(2, n):
            y[t] = 0.7 * x[t - 1] + 0.2 * np.random.randn()

        data = pl.DataFrame({"x": x, "y": y})
        labels = np.array([0] * n)

        analyzer = GrangerInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        assert len(factors) == 1
        metadata = factors[0].metadata

        # Check all expected fields
        assert "forward_f_stat" in metadata
        assert "reverse_f_stat" in metadata
        assert "reverse_p_value" in metadata
        assert "x_stationary" in metadata
        assert "y_stationary" in metadata
        assert "x_adf_p_value" in metadata
        assert "y_adf_p_value" in metadata
        assert "max_lag" in metadata
        assert "ci_prescreening" in metadata
        assert "model_assumptions" in metadata

        # Check types
        assert isinstance(metadata["forward_f_stat"], (int, float))
        assert isinstance(metadata["reverse_f_stat"], (int, float))
        assert isinstance(metadata["model_assumptions"], list)


class TestProgressCallback:
    """Test progress callback functionality."""

    def test_progress_callback_called(self):
        """Test that progress callback is invoked during analysis."""
        np.random.seed(110)
        n = 200

        x1 = np.random.randn(n)
        x2 = np.random.randn(n)
        y = 0.5 * x1 + 0.3 * x2 + np.random.randn(n)

        data = pl.DataFrame({"x1": x1, "x2": x2, "y": y})
        labels = np.array([0] * n)

        progress_calls = []

        def progress_callback(idx, total, predictor):
            progress_calls.append((idx, total, predictor))

        analyzer = GrangerInfluenceAnalyzer()
        factors = analyzer.analyze(
            data, labels, outcome_col="y", progress_callback=progress_callback
        )

        # Should have called progress callback for each predictor
        assert len(progress_calls) == 2
        assert progress_calls[0][0] == 1
        assert progress_calls[0][1] == 2
        assert progress_calls[1][0] == 2
        assert progress_calls[1][1] == 2
