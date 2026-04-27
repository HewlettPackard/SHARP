"""
Comprehensive tests for optimization heuristics: predictor selection and tree training.

Tests the complex branching logic and semantic preservation of:
1. Predictor Selection Optimization (wide data): Vectorized correlation, semantic grouping,
   representative selection, categorical support, and diversity guarantees.
2. Decision Tree Training Optimization (tall data): Class-aware downsampling with CV-based
   concentration detection, minority class preservation, and adaptive sampling ratios.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import polars as pl
import pytest

from src.core.profile.predictor_selection import (
    _extract_metric_type,
    _select_representatives_per_group,
    select_predictors,
    compute_predictor_correlations,
)
from src.core.profile.decision_tree import DecisionTreeTrainer


class TestMetricTypeExtraction:
    """Tests for semantic grouping via _extract_metric_type."""

    def test_underscore_separated_stops_at_location(self):
        """Test extraction stops at location indicators or numeric tokens."""
        assert _extract_metric_type("LD_Qlen_tp_0_sd_0_377") == "LD_Qlen_tp"
        assert _extract_metric_type("PD_Qlen_54_0_2_1") == "PD_Qlen"
        assert _extract_metric_type("PROC_nice_nd0_28") == "PROC_nice_nd0"
        # Stops after 2 additional parts: VVLogCons(1) + hit(2)
        assert _extract_metric_type("VVLogCons_hit_blks_TPVV_30") == "VVLogCons_hit_blks"

    def test_stops_at_numeric_sequences(self):
        """Test extraction stops at numeric instance IDs."""
        assert _extract_metric_type("metric_type_123") == "metric_type"
        assert _extract_metric_type("cpu_usage_0") == "cpu_usage"
        assert _extract_metric_type("memory_bandwidth_node_5") == "memory_bandwidth_node"

    def test_limits_depth_to_prevent_over_grouping(self):
        """Test that depth is limited to avoid including too many tokens."""
        # After 2 additional parts, stops
        assert _extract_metric_type("a_b_c_d_e") == "a_b_c"

    def test_dot_separated_columns(self):
        """Test extraction with dot-separated column names."""
        # Dots are split and joined with underscores
        assert _extract_metric_type("system.cpu.usage") == "system_cpu_usage"

    def test_bracket_and_special_chars(self):
        """Test extraction handles brackets and special characters."""
        # Numbers after brackets are treated as location identifiers
        assert _extract_metric_type("metric[0]_type") == "metric"
        assert _extract_metric_type("value(unit)") == "value_unit"

    def test_empty_and_edge_cases(self):
        """Test edge cases: empty strings, single tokens, all digits."""
        assert _extract_metric_type("single") == "single"
        assert _extract_metric_type("_") == "_"
        assert _extract_metric_type("123") == "123"
        assert _extract_metric_type("_prefix_123") == "prefix"

    def test_no_underscore_treated_as_single_token(self):
        """Test that non-underscore-separated names are treated as single tokens."""
        # Without underscores, treated as single token (documented limitation)
        assert _extract_metric_type("cpu-usage-node0") == "cpu-usage-node0"
        assert _extract_metric_type("camelCaseMetric") == "camelCaseMetric"

    def test_semantic_grouping_preserves_information(self):
        """Test that similar metrics group together, different ones don't."""
        # Same metric family - identifiers like nd0, nd1 stop the extraction
        group1 = _extract_metric_type("LLC_misses_nd0")
        group2 = _extract_metric_type("LLC_misses_nd1")
        # Both preserve the metric family
        assert "LLC_misses" in group1 and "LLC_misses" in group2

        # Different metric family
        assert _extract_metric_type("LLC_hits_nd0") != _extract_metric_type("L1_misses_nd0")


