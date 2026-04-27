"""
Test is_mutable property for different labeler types.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""
import numpy as np
import pytest
from src.core.profile.labeler import (
    BinaryLabeler,
    CutoffBasedLabeler,
    TertileLabeler,
    QuartileLabeler
)


@pytest.fixture
def sample_data():
    """Sample data for testing."""
    return np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])


class TestLabelerMutability:
    """Test is_mutable property for different labeler types."""

    def test_binary_labeler_is_mutable(self, sample_data):
        """BinaryLabeler should be mutable (allows cutoff adjustment)."""
        labeler = BinaryLabeler(sample_data, lower_is_better=True)
        assert labeler.is_mutable is True

    def test_cutoff_based_labeler_is_mutable(self, sample_data):
        """CutoffBasedLabeler should be mutable."""
        labeler = CutoffBasedLabeler(
            cutoffs=[30, 70],
            class_names=["FAST", "MEDIUM", "SLOW"],
            lower_is_better=True
        )
        assert labeler.is_mutable is True

    def test_tertile_labeler_is_immutable(self, sample_data):
        """TertileLabeler should be immutable (quantile-based)."""
        labeler = TertileLabeler(sample_data, lower_is_better=True)
        assert labeler.is_mutable is False

    def test_quartile_labeler_is_immutable(self, sample_data):
        """QuartileLabeler should be immutable (quantile-based)."""
        labeler = QuartileLabeler(sample_data, lower_is_better=True)
        assert labeler.is_mutable is False

    def test_immutable_labelers_still_have_cutoffs(self, sample_data):
        """Immutable labelers still return cutoffs (the computed quantiles)."""
        tertile = TertileLabeler(sample_data, lower_is_better=True)
        quartile = QuartileLabeler(sample_data, lower_is_better=True)

        assert tertile.get_cutoffs() is not None
        assert len(tertile.get_cutoffs()) == 2  # 2 cutoffs for 3 groups

        assert quartile.get_cutoffs() is not None
        assert len(quartile.get_cutoffs()) == 3  # 3 cutoffs for 4 groups

    def test_mutability_independent_of_lower_is_better(self, sample_data):
        """Mutability should be independent of lower_is_better setting."""
        # Binary is mutable regardless of lower_is_better
        binary_lower = BinaryLabeler(sample_data, lower_is_better=True)
        binary_higher = BinaryLabeler(sample_data, lower_is_better=False)
        assert binary_lower.is_mutable is True
        assert binary_higher.is_mutable is True

        # Tertile is immutable regardless of lower_is_better
        tertile_lower = TertileLabeler(sample_data, lower_is_better=True)
        tertile_higher = TertileLabeler(sample_data, lower_is_better=False)
        assert tertile_lower.is_mutable is False
        assert tertile_higher.is_mutable is False
