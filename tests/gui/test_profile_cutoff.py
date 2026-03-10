"""
Tests for GUI profile cutoff utilities.

Tests pure functions in src/gui/utils/profile/cutoff.py that don't require Shiny.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import numpy as np
import polars as pl

from src.gui.utils.profile.cutoff import (
    suggest_cutoff,
    compute_cutoff_from_data,
    validate_cutoff_range,
)


class TestSuggestCutoff:
    """Tests for suggest_cutoff function."""

    @pytest.fixture
    def normal_data(self):
        """Create normally distributed data."""
        np.random.seed(42)
        return np.random.normal(100, 10, 100)

    @pytest.fixture
    def bimodal_data(self):
        """Create bimodal data (fast and slow runs)."""
        np.random.seed(42)
        fast = np.random.normal(50, 5, 50)
        slow = np.random.normal(100, 5, 50)
        return np.concatenate([fast, slow])

    def test_returns_float(self, normal_data):
        """Test that suggest_cutoff returns a float."""
        result = suggest_cutoff(normal_data)
        assert isinstance(result, float)

    def test_cutoff_within_data_range(self, normal_data):
        """Test that cutoff is within the data range."""
        result = suggest_cutoff(normal_data)
        assert result >= np.min(normal_data)
        assert result <= np.max(normal_data)

    def test_single_value_data(self):
        """Test handling of single-value data."""
        single = np.array([100.0])
        result = suggest_cutoff(single)
        assert result == 100.0

    def test_two_value_data(self):
        """Test handling of two-value data."""
        two_vals = np.array([50.0, 100.0])
        result = suggest_cutoff(two_vals)
        assert result >= 50.0
        assert result <= 100.0

    def test_handles_nan_values(self):
        """Test that NaN values are handled."""
        data_with_nan = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
        result = suggest_cutoff(data_with_nan)
        assert not np.isnan(result)

    def test_all_same_values(self):
        """Test handling of constant data."""
        constant = np.array([100.0, 100.0, 100.0, 100.0])
        result = suggest_cutoff(constant)
        assert result == 100.0

    def test_small_sample(self):
        """Test handling of small sample (<=5 returns median)."""
        small = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        result = suggest_cutoff(small)
        assert result == 30.0  # median


class TestComputeCutoffFromData:
    """Tests for compute_cutoff_from_data function."""

    @pytest.fixture
    def sample_df(self):
        """Create sample DataFrame for cutoff computation."""
        np.random.seed(42)
        return pl.DataFrame({
            "metric": np.random.normal(100, 20, 100).tolist(),
            "other_col": list(range(100)),
        })

    def test_returns_float(self, sample_df):
        """Test that function returns a float."""
        result = compute_cutoff_from_data(sample_df, "metric")
        assert isinstance(result, float)

    def test_cutoff_within_metric_range(self, sample_df):
        """Test cutoff is within metric range."""
        result = compute_cutoff_from_data(sample_df, "metric")
        metric_values = sample_df["metric"].to_numpy()
        assert result >= np.min(metric_values)
        assert result <= np.max(metric_values)

    def test_missing_column_returns_none(self, sample_df):
        """Test that missing column returns None."""
        result = compute_cutoff_from_data(sample_df, "nonexistent")
        assert result is None

    def test_empty_dataframe_returns_none(self):
        """Test that empty DataFrame returns None."""
        empty_df = pl.DataFrame({"metric": []})
        result = compute_cutoff_from_data(empty_df, "metric")
        assert result is None

    def test_all_null_column_returns_none(self):
        """Test that all-null column returns None."""
        null_df = pl.DataFrame({"metric": [None, None, None]})
        result = compute_cutoff_from_data(null_df, "metric")
        assert result is None

    def test_empty_metric_col_returns_none(self, sample_df):
        """Test that empty metric_col returns None."""
        result = compute_cutoff_from_data(sample_df, "")
        assert result is None

    def test_none_metric_col_returns_none(self, sample_df):
        """Test that None metric_col returns None."""
        result = compute_cutoff_from_data(sample_df, None)
        assert result is None


class TestValidateCutoffRange:
    """Tests for validate_cutoff_range function.

    Note: validate_cutoff_range returns a tuple (n_below, n_above) indicating
    the number of points below/at cutoff and above cutoff.
    """

    @pytest.fixture
    def sample_df(self):
        """Create sample DataFrame for cutoff validation."""
        return pl.DataFrame({
            "metric": [10.0, 20.0, 30.0, 40.0, 50.0],
        })

    def test_returns_tuple(self, sample_df):
        """Test that function returns a tuple."""
        result = validate_cutoff_range(sample_df, "metric", 25.0)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_counts_below_and_above(self, sample_df):
        """Test correct counting of points below and above cutoff."""
        # Cutoff at 25: 10, 20 below; 30, 40, 50 above
        n_below, n_above = validate_cutoff_range(sample_df, "metric", 25.0)
        assert n_below == 2
        assert n_above == 3

    def test_cutoff_at_value_counts_as_below(self, sample_df):
        """Test that points at cutoff are counted as below (<=)."""
        # Cutoff at 30: 10, 20, 30 below; 40, 50 above
        n_below, n_above = validate_cutoff_range(sample_df, "metric", 30.0)
        assert n_below == 3
        assert n_above == 2

    def test_cutoff_below_all_values(self, sample_df):
        """Test cutoff below all values."""
        n_below, n_above = validate_cutoff_range(sample_df, "metric", 5.0)
        assert n_below == 0
        assert n_above == 5

    def test_cutoff_above_all_values(self, sample_df):
        """Test cutoff above all values."""
        n_below, n_above = validate_cutoff_range(sample_df, "metric", 100.0)
        assert n_below == 5
        assert n_above == 0

    def test_missing_column_returns_zeros(self, sample_df):
        """Test that missing column returns (0, 0)."""
        result = validate_cutoff_range(sample_df, "nonexistent", 25.0)
        assert result == (0, 0)

    def test_empty_dataframe_returns_zeros(self):
        """Test that empty DataFrame returns (0, 0)."""
        empty_df = pl.DataFrame({"metric": []})
        result = validate_cutoff_range(empty_df, "metric", 25.0)
        assert result == (0, 0)

    def test_none_dataframe_returns_zeros(self):
        """Test that None DataFrame returns (0, 0)."""
        result = validate_cutoff_range(None, "metric", 25.0)
        assert result == (0, 0)

    def test_none_cutoff_returns_zeros(self, sample_df):
        """Test that None cutoff returns (0, 0)."""
        result = validate_cutoff_range(sample_df, "metric", None)
        assert result == (0, 0)

    def test_handles_nulls_in_data(self):
        """Test that null values in data are excluded from count."""
        df_with_nulls = pl.DataFrame({
            "metric": [10.0, 20.0, None, 40.0, 50.0],
        })
        n_below, n_above = validate_cutoff_range(df_with_nulls, "metric", 25.0)
        # Only 4 non-null values: 10, 20 below; 40, 50 above
        assert n_below == 2
        assert n_above == 2
