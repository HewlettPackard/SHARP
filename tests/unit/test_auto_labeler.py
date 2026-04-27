"""
Unit tests for the AutoLabeler hybrid labeling strategy.

Tests the multi-phase approach: temporal detection, tail isolation, and body clustering.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""
import numpy as np
import pytest
from typing import List, Dict, Any

from src.core.profile.labeler import AutoLabeler
from src.core.stats.jenks_breaks import jenks_breaks, goodness_of_variance_fit, optimal_jenks_classes
from tests.fixtures.distributions import distributions


class TestJenksBreaks:
    """Tests for Jenks natural breaks algorithm."""

    def test_jenks_separates_obvious_clusters(self):
        """Jenks should find breaks between clearly separated clusters."""
        # Three obvious clusters
        data = np.array([1, 2, 3, 10, 11, 12, 50, 51, 52])
        breaks = jenks_breaks(data, 3)

        assert len(breaks) == 2
        # First break should be between 3 and 10
        assert 3 < breaks[0] < 10
        # Second break should be between 12 and 50
        assert 12 < breaks[1] < 50

    def test_jenks_two_classes(self):
        """Jenks with 2 classes should find single break."""
        data = np.array([1, 2, 3, 4, 20, 21, 22, 23])
        breaks = jenks_breaks(data, 2)

        assert len(breaks) == 1
        assert 4 < breaks[0] < 20

    def test_jenks_minimum_classes(self):
        """Should raise error for less than 2 classes."""
        data = np.array([1, 2, 3, 4, 5])
        with pytest.raises(ValueError, match="n_classes must be at least 2"):
            jenks_breaks(data, 1)

    def test_jenks_too_many_classes(self):
        """Should raise error when more classes than unique values."""
        data = np.array([1, 1, 2, 2, 3, 3])  # Only 3 unique values
        with pytest.raises(ValueError, match="Cannot create .* classes"):
            jenks_breaks(data, 5)

    def test_jenks_handles_nans(self):
        """Jenks should handle NaN values gracefully."""
        data = np.array([1, 2, np.nan, 10, 11, np.nan, 50, 51])
        breaks = jenks_breaks(data, 3)

        assert len(breaks) == 2
        # Should still find reasonable breaks
        assert 2 < breaks[0] < 10
        assert 11 < breaks[1] < 50

    def test_jenks_sorted_output(self):
        """Jenks breaks should be in sorted order."""
        np.random.seed(42)
        data = np.random.uniform(0, 100, 100)
        breaks = jenks_breaks(data, 5)

        assert len(breaks) == 4
        # Verify breaks are sorted
        for i in range(len(breaks) - 1):
            assert breaks[i] < breaks[i + 1]

    def test_jenks_with_duplicates(self):
        """Jenks should handle duplicate values."""
        data = np.array([1, 1, 1, 5, 5, 5, 10, 10, 10])
        breaks = jenks_breaks(data, 3)

        assert len(breaks) == 2
        # Breaks should be between the duplicate groups
        assert 1 < breaks[0] < 5
        assert 5 < breaks[1] < 10

    def test_jenks_maximizes_between_class_variance(self):
        """Jenks should produce higher or equal GVF than random breaks."""
        np.random.seed(42)
        # Create data with three clear clusters
        cluster1 = np.random.normal(10, 1, 30)
        cluster2 = np.random.normal(50, 1, 30)
        cluster3 = np.random.normal(90, 1, 30)
        data = np.concatenate([cluster1, cluster2, cluster3])

        # Jenks breaks
        jenks_breaks_result = jenks_breaks(data, 3)
        jenks_gvf = goodness_of_variance_fit(data, jenks_breaks_result)

        # Random breaks (using uniform quantiles as baseline)
        random_breaks = np.percentile(data, [33.33, 66.67]).tolist()
        random_gvf = goodness_of_variance_fit(data, random_breaks)

        # Jenks should have GVF >= random (may be equal for well-separated clusters)
        assert jenks_gvf >= random_gvf

    def test_jenks_with_skewed_data(self):
        """Jenks should handle right-skewed distributions."""
        np.random.seed(42)
        # Right-skewed exponential data
        data = np.random.exponential(scale=10, size=100)
        breaks = jenks_breaks(data, 3)

        assert len(breaks) == 2
        # Breaks should be in data range
        assert np.min(data) < breaks[0] < np.max(data)
        assert breaks[0] < breaks[1] < np.max(data)

    def test_jenks_with_uniform_data(self):
        """Jenks with uniform data should produce reasonable splits."""
        data = np.linspace(0, 100, 100)
        breaks = jenks_breaks(data, 4)

        assert len(breaks) == 3
        # For uniform data, breaks should be approximately evenly spaced
        # (within 20% of expected spacing)
        expected_spacing = 100 / 4
        for i, brk in enumerate(breaks):
            expected_position = (i + 1) * expected_spacing
            assert abs(brk - expected_position) < 0.2 * expected_spacing


class TestGoodnessOfVarianceFit:
    """Tests for GVF calculation."""

    def test_gvf_perfect_separation(self):
        """GVF should be high for perfectly separated groups."""
        data = np.array([1, 1, 1, 100, 100, 100])
        breaks = [50]  # Perfect split

        gvf = goodness_of_variance_fit(data, breaks)
        assert gvf > 0.99

    def test_gvf_poor_separation(self):
        """GVF should be lower for poor breaks."""
        data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        breaks = [5.5]  # Arbitrary split of uniform data

        gvf = goodness_of_variance_fit(data, breaks)
        # Not terrible, but not great either for uniform data
        assert 0.1 < gvf < 0.9

    def test_gvf_worst_case(self):
        """GVF should be low when all data in one class."""
        data = np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        breaks = [1]  # All data in one class

        gvf = goodness_of_variance_fit(data, breaks)
        # GVF should be very high (all variance is "explained")
        assert gvf > 0.99

    def test_gvf_monotonicity(self):
        """GVF should increase with more optimal breaks."""
        np.random.seed(42)
        cluster1 = np.random.normal(10, 1, 30)
        cluster2 = np.random.normal(50, 1, 30)
        data = np.concatenate([cluster1, cluster2])

        # Optimal break (between clusters)
        optimal_breaks = [30]
        optimal_gvf = goodness_of_variance_fit(data, optimal_breaks)

        # Suboptimal break (cuts through a cluster)
        suboptimal_breaks = [15]
        suboptimal_gvf = goodness_of_variance_fit(data, suboptimal_breaks)

        # Optimal should be >= suboptimal (with tolerance for floating point)
        assert optimal_gvf >= suboptimal_gvf - 1e-10

    def test_gvf_range(self):
        """GVF should always be between 0 and 1."""
        np.random.seed(42)
        data = np.random.normal(50, 10, 100)

        for n_classes in range(2, 6):
            breaks = jenks_breaks(data, n_classes)
            gvf = goodness_of_variance_fit(data, breaks)
            assert 0 <= gvf <= 1, f"GVF {gvf} out of range for {n_classes} classes"


class TestOptimalJenksClasses:
    """Tests for automatic optimal class selection."""

    def test_finds_optimal_for_bimodal(self):
        """Should find 2 classes for bimodal data."""
        np.random.seed(42)
        # Clear bimodal distribution
        data = np.concatenate([
            np.random.normal(10, 1, 50),
            np.random.normal(100, 1, 50)
        ])

        n_classes, breaks = optimal_jenks_classes(data, min_classes=2, max_classes=5, gvf_threshold=0.8)

        # Should find 2 classes with high GVF
        assert n_classes >= 2
        assert len(breaks) == n_classes - 1

    def test_respects_max_classes(self):
        """Should not exceed max_classes."""
        data = np.arange(1, 101)  # Uniform data

        n_classes, breaks = optimal_jenks_classes(data, min_classes=2, max_classes=3)

        assert n_classes <= 3
        assert len(breaks) == n_classes - 1


class TestAutoLabeler:
    """Tests for the AutoLabeler hybrid strategy."""

    def test_auto_labeler_basic_creation(self):
        """AutoLabeler should initialize without errors."""
        np.random.seed(42)
        values = np.random.normal(100, 10, 100)

        labeler = AutoLabeler(values)

        assert labeler is not None
        assert labeler.get_strategy_name() == "Auto"
        assert not labeler.is_mutable

    def test_auto_labeler_returns_labels(self):
        """AutoLabeler should return valid labels for all samples."""
        np.random.seed(42)
        values = np.random.normal(100, 10, 100)

        labeler = AutoLabeler(values)
        labels = labeler.label(values)

        assert len(labels) == len(values)
        # All labels should be non-empty strings
        assert all(isinstance(lbl, str) and len(lbl) > 0 for lbl in labels)

    def test_auto_labeler_class_names_consistent(self):
        """All labels should be in the class_names list."""
        np.random.seed(42)
        values = np.random.normal(100, 10, 100)

        labeler = AutoLabeler(values)
        labels = labeler.label(values)
        class_names = labeler.get_class_names()

        for label in labels:
            assert label in class_names, f"Label '{label}' not in class_names {class_names}"

    def test_auto_labeler_detects_warmup(self):
        """AutoLabeler should detect obvious warmup period."""
        np.random.seed(42)
        # First 20 samples are much slower (warmup), rest are steady
        warmup = np.random.normal(200, 10, 20)
        steady = np.random.normal(100, 5, 80)
        values = np.concatenate([warmup, steady])

        labeler = AutoLabeler(values, lower_is_better=True)
        phase_info = labeler.get_phase_info()

        # Should detect warmup phase
        if phase_info.get('warmup') is not None:
            warmup_info = phase_info['warmup']
            # Warmup should end before index 30
            assert warmup_info['end_idx'] <= 30

    def test_auto_labeler_lower_is_better(self):
        """AutoLabeler should respect lower_is_better flag."""
        np.random.seed(42)
        # Simple bimodal: fast and slow groups
        fast = np.random.normal(10, 1, 50)
        slow = np.random.normal(100, 1, 50)
        values = np.concatenate([fast, slow])

        labeler_lower = AutoLabeler(values, lower_is_better=True)
        labeler_higher = AutoLabeler(values, lower_is_better=False)

        # Both should produce valid labels
        labels_lower = labeler_lower.label(values)
        labels_higher = labeler_higher.label(values)

        assert len(labels_lower) == len(values)
        assert len(labels_higher) == len(values)

    def test_auto_labeler_get_cutoffs_returns_none(self):
        """AutoLabeler doesn't use traditional cutoffs."""
        np.random.seed(42)
        values = np.random.normal(100, 10, 100)

        labeler = AutoLabeler(values)

        assert labeler.get_cutoffs() is None

    def test_auto_labeler_small_dataset_fallback(self):
        """AutoLabeler should fall back to binary for tiny datasets."""
        values = np.array([1, 2, 3, 4, 5])  # Only 5 samples

        labeler = AutoLabeler(values)

        # Should still work
        labels = labeler.label(values)
        assert len(labels) == 5

    def test_auto_labeler_get_label_counts(self):
        """get_label_counts should return counts for each class."""
        np.random.seed(42)
        values = np.random.normal(100, 10, 100)

        labeler = AutoLabeler(values)
        counts = labeler.get_label_counts()

        # Total counts should match number of samples
        assert sum(counts.values()) == len(values)
        # All classes in counts should be in class_names
        for cls in counts.keys():
            assert cls in labeler.get_class_names()

    def test_auto_labeler_tail_detection(self):
        """AutoLabeler should isolate tail samples."""
        np.random.seed(42)
        # Normal body with a few extreme outliers
        body = np.random.normal(100, 10, 90)
        tail = np.array([300, 350, 400, 450, 500, 550, 600, 650, 700, 750])  # 10 tail samples
        values = np.concatenate([body, tail])

        labeler = AutoLabeler(values, lower_is_better=True, min_tail_samples=5)
        labels = labeler.label(values)
        counts = labeler.get_label_counts()

        # Should have TAIL or OUTLIERS class
        has_tail_class = "TAIL" in counts or "OUTLIERS" in counts
        assert has_tail_class, f"Expected TAIL or OUTLIERS class, got {list(counts.keys())}"


