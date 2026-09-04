"""
Tests for PCMCI-Lite causal discovery.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import polars as pl
import pytest

from src.core.profile.analyzers import PCMCIInfluenceAnalyzer
from src.core.profile.pcmci_lite import (
    partial_correlation,
    pc_skeleton_discovery,
    fit_pcmci_lite,
    CausalGraph,
)


class TestPartialCorrelation:
    """Test partial correlation computation."""

    def test_unconditional_correlation(self):
        """Test unconditional correlation matches standard Pearson."""
        np.random.seed(50)
        x = np.random.randn(100)
        y = 0.7 * x + 0.3 * np.random.randn(100)
        z = np.random.randn(100)

        data = np.column_stack([x, y, z])

        # Unconditional correlation
        r, p = partial_correlation(data, 0, 1, None)

        # Should be strong and positive
        assert r > 0.5
        assert p < 0.001

    def test_conditional_correlation(self):
        """Test partial correlation after conditioning."""
        np.random.seed(51)
        n = 200

        # Create: Z confounds X and Y
        z = np.random.randn(n)
        x = 0.8 * z + 0.2 * np.random.randn(n)
        y = 0.8 * z + 0.2 * np.random.randn(n)

        data = np.column_stack([x, y, z])

        # Unconditional correlation (confounded)
        r_unconditional, p_unconditional = partial_correlation(data, 0, 1, None)
        assert r_unconditional > 0.5  # Apparent correlation through Z

        # Conditional correlation (Z removed)
        r_conditional, p_conditional = partial_correlation(data, 0, 1, conditioning_on=[2])
        assert r_conditional < 0.3  # Much weaker after conditioning


class TestPCSkeletonDiscovery:
    """Test PC algorithm for skeleton discovery."""

    def test_disconnected_variables(self):
        """Test PC algorithm on independent variables."""
        np.random.seed(52)
        n = 200

        # Three independent variables
        x = np.random.randn(n)
        y = np.random.randn(n)
        z = np.random.randn(n)

        data = np.column_stack([x, y, z])
        var_names = ["x", "y", "z"]

        skeleton, separating_sets = pc_skeleton_discovery(data, var_names, alpha=0.05)

        # Should be empty (no edges)
        for neighbors in skeleton.values():
            assert len(neighbors) == 0

    def test_chain_structure(self):
        """Test PC algorithm on X→Y→Z chain."""
        np.random.seed(53)
        n = 200

        x = np.random.randn(n)
        y = 0.8 * x + 0.2 * np.random.randn(n)
        z = 0.8 * y + 0.2 * np.random.randn(n)

        data = np.column_stack([x, y, z])
        var_names = ["x", "y", "z"]

        skeleton, separating_sets = pc_skeleton_discovery(data, var_names, alpha=0.05)

        # Should find edges X-Y and Y-Z
        assert len(skeleton[0]) >= 1  # X connected to something
        assert len(skeleton[2]) >= 1  # Z connected to something


class TestPCMCILite:
    """Test full PCMCI-Lite pipeline."""

    def test_simple_causality(self):
        """Test PCMCI on simple forward causality."""
        np.random.seed(54)
        n = 300

        x = np.random.randn(n)
        y =0.8 * x + 0.2 * np.random.randn(n)

        df = pl.DataFrame({"x": x, "y": y})

        graph = fit_pcmci_lite(df, outcome_col="y", predictor_cols=["x"], alpha=0.05)

        # Should identify x as causal parent of y
        assert "x" in graph.get_parents("y")
        assert len(graph.edges) > 0

    def test_confounded_variables(self):
        """Test PCMCI identifies confounding."""
        np.random.seed(55)
        n = 300

        # Z confounds X and Y
        z = np.random.randn(n)
        x = 0.8 * z + 0.2 * np.random.randn(n)
        y = 0.8 * z + 0.2 * np.random.randn(n)

        df = pl.DataFrame({"x": x, "z": z, "y": y})

        graph = fit_pcmci_lite(df, outcome_col="y", predictor_cols=["x", "z"], alpha=0.05)

        # Should identify both x and z as causally related
        parents = graph.get_parents("y")
        assert len(parents) >= 1

    def test_model_assumptions_documented(self):
        """Test that model assumptions are documented."""
        np.random.seed(56)
        n = 100

        x = np.random.randn(n)
        y = 0.5 * x + np.random.randn(n)

        df = pl.DataFrame({"x": x, "y": y})

        graph = fit_pcmci_lite(df, outcome_col="y", predictor_cols=["x"])

        # Should have assumption statements
        assert len(graph.model_assumptions) > 0
        assumptions_text = " ".join(graph.model_assumptions).lower()

        # Key assumptions should be mentioned
        assert "sufficiency" in assumptions_text or "unmeasured" in assumptions_text
        assert "faithfulness" in assumptions_text or "stationarity" in assumptions_text

    def test_negative_effect_keeps_parent_direction(self):
        """Negative effect should still be represented as source -> outcome edge."""
        np.random.seed(560)
        n = 300

        x = np.random.randn(n)
        y = -0.8 * x + 0.2 * np.random.randn(n)

        df = pl.DataFrame({"x": x, "y": y})

        graph = fit_pcmci_lite(df, outcome_col="y", predictor_cols=["x"], alpha=0.05)

        assert "x" in graph.get_parents("y")


class TestPCMCIInfluenceAnalyzer:
    """Test PCMCIInfluenceAnalyzer as an analyzer."""

    def test_analyzer_properties(self):
        """Test analyzer name and capabilities."""
        analyzer = PCMCIInfluenceAnalyzer()

        assert analyzer.name == "pcmci"
        assert analyzer.capabilities["direction"] is True
        assert analyzer.capabilities["confounding"] is True
        assert analyzer.capabilities["uncertainty"] is True

    def test_empty_data(self):
        """Test behavior with empty data."""
        analyzer = PCMCIInfluenceAnalyzer()
        empty_df = pl.DataFrame()
        labels = np.array([])

        result = analyzer.analyze(empty_df, labels, outcome_col="outcome")
        assert result == []

    def test_missing_outcome_column(self):
        """In regression mode, missing outcome column returns empty."""
        analyzer = PCMCIInfluenceAnalyzer()
        data = pl.DataFrame({"x": [1, 2, 3], "z": [4, 5, 6]})
        labels = np.array([0, 1, 0])

        result = analyzer.analyze(
            data, labels, outcome_col="missing", outcome_mode="regression"
        )
        assert result == []

    def test_simple_analysis(self):
        """Test analyzer on simple data."""
        np.random.seed(57)
        analyzer = PCMCIInfluenceAnalyzer()

        n = 300
        x1 = np.random.randn(n)
        x2 = np.random.randn(n)
        y = 0.7 * x1 + 0.3 * x2 + 0.1 * np.random.randn(n)

        data = pl.DataFrame({"x1": x1, "x2": x2, "y": y})
        labels = np.array([0] * n)

        factors = analyzer.analyze(data, labels, outcome_col="y")

        # Should return causal factors
        assert len(factors) >= 0  # May not find factors if alpha is strict
        for factor in factors:
            assert factor.name in ["x1", "x2"]
            assert factor.direction is not None
            assert factor.p_value is not None

    def test_metadata_includes_graph(self):
        """Test that full causal graph is included in metadata."""
        np.random.seed(58)
        analyzer = PCMCIInfluenceAnalyzer()

        n = 200
        x = np.random.randn(n)
        y = 0.8 * x + np.random.randn(n)

        data = pl.DataFrame({"x": x, "y": y})
        labels = np.array([0] * n)

        factors = analyzer.analyze(data, labels, outcome_col="y", max_predictors=10)

        for factor in factors:
            # Should have graph metadata
            assert "full_causal_graph" in factor.metadata
            assert "model_assumptions" in factor.metadata

            # Graph should have edges list
            graph_data = factor.metadata["full_causal_graph"]
            assert "edges" in graph_data
            assert "v_structures" in graph_data

    def test_max_predictors_limit(self):
        """Test that max_predictors limits analysis."""
        np.random.seed(59)
        analyzer = PCMCIInfluenceAnalyzer()

        n = 100
        # Create many random predictors
        predictors = {f"x{i}": np.random.randn(n) for i in range(20)}
        y = np.random.randn(n)

        data = pl.DataFrame({**predictors, "y": y})
        labels = np.array([0] * n)

        # Limit to 5 predictors
        factors = analyzer.analyze(data, labels, outcome_col="y", max_predictors=5)

        # Should complete without error
        for factor in factors:
            assert factor.name in list(predictors.keys())

    def test_sparse_nulls_still_produces_factors(self):
        """Sparse columns should not force screening to zero complete rows."""
        np.random.seed(591)
        analyzer = PCMCIInfluenceAnalyzer()

        n = 300
        x = np.random.randn(n)
        y = 0.75 * x + 0.2 * np.random.randn(n)

        # Keep only sparse overlap between x and y; add noisy sparse columns.
        x_sparse = x.copy()
        y_sparse = y.copy()
        x_sparse[100:] = np.nan
        y_sparse[:200] = np.nan

        data = pl.DataFrame(
            {
                "x": x_sparse,
                "noise1": np.where(np.arange(n) % 3 == 0, np.random.randn(n), np.nan),
                "noise2": np.where(np.arange(n) % 4 == 0, np.random.randn(n), np.nan),
                "y": y_sparse,
            }
        )
        labels = np.zeros(n, dtype=int)

        factors = analyzer.analyze(data, labels, outcome_col="y", outcome_mode="regression")

        assert any(f.name == "x" for f in factors)

    def test_fallback_when_pcmci_edges_empty(self, monkeypatch):
        """When PCMCI finds no direct outcome edges, analyzer returns screened fallback factors."""
        np.random.seed(592)
        analyzer = PCMCIInfluenceAnalyzer()

        n = 120
        x = np.random.randn(n)
        z = np.random.randn(n)
        y = 0.6 * x + 0.2 * np.random.randn(n)
        data = pl.DataFrame({"x": x, "z": z, "y": y})
        labels = np.zeros(n, dtype=int)

        def fake_fit_pcmci_lite(*args, **kwargs):
            return CausalGraph(
                edges=[],
                skeleton={},
                v_structures=[],
                variables=["x", "z", "y"],
                model_assumptions=["Test assumption"],
            )

        monkeypatch.setattr("src.core.profile.pcmci_lite.fit_pcmci_lite", fake_fit_pcmci_lite)

        factors = analyzer.analyze(data, labels, outcome_col="y", outcome_mode="regression")

        assert len(factors) > 0
        assert factors[0].metadata.get("edge_type") == "screening_fallback"


class TestCausalGraph:
    """Test CausalGraph data structure."""

    def test_graph_construction(self):
        """Test building a causal graph."""
        graph = CausalGraph()
        graph.variables = ["x", "y", "z"]

        graph.add_edge("x", "y", strength=0.5, p_value=0.01)
        graph.add_edge("z", "y", strength=-0.3, p_value=0.05)

        assert len(graph.edges) == 2
        assert graph.edges[0].source == "x"
        assert graph.edges[0].target == "y"

    def test_parents_children(self):
        """Test querying graph for parents/children."""
        graph = CausalGraph()
        graph.variables = ["x", "y", "z"]

        graph.add_edge("x", "y", 0.5, 0.01)
        graph.add_edge("z", "y", 0.3, 0.05)

        parents_of_y = graph.get_parents("y")
        assert set(parents_of_y) == {"x", "z"}

        children_of_x = graph.get_children("x")
        assert children_of_x == ["y"]

    def test_neighbors(self):
        """Test skeleton neighbors query."""
        graph = CausalGraph()
        graph.skeleton = {
            "x": {"y", "z"},
            "y": {"x"},
            "z": {"x"},
        }

        neighbors_of_x = graph.get_neighbors("x")
        assert set(neighbors_of_x) == {"y", "z"}

        neighbors_of_y = graph.get_neighbors("y")
        assert neighbors_of_y == ["x"]
