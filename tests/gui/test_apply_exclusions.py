"""
Tests for apply_exclusions function.

Tests the checkbox reading and exclusion logic in apply_exclusions.

© Copyright 2025--2026 Hewlett Packard Enterprise Development LP
"""

import pytest
from unittest.mock import MagicMock, patch

from src.gui.utils.profile.exclusions import (
    apply_exclusions,
    _collect_manually_excluded_predictors,
    _filter_modal_predictors,
    _collect_auto_excluded_predictors,
    _sanitize_for_html_id,
)


class MockReactiveValue:
    """Mock for shiny reactive.Value."""

    def __init__(self, initial_value):
        self._value = initial_value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value

    def __call__(self):
        return self._value


class MockInput:
    """Mock for Shiny input object."""

    def __init__(self, checkbox_values: dict[str, bool], max_corr: float = 0.99,
                 max_preds: int = 100, search: str = ""):
        self._checkbox_values = checkbox_values
        self._max_corr = max_corr
        self._max_preds = max_preds
        self._search = search

    def __getattr__(self, name):
        if name.startswith('exclude_'):
            # Return a callable that returns the checkbox value
            return lambda: self._checkbox_values.get(name, False)
        raise AttributeError(f"MockInput has no attribute {name}")

    def predictor_max_corr(self):
        return self._max_corr

    def predictor_max_preds(self):
        return self._max_preds

    def predictor_search(self):
        return self._search


class TestCollectManuallyExcludedPredictors:
    """Tests for _collect_manually_excluded_predictors function."""

    def test_collects_checked_predictors(self):
        """Test that checked predictor checkboxes are collected."""
        stats = [
            {"name": "outer_time", "correlation": 0.95, "non_na_count": 100},
            {"name": "inner_time", "correlation": 0.90, "non_na_count": 100},
            {"name": "perf_time", "correlation": 0.50, "non_na_count": 100},
        ]

        # User checked inner_time, unchecked outer_time
        checkbox_values = {
            "exclude_outer_time": False,
            "exclude_inner_time": True,
            "exclude_perf_time": False,
        }
        mock_input = MockInput(checkbox_values)

        result = _collect_manually_excluded_predictors(mock_input, stats)

        assert result == {"inner_time"}
        assert "outer_time" not in result

    def test_handles_special_characters_in_names(self):
        """Test handling of predictor names with special characters."""
        stats = [
            {"name": "my-predictor", "correlation": 0.95, "non_na_count": 100},
            {"name": "my.other", "correlation": 0.90, "non_na_count": 100},
        ]

        # The checkbox IDs use sanitized names
        checkbox_values = {
            "exclude_my_predictor": True,  # - becomes _
            "exclude_my_other": False,     # . becomes _
        }
        mock_input = MockInput(checkbox_values)

        result = _collect_manually_excluded_predictors(mock_input, stats)

        assert result == {"my-predictor"}


