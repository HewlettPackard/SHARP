"""
Tests for GUI filter utilities.

Tests pure functions in src/gui/utils/filters.py that don't require Shiny.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import polars as pl

from src.gui.utils.filters import (
    apply_filter,
    get_filterable_columns,
    is_full_range_filter,
)


class TestApplyFilter:
    """Tests for apply_filter function."""

    @pytest.fixture
    def sample_df(self):
        """Create sample DataFrame for filter tests."""
        return pl.DataFrame({
            "name": ["Alice", "Bob", "Charlie", "Diana"],
            "age": [25, 30, 35, 40],
            "score": [85.5, 92.3, 78.1, 88.9],
            "category": ["A", "B", "A", "C"],
        })

    def test_string_column_single_value(self, sample_df):
        """Test filtering string column with single value."""
        result = apply_filter(sample_df, "name", ["Alice"])
        assert len(result) == 1
        assert result["name"].to_list() == ["Alice"]

    def test_string_column_multiple_values(self, sample_df):
        """Test filtering string column with multiple values."""
        result = apply_filter(sample_df, "name", ["Alice", "Bob"])
        assert len(result) == 2
        assert set(result["name"].to_list()) == {"Alice", "Bob"}

    def test_numeric_column_range(self, sample_df):
        """Test filtering numeric column with min/max range."""
        result = apply_filter(sample_df, "age", (28, 38))
        assert len(result) == 2
        assert set(result["name"].to_list()) == {"Bob", "Charlie"}

    def test_float_column_range(self, sample_df):
        """Test filtering float column with min/max range."""
        result = apply_filter(sample_df, "score", (80.0, 90.0))
        assert len(result) == 2
        assert set(result["name"].to_list()) == {"Alice", "Diana"}

    def test_empty_filter_value_returns_all(self, sample_df):
        """Test that empty filter value returns all rows."""
        result = apply_filter(sample_df, "name", [])
        assert len(result) == len(sample_df)

    def test_none_filter_value_returns_all(self, sample_df):
        """Test that None filter value returns all rows."""
        result = apply_filter(sample_df, "name", None)
        assert len(result) == len(sample_df)

    def test_nonexistent_column_returns_all(self, sample_df):
        """Test that filtering on non-existent column returns all rows."""
        result = apply_filter(sample_df, "nonexistent", ["value"])
        assert len(result) == len(sample_df)

    def test_string_filter_no_matches(self, sample_df):
        """Test filtering with values that don't match anything."""
        result = apply_filter(sample_df, "name", ["Unknown"])
        assert len(result) == 0

    def test_numeric_range_inclusive_boundary(self, sample_df):
        """Test numeric range filtering at exact boundaries."""
        # Range (25, 40) should include Alice (25) and Diana (40) since it's >=, <=
        result = apply_filter(sample_df, "age", (25, 40))
        assert len(result) == 4  # All should match

    def test_numeric_range_no_matches(self, sample_df):
        """Test numeric range that excludes all rows."""
        result = apply_filter(sample_df, "age", (100, 200))
        assert len(result) == 0

    def test_empty_dataframe(self):
        """Test filtering empty DataFrame."""
        empty_df = pl.DataFrame({"col": []})
        result = apply_filter(empty_df, "col", ["value"])
        assert len(result) == 0

    def test_none_metric_returns_all(self, sample_df):
        """Test that 'None' string metric returns all rows."""
        result = apply_filter(sample_df, "None", ["anything"])
        assert len(result) == len(sample_df)