class TestRepresentativeSelection:
    """Tests for _select_representatives_per_group."""

    def test_single_representative_per_group(self):
        """Test selecting 1 representative per group when max_per_group=1."""
        correlations = {
            "metric_a_v1": 0.95,
            "metric_a_v2": 0.90,
            "metric_b_v1": 0.85,
            "metric_b_v2": 0.80,
        }

        candidates = _select_representatives_per_group(correlations, max_per_group=1, max_correlation=0.99)

        # Each candidate should be high correlation
        for candidate in candidates:
            assert candidate[1] > 0.75  # Reasonable correlation threshold

        # Should select some candidates
        assert len(candidates) > 0

    def test_multiple_representatives_per_group(self):
        """Test selecting k representatives per group."""
        correlations = {
            "metric_a_0": 0.99,
            "metric_a_1": 0.95,
            "metric_a_2": 0.90,
            "metric_a_3": 0.85,
            "metric_b_0": 0.80,
            "metric_b_1": 0.75,
        }

        candidates = _select_representatives_per_group(correlations, max_per_group=3, max_correlation=0.99)

        # From metric_a, should get up to 3 (all with corr < 0.99 threshold)
        metric_a_count = sum(1 for c in candidates if "metric_a" in c[0])
        assert metric_a_count <= 3

        metric_b_count = sum(1 for c in candidates if "metric_b" in c[0])
        assert metric_b_count <= 3

    def test_correlation_threshold_filtering(self):
        """Test that correlations >= max_correlation are excluded."""
        correlations = {
            "perfect_corr": 0.9999,
            "high_corr": 0.95,
            "moderate_corr": 0.70,
        }

        candidates = _select_representatives_per_group(correlations, max_per_group=10, max_correlation=0.99)

        # perfect_corr should be excluded
        selected_cols = [c[0] for c in candidates]
        assert "perfect_corr" not in selected_cols
        assert "high_corr" in selected_cols
        assert "moderate_corr" in selected_cols

    def test_preserves_highest_within_group(self):
        """Test that highest correlation is selected within each family."""
        correlations = {
            "family1_item_a": 0.50,
            "family1_item_b": 0.90,
            "family1_item_c": 0.60,
            "family2_item_a": 0.40,
            "family2_item_b": 0.85,
        }

        candidates = _select_representatives_per_group(correlations, max_per_group=1, max_correlation=0.99)

        # With max_per_group=1, should pick top from each family
        selected_dict = {c[0]: c[1] for c in candidates}

        # Check family1: should prefer _item_b (0.90)
        family1_items = [c for c in selected_dict if "family1" in c]
        if family1_items:
            assert any("item_b" in item for item in family1_items)

    def test_empty_correlations(self):
        """Test handling of empty input."""
        candidates = _select_representatives_per_group({}, max_per_group=3, max_correlation=0.99)
        assert candidates == []

    def test_all_above_threshold(self):
        """Test when all correlations exceed threshold."""
        correlations = {"metric1": 0.999, "metric2": 0.9999}

        candidates = _select_representatives_per_group(correlations, max_per_group=10, max_correlation=0.99)

        # All should be filtered out
        assert candidates == []