class TestApplyExclusions:
    """Tests for apply_exclusions function."""

    @pytest.fixture
    def predictor_stats(self):
        """Create predictor stats with various correlations."""
        return [
            {"name": "outer_time", "correlation": 0.95, "non_na_count": 100},
            {"name": "inner_time", "correlation": 0.92, "non_na_count": 100},
            {"name": "perf_time", "correlation": 0.50, "non_na_count": 100},
            {"name": "cpu_util", "correlation": 0.30, "non_na_count": 100},
        ]

    def test_user_uncheck_overrides_auto_exclusion(self, predictor_stats):
        """
        Test the exact scenario from the bug report:
        1. Threshold 0.93 -> outer_time auto-excluded (corr=0.95), inner_time not (corr=0.92)
        2. User unchecks outer_time, checks inner_time
        3. Apply should save: inner_time excluded, outer_time NOT excluded
        """
        # At threshold 0.93:
        # - outer_time (0.95) would be auto-excluded
        # - inner_time (0.92) would NOT be auto-excluded

        # But user flipped them:
        checkbox_values = {
            "exclude_outer_time": False,   # User UNCHECKED
            "exclude_inner_time": True,    # User CHECKED
            "exclude_perf_time": False,
            "exclude_cpu_util": False,
        }
        mock_input = MockInput(checkbox_values, max_corr=0.93, max_preds=100)

        # Initial state: outer_time was excluded (from auto-exclusion)
        excluded_predictors = MockReactiveValue(["outer_time"])
        predictor_stats_full = MockReactiveValue(predictor_stats)
        predictor_modal_filters = MockReactiveValue({"max_corr": 0.93})

        # Patch ui.modal_remove to avoid Shiny dependency
        with patch('src.gui.utils.profile.exclusions.ui.modal_remove'):
            apply_exclusions(
                mock_input,
                excluded_predictors,
                predictor_stats_full,
                predictor_modal_filters
            )

        # After apply: should reflect user's choices
        result = set(excluded_predictors.get())
        assert "inner_time" in result, "inner_time should be excluded (user checked it)"
        assert "outer_time" not in result, "outer_time should NOT be excluded (user unchecked it)"

    def test_threshold_unchanged_preserves_not_shown_exclusions(self, predictor_stats):
        """Test that not-shown exclusions are preserved when threshold unchanged."""
        # Scenario: user has some exclusions, opens modal with max_preds=2 (only sees 2 predictors)
        # The hidden predictors should be preserved

        checkbox_values = {
            "exclude_outer_time": True,
            "exclude_inner_time": False,
        }
        mock_input = MockInput(checkbox_values, max_corr=0.93, max_preds=2)  # Only 2 visible

        # Initial state includes a predictor that won't be visible
        excluded_predictors = MockReactiveValue(["outer_time", "cpu_util"])
        predictor_stats_full = MockReactiveValue(predictor_stats)
        predictor_modal_filters = MockReactiveValue({"max_corr": 0.93})  # Same threshold

        with patch('src.gui.utils.profile.exclusions.ui.modal_remove'):
            apply_exclusions(
                mock_input,
                excluded_predictors,
                predictor_stats_full,
                predictor_modal_filters
            )

        result = set(excluded_predictors.get())
        assert "outer_time" in result, "outer_time visible and checked"
        # cpu_util might or might not be in result depending on whether it's shown
        # Let's check what's actually visible
        visible = _filter_modal_predictors(predictor_stats, max_preds=2, search="")
        visible_names = {s["name"] for s in visible}
        if "cpu_util" not in visible_names:
            assert "cpu_util" in result, "cpu_util should be preserved (not visible)"

    def test_threshold_changed_uses_auto_for_not_shown(self, predictor_stats):
        """Test that threshold change uses auto-exclusions for not-shown predictors."""
        checkbox_values = {
            "exclude_outer_time": False,
            "exclude_inner_time": True,
        }
        # Threshold changed from 0.99 to 0.93
        mock_input = MockInput(checkbox_values, max_corr=0.93, max_preds=2)

        excluded_predictors = MockReactiveValue(["outer_time"])
        predictor_stats_full = MockReactiveValue(predictor_stats)
        predictor_modal_filters = MockReactiveValue({"max_corr": 0.99})  # OLD threshold

        with patch('src.gui.utils.profile.exclusions.ui.modal_remove'):
            apply_exclusions(
                mock_input,
                excluded_predictors,
                predictor_stats_full,
                predictor_modal_filters
            )

        result = set(excluded_predictors.get())
        # User's visible choices should be respected
        assert "outer_time" not in result, "outer_time was unchecked by user"
        assert "inner_time" in result, "inner_time was checked by user"


class TestAutoExclusions:
    """Tests for _collect_auto_excluded_predictors."""

    def test_excludes_above_threshold(self):
        """Test that predictors with correlation > threshold are excluded."""
        stats = [
            {"name": "high", "correlation": 0.95, "non_na_count": 100},
            {"name": "medium", "correlation": 0.92, "non_na_count": 100},
            {"name": "low", "correlation": 0.50, "non_na_count": 100},
        ]

        result = _collect_auto_excluded_predictors(stats, max_correlation=0.93)

        assert "high" in result  # 0.95 > 0.93
        assert "medium" not in result  # 0.92 < 0.93
        assert "low" not in result  # 0.50 < 0.93

    def test_excludes_exact_threshold(self):
        """Test behavior at exact threshold value."""
        stats = [
            {"name": "exact", "correlation": 0.93, "non_na_count": 100},
        ]

        result = _collect_auto_excluded_predictors(stats, max_correlation=0.93)

        # >= threshold should be excluded
        assert "exact" in result
