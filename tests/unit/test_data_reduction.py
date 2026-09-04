"""
Unit tests for column and row reduction strategies.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import polars as pl
import pytest

from src.core.profile.data_reduction import (
    filter_by_completeness_adaptive,
    filter_near_zero_variance,
    filter_by_outcome_relevance,
    select_by_mutual_information,
    reduce_columns,
    filter_relevant_rows,
    filter_uninformative_rows,
    filter_steady_state,
    reduce_rows,
)


class _DummySettings:
    """Minimal settings shim for testing explicit enable/disable behavior."""

    def __init__(self, values: dict[str, object]):
        self._values = values

    def get(self, key: str, default: object = None) -> object:
        return self._values.get(key, default)


class TestC1CompletednessGate:
    """Tests for C1: Column completeness gate."""

    def test_drops_columns_below_absolute_minimum(self):
        """Columns with fewer than min_absolute_non_null non-nulls are dropped."""
        data = pl.DataFrame({
            "time": [1, 2, 3, 4, 5],
            "outcome": [10, 11, 12, 13, 14],
            "good_col": [1, 2, 3, 4, 5],  # 5 non-nulls
            "bad_col": [None, None, None, None, 1],  # only 1 non-null
        })

        result = filter_by_completeness_adaptive(
            data, "outcome", min_absolute_non_null=3
        )

        assert "good_col" in result
        assert "bad_col" not in result

    def test_adapts_to_single_host_data(self):
        """Adapts to single-host data where most columns have low nulls."""
        # Single-host: most columns ~0-10% null
        data = pl.DataFrame({
            "time": list(range(100)),
            "outcome": list(range(100)),
            "metric_a": list(range(100)),  # 0% null
            "metric_b": list(range(100)),  # 0% null
            "sparse_col": [1] + [None] * 99,  # 99% null
        })

        result = filter_by_completeness_adaptive(
            data, "outcome", max_null_percentile=0.05
        )

        # sparse_col should be dropped (in bottom 5%)
        assert "metric_a" in result
        assert "metric_b" in result
        assert "sparse_col" not in result

    def test_preserves_outcome_aligned_sparse_columns(self):
        """Preserves sparse columns that appear with outcome."""
        data = pl.DataFrame({
            "time": [1, 2, 3, 4, 5],
            "outcome": [10, None, 12, None, 14],
            "aligned_sparse": [1, None, 3, None, 5],  # sparse but aligned with outcome
            "unaligned_sparse": [None, None, None, None, 1],  # sparse, never appears with outcome
        })

        result = filter_by_completeness_adaptive(
            data, "outcome",
            min_absolute_non_null=2,
            preserve_outcome_aligned_sparse=True,
        )

        assert "aligned_sparse" in result  # preserved due to alignment
        assert "unaligned_sparse" not in result


class TestC2NearZeroVariance:
    """Tests for C2: Near-zero variance filter."""

    def test_drops_constant_columns(self):
        """Drops columns where 95%+ of non-null values are identical."""
        data = pl.DataFrame({
            "time": [1, 2, 3, 4, 5],
            "constant_col": [1, 1, 1, 1, 1],  # 100% identical
            "mostly_constant": [1, 1, 1, 1, 2],  # 80% identical
            "variable_col": [1, 2, 3, 4, 5],  # 20% max
        })

        result = filter_near_zero_variance(
            data,
            ["constant_col", "mostly_constant", "variable_col"],
            max_constant_fraction=0.95,
        )

        assert "constant_col" not in result
        assert "mostly_constant" in result  # 80% < 0.95 so it should be kept
        assert "variable_col" in result

    def test_handles_empty_columns(self):
        """Handles columns with all nulls gracefully."""
        data = pl.DataFrame({
            "time": [1, 2, 3],
            "all_null": [None, None, None],
            "good": [1, 2, 3],
        })

        result = filter_near_zero_variance(
            data, ["all_null", "good"], max_constant_fraction=0.95
        )

        # all_null should be skipped (no non-null values)
        # good should be kept
        assert "good" in result


class TestC3OutcomeRelevance:
    """Tests for C3: Outcome-relevance gate."""

    def test_drops_low_correlation_columns(self):
        """Drops columns with |correlation| below threshold."""
        correlations = {
            "high_corr": 0.75,
            "med_corr": 0.05,
            "low_corr": 0.02,
            "zero_corr": 0.0,
        }

        result = filter_by_outcome_relevance(correlations, min_abs_correlation=0.05)

        assert "high_corr" in result
        assert "med_corr" in result
        assert "low_corr" not in result
        assert "zero_corr" not in result


class TestC4MutualInformation:
    """Tests for C4: Mutual information screening."""

    def test_selects_top_n_columns(self):
        """Selects top-N columns by mutual information."""
        data = pl.DataFrame({
            "outcome": [0, 1, 0, 1, 0, 1] * 100,  # Binary outcome
            "high_mi": [0, 1, 0, 1, 0, 1] * 100,  # Perfect MI with outcome
            "low_mi": [0, 0, 1, 1, 0, 0] * 100,  # Lower MI
            "noise": [0, 1, 1, 0, 1, 0] * 100,  # Low MI
        })

        result = select_by_mutual_information(
            data, "outcome",
            ["high_mi", "low_mi", "noise"],
            n_select=2,
        )

        assert len(result) == 2
        assert "high_mi" in result  # Should be selected


class TestReduceColumnsIntegration:
    """Integration tests for the full column reduction pipeline."""

    def test_skips_reduction_if_small_data(self):
        """Skips reduction if data is below threshold."""
        data = pl.DataFrame({
            "outcome": [1, 2, 3],
            "col_1": [10, 20, 30],
            "col_2": [40, 50, 60],
        })

        from src.core.config.settings import Settings
        settings = Settings()
        # Assume default threshold is 500 columns
        result = reduce_columns(data, "outcome", settings)

        # Should return all columns except outcome
        assert set(result) == {"col_1", "col_2"}

    def test_multi_host_adaptive_filter(self):
        """Tests multi-host data with many sparse columns."""
        # Simulate multi-host data where each host's metrics only appear on its rows
        n_rows = 1000
        data = pl.DataFrame({
            "outcome": list(range(n_rows)),
            "host": [i % 5 for i in range(n_rows)],
            **{
                f"host_{h}_metric": [i if (i % 5 == h) else None for i in range(n_rows)]
                for h in range(5)
            },
            "global_metric": list(range(n_rows)),  # present on all rows
        })

        # With adaptive C1, should keep mostly-sparse columns that follow host pattern
        result = filter_by_completeness_adaptive(
            data, "outcome",
            min_absolute_non_null=30,
            max_null_percentile=0.05,
        )

        # global_metric should definitely survive
        assert "global_metric" in result
        # Some host metrics should survive (have ~200 non-nulls)
        host_metrics = [c for c in result if c.startswith("host_")]
        assert len(host_metrics) > 0

    def test_reduction_disabled_returns_predictors_unmodified(self):
        """When disabled, reduce_columns should preserve all predictors."""
        data = pl.DataFrame({
            "outcome": [1, 2, 3, 4],
            "col_1": [10, 20, 30, 40],
            "col_2": [40, 30, 20, 10],
        })
        settings = _DummySettings({"profiling.data_reduction.enabled": False})

        result = reduce_columns(data, "outcome", settings)

        assert result == ["col_1", "col_2"]


class TestR3RowCompleteness:
    """Tests for R3: Row relevance filter (preserve lag-based associations)."""

    def test_keeps_rows_with_outcome_or_predictors(self):
        """Keeps rows with outcome or any predictor, drops rows with neither."""
        data = pl.DataFrame({
            "outcome": [1, None, 3, None, 5],
            "pred_a": [10, 20, None, None, None],
            "pred_b": [100, None, 300, None, None],
        })

        result = filter_relevant_rows(
            data, "outcome", ["pred_a", "pred_b"]
        )

        # Row 0: outcome=1, pred_a=10 → keep
        # Row 1: pred_a=20 (no outcome) → keep (for lag analysis)
        # Row 2: outcome=3, pred_b=300 → keep
        # Row 3: all null → drop (no outcome, no predictors)
        # Row 4: outcome=5 (no predictors) → keep (for lag analysis)
        assert result.height == 4

    def test_drops_rows_with_neither_outcome_nor_predictors(self):
        """Drops only rows with neither outcome nor any predictor value."""
        data = pl.DataFrame({
            "outcome": [1, None, None],
            "predictor": [None, 20, None],
        })

        result = filter_relevant_rows(data, "outcome", ["predictor"])

        # Row 0: outcome=1 → keep
        # Row 1: predictor=20 → keep (supports lag detection)
        # Row 2: both null → drop
        assert result.height == 2


class TestR1EmptyRows:
    """Tests for R1: Empty row filter (completely empty rows)."""

    def test_drops_all_null_rows(self):
        """Drops rows with all columns null."""
        data = pl.DataFrame({
            "outcome": [1, None, 3, None],
            "pred_a": [10, 20, None, None],
            "pred_b": [100, None, 300, None],
        })

        result = filter_uninformative_rows(data)

        # Row 0: outcome=1, pred_a=10, pred_b=100 → keep
        # Row 1: pred_a=20 (non-null) → keep
        # Row 2: outcome=3, pred_b=300 → keep
        # Row 3: all null → drop
        assert result.height == 3

    def test_preserves_rows_with_any_non_null(self):
        """Preserves any row with at least one non-null value."""
        data = pl.DataFrame({
            "outcome": [10, None, 12, None],
            "predictor": [None, 20, None, 30],
            "other": [None, None, None, None],
        })

        result = filter_uninformative_rows(data)

        # Rows 0,1,2,3 all have at least one non-null value
        # The "other" column being all-null doesn't matter
        assert result.height == 4


class TestR2WarmupFilter:
    """Tests for R2: Warmup/cooldown exclusion."""

    def test_skips_warmup_fraction(self):
        """Skips first N% of rows."""
        data = pl.DataFrame({
            "outcome": list(range(100)),
        })

        result = filter_steady_state(
            data, "outcome", warmup_fraction=0.1
        )

        # Should skip first 10 rows
        assert result.height == 90
        assert result["outcome"][0] == 10


class TestReduceRowsIntegration:
    """Integration tests for the full row reduction pipeline."""

    def test_skips_reduction_if_small_data(self):
        """Skips reduction if data is below threshold."""
        data = pl.DataFrame({
            "outcome": [1, 2, 3],
            "predictor": [10, 20, 30],
        })

        from src.core.config.settings import Settings
        settings = Settings()
        result = reduce_rows(data, "outcome", ["predictor"], settings)

        # With default threshold of 50K rows, small data should pass through unchanged
        assert result.height == 3

    def test_reduction_disabled_returns_data_unmodified(self):
        """When disabled, reduce_rows should return the original DataFrame."""
        data = pl.DataFrame({
            "outcome": [1, None, 3, None],
            "predictor": [10, None, None, None],
            "other": [None, None, None, None],
        })
        settings = _DummySettings({"profiling.data_reduction.enabled": False})

        result = reduce_rows(data, "outcome", ["predictor"], settings)

        assert result.equals(data)