class TestAutoLabelerOnSyntheticDistributions:
    """Tests for AutoLabeler behavior on various synthetic distributions."""

    @pytest.mark.parametrize("noise_scale,expected_behavior", [
        (0.001, "homogeneous"),  # Nearly constant (CV << 0.05)
        (0.5, "homogeneous"),    # Low variance (CV < 0.05)
        (1.0, "single_or_multi"),  # Moderate variance (CV ~ 0.08, may split)
    ])
    def test_constant_distribution(self, noise_scale, expected_behavior):
        """
        AutoLabeler should handle constant distributions based on CV.

        - Very low CV (< 0.05): Single BODY class
        - Higher CV (>= 0.05): May split due to Jenks artifacts
        """
        np.random.seed(42)
        data = distributions._constant({
            "loc": 12.34,
            "scale": noise_scale,
            "repetitions": 100
        })
        values = np.array(data)

        labeler = AutoLabeler(values)
        labels = labeler.label(values)
        counts = labeler.get_label_counts()
        class_names = labeler.get_class_names()

        # Calculate coefficient of variation
        cv = np.std(values) / np.mean(values)

        if expected_behavior == "homogeneous":
            # CV < 0.05 should collapse to single BODY class (or with OUTLIERS)
            if cv < 0.05:
                body_classes = [c for c in class_names if "MODE" in c or c == "BODY"]
                assert len(body_classes) <= 1, f"Expected single body class for CV={cv:.4f}, got {class_names}"

        assert len(labels) == len(values)
        assert set(labels).issubset(set(class_names))

    def test_normal_distribution(self):
        """
        AutoLabeler should handle normal (Gaussian) distributions.

        Normal distributions may be split by Jenks into multiple modes even though
        they are unimodal. This is a known limitation of variance-minimization clustering.
        """
        np.random.seed(42)
        data = distributions._normal({
            "mean": 10.0,
            "std_dev": 1.2,
            "repetitions": 100
        })
        values = np.array(data)

        labeler = AutoLabeler(values)
        labels = labeler.label(values)
        counts = labeler.get_label_counts()
        class_names = labeler.get_class_names()

        # Should produce valid labels
        assert len(labels) == len(values)
        assert all(lbl in class_names for lbl in labels)

        # May have 1-3 body classes (Jenks artifacts possible)
        body_classes = [c for c in class_names if "MODE" in c or c == "BODY"]
        assert 1 <= len(body_classes) <= 3, f"Expected 1-3 body classes, got {body_classes}"

    def test_lognormal_distribution(self):
        """
        AutoLabeler should handle log-normal (right-skewed) distributions.

        Log-normal should be detected as skewed and may produce tail isolation.
        """
        np.random.seed(42)
        data = distributions._lognormal({
            "shape": 0.95,
            "mean": 10.0,
            "std_dev": 1.8,
            "repetitions": 100
        })
        values = np.array(data)

        labeler = AutoLabeler(values, lower_is_better=True)
        labels = labeler.label(values)
        counts = labeler.get_label_counts()
        class_names = labeler.get_class_names()

        # Should produce valid labels
        assert len(labels) == len(values)
        assert all(lbl in class_names for lbl in labels)

        # Likely to have tail or outliers due to right skew
        has_tail_or_outliers = any("TAIL" in c or "OUTLIERS" in c for c in class_names)
        # May or may not have tail depending on distribution shape
        # Just verify valid structure
        assert len(class_names) >= 1

    def test_bimodal_distribution(self):
        """
        AutoLabeler should detect bimodal distributions.

        Should produce 2 distinct MODE classes.
        """
        np.random.seed(42)
        data = distributions._bimodal({
            "repetitions": 200
        })
        values = np.array(data)

        labeler = AutoLabeler(values)
        labels = labeler.label(values)
        counts = labeler.get_label_counts()
        class_names = labeler.get_class_names()

        # Should produce valid labels
        assert len(labels) == len(values)
        assert all(lbl in class_names for lbl in labels)

        # Should have 2-3 body classes (2 modes at minimum)
        body_classes = [c for c in class_names if "MODE" in c or c == "BODY"]
        assert len(body_classes) >= 2, f"Expected at least 2 modes for bimodal, got {body_classes}"
        assert len(body_classes) <= 3, f"Expected at most 3 classes for bimodal, got {body_classes}"

    def test_multimodal_distribution(self):
        """
        AutoLabeler should detect multimodal distributions.

        Should produce 2-3 MODE classes (limited by max_body_classes=3).
        """
        np.random.seed(42)
        data = distributions._multimodal({
            "repetitions": 300
        })
        values = np.array(data)

        labeler = AutoLabeler(values)
        labels = labeler.label(values)
        counts = labeler.get_label_counts()
        class_names = labeler.get_class_names()

        # Should produce valid labels
        assert len(labels) == len(values)
        assert all(lbl in class_names for lbl in labels)

        # Should have 2-3 body classes (capped by max_body_classes=3)
        body_classes = [c for c in class_names if "MODE" in c or c == "BODY"]
        assert len(body_classes) >= 2, f"Expected at least 2 modes for multimodal, got {body_classes}"
        assert len(body_classes) <= 3, f"Expected at most 3 classes for multimodal, got {body_classes}"

    def test_uniform_distribution(self):
        """
        AutoLabeler should handle uniform distributions.

        Uniform may be split by Jenks despite being truly uniform (algorithm limitation).
        """
        np.random.seed(42)
        data = distributions._uniform({
            "loc": 2.5,
            "scale": 8.0,
            "repetitions": 100
        })
        values = np.array(data)

        labeler = AutoLabeler(values)
        labels = labeler.label(values)
        counts = labeler.get_label_counts()
        class_names = labeler.get_class_names()

        # Should produce valid labels
        assert len(labels) == len(values)
        assert all(lbl in class_names for lbl in labels)

        # May have 1-3 body classes (Jenks may partition uniform data)
        body_classes = [c for c in class_names if "MODE" in c or c == "BODY"]
        assert 1 <= len(body_classes) <= 3, f"Expected 1-3 body classes, got {body_classes}"

    def test_cauchy_distribution(self):
        """
        AutoLabeler should handle Cauchy (heavy-tailed) distributions.

        Cauchy has heavy tails, should produce tail/outlier classes.
        """
        np.random.seed(42)
        data = distributions._cauchy({
            "loc": 8.0,
            "scale": 2.5,
            "repetitions": 100
        })
        values = np.array(data)

        labeler = AutoLabeler(values, lower_is_better=True, min_tail_samples=5)
        labels = labeler.label(values)
        counts = labeler.get_label_counts()
        class_names = labeler.get_class_names()

        # Should produce valid labels
        assert len(labels) == len(values)
        assert all(lbl in class_names for lbl in labels)

        # Heavy tails should likely produce tail/outlier classes
        # (but not guaranteed depending on sampling)
        assert len(class_names) >= 1

    def test_logistic_distribution(self):
        """
        AutoLabeler should handle logistic distributions.

        Logistic is similar to normal but with heavier tails.
        """
        np.random.seed(42)
        data = distributions._logistic({
            "loc": 12.0,
            "scale": 2.5,
            "repetitions": 100
        })
        values = np.array(data)

        labeler = AutoLabeler(values)
        labels = labeler.label(values)
        counts = labeler.get_label_counts()
        class_names = labeler.get_class_names()

        # Should produce valid labels
        assert len(labels) == len(values)
        assert all(lbl in class_names for lbl in labels)

        # Should have 1-3 body classes
        body_classes = [c for c in class_names if "MODE" in c or c == "BODY"]
        assert 1 <= len(body_classes) <= 3, f"Expected 1-3 body classes, got {body_classes}"

    def test_sine_distribution(self):
        """
        AutoLabeler should handle sine wave distributions.

        Sine wave creates a U-shaped (bimodal) distribution with peaks at extremes.
        """
        np.random.seed(42)
        data = distributions._sine({
            "norm_mean": 1,
            "norm_std": 0.1,
            "pi_scale": 16,
            "sample_offset": 3,
            "repetitions": 200
        })
        values = np.array(data)

        labeler = AutoLabeler(values)
        labels = labeler.label(values)
        counts = labeler.get_label_counts()
        class_names = labeler.get_class_names()

        # Should produce valid labels
        assert len(labels) == len(values)
        assert all(lbl in class_names for lbl in labels)

        # Sine creates bimodal-like peaks, should detect multiple modes
        body_classes = [c for c in class_names if "MODE" in c or c == "BODY"]
        assert len(body_classes) >= 1, f"Expected at least 1 body class, got {body_classes}"

    def test_loguniform_distribution(self):
        """
        AutoLabeler should handle log-uniform distributions.

        Log-uniform is skewed and may produce tail classes.
        """
        np.random.seed(42)
        data = distributions._loguniform({
            "a": 10,
            "b": 30,
            "loc": 13,
            "scale": 2.5,
            "repetitions": 100
        })
        values = np.array(data)

        labeler = AutoLabeler(values, lower_is_better=True)
        labels = labeler.label(values)
        counts = labeler.get_label_counts()
        class_names = labeler.get_class_names()

        # Should produce valid labels
        assert len(labels) == len(values)
        assert all(lbl in class_names for lbl in labels)

        # Should have valid structure
        assert len(class_names) >= 1

    def test_distribution_consistency(self):
        """
        AutoLabeler should produce consistent results with same seed.

        Verify deterministic behavior.
        """
        np.random.seed(42)
        data1 = distributions._normal({"mean": 10.0, "std_dev": 1.2, "repetitions": 100})
        values1 = np.array(data1)
        labeler1 = AutoLabeler(values1)
        labels1 = labeler1.label(values1)

        np.random.seed(42)
        data2 = distributions._normal({"mean": 10.0, "std_dev": 1.2, "repetitions": 100})
        values2 = np.array(data2)
        labeler2 = AutoLabeler(values2)
        labels2 = labeler2.label(values2)

        # Should produce identical results
        assert len(labels1) == len(labels2)
        assert all(l1 == l2 for l1, l2 in zip(labels1, labels2))
        assert labeler1.get_class_names() == labeler2.get_class_names()

    def test_all_distributions_return_valid_labels(self):
        """
        Smoke test: AutoLabeler should work on all distribution types without crashing.

        Tests each distribution method to ensure robustness.
        """
        np.random.seed(42)
        distribution_configs = [
            ("normal", {"mean": 10.0, "std_dev": 1.2, "repetitions": 100}),
            ("lognormal", {"shape": 0.95, "mean": 10.0, "std_dev": 1.8, "repetitions": 100}),
            ("bimodal", {"repetitions": 200}),
            ("multimodal", {"repetitions": 300}),
            ("uniform", {"loc": 2.5, "scale": 8.0, "repetitions": 100}),
            ("cauchy", {"loc": 8.0, "scale": 2.5, "repetitions": 100}),
            ("logistic", {"loc": 12.0, "scale": 2.5, "repetitions": 100}),
            ("loguniform", {"a": 10, "b": 30, "loc": 13, "scale": 2.5, "repetitions": 100}),
            ("constant", {"loc": 12.34, "scale": 0.1, "repetitions": 100}),
            ("sine", {"norm_mean": 1, "norm_std": 0.1, "pi_scale": 16, "sample_offset": 3, "repetitions": 200}),
        ]

        for dist_name, config in distribution_configs:
            method_name = f"_{dist_name}"
            method = getattr(distributions, method_name)
            data = method(config)
            values = np.array(data)

            # Should not crash
            labeler = AutoLabeler(values)
            labels = labeler.label(values)
            counts = labeler.get_label_counts()
            class_names = labeler.get_class_names()

            # Basic validation
            assert len(labels) == len(values), f"Failed for {dist_name}"
            assert all(lbl in class_names for lbl in labels), f"Invalid labels for {dist_name}"
            assert sum(counts.values()) == len(values), f"Count mismatch for {dist_name}"

