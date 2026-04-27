"""
Unit tests for the ManualLabeler class.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""
import numpy as np
import pytest

from src.core.profile.labeler import ManualLabeler


class TestManualLabeler:
    """Tests for Manual labeling strategy."""

    def test_manual_labeler_single_cutoff(self):
        """ManualLabeler with 1 cutoff should work like binary."""
        np.random.seed(42)
        values = np.array([1, 2, 3, 10, 11, 12, 50, 51, 52])

        labeler = ManualLabeler(values, num_cutoffs=1)

        assert len(labeler.get_cutoffs()) == 1
        assert len(labeler.get_class_names()) == 2
        assert labeler.get_class_names() == ["GROUP_1", "GROUP_2"]
        assert labeler.is_mutable

    def test_manual_labeler_multiple_cutoffs(self):
        """ManualLabeler with multiple cutoffs should create multiple groups."""
        np.random.seed(42)
        values = np.array([1, 2, 3, 10, 11, 12, 50, 51, 52])

        labeler = ManualLabeler(values, num_cutoffs=3)

        assert len(labeler.get_cutoffs()) == 3
        assert len(labeler.get_class_names()) == 4
        assert labeler.get_class_names() == ["GROUP_1", "GROUP_2", "GROUP_3", "GROUP_4"]

    def test_manual_labeler_with_cutoffs(self):
        """with_cutoffs should create labeler with specified cutoffs."""
        cutoffs = [10, 30, 50]
        labeler = ManualLabeler.with_cutoffs(cutoffs, lower_is_better=True)

        assert labeler.get_cutoffs() == [10, 30, 50]
        assert len(labeler.get_class_names()) == 4
        assert labeler.is_mutable

    def test_manual_labeler_set_num_cutoffs_increase(self):
        """set_num_cutoffs should add cutoffs to the right when increasing."""
        values = np.array([1, 2, 3, 10, 11, 12, 50, 51, 52])
        labeler = ManualLabeler(values, num_cutoffs=2)

        initial_cutoffs = labeler.get_cutoffs()
        labeler2 = labeler.set_num_cutoffs(4, (1, 52))

        # First two cutoffs should be preserved
        assert labeler2.get_cutoffs()[:2] == initial_cutoffs
        # Should now have 4 cutoffs
        assert len(labeler2.get_cutoffs()) == 4
        # New cutoffs should be to the right
        assert labeler2.get_cutoffs()[2] > initial_cutoffs[-1]
        assert labeler2.get_cutoffs()[3] > labeler2.get_cutoffs()[2]

    def test_manual_labeler_set_num_cutoffs_decrease(self):
        """set_num_cutoffs should remove cutoffs from the right when decreasing."""
        values = np.array([1, 2, 3, 10, 11, 12, 50, 51, 52])
        labeler = ManualLabeler(values, num_cutoffs=4)

        initial_cutoffs = labeler.get_cutoffs()
        labeler2 = labeler.set_num_cutoffs(2, (1, 52))

        # Should keep first two cutoffs
        assert labeler2.get_cutoffs() == initial_cutoffs[:2]
        assert len(labeler2.get_cutoffs()) == 2

    def test_manual_labeler_labels_correctly(self):
        """Manual labeler should assign correct labels based on cutoffs."""
        values = np.array([1, 5, 10, 15, 20, 25])
        labeler = ManualLabeler.with_cutoffs([10, 20], lower_is_better=True)

        labels = labeler.label(values)

        # Values <= 10 should be GROUP_1
        assert labels[0] == "GROUP_1"  # 1
        assert labels[1] == "GROUP_1"  # 5
        assert labels[2] == "GROUP_1"  # 10
        # Values 10 < x <= 20 should be GROUP_2
        assert labels[3] == "GROUP_2"  # 15
        assert labels[4] == "GROUP_2"  # 20
        # Values > 20 should be GROUP_3
        assert labels[5] == "GROUP_3"  # 25

    def test_manual_labeler_strategy_name(self):
        """Manual labeler should return correct strategy name."""
        values = np.array([1, 2, 3, 4, 5])
        labeler = ManualLabeler(values, num_cutoffs=2)

        assert labeler.get_strategy_name() == "Manual"

    def test_manual_labeler_invalid_num_cutoffs(self):
        """Manual labeler should reject invalid num_cutoffs."""
        values = np.array([1, 2, 3, 4, 5])

        with pytest.raises(ValueError, match="must be between 1 and 9"):
            ManualLabeler(values, num_cutoffs=0)

        with pytest.raises(ValueError, match="must be between 1 and 9"):
            ManualLabeler(values, num_cutoffs=10)

    def test_manual_labeler_with_cutoffs_invalid_count(self):
        """with_cutoffs should reject invalid number of cutoffs."""
        with pytest.raises(ValueError, match="Must have 1-9 cutoffs"):
            ManualLabeler.with_cutoffs([], lower_is_better=True)

        with pytest.raises(ValueError, match="Must have 1-9 cutoffs"):
            ManualLabeler.with_cutoffs([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], lower_is_better=True)

    def test_manual_labeler_cutoffs_sorted(self):
        """with_cutoffs should sort cutoffs automatically."""
        cutoffs = [30, 10, 50]  # Unsorted
        labeler = ManualLabeler.with_cutoffs(cutoffs, lower_is_better=True)

        assert labeler.get_cutoffs() == [10, 30, 50]  # Should be sorted

    def test_manual_labeler_lower_is_better(self):
        """Manual labeler should respect lower_is_better flag."""
        values = np.array([1, 2, 3, 10, 11, 12])

        labeler_lower = ManualLabeler(values, lower_is_better=True, num_cutoffs=1)
        labeler_higher = ManualLabeler(values, lower_is_better=False, num_cutoffs=1)

        # Both should have same structure
        assert len(labeler_lower.get_cutoffs()) == 1
        assert len(labeler_higher.get_cutoffs()) == 1
        assert len(labeler_lower.get_class_names()) == 2
        assert len(labeler_higher.get_class_names()) == 2
