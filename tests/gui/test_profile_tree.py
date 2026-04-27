"""
Tests for GUI profile tree utilities.

Tests pure functions in src/gui/utils/profile/tree.py that don't require Shiny.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import numpy as np
import polars as pl

from src.gui.utils.profile.tree import (
    _encode_features,
    _filter_predictors_by_variance,
    _filter_and_select_top_predictors,
    _format_threshold,
    _calculate_aic,
    select_tree_predictors,
    select_complete_rows,
)


class TestEncodeFeatures:
    """Tests for _encode_features function."""

    def test_numeric_column_unchanged(self):
        """Test that numeric columns are passed through unchanged."""
        df = pl.DataFrame({
            "numeric": [1.0, 2.0, 3.0],
        })
        X, names = _encode_features(df, ["numeric"])
        assert X.shape == (3, 1)
        assert names == ["numeric"]
        np.testing.assert_array_equal(X.flatten(), [1.0, 2.0, 3.0])

    def test_categorical_column_one_hot_encoded(self):
        """Test that categorical columns are one-hot encoded."""
        df = pl.DataFrame({
            "category": ["A", "B", "A"],
        })
        X, names = _encode_features(df, ["category"])
        # Should have 2 columns (A, B)
        assert X.shape == (3, 2)
        assert "category=A" in names
        assert "category=B" in names

    def test_mixed_columns(self):
        """Test encoding of mixed numeric and categorical columns."""
        df = pl.DataFrame({
            "numeric": [1.0, 2.0, 3.0],
            "category": ["A", "B", "A"],
        })
        X, names = _encode_features(df, ["numeric", "category"])
        # 1 numeric + 2 categorical indicator columns
        assert X.shape == (3, 3)
        assert "numeric" in names

    def test_empty_columns_returns_none(self):
        """Test that empty column list returns None."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        X, names = _encode_features(df, [])
        assert X is None
        assert names == []

    def test_preserves_nan_values(self):
        """Test that NaN values are preserved for sklearn."""
        df = pl.DataFrame({
            "numeric": [1.0, np.nan, 3.0],
        })
        X, names = _encode_features(df, ["numeric"])
        assert np.isnan(X[1, 0])


class TestFilterPredictorsByVariance:
    """Tests for _filter_predictors_by_variance function."""

    def test_excludes_constant_columns(self):
        """Test that columns with single value are excluded."""
        df = pl.DataFrame({
            "constant": [1, 1, 1],
            "varied": [1, 2, 3],
            "metric": [10, 20, 30],
        })
        result = _filter_predictors_by_variance(df, [], "metric")
        assert "constant" not in result
        assert "varied" in result

    def test_excludes_metric_column(self):
        """Test that the metric column itself is excluded."""
        df = pl.DataFrame({
            "a": [1, 2, 3],
            "metric": [10, 20, 30],
        })
        result = _filter_predictors_by_variance(df, [], "metric")
        assert "metric" not in result
        assert "a" in result

    def test_excludes_user_specified_columns(self):
        """Test that user-excluded columns are excluded."""
        df = pl.DataFrame({
            "a": [1, 2, 3],
            "b": [4, 5, 6],
            "metric": [10, 20, 30],
        })
        result = _filter_predictors_by_variance(df, ["a"], "metric")
        assert "a" not in result
        assert "b" in result

    def test_handles_null_values(self):
        """Test handling of null values in columns."""
        df = pl.DataFrame({
            "with_nulls": [1, None, 3],
            "metric": [10, 20, 30],
        })
        result = _filter_predictors_by_variance(df, [], "metric")
        # Should be included if it has >1 unique non-null value
        assert "with_nulls" in result


class TestFilterAndSelectTopPredictors:
    """Tests for _filter_and_select_top_predictors function."""

    def test_selects_top_n_by_correlation(self):
        """Test that top N predictors by correlation are selected."""
        correlations = {
            "pred_a": 0.9,
            "pred_b": 0.5,
            "pred_c": 0.8,
            "pred_d": 0.3,
        }
        result = _filter_and_select_top_predictors(correlations, max_predictors=2, max_correlation=0.99)
        assert len(result) == 2
        assert "pred_a" in result
        assert "pred_c" in result

    def test_filters_out_high_correlation(self):
        """Test that predictors with correlation >= max_correlation are filtered."""
        correlations = {
            "perfect": 1.0,
            "near_perfect": 0.99,
            "good": 0.7,
        }
        result = _filter_and_select_top_predictors(correlations, max_predictors=10, max_correlation=0.99)
        assert "perfect" not in result
        assert "good" in result

    def test_fallback_when_all_filtered(self):
        """Test fallback when all correlations are >= max_correlation."""
        correlations = {
            "a": 1.0,
            "b": 0.99,
        }
        result = _filter_and_select_top_predictors(correlations, max_predictors=10, max_correlation=0.5)
        # Should fall back to include some predictors
        assert len(result) > 0

    def test_empty_correlations(self):
        """Test handling of empty correlations dict."""
        result = _filter_and_select_top_predictors({}, max_predictors=10, max_correlation=0.99)
        assert result == []


class TestFormatThreshold:
    """Tests for _format_threshold function."""

    def test_normal_value(self):
        """Test formatting of normal values."""
        result = _format_threshold(42.5)
        assert result == "42.50"

    def test_large_value_scientific(self):
        """Test that large values use scientific notation."""
        result = _format_threshold(10000.0)
        assert "e" in result or "E" in result

    def test_small_value_scientific(self):
        """Test that small values use scientific notation."""
        result = _format_threshold(0.001)
        assert "e" in result or "E" in result

    def test_zero_value(self):
        """Test formatting of zero."""
        result = _format_threshold(0.0)
        assert result == "0.00"

    def test_negative_large_value(self):
        """Test formatting of negative large values."""
        result = _format_threshold(-5000.0)
        assert "e" in result or "E" in result


