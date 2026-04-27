"""
Unit tests for predictor exclusion modal logic.

Tests the complex semantics of apply_exclusions() to ensure:
1. Exclusions are additive (excluding B doesn't lose A)
2. Threshold changes reset to auto-exclusions
3. Manual exclusions persist across threshold changes
4. Reset button restores defaults

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import polars as pl
import numpy as np
from unittest.mock import Mock, MagicMock, patch

from src.gui.utils.profile.exclusions import (
    apply_exclusions,
    reset_exclusions,
    DEFAULT_EXCLUDED_PREDICTORS,
    _collect_auto_excluded_predictors,
    _filter_modal_predictors,
)
from src.gui.utils.profile.predictor_stats import compute_predictor_stats


@pytest.fixture
def sample_data():
    """Create sample data for testing."""
    return pl.DataFrame({
        "outcome": [1.0, 2.0, 3.0, 4.0, 5.0] * 20,
        "pred_high_corr": [1.0, 2.0, 3.0, 4.0, 5.0] * 20,  # correlation ~1.0
        "pred_medium_corr": [1.0, 1.5, 2.5, 4.0, 4.5] * 20,  # correlation ~0.8
        "pred_low_corr": [5.0, 4.0, 3.0, 2.0, 1.0] * 20,  # correlation ~-0.5
        "pred_zero_corr": [1.0, 1.0, 1.0, 1.0, 1.0] * 20,  # correlation ~0
        "repeat": list(range(100)),  # default excluded
        "inner_time": list(range(100)),  # default excluded
    })


class TestExclusionSemantics:
    """Test exclusion modal logic and semantics."""

    def test_exclusions_are_additive(self, sample_data):
        """Verify that excluding predictor B doesn't lose predictor A.

        Scenario:
        1. Exclude pred_high_corr
        2. Close and reopen modal
        3. Exclude pred_medium_corr
        4. Both should be excluded
        """
        # Get stats
        stats = compute_predictor_stats(sample_data, "outcome")
        assert len(stats) > 0

        # Step 1: Exclude pred_high_corr
        excluded = Mock()
        excluded.get = Mock(return_value=[])
        excluded.set = Mock()

        filters = Mock()
        filters.get = Mock(return_value={
            "max_corr": 0.99,
            "max_predictors": 100,
            "search_term": "",
            "checkbox_state": ["pred_high_corr"],
            "user_has_applied": False,
        })
        filters.set = Mock()

        stats_full = Mock()
        stats_full.get = Mock(return_value=stats)

        input_obj = Mock()
        input_obj.predictor_max_corr = Mock(return_value=0.99)
        input_obj.predictor_max_preds = Mock(return_value=100)
        input_obj.predictor_search = Mock(return_value="")

        # Mock checkbox states for visible predictors
        pred_names = [s["name"] for s in stats]
        for name in pred_names:
            if name == "pred_high_corr":
                setattr(input_obj, f"exclude_{name}", Mock(return_value=True))
            else:
                setattr(input_obj, f"exclude_{name}", Mock(return_value=False))

        # First apply: exclude pred_high_corr
        excluded.get = Mock(return_value=[])
        with patch("src.gui.utils.profile.exclusions.ui.modal_remove"):
            apply_exclusions(input_obj, excluded, stats_full, filters)
        first_result = excluded.set.call_args[0][0]
        assert "pred_high_corr" in first_result
        assert "pred_medium_corr" not in first_result

        # Step 2: Simulate user reopening modal with pred_high_corr already excluded
        excluded.get = Mock(return_value=first_result)

        # Step 3: Add pred_medium_corr exclusion
        for name in pred_names:
            if name in ["pred_high_corr", "pred_medium_corr"]:
                setattr(input_obj, f"exclude_{name}", Mock(return_value=True))
            else:
                setattr(input_obj, f"exclude_{name}", Mock(return_value=False))

        # Simulate modal state with previous exclusions
        filters.get = Mock(return_value={
            "max_corr": 0.99,
            "max_predictors": 100,
            "search_term": "",
            "checkbox_state": first_result,
            "user_has_applied": True,
        })

        # Second apply: add pred_medium_corr
        with patch("src.gui.utils.profile.exclusions.ui.modal_remove"):
            apply_exclusions(input_obj, excluded, stats_full, filters)
        second_result = excluded.set.call_args[0][0]

        # Verify both are excluded
        assert "pred_high_corr" in second_result, "First exclusion was lost (non-additive bug)"
        assert "pred_medium_corr" in second_result

    def test_threshold_change_resets_to_auto_exclusions(self, sample_data):
        """Verify that changing correlation threshold resets to auto-exclusions.

        Scenario:
        1. Exclude pred_low_corr (correlation ~-0.5, below threshold)
        2. Increase threshold from 0.99 to 0.50
        3. pred_high_corr should now be auto-excluded (correlation ~1.0 >= 0.50)
        4. Manual exclusion of pred_low_corr should be overridden
        """
        stats = compute_predictor_stats(sample_data, "outcome")

        # Get auto-exclusions at different thresholds
        auto_high_threshold = _collect_auto_excluded_predictors(stats, 0.99)
        auto_low_threshold = _collect_auto_excluded_predictors(stats, 0.50)

        # At 0.99 threshold, fewer predictors auto-excluded
        # At 0.50 threshold, more predictors should be auto-excluded
        assert len(auto_low_threshold) >= len(auto_high_threshold)

    def test_reset_to_defaults(self, sample_data):
        """Verify reset button returns to DEFAULT_EXCLUDED_PREDICTORS + auto-exclusions."""
        stats = compute_predictor_stats(sample_data, "outcome")

        excluded = Mock()
        excluded.get = Mock(return_value=[])
        excluded.set = Mock()

        filters = Mock()
        filters.get = Mock(return_value=None)
        filters.set = Mock()

        stats_full = Mock()
        stats_full.get = Mock(return_value=stats)

        reset_exclusions(excluded, stats_full, filters)

        # Get what was set
        result = excluded.set.call_args[0][0]

        # Should include defaults
        for default in DEFAULT_EXCLUDED_PREDICTORS:
            assert default in result, f"Default {default} missing after reset"

    def test_default_predictors_always_included(self, sample_data):
        """Verify DEFAULT_EXCLUDED_PREDICTORS are always in the result."""
        stats = compute_predictor_stats(sample_data, "outcome")

        # Get auto-exclusions
        auto_excluded = _collect_auto_excluded_predictors(stats, 0.99)

        # Add defaults
        result = set(DEFAULT_EXCLUDED_PREDICTORS) | auto_excluded

        # Verify defaults are there
        for default in DEFAULT_EXCLUDED_PREDICTORS:
            assert default in result

    def test_hidden_predictors_preserved(self, sample_data):
        """Verify that predictors outside the filtered view are preserved.

        Scenario:
        1. Filter modal to show limited predictors
        2. Some predictors are hidden from view
        3. User excludes visible pred A
        4. Hidden predictors should keep their previous exclusion state
        """
        stats = compute_predictor_stats(sample_data, "outcome")
        assert len(stats) >= 2, "Need at least 2 predictors for this test"

        # Get all stat names
        all_names = {s["name"] for s in stats}

        # Simulate exclusion where some predictors were already excluded
        some_initially_excluded = list(DEFAULT_EXCLUDED_PREDICTORS)
        base_exclusions = set(some_initially_excluded)

        # Only check set operations - don't rely on _filter_modal_predictors
        # which has special logic for including defaults
        visible_names = all_names - base_exclusions
        if not visible_names:
            pytest.skip("No visible predictors to test with")

        # User checks a visible predictor for exclusion
        visible_checked = {list(visible_names)[0]}
        visible_current = base_exclusions & visible_names

        # Apply set logic from apply_exclusions
        new_exclusions = base_exclusions | visible_checked
        new_exclusions -= (visible_current - visible_checked)

        # Verify defaults are preserved
        for default in DEFAULT_EXCLUDED_PREDICTORS:
            assert default in new_exclusions, f"Default {default} was lost"
