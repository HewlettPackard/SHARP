"""
Tests for GUI profile metrics utilities.

Tests pure functions in src/gui/utils/profile/metrics.py that don't require Shiny.

© Copyright 2025--2026 Hewlett Packard Enterprise Development LP
"""

import pytest
import polars as pl

from src.gui.utils.ui_helpers import (
    get_numeric_columns,
    select_preferred_metric,
)


class TestGetNumericColumns:
    """Tests for get_numeric_columns function."""

    @pytest.fixture
    def mixed_df(self):
        """Create DataFrame with mixed column types."""
        return pl.DataFrame({
            "int_col": [1, 2, 3],
            "float_col": [1.1, 2.2, 3.3],
            "str_col": ["a", "b", "c"],
            "bool_col": [True, False, True],
        })

    def test_returns_numeric_columns_only(self, mixed_df):
        """Test that only numeric columns are returned."""
        result = get_numeric_columns(mixed_df)
        assert "int_col" in result
        assert "float_col" in result
        assert "str_col" not in result

    def test_empty_dataframe_returns_empty_dict(self):
        """Test handling of empty DataFrame."""
        empty_df = pl.DataFrame()
        result = get_numeric_columns(empty_df)
        assert result == {}

    def test_all_string_columns(self):
        """Test DataFrame with only string columns."""
        str_df = pl.DataFrame({
            "a": ["x", "y"],
            "b": ["p", "q"],
        })
        result = get_numeric_columns(str_df)
        assert result == {}

    def test_all_numeric_columns(self):
        """Test DataFrame with only numeric columns."""
        num_df = pl.DataFrame({
            "a": [1, 2, 3],
            "b": [1.0, 2.0, 3.0],
            "c": [100, 200, 300],
        })
        result = get_numeric_columns(num_df)
        assert len(result) == 3

    def test_none_dataframe_returns_empty_dict(self):
        """Test that None DataFrame returns empty dict."""
        result = get_numeric_columns(None)
        assert result == {}


class TestSelectPreferredMetric:
    """Tests for select_preferred_metric function."""

    @pytest.fixture
    def metrics_df(self):
        """Create DataFrame with typical metric columns."""
        return pl.DataFrame({
            "run_id": ["a", "b", "c"],
            "perf_time": [0.9, 1.9, 2.9],
            "inner_time": [1.0, 2.0, 3.0],
            "outer_time": [1.1, 2.1, 3.1],
            "wall_time": [1.5, 2.5, 3.5],
            "other_metric": [10, 20, 30],
        })

    def test_prefers_perf_time(self, metrics_df):
        """Test that perf_time is preferred when available."""
        metrics = get_numeric_columns(metrics_df)
        result = select_preferred_metric(metrics)
        assert result == "perf_time"

    def test_falls_back_to_inner_time(self):
        """Test fallback to inner_time when perf_time not available."""
        df = pl.DataFrame({
            "run_id": ["a", "b"],
            "inner_time": [1.0, 2.0],
            "other": [10, 20],
        })
        metrics = get_numeric_columns(df)
        result = select_preferred_metric(metrics)
        assert result == "inner_time"

    def test_falls_back_to_outer_time(self):
        """Test fallback to outer_time when others not available."""
        df = pl.DataFrame({
            "run_id": ["a", "b"],
            "outer_time": [1.0, 2.0],
            "other": [10, 20],
        })
        metrics = get_numeric_columns(df)
        result = select_preferred_metric(metrics)
        assert result == "outer_time"

    def test_returns_first_available_when_no_preferred(self):
        """Test that no preferred metrics returns first available."""
        df = pl.DataFrame({
            "run_id": ["a", "b"],
            "custom_metric": [1.0, 2.0],
            "string_col": ["x", "y"],
        })
        metrics = get_numeric_columns(df)
        result = select_preferred_metric(metrics)
        assert result == "custom_metric"

    def test_empty_dataframe_returns_empty_string(self):
        """Test that empty DataFrame returns empty string."""
        empty_df = pl.DataFrame()
        metrics = get_numeric_columns(empty_df)
        result = select_preferred_metric(metrics)
        assert result == ""

    def test_no_numeric_columns_returns_empty_string(self):
        """Test that DataFrame with no numeric columns returns empty string."""
        str_df = pl.DataFrame({
            "a": ["x", "y"],
            "b": ["p", "q"],
        })
        metrics = get_numeric_columns(str_df)
        result = select_preferred_metric(metrics)
        assert result == ""

    def test_custom_preferred_metrics(self):
        """Test with custom preferred metrics list."""
        df = pl.DataFrame({
            "custom_time": [1.0, 2.0],
            "other": [10, 20],
        })
        metrics = get_numeric_columns(df)
        result = select_preferred_metric(metrics, preferences=["custom_time"])
        assert result == "custom_time"