class TestCalculateAIC:
    """Tests for _calculate_aic function."""

    def test_perfect_accuracy(self):
        """Test AIC calculation with perfect accuracy."""
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 1, 0, 1])
        aic = _calculate_aic(y_true, y_pred, n_nodes=3)
        # With perfect accuracy, log-likelihood is 0, so AIC = 2k
        assert aic == pytest.approx(6.0, rel=1e-6)

    def test_imperfect_accuracy(self):
        """Test AIC calculation with imperfect accuracy."""
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 0, 0, 1])  # 75% accuracy
        aic = _calculate_aic(y_true, y_pred, n_nodes=3)
        # AIC should be finite and > 6 (worse than perfect)
        assert np.isfinite(aic)
        assert aic > 6.0

    def test_more_nodes_higher_aic(self):
        """Test that more nodes increases AIC (all else equal)."""
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 1, 0, 1])
        aic_few = _calculate_aic(y_true, y_pred, n_nodes=3)
        aic_many = _calculate_aic(y_true, y_pred, n_nodes=10)
        assert aic_many > aic_few

    def test_empty_arrays(self):
        """Test handling of empty arrays."""
        result = _calculate_aic(np.array([]), np.array([]), n_nodes=1)
        assert result is None

    def test_all_wrong(self):
        """Test AIC with all wrong predictions."""
        y_true = np.array([0, 0, 0, 0])
        y_pred = np.array([1, 1, 1, 1])  # All wrong
        result = _calculate_aic(y_true, y_pred, n_nodes=3)
        # Previously returned None, now returns a large AIC value
        assert result is not None
        assert result > 0


class TestSelectTreePredictors:
    """Tests for select_tree_predictors function."""

    @pytest.fixture
    def simple_df(self):
        """Create simple DataFrame for predictor selection."""
        np.random.seed(42)
        n = 50
        return pl.DataFrame({
            "predictor1": np.random.normal(0, 1, n).tolist(),
            "predictor2": np.random.normal(0, 1, n).tolist(),
            "constant": [1.0] * n,
            "metric": np.random.normal(100, 10, n).tolist(),
        })

    def test_excludes_metric_column(self, simple_df):
        """Test that metric column is excluded from predictors."""
        result = select_tree_predictors(simple_df, "metric")
        assert "metric" not in result

    def test_excludes_constant_columns(self, simple_df):
        """Test that constant columns are excluded."""
        result = select_tree_predictors(simple_df, "metric")
        assert "constant" not in result

    def test_returns_list(self, simple_df):
        """Test that function returns a list."""
        result = select_tree_predictors(simple_df, "metric")
        assert isinstance(result, list)

    def test_respects_exclude_list(self, simple_df):
        """Test that user exclude list is respected."""
        result = select_tree_predictors(simple_df, "metric", exclude=["predictor1"])
        assert "predictor1" not in result
        assert "predictor2" in result


class TestSelectCompleteRows:
    """Tests for select_complete_rows function."""

    @pytest.fixture
    def sparse_df(self):
        """Create DataFrame with varying completeness."""
        return pl.DataFrame({
            "a": [1.0, 2.0, None, 4.0, None],
            "b": [1.0, None, 3.0, 4.0, None],
            "c": [1.0, 2.0, 3.0, 4.0, 5.0],
        })

    def test_selects_complete_rows(self, sparse_df):
        """Test that rows with high completeness are selected first."""
        result = select_complete_rows(sparse_df, ["a", "b", "c"], target_rows=10, completeness_threshold=1.0)
        # Function has adaptive threshold - if not enough complete rows at 1.0, it lowers threshold
        # Rows 0 and 3 have 100% completeness, but with 5 rows total it may include more
        # With threshold starting at 1.0, it finds 2 rows, then tries lower thresholds until it has >= 10
        # Since we only have 5 rows total, it may return more
        assert len(result) >= 2  # At least the complete rows

    def test_adaptive_threshold(self, sparse_df):
        """Test that threshold adapts when few complete rows."""
        result = select_complete_rows(sparse_df, ["a", "b", "c"], target_rows=10, completeness_threshold=0.95)
        # Should include more rows with lower threshold
        assert len(result) >= 2

    def test_respects_target_rows(self):
        """Test that result is limited by target_rows."""
        df = pl.DataFrame({
            "a": [1.0] * 100,
            "b": [2.0] * 100,
        })
        result = select_complete_rows(df, ["a", "b"], target_rows=10, completeness_threshold=1.0)
        assert len(result) <= 10

    def test_returns_dataframe(self, sparse_df):
        """Test that function returns a DataFrame."""
        result = select_complete_rows(sparse_df, ["a", "b", "c"])
        assert isinstance(result, pl.DataFrame)

    def test_preserves_schema(self, sparse_df):
        """Test that returned DataFrame has same schema."""
        result = select_complete_rows(sparse_df, ["a", "b", "c"])
        assert result.columns == sparse_df.columns

    def test_all_complete_rows(self):
        """Test with all complete rows."""
        df = pl.DataFrame({
            "a": [1.0, 2.0, 3.0],
            "b": [4.0, 5.0, 6.0],
        })
        result = select_complete_rows(df, ["a", "b"], target_rows=10, completeness_threshold=1.0)
        assert len(result) == 3
