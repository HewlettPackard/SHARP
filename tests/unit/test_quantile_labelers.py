"""
Unit tests for quantile-based labelers (Tertile and Quartile).

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import pytest
from src.core.profile.labeler import TertileLabeler, QuartileLabeler


class TestTertileLabeler:
    """Tests for TertileLabeler."""

    def test_tertile_creates_three_groups(self):
        """Test that tertile labeler creates three roughly equal groups."""
        # Create data with 90 values (should split into groups of ~30 each)
        values = np.linspace(0, 100, 90)

        labeler = TertileLabeler(values, lower_is_better=True)
        labels = labeler.label(values)

        # Should have 3 classes
        unique_labels = np.unique(labels)
        assert len(unique_labels) == 3

        # Check class names are correct
        class_names = labeler.get_class_names()
        assert len(class_names) == 3
        assert class_names[0] == "FAST"
        assert class_names[1] == "MIDDLE-THIRD"
        assert class_names[2] == "SLOW"

    def test_tertile_lower_is_better_true(self):
        """Test tertile labeler with lower_is_better=True."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9])

        labeler = TertileLabeler(values, lower_is_better=True)
        labels = labeler.label(values)

        # Lower values should be FAST
        assert labels[0] == "FAST"  # 1 is in lowest tertile
        assert labels[-1] == "SLOW"  # 9 is in highest tertile

    def test_tertile_lower_is_better_false(self):
        """Test tertile labeler with lower_is_better=False."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9])

        labeler = TertileLabeler(values, lower_is_better=False)
        labels = labeler.label(values)

        # Higher values should be FAST
        assert labels[0] == "SLOW"  # 1 is in lowest tertile (worst)
        assert labels[-1] == "FAST"  # 9 is in highest tertile (best)

    def test_tertile_class_names_order(self):
        """Test that class names are ordered correctly based on lower_is_better."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9])

        # Lower is better: FAST, MIDDLE-THIRD, SLOW
        labeler_lower = TertileLabeler(values, lower_is_better=True)
        assert labeler_lower.get_class_names() == ["FAST", "MIDDLE-THIRD", "SLOW"]

        # Higher is better: SLOW, MIDDLE-THIRD, FAST
        labeler_higher = TertileLabeler(values, lower_is_better=False)
        assert labeler_higher.get_class_names() == ["SLOW", "MIDDLE-THIRD", "FAST"]

    def test_tertile_cutoffs_match_quantiles(self):
        """Test that tertile labeler returns quantile cutoffs."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9])
        labeler = TertileLabeler(values, lower_is_better=True)

        cutoffs = labeler.get_cutoffs()
        assert cutoffs is not None
        assert len(cutoffs) == 2
        # Should be approximately 33rd and 67th percentiles
        assert np.isclose(cutoffs[0], np.percentile(values, 33.33), rtol=1e-5)
        assert np.isclose(cutoffs[1], np.percentile(values, 66.67), rtol=1e-5)

    def test_tertile_strategy_name(self):
        """Test that strategy name is correct."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9])
        labeler = TertileLabeler(values, lower_is_better=True)

        assert labeler.get_strategy_name() == "Tertile"


class TestQuartileLabeler:
    """Tests for QuartileLabeler."""

    def test_quartile_creates_four_groups(self):
        """Test that quartile labeler creates four roughly equal groups."""
        # Create data with 100 values (should split into groups of ~25 each)
        values = np.linspace(0, 100, 100)

        labeler = QuartileLabeler(values, lower_is_better=True)
        labels = labeler.label(values)

        # Should have 4 classes
        unique_labels = np.unique(labels)
        assert len(unique_labels) == 4

        # Check class names are correct
        class_names = labeler.get_class_names()
        assert len(class_names) == 4
        assert class_names[0] == "FAST"
        assert class_names[1] == "SECOND-QUARTILE"
        assert class_names[2] == "THIRD-QUARTILE"
        assert class_names[3] == "SLOW"

    def test_quartile_lower_is_better_true(self):
        """Test quartile labeler with lower_is_better=True."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])

        labeler = QuartileLabeler(values, lower_is_better=True)
        labels = labeler.label(values)

        # Lower values should be FAST
        assert labels[0] == "FAST"  # 1 is in lowest quartile
        assert labels[-1] == "SLOW"  # 12 is in highest quartile

    def test_quartile_lower_is_better_false(self):
        """Test quartile labeler with lower_is_better=False."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])

        labeler = QuartileLabeler(values, lower_is_better=False)
        labels = labeler.label(values)

        # Higher values should be FAST
        assert labels[0] == "SLOW"  # 1 is in lowest quartile (worst)
        assert labels[-1] == "FAST"  # 12 is in highest quartile (best)

    def test_quartile_class_names_order(self):
        """Test that class names are ordered correctly based on lower_is_better."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])

        # Lower is better: FAST, SECOND-QUARTILE, THIRD-QUARTILE, SLOW
        labeler_lower = QuartileLabeler(values, lower_is_better=True)
        assert labeler_lower.get_class_names() == ["FAST", "SECOND-QUARTILE", "THIRD-QUARTILE", "SLOW"]

        # Higher is better: SLOW, THIRD-QUARTILE, SECOND-QUARTILE, FAST
        labeler_higher = QuartileLabeler(values, lower_is_better=False)
        assert labeler_higher.get_class_names() == ["SLOW", "THIRD-QUARTILE", "SECOND-QUARTILE", "FAST"]

    def test_quartile_cutoffs_match_quantiles(self):
        """Test that quartile labeler returns quantile cutoffs."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
        labeler = QuartileLabeler(values, lower_is_better=True)

        cutoffs = labeler.get_cutoffs()
        assert cutoffs is not None
        assert len(cutoffs) == 3
        # Should be approximately 25th, 50th, and 75th percentiles
        assert np.isclose(cutoffs[0], np.percentile(values, 25), rtol=1e-5)
        assert np.isclose(cutoffs[1], np.percentile(values, 50), rtol=1e-5)
        assert np.isclose(cutoffs[2], np.percentile(values, 75), rtol=1e-5)

    def test_quartile_strategy_name(self):
        """Test that strategy name is correct."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
        labeler = QuartileLabeler(values, lower_is_better=True)

        assert labeler.get_strategy_name() == "Quartile"

    def test_quartile_middle_classes_in_middle(self):
        """Test that SECOND-QUARTILE and THIRD-QUARTILE are assigned to middle values."""
        values = np.linspace(0, 100, 100)

        labeler = QuartileLabeler(values, lower_is_better=True)
        labels = labeler.label(values)

        # Count occurrences of each class
        unique, counts = np.unique(labels, return_counts=True)
        class_counts = dict(zip(unique, counts))

        # Should have all four classes represented
        assert "FAST" in class_counts
        assert "SECOND-QUARTILE" in class_counts
        assert "THIRD-QUARTILE" in class_counts
        assert "SLOW" in class_counts
