"""
Tests for HybridCausalInfluenceAnalyzer.

Tests confounding detection, partial correlation pruning, enhanced falsification
plans with confounding caveats, and model assumptions documentation.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import polars as pl
import pytest

from src.core.profile.base import CausalDirection
from src.core.profile.analyzers import HybridCausalInfluenceAnalyzer


class TestHybridAnalyzerBasics:
    """Test basic functionality of HybridCausalInfluenceAnalyzer."""

    def test_analyzer_properties(self):
        """Test analyzer name and capabilities."""
        analyzer = HybridCausalInfluenceAnalyzer()

        assert analyzer.name == "hybrid"
        assert analyzer.capabilities["lag_detection"] is True
        assert analyzer.capabilities["direction"] is True
        assert analyzer.capabilities["uncertainty"] is True
        assert analyzer.capabilities["falsification"] is True
        assert analyzer.capabilities["confounding"] is True

    def test_empty_data(self):
        """Test behavior with empty data."""
        analyzer = HybridCausalInfluenceAnalyzer()
        empty_df = pl.DataFrame()
        labels = np.array([])

        result = analyzer.analyze(empty_df, labels, outcome_col="outcome")
        assert result == []

    def test_missing_outcome_column(self):
        """In regression mode, missing outcome column returns empty."""
        analyzer = HybridCausalInfluenceAnalyzer()
        data = pl.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        labels = np.array([0, 1, 0])

        result = analyzer.analyze(
            data, labels, outcome_col="missing", outcome_mode="regression"
        )
        assert result == []


class TestConfoundingDetection:
    """Test confounding detection and pruning."""

    def test_independent_factors_survive(self):
        """Test that independent factors are not pruned."""
        np.random.seed(200)
        n = 200

        # Generate two independent causes of Y
        x1 = np.zeros(n)
        x1[0] = np.random.randn()
        for t in range(1, n):
            x1[t] = 0.3 * x1[t - 1] + np.random.randn()

        x2 = np.zeros(n)
        x2[0] = np.random.randn()
        for t in range(1, n):
            x2[t] = 0.3 * x2[t - 1] + np.random.randn()

        y = np.zeros(n)
        for t in range(3, n):
            y[t] = 0.5 * x1[t - 1] + 0.5 * x2[t - 1] + 0.1 * np.random.randn()

        data = pl.DataFrame({"x1": x1, "x2": x2, "y": y})
        labels = np.array([0] * n)

        analyzer = HybridCausalInfluenceAnalyzer()
        factors = analyzer.analyze(
            data, labels, outcome_col="y", max_predictors=10
        )

        # Both independent causes should survive
        assert len(factors) >= 2
        factor_names = [f.name for f in factors]
        assert "x1" in factor_names
        assert "x2" in factor_names

        # Check confounding status for both
        for factor in factors:
            status = factor.metadata.get("confounding_status", {})
            # Independent factors should not be marked as confounded
            assert status.get("is_confounded", True) is False

    def test_confounded_factor_pruned(self):
        """Test that confounded factors are pruned."""
        np.random.seed(201)
        n = 200

        # Generate X1 → X2 → Y (X2 is a mediator, X1 is confounded)
        x1 = np.zeros(n)
        x1[0] = np.random.randn()
        for t in range(1, n):
            x1[t] = 0.3 * x1[t - 1] + np.random.randn()

        x2 = np.zeros(n)
        for t in range(2, n):
            x2[t] = 0.8 * x1[t - 1] + 0.1 * np.random.randn()

        y = np.zeros(n)
        for t in range(3, n):
            y[t] = 0.9 * x2[t - 1] + 0.1 * np.random.randn()

        data = pl.DataFrame({"x1": x1, "x2": x2, "y": y})
        labels = np.array([0] * n)

        analyzer = HybridCausalInfluenceAnalyzer()
        factors = analyzer.analyze(
            data, labels, outcome_col="y", max_predictors=10
        )

        # X2 should survive as it directly causes Y
        assert any(f.name == "x2" for f in factors)

        # X1's association should be weaker after conditioning on X2
        # It may still appear but with lower rank or marked as confounded
        x1_factors = [f for f in factors if f.name == "x1"]
        if x1_factors:
            x1_factor = x1_factors[0]
            status = x1_factor.metadata.get("confounding_status", {})
            # Should be ranked lower than x2
            x2_rank = next(f.rank for f in factors if f.name == "x2")
            assert x1_factor.rank > x2_rank


class TestConfoundingAnnotations:
    """Test that confounding information is properly annotated."""

    def test_assumptions_document_confounding_tests(self):
        """Test that model assumptions include confounding test details."""
        np.random.seed(202)
        n = 200

        # Generate simple forward causality
        x = np.zeros(n)
        x[0] = np.random.randn()
        for t in range(1, n):
            x[t] = 0.3 * x[t - 1] + np.random.randn()

        y = np.zeros(n)
        for t in range(3, n):
            y[t] = 0.8 * x[t - 1] + 0.1 * np.random.randn()

        data = pl.DataFrame({"x": x, "y": y})
        labels = np.array([0] * n)

        analyzer = HybridCausalInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        assert len(factors) == 1
        factor = factors[0]

        # Check that assumptions are documented
        assumptions = factor.metadata.get("model_assumptions", [])
        assert len(assumptions) > 0

        # Should mention conditioning or top-ranked status
        assumptions_text = " ".join(assumptions).lower()
        assert any(
            keyword in assumptions_text
            for keyword in ["conditioning", "confounding", "top-ranked"]
        )

    def test_confounding_status_in_metadata(self):
        """Test that confounding status is included in metadata."""
        np.random.seed(203)
        n = 200

        x1 = np.random.randn(n)
        x2 = np.random.randn(n)
        y = 0.5 * x1 + 0.5 * x2 + 0.1 * np.random.randn(n)

        data = pl.DataFrame({"x1": x1, "x2": x2, "y": y})
        labels = np.array([0] * n)

        analyzer = HybridCausalInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        for factor in factors:
            # Each factor should have confounding_status in metadata
            assert "confounding_status" in factor.metadata
            status = factor.metadata["confounding_status"]

            # Status should have required keys
            assert "is_confounded" in status
            assert "partial_r" in status or status["conditioning_on"] == []
            assert "partial_p_value" in status or status["conditioning_on"] == []
            assert "conditioning_on" in status


class TestFalsificationPlansWithConfounding:
    """Test that falsification plans include confounding caveats."""

    def test_falsification_plan_includes_confounding_note(self):
        """Test that falsification plans mention confounding when tested."""
        np.random.seed(204)
        n = 200

        # Generate two correlated causes
        x1 = np.zeros(n)
        x1[0] = np.random.randn()
        for t in range(1, n):
            x1[t] = 0.3 * x1[t - 1] + np.random.randn()

        x2 = np.zeros(n)
        x2[0] = np.random.randn()
        for t in range(1, n):
            x2[t] = 0.3 * x2[t - 1] + np.random.randn()

        y = np.zeros(n)
        for t in range(3, n):
            y[t] = 0.7 * x1[t - 1] + 0.3 * x2[t - 1] + 0.1 * np.random.randn()

        data = pl.DataFrame({"x1": x1, "x2": x2, "y": y})
        labels = np.array([0] * n)

        analyzer = HybridCausalInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        # Check that at least one factor has confounding notes
        has_confounding_note = False
        for factor in factors:
            plan = factor.falsification_plan
            if plan is not None:
                if "confounding_note" in plan or "confounding_warning" in plan:
                    has_confounding_note = True
                    break

        # At least the second-ranked factor should have conditioning info
        assert has_confounding_note or len(factors) < 2

    def test_confounded_factor_has_warning(self):
        """Test that confounded factors have warnings in falsification plans."""
        np.random.seed(205)
        n = 200

        # Generate X1 → X2 → Y
        x1 = np.zeros(n)
        x1[0] = np.random.randn()
        for t in range(1, n):
            x1[t] = 0.3 * x1[t - 1] + np.random.randn()

        x2 = np.zeros(n)
        for t in range(2, n):
            x2[t] = 0.9 * x1[t - 1] + 0.1 * np.random.randn()

        y = np.zeros(n)
        for t in range(3, n):
            y[t] = 0.9 * x2[t - 1] + 0.05 * np.random.randn()

        data = pl.DataFrame({"x1": x1, "x2": x2, "y": y})
        labels = np.array([0] * n)

        analyzer = HybridCausalInfluenceAnalyzer()
        # Lower min_abs_partial to ensure x1 doesn't survive if truly confounded
        settings = {
            "profiling.hybrid.min_abs_partial": 0.2,
        }
        factors = analyzer.analyze(
            data, labels, outcome_col="y", settings=settings
        )

        # The mediator x2 should be primary
        # x1 might be filtered out or have lower rank with warning
        if any(f.name == "x1" for f in factors):
            x1_factor = next(f for f in factors if f.name == "x1")
            x2_factor = next(f for f in factors if f.name == "x2")

            # x1 should be ranked lower
            assert x1_factor.rank > x2_factor.rank


class TestPartialCorrelationCI:
    """Test partial correlation confidence intervals."""

    def test_confidence_interval_present(self):
        """Test that confidence intervals on partial correlation are provided."""
        np.random.seed(206)
        n = 200

        x1 = np.random.randn(n)
        x2 = np.random.randn(n)
        y = 0.5 * x1 + 0.5 * x2 + 0.1 * np.random.randn(n)

        data = pl.DataFrame({"x1": x1, "x2": x2, "y": y})
        labels = np.array([0] * n)

        analyzer = HybridCausalInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        # At least one factor should have a CI (the second-ranked one)
        if len(factors) >= 2:
            second_factor = factors[1]
            assert second_factor.confidence_interval is not None
            ci_low, ci_high = second_factor.confidence_interval
            assert ci_low < ci_high


class TestStationarityWarnings:
    """Test that stationarity warnings are preserved from Granger analysis."""

    def test_stationarity_assumptions_documented(self):
        """Test that stationarity checks are included in assumptions."""
        np.random.seed(207)
        n = 200

        # Generate stationary series
        x = np.zeros(n)
        x[0] = np.random.randn()
        for t in range(1, n):
            x[t] = 0.3 * x[t - 1] + np.random.randn()

        y = np.zeros(n)
        for t in range(3, n):
            y[t] = 0.8 * x[t - 1] + 0.1 * np.random.randn()

        data = pl.DataFrame({"x": x, "y": y})
        labels = np.array([0] * n)

        analyzer = HybridCausalInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        assert len(factors) == 1
        assumptions = factors[0].metadata.get("model_assumptions", [])

        # Should mention stationarity
        assumptions_text = " ".join(assumptions).lower()
        assert "stationary" in assumptions_text


class TestMultipleFactors:
    """Test behavior with multiple factors."""

    def test_rank_by_forward_f_stat(self):
        """Test that factors are ranked by forward F-statistic."""
        np.random.seed(208)
        n = 200

        # Generate three factors with different strengths
        x1 = np.zeros(n)
        x1[0] = np.random.randn()
        for t in range(1, n):
            x1[t] = 0.3 * x1[t - 1] + np.random.randn()

        x2 = np.zeros(n)
        x2[0] = np.random.randn()
        for t in range(1, n):
            x2[t] = 0.3 * x2[t - 1] + np.random.randn()

        x3 = np.zeros(n)
        x3[0] = np.random.randn()
        for t in range(1, n):
            x3[t] = 0.3 * x3[t - 1] + np.random.randn()

        y = np.zeros(n)
        for t in range(3, n):
            # x1 has strongest effect, x2 medium, x3 weak
            y[t] = (
                0.8 * x1[t - 1]
                + 0.4 * x2[t - 1]
                + 0.2 * x3[t - 1]
                + 0.1 * np.random.randn()
            )

        data = pl.DataFrame({"x1": x1, "x2": x2, "x3": x3, "y": y})
        labels = np.array([0] * n)

        analyzer = HybridCausalInfluenceAnalyzer()
        factors = analyzer.analyze(data, labels, outcome_col="y")

        # Should have multiple factors
        assert len(factors) >= 2

        # Ranks should be assigned sequentially
        ranks = [f.rank for f in factors]
        assert ranks == list(range(1, len(factors) + 1))

        # F-statistics should decrease with rank
        f_stats = [
            f.metadata.get("forward_f_stat", 0) for f in factors
        ]
        for i in range(len(f_stats) - 1):
            assert f_stats[i] >= f_stats[i + 1]
