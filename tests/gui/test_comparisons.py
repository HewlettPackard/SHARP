"""
Tests for GUI comparison utilities.

Tests pure functions in src/gui/utils/comparisons.py that don't require Shiny.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import numpy as np

from src.gui.utils.comparisons import (
    _compute_pct_change,
    compute_comparison_summary,
)


class TestComputePctChange:
    """Tests for _compute_pct_change function.

    Note: _compute_pct_change returns a tuple of (pct_str, raw_value_or_none).
    """

    def test_positive_change(self):
        """Test percentage change for increase."""
        # 50 to 100 is 100% increase
        pct_str, raw_value = _compute_pct_change(50.0, 100.0)
        assert raw_value == 100.0
        assert pct_str == "+100.0%"

    def test_negative_change(self):
        """Test percentage change for decrease."""
        # 100 to 50 is -50% change
        pct_str, raw_value = _compute_pct_change(100.0, 50.0)
        assert raw_value == -50.0
        assert pct_str == "-50.0%"

    def test_no_change(self):
        """Test percentage change when values are equal."""
        pct_str, raw_value = _compute_pct_change(100.0, 100.0)
        assert raw_value == 0.0
        assert pct_str == "+0.0%"

    def test_zero_baseline_returns_infinity_symbol(self):
        """Test that zero baseline returns infinity symbol and None raw value."""
        pct_str, raw_value = _compute_pct_change(0.0, 100.0)
        assert raw_value is None
        assert pct_str == "∞"

    def test_zero_baseline_zero_treatment_returns_zero_pct(self):
        """Test that zero baseline with zero treatment returns 0%."""
        pct_str, raw_value = _compute_pct_change(0.0, 0.0)
        assert raw_value is None
        assert pct_str == "0%"

    def test_small_baseline(self):
        """Test with very small baseline value."""
        # 0.001 to 0.002 is 100% increase
        pct_str, raw_value = _compute_pct_change(0.001, 0.002)
        assert raw_value == pytest.approx(100.0, rel=1e-6)

    def test_negative_values(self):
        """Test with negative values."""
        # -100 to -50: ((-50) - (-100)) / (-100) * 100 = 50 / -100 * 100 = -50%
        pct_str, raw_value = _compute_pct_change(-100.0, -50.0)
        assert raw_value == pytest.approx(-50.0, rel=1e-6)


class TestComputeComparisonSummary:
    """Tests for compute_comparison_summary function.

    Note: compute_comparison_summary returns a dict with:
    - 'statistic_names': list of statistic names
    - 'baseline': list of formatted baseline values
    - 'treatment': list of formatted treatment values
    - 'pct_change': list of percentage change strings
    """

    @pytest.fixture
    def baseline_data(self):
        """Create baseline comparison data."""
        return np.array([100.0, 110.0, 105.0, 95.0, 100.0])

    @pytest.fixture
    def comparison_data(self):
        """Create comparison data with slight improvement."""
        return np.array([90.0, 100.0, 95.0, 85.0, 90.0])

    def test_basic_comparison(self, baseline_data, comparison_data):
        """Test basic comparison summary returns expected structure."""
        result = compute_comparison_summary(baseline_data, comparison_data)

        assert result is not None
        assert "statistic_names" in result
        assert "baseline" in result
        assert "treatment" in result
        assert "pct_change" in result

    def test_includes_expected_statistics(self, baseline_data, comparison_data):
        """Test that result includes all expected statistics."""
        result = compute_comparison_summary(baseline_data, comparison_data)

        expected_stats = ['n', 'min', 'median', 'mode', 'mean',
                         'CI95_low', 'CI95_high', 'p95', 'p99', 'max',
                         'stddev', 'stderr', 'cv']
        assert result["statistic_names"] == expected_stats

    def test_same_length_arrays(self, baseline_data, comparison_data):
        """Test that all arrays in result have same length."""
        result = compute_comparison_summary(baseline_data, comparison_data)

        n_stats = len(result["statistic_names"])
        assert len(result["baseline"]) == n_stats
        assert len(result["treatment"]) == n_stats
        assert len(result["pct_change"]) == n_stats

    def test_sample_size_dash_for_pct_change(self, baseline_data, comparison_data):
        """Test that sample size (n) shows dash for pct change."""
        result = compute_comparison_summary(baseline_data, comparison_data)

        n_index = result["statistic_names"].index("n")
        assert result["pct_change"][n_index] == "-"

    def test_pct_change_strings_formatted(self, baseline_data, comparison_data):
        """Test that percentage changes are formatted strings."""
        result = compute_comparison_summary(baseline_data, comparison_data)

        # Mean pct change should be a string with % sign (treatment < baseline = negative)
        mean_index = result["statistic_names"].index("mean")
        pct_str = result["pct_change"][mean_index]
        assert isinstance(pct_str, str)
        # Treatment mean (92) < Baseline mean (102) so should be negative
        assert "-" in pct_str or "∞" in pct_str or "NA" in pct_str

    def test_identical_data_zero_change(self):
        """Test comparison of identical data shows no change."""
        data = np.array([100.0, 100.0, 100.0])
        result = compute_comparison_summary(data, data.copy())

        mean_index = result["statistic_names"].index("mean")
        assert "+0.0%" in result["pct_change"][mean_index]

    def test_values_formatted_as_strings(self, baseline_data, comparison_data):
        """Test that values are formatted as strings."""
        result = compute_comparison_summary(baseline_data, comparison_data)

        # All values should be strings
        for val in result["baseline"]:
            assert isinstance(val, str)
        for val in result["treatment"]:
            assert isinstance(val, str)