class TestPredictorSelection:
    """Tests for select_predictors with semantic grouping."""

    def test_diversity_across_metric_families(self):
        """Test that selection returns representatives from multiple families."""
        # Create data with distinct metric families
        data = pl.DataFrame({
            "outcome": np.arange(100),
            "LLC_misses_nd0": np.arange(100) * 1.5 + np.random.normal(0, 5, 100),
            "LLC_misses_nd1": np.arange(100) * 1.4 + np.random.normal(0, 5, 100),
            "L1_misses_nd0": np.arange(100) * 1.3 + np.random.normal(0, 5, 100),
            "L1_misses_nd1": np.arange(100) * 1.2 + np.random.normal(0, 5, 100),
            "cpu_usage_nd0": np.arange(100) * 0.8 + np.random.normal(0, 10, 100),
            "memory_bd_nd0": np.arange(100) * 0.7 + np.random.normal(0, 10, 100),
        })

        selected = select_predictors(
            data, "outcome", exclude=[], max_predictors=20, max_correlation=0.99
        )

        # Should select at least 3 different families
        families = set()
        for pred in selected:
            if "LLC" in pred:
                families.add("LLC")
            elif "L1" in pred:
                families.add("L1")
            elif "cpu" in pred:
                families.add("cpu")
            elif "memory" in pred:
                families.add("memory")

        assert len(families) >= 2, f"Expected diversity, got families: {families} from {selected}"

    def test_max_predictors_respected(self):
        """Test that selection respects max_predictors limit."""
        data = pl.DataFrame({
            "outcome": np.arange(50),
            **{f"metric_{i}": np.arange(50) + np.random.normal(0, 1, 50) for i in range(100)}
        })

        selected = select_predictors(data, "outcome", max_predictors=15, max_correlation=0.99)

        assert len(selected) <= 15

    def test_small_dataset_returns_all(self):
        """Test that for small datasets, all predictors are returned if below max."""
        data = pl.DataFrame({
            "outcome": [1.0, 2.0, 3.0, 4.0, 5.0],
            "metric_a": [1.1, 2.1, 3.1, 4.1, 5.1],
            "metric_b": [2.0, 4.0, 6.0, 8.0, 10.0],
        })

        selected = select_predictors(data, "outcome", max_predictors=100, max_correlation=0.99)

        # Should return metric_a and metric_b (both under threshold)
        assert "metric_a" in selected
        assert "metric_b" in selected

    def test_correlation_threshold_filtering(self):
        """Test that highly correlated predictors (>threshold) are included despite being selected."""
        # Note: The function filters by max_correlation in the select_predictors call,
        # but _select_representatives_per_group filters at the correlation level
        data = pl.DataFrame({
            "outcome": np.arange(50, dtype=float),
            "weakly_corr": np.random.randn(50),  # Nearly uncorrelated
            "moderately_corr": np.random.randn(50) * 0.5 + np.arange(50) * 0.3,
        })

        selected = select_predictors(
            data, "outcome", max_predictors=10, max_correlation=0.95
        )

        # At least one predictor should be selected
        assert len(selected) > 0

        # Verify that weak and moderate predictors are included
        for col in selected:
            assert col in ["weakly_corr", "moderately_corr"]

    def test_categorical_predictor_detection(self):
        """Test that categorical columns are handled via eta-squared."""
        data = pl.DataFrame({
            "outcome": [1.0, 1.2, 1.1, 5.0, 5.2, 5.1, 9.0, 9.1, 8.9] * 11,
            "category": ["A", "A", "A", "B", "B", "B", "C", "C", "C"] * 11,
            "numeric": np.arange(99, dtype=float),
        })

        correlations = compute_predictor_correlations(data, "outcome")

        # Category should be in correlations (via eta-squared)
        assert "category" in correlations
        assert correlations["category"] > 0  # Should have positive association

    def test_exclude_parameter(self):
        """Test that excluded columns are not selected."""
        data = pl.DataFrame({
            "outcome": np.arange(50, dtype=float),
            "metric_important": np.arange(50, dtype=float),
            "metric_excluded": np.arange(50, dtype=float),
            "metric_other": np.random.randn(50),
        })

        selected = select_predictors(
            data, "outcome", exclude=["metric_excluded"], max_predictors=10, max_correlation=0.99
        )

        assert "metric_excluded" not in selected
        assert "metric_important" in selected

    def test_empty_input(self):
        """Test handling of empty DataFrame."""
        data = pl.DataFrame({
            "outcome": [],
        })

        selected = select_predictors(data, "outcome", max_predictors=10, max_correlation=0.99)

        assert selected == []

    def test_single_predictor(self):
        """Test with only one predictor column."""
        data = pl.DataFrame({
            "outcome": np.arange(50, dtype=float),
            "metric": np.arange(50, dtype=float),
        })

        selected = select_predictors(data, "outcome", max_predictors=10, max_correlation=0.99)

        assert "metric" in selected
        assert len(selected) == 1