class TestGetFilterableColumns:
    """Tests for get_filterable_columns function."""

    @pytest.fixture
    def mixed_df(self):
        """Create DataFrame with varied column types and uniqueness."""
        return pl.DataFrame({
            "constant": ["A", "A", "A", "A"],  # Single unique value
            "binary": ["X", "Y", "X", "Y"],  # Two unique values
            "varied": ["P", "Q", "R", "S"],  # All unique (excluded)
            "numeric": [1, 2, 3, 4],  # Numeric column
            "with_nulls": ["A", None, "B", None],  # Has nulls
        })

    def test_excludes_columns_with_single_value(self, mixed_df):
        """Test that columns with only one unique value are excluded."""
        filterable = get_filterable_columns(mixed_df)
        assert "constant" not in filterable

    def test_includes_binary_categorical_columns(self, mixed_df):
        """Test that categorical columns with multiple values are included."""
        filterable = get_filterable_columns(mixed_df)
        assert "binary" in filterable

    def test_excludes_all_unique_categorical(self, mixed_df):
        """Test that categorical columns where all values are unique are excluded."""
        filterable = get_filterable_columns(mixed_df)
        # All 4 rows have different values, so it's useless for filtering
        assert "varied" not in filterable

    def test_includes_numeric_columns(self, mixed_df):
        """Test that numeric columns are included."""
        filterable = get_filterable_columns(mixed_df)
        assert "numeric" in filterable

    def test_handles_nulls_correctly(self, mixed_df):
        """Test that columns with nulls are handled correctly."""
        filterable = get_filterable_columns(mixed_df)
        # Column has 2 unique non-null values (A, B), should be filterable
        assert "with_nulls" in filterable

    def test_empty_dataframe(self):
        """Test handling of empty DataFrame."""
        empty_df = pl.DataFrame({"col": []})
        filterable = get_filterable_columns(empty_df)
        assert filterable == []

    def test_all_constant_columns(self):
        """Test DataFrame where all columns have single value."""
        df = pl.DataFrame({
            "a": [1, 1, 1],
            "b": ["X", "X", "X"],
        })
        filterable = get_filterable_columns(df)
        assert filterable == []

    def test_returns_sorted_list(self):
        """Test that result is sorted alphabetically."""
        df = pl.DataFrame({
            "zebra": [1, 2, 3],
            "alpha": [4, 5, 6],
            "middle": [7, 8, 9],
        })
        filterable = get_filterable_columns(df)
        assert filterable == sorted(filterable)


class TestIsFullRangeFilter:
    """Tests for is_full_range_filter function.

    Note: is_full_range_filter takes (data, filter_column, filter_value) and
    checks if the filter covers the full range of the data.
    """

    @pytest.fixture
    def numeric_df(self):
        """Create DataFrame with numeric data for range tests."""
        return pl.DataFrame({
            "values": [0.0, 25.0, 50.0, 75.0, 100.0],
            "category": ["A", "B", "C", "D", "E"],
        })

    def test_exact_full_range_returns_true(self, numeric_df):
        """Test that exact full range returns True."""
        result = is_full_range_filter(numeric_df, "values", [0.0, 100.0])
        assert result is True

    def test_partial_range_returns_false(self, numeric_df):
        """Test that partial range returns False."""
        result = is_full_range_filter(numeric_df, "values", [10.0, 90.0])
        assert result is False

    def test_non_list_filter_value_returns_false(self, numeric_df):
        """Test that non-list filter value returns False."""
        result = is_full_range_filter(numeric_df, "values", 50.0)
        assert result is False

    def test_string_column_returns_false(self, numeric_df):
        """Test that string column returns False."""
        result = is_full_range_filter(numeric_df, "category", ["A", "E"])
        assert result is False

    def test_missing_column_returns_false(self, numeric_df):
        """Test that missing column returns False."""
        result = is_full_range_filter(numeric_df, "nonexistent", [0.0, 100.0])
        assert result is False

    def test_empty_dataframe_returns_false(self):
        """Test that empty DataFrame returns False."""
        empty_df = pl.DataFrame({"values": []}).cast({"values": pl.Float64})
        result = is_full_range_filter(empty_df, "values", [0.0, 100.0])
        assert result is False

    def test_none_dataframe_returns_false(self):
        """Test that None DataFrame returns False."""
        result = is_full_range_filter(None, "values", [0.0, 100.0])
        assert result is False

    def test_integer_column(self):
        """Test with integer column."""
        df = pl.DataFrame({"int_col": [1, 2, 3, 4, 5]})
        result = is_full_range_filter(df, "int_col", [1.0, 5.0])
        assert result is True

    def test_slightly_off_returns_false(self):
        """Test that slightly off range returns False."""
        df = pl.DataFrame({"values": [0.0, 100.0]})
        result = is_full_range_filter(df, "values", [0.001, 100.0])
        assert result is False