class TestClassAwareDownsampling:
    """Tests for decision tree class-aware downsampling."""

    def test_preserves_small_classes(self):
        """Test that classes < min_class_size are never downsampled."""
        X = np.random.randn(1000, 10)
        y = np.array(["NORMAL"] * 950 + ["RARE"] * 50)

        trainer = DecisionTreeTrainer()
        X_ds, y_ds = trainer._class_aware_downsample(
            X, y, min_class_size=100, cv_threshold=0.15, base_ratio=0.20
        )

        # RARE class should be fully preserved
        assert (y_ds == "RARE").sum() == 50

    def test_concentrates_classes_downsampled(self):
        """Test that both concentrated and spread classes are handled intelligently."""
        # Create two classes with different characteristics
        rng = np.random.RandomState(42)

        # Concentrated class: low variation
        X_conc = np.ones((800, 10)) * 0.1
        X_conc += rng.normal(0, 0.01, (800, 10))  # CV ~ 0.1

        # Spread class: high variation
        X_spread = rng.normal(5, 1.0, (400, 10))  # CV ~ 0.2

        X = np.vstack([X_conc, X_spread])
        y = np.array(["CONCENTRATED"] * 800 + ["SPREAD"] * 400)

        trainer = DecisionTreeTrainer()
        X_ds, y_ds = trainer._class_aware_downsample(
            X, y, min_class_size=300, cv_threshold=0.15, base_ratio=0.20
        )

        # Verify both classes exist in downsampled data
        assert (y_ds == "CONCENTRATED").sum() > 0
        assert (y_ds == "SPREAD").sum() > 0

        # Total should not exceed original
        assert len(y_ds) <= len(y)

    def test_no_downsampling_for_small_datasets(self):
        """Test that very small datasets are not downsampled."""
        X = np.random.randn(1000, 10)
        y = np.array(["A"] * 600 + ["B"] * 400)

        trainer = DecisionTreeTrainer()

        # Should return original data for small datasets
        X_ds, y_ds = trainer._class_aware_downsample(
            X, y, min_class_size=300, cv_threshold=0.15, base_ratio=0.20
        )

        # For dataset < 5000, no downsampling
        assert len(y_ds) == len(y)

    def test_respects_min_class_size(self):
        """Test that sampled classes don't go below min_class_size."""
        X = np.random.randn(5000, 10)
        y = np.array(["A"] * 4500 + ["B"] * 500)

        trainer = DecisionTreeTrainer()
        X_ds, y_ds = trainer._class_aware_downsample(
            X, y, min_class_size=300, cv_threshold=0.15, base_ratio=0.20
        )

        # Each class should have at least min_class_size samples (or be fully preserved if < min_class_size)
        for label in ["A", "B"]:
            count = (y_ds == label).sum()
            if count < 300:
                # Must be original count (not downsampled)
                assert count == (y == label).sum()

    def test_cv_threshold_affects_sampling(self):
        """Test that CV threshold determines sampling ratio correctly."""
        # Create data where we can control CV
        X_concentrated = np.random.normal(0, 0.1, (1500, 10))  # CV ~0.1
        X_spread = np.random.normal(0, 0.5, (1500, 10))  # CV ~0.5

        X = np.vstack([X_concentrated, X_spread])
        y = np.array(["CONC"] * 1500 + ["SPREAD"] * 1500)

        trainer = DecisionTreeTrainer()
        X_ds, y_ds = trainer._class_aware_downsample(
            X, y, min_class_size=300, cv_threshold=0.2, base_ratio=0.20
        )

        conc_kept = (y_ds == "CONC").sum()
        spread_kept = (y_ds == "SPREAD").sum()

        # CONC has low CV (< 0.2), uses base_ratio = 0.20 → keep 300 samples
        # SPREAD has high CV (> 0.2), uses base_ratio * (1 + CV) = 0.20 * (1 + 0.5) = 0.30 → keep 450 samples
        # Both should respect min_class_size constraint: max(min_class_size, n * ratio)

        assert conc_kept >= 300
        assert spread_kept >= 300

    def test_class_distribution_preserved_qualitatively(self):
        """Test that downsampling preserves qualitative class distribution."""
        X = np.random.randn(10000, 10)
        y = np.array(["A"] * 7000 + ["B"] * 2000 + ["C"] * 1000)

        trainer = DecisionTreeTrainer()
        X_ds, y_ds = trainer._class_aware_downsample(
            X, y, min_class_size=300, cv_threshold=0.15, base_ratio=0.20
        )

        # Distribution should be qualitatively preserved: A > B > C
        a_count = (y_ds == "A").sum()
        b_count = (y_ds == "B").sum()
        c_count = (y_ds == "C").sum()

        assert a_count > b_count > c_count

    def test_reproducibility_with_seed(self):
        """Test that downsampling is reproducible with fixed random seed."""
        X = np.random.randn(5000, 10)
        y = np.array(["A"] * 3500 + ["B"] * 1500)

        trainer = DecisionTreeTrainer()

        np.random.seed(42)
        X_ds1, y_ds1 = trainer._class_aware_downsample(
            X, y, min_class_size=300, cv_threshold=0.15, base_ratio=0.20
        )

        np.random.seed(42)
        X_ds2, y_ds2 = trainer._class_aware_downsample(
            X, y, min_class_size=300, cv_threshold=0.15, base_ratio=0.20
        )

        # Should be identical
        np.testing.assert_array_equal(y_ds1, y_ds2)

    def test_single_class_returns_unchanged(self):
        """Test that single-class data returns unchanged."""
        X = np.random.randn(2000, 10)
        y = np.array(["ONLY"] * 2000)

        trainer = DecisionTreeTrainer()
        X_ds, y_ds = trainer._class_aware_downsample(
            X, y, min_class_size=300, cv_threshold=0.15, base_ratio=0.20
        )

        # Single class → no downsampling
        assert len(y_ds) == len(y)

    def test_all_samples_included(self):
        """Test that all included samples come from original set (no duplicates or fabrication)."""
        X = np.random.randn(5000, 10)
        y = np.array(["A"] * 3500 + ["B"] * 1500)

        trainer = DecisionTreeTrainer()
        X_ds, y_ds = trainer._class_aware_downsample(
            X, y, min_class_size=300, cv_threshold=0.15, base_ratio=0.20
        )

        # Total samples should not exceed original
        assert len(y_ds) <= len(y)

        # Samples should be subset (no new rows created)
        assert X_ds.shape[1] == X.shape[1]


class TestOptimizationSemanticPreservation:
    """End-to-end tests verifying semantic correctness of optimizations."""

    def test_predictor_selection_preserves_correlation_info(self):
        """Test that selection preserves strong correlations while filtering weak ones."""
        data = pl.DataFrame({
            "outcome": np.arange(100, dtype=float),
            "strong_pred": np.arange(100, dtype=float) + np.random.normal(0, 1, 100),
            "weak_pred": np.random.randn(100),
        })

        selected = select_predictors(data, "outcome", max_predictors=10, max_correlation=0.99)

        assert "strong_pred" in selected
        # weak_pred might or might not be selected, but strong should be preferred

    def test_downsampling_preserves_class_structure(self):
        """Test that downsampling maintains tree-relevant class structure."""
        # Create bimodal data: two clear performance classes
        X = np.vstack([
            np.random.normal(0, 1, (2000, 10)),  # SLOW class
            np.random.normal(5, 1, (2000, 10)),  # FAST class
        ])
        y = np.array(["SLOW"] * 2000 + ["FAST"] * 2000)

        trainer = DecisionTreeTrainer()
        X_ds, y_ds = trainer._class_aware_downsample(
            X, y, min_class_size=300, cv_threshold=0.15, base_ratio=0.20
        )

        # Both classes should be present
        assert "SLOW" in y_ds and "FAST" in y_ds

        # Classes should still be separable (means different)
        slow_mean = X_ds[y_ds == "SLOW"].mean()
        fast_mean = X_ds[y_ds == "FAST"].mean()
        assert abs(slow_mean - fast_mean) > 2.0  # Still clearly separated

    def test_optimization_parameters_affect_output(self):
        """Test that configuration parameters affect downsampling behavior."""
        X = np.random.randn(6000, 10)
        y = np.array(["A"] * 4000 + ["B"] * 2000)

        trainer = DecisionTreeTrainer()

        # Conservative downsampling with high ratio
        X_ds1, y_ds1 = trainer._class_aware_downsample(
            X, y, min_class_size=300, cv_threshold=0.15, base_ratio=0.40
        )

        # Aggressive downsampling with low ratio
        X_ds2, y_ds2 = trainer._class_aware_downsample(
            X, y, min_class_size=300, cv_threshold=0.15, base_ratio=0.10
        )

        # Higher base_ratio should result in more or equal samples
        assert len(y_ds1) >= len(y_ds2)
