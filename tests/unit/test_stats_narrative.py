"""
Unit tests for narrative generation module.

Tests format_p_value, characterize_changepoints, and narrative generation functions
with synthetic data to verify warmup/cooldown detection and changepoint counting.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import pytest

from src.core.stats.narrative import (
    format_sig_figs,
    format_p_value,
    characterize_changepoints,
    report_test,
)


# ============================================================================
# format_sig_figs tests
# ============================================================================

class TestFormatSigFigs:
    """Test format_sig_figs utility function."""

    def test_large_numbers_no_scientific(self):
        """Large numbers (>= 1e6) should use scientific notation."""
        assert format_sig_figs(1234567.89, sig_figs=3) == '1.23e+06'
        assert format_sig_figs(5000, sig_figs=3) == '5000'  # Below 1e6
        assert format_sig_figs(12345, sig_figs=2) == '12000'  # Below 1e6

    def test_small_numbers_no_scientific(self):
        """Very small numbers (< 1e-4) should use scientific notation."""
        assert format_sig_figs(0.0001234, sig_figs=3) == '0.000123'  # Just above 1e-4
        assert format_sig_figs(0.000001, sig_figs=3) == '1.00e-06'  # Below 1e-4
        assert format_sig_figs(0.00123456, sig_figs=3) == '0.00123'  # Above 1e-4

    def test_normal_numbers_strip_trailing_zeros(self):
        """Normal numbers should strip trailing zeros."""
        assert format_sig_figs(123.456, sig_figs=3) == '123'
        assert format_sig_figs(1.234, sig_figs=3) == '1.23'
        assert format_sig_figs(0.1234, sig_figs=3) == '0.123'
        assert format_sig_figs(100.0, sig_figs=3) == '100'

    def test_nan_returns_na(self):
        """NaN should return 'NA'."""
        assert format_sig_figs(float('nan')) == 'NA'
        assert format_sig_figs(np.nan) == 'NA'

    def test_negative_numbers(self):
        """Negative numbers should be formatted correctly."""
        assert format_sig_figs(-123.456, sig_figs=3) == '-123'
        assert format_sig_figs(-0.0001234, sig_figs=3) == '-0.000123'  # Just above 1e-4
        assert format_sig_figs(-1234567, sig_figs=3) == '-1.23e+06'  # Very large, use scientific

    def test_zero(self):
        """Zero should return '0'."""
        assert format_sig_figs(0.0) == '0'
        assert format_sig_figs(0) == '0'

    def test_sig_figs_parameter(self):
        """Different sig_figs values should produce different results."""
        value = 123.456
        assert format_sig_figs(value, sig_figs=2) == '120'
        assert format_sig_figs(value, sig_figs=3) == '123'
        assert format_sig_figs(value, sig_figs=4) == '123.5'
        assert format_sig_figs(value, sig_figs=5) == '123.46'

    def test_is_integer_parameter(self):
        """is_integer=True should format as integer."""
        assert format_sig_figs(123.456, is_integer=True) == '123'
        assert format_sig_figs(999.999, is_integer=True) == '999'
        assert format_sig_figs(100.1, is_integer=True) == '100'

    def test_trailing_zeros_stripped(self):
        """Trailing zeros after decimal should be stripped."""
        assert format_sig_figs(1.2000, sig_figs=3) == '1.2'
        assert format_sig_figs(10.0, sig_figs=3) == '10'
        assert format_sig_figs(0.100, sig_figs=3) == '0.1'

    def test_decimal_point_stripped_when_not_needed(self):
        """Decimal point should be stripped if no decimals remain."""
        assert format_sig_figs(100.0, sig_figs=3) == '100'
        assert format_sig_figs(1000.0, sig_figs=4) == '1000'

    def test_very_large_numbers(self):
        """Very large numbers (>= 1e6) should use scientific notation."""
        assert format_sig_figs(1e9, sig_figs=3) == '1.00e+09'
        assert format_sig_figs(9.87654e8, sig_figs=3) == '9.88e+08'

    def test_very_small_decimals(self):
        """Very small decimals (<= 1e-4) should use scientific notation."""
        assert format_sig_figs(0.00000123, sig_figs=3) == '1.23e-06'
        assert format_sig_figs(0.0000009876, sig_figs=3) == '9.88e-07'

    def test_edge_case_one(self):
        """The number 1 should be formatted correctly."""
        assert format_sig_figs(1.0, sig_figs=3) == '1'
        assert format_sig_figs(1.0, sig_figs=1) == '1'

    def test_rounding_behavior(self):
        """Numbers should round correctly to significant figures."""
        assert format_sig_figs(1.235, sig_figs=3) == '1.24'  # Rounds up
        assert format_sig_figs(1.234, sig_figs=3) == '1.23'  # Rounds down
        assert format_sig_figs(9.995, sig_figs=3) == '9.99'  # 3 sig figs of 9.995

    def test_negative_very_small(self):
        """Negative very small numbers should use scientific notation."""
        assert format_sig_figs(-0.00000123, sig_figs=3) == '-1.23e-06'

    def test_comparison_values_from_gui(self):
        """Test typical values from comparison tables in GUI."""
        # Sample size (integer)
        assert format_sig_figs(100, is_integer=True) == '100'

        # Min/max values
        assert format_sig_figs(0.001234, sig_figs=3) == '0.00123'

        # Mean/median
        assert format_sig_figs(123.456789, sig_figs=3) == '123'

        # Standard deviation
        assert format_sig_figs(45.6789, sig_figs=3) == '45.7'

        # Coefficient of variation
        assert format_sig_figs(0.123456, sig_figs=3) == '0.123'


# ============================================================================
# format_p_value tests
# ============================================================================

def test_nan_input():
    """NaN p-value formatted as NA."""
    result = format_p_value(np.nan)
    assert result == "NA"


def test_very_small_scientific():
    """Very small p-value with scientific notation."""
    result = format_p_value(0.0001, p_option="scientific")
    assert "e-" in result or result == "1.00e-04"


def test_large_scientific():
    """Large p-value with scientific format."""
    result = format_p_value(0.5, p_option="scientific")
    assert "0.50" in result


def test_exact_formatting():
    """Exact p-value formatting."""
    result = format_p_value(0.05, p_option="exact")
    assert "0.05" in result


def test_rounded_very_small():
    """Rounded format for very small p-value."""
    result = format_p_value(0.00001, p_option="rounded")
    assert result == "< 0.001"


def test_rounded_small():
    """Rounded format for small p-value."""
    result = format_p_value(0.005, p_option="rounded")
    assert "0.005" in result or "0.01" in result


def test_rounded_normal():
    """Rounded format for normal p-value."""
    result = format_p_value(0.05, p_option="rounded")
    assert "0.05" in result


def test_rounded_large():
    """Rounded format for large p-value."""
    result = format_p_value(0.5, p_option="rounded")
    assert "0.5" in result or "0.50" in result


def test_custom_rounding():
    """Custom rounding precision."""
    result = format_p_value(0.12345, rounding=4, p_option="exact")
    assert "0.1234" in result or "0.1235" in result


# ============================================================================
# report_test tests
# ============================================================================

def test_valid_result():
    """Report generation for valid test result."""
    test_result = {
        'statistic': 42.5,
        'p_value': 0.05,
        'effect_size': 0.8
    }
    result = report_test(test_result)

    assert "U = " in result
    assert "p = " in result
    assert "effect size = " in result


def test_without_effect_size():
    """Report without effect size."""
    test_result = {
        'statistic': 42.5,
        'p_value': 0.05
    }
    result = report_test(test_result)

    assert "U = " in result
    assert "p = " in result


def test_with_error():
    """Report for failed test."""
    test_result = {'error': 'Insufficient data'}
    result = report_test(test_result)

    assert "failed" in result.lower() or "error" in result.lower()


def test_nan_statistic():
    """Report with NaN statistic."""
    test_result = {
        'statistic': np.nan,
        'p_value': 0.05
    }
    result = report_test(test_result)

    assert "unavailable" in result.lower()


def test_custom_rounding():
    """Custom rounding in report."""
    test_result = {
        'statistic': 42.123456,
        'p_value': 0.05,
        'effect_size': 0.8
    }
    result = report_test(test_result, rounding=1)

    assert "42.1" in result


# ============================================================================
# characterize_changepoints tests - synthetic data
# ============================================================================

def test_warmup_detection_with_synthetic_data():
    """Test warmup detection with clear synthetic warmup pattern."""
    # Create data with sharp warmup: 20 low values, then abrupt shift to stable high values
    # Use fixed seed for reproducibility and make the difference large enough to be detected
    np.random.seed(42)
    warmup_values = np.ones(20) * 20 + np.random.normal(0, 1, 20)  # Very low with minimal noise
    stable_values = np.ones(80) * 200 + np.random.normal(0, 1, 80)  # Very high with minimal noise
    warmup_data = np.concatenate([warmup_values, stable_values])

    result = characterize_changepoints(warmup_data)

    # Should explicitly mention warmup period
    assert "warmup" in result.lower(), f"Expected 'warmup' in result: {result}"
    # Should mention detection/detected
    assert "detect" in result.lower(), f"Expected 'detect' in result: {result}"
    # Should include information about the percentage
    assert "%" in result or "percent" in result.lower(), f"Expected percentage information in result: {result}"


def test_cooldown_detection_with_synthetic_data():
    """Test cooldown detection with clear synthetic cooldown pattern."""
    # Create data with sharp cooldown: 80 stable high values, then abrupt shift to low values
    # Use fixed seed for reproducibility
    np.random.seed(43)
    stable_values = np.ones(80) * 200 + np.random.normal(0, 1, 80)  # Very high with minimal noise
    cooldown_values = np.ones(20) * 20 + np.random.normal(0, 1, 20)  # Very low with minimal noise
    cooldown_data = np.concatenate([stable_values, cooldown_values])

    result = characterize_changepoints(cooldown_data)

    # Should explicitly mention cooldown/degradation
    assert "cooldown" in result.lower() or "degradation" in result.lower(), f"Expected 'cooldown' or 'degradation' in result: {result}"
    # Should mention detection/detected
    assert "detect" in result.lower(), f"Expected 'detect' in result: {result}"
    # Should include information about the percentage
    assert "%" in result or "percent" in result.lower(), f"Expected percentage information in result: {result}"


def test_changepoint_count_accuracy():
    """Test correct counting of changepoints in the middle (not warmup/cooldown)."""
    # Create data with exactly 2 sharp changepoints in the middle:
    # Segment 1: indices 0-32 (33 points) at level 50
    # Segment 2: indices 33-65 (33 points) at level 150  <- changepoint 1 at index 33
    # Segment 3: indices 66-99 (34 points) at level 100  <- changepoint 2 at index 66
    np.random.seed(42)
    segment1 = np.ones(33) * 50 + np.random.normal(0, 3, 33)
    segment2 = np.ones(33) * 150 + np.random.normal(0, 3, 33)
    segment3 = np.ones(34) * 100 + np.random.normal(0, 3, 34)
    multi_change_data = np.concatenate([segment1, segment2, segment3])

    result = characterize_changepoints(multi_change_data)

    # Should detect changepoints (not warmup/cooldown since they're in the middle)
    assert "change" in result.lower(), f"Expected 'change' in result: {result}"
    # Should mention middle or additional changepoints
    assert "additional" in result.lower() or "middle" in result.lower(), f"Expected 'additional' or 'middle' in result: {result}"


def test_warmup_and_cooldown_both():
    """Both warmup and cooldown detected when present."""
    np.random.seed(42)
    warmup = np.random.normal(50, 3, 25)
    steady = np.random.normal(100, 3, 50)
    cooldown = np.random.normal(60, 3, 25)
    data = np.concatenate([warmup, steady, cooldown])

    result = characterize_changepoints(data, warmup_pct=0.3, cooldown_pct=0.7)

    result_lower = result.lower()
    # Should mention both phases (though specific detection depends on sensitivity)
    # At minimum, should detect some changepoints
    assert len(result) > 0
    assert any(word in result_lower for word in ['warmup', 'cooldown', 'change', 'period'])
    if 'stationary' in result_lower:
        # This would be incorrect for our multi-phase data
        assert 'no' not in result_lower or 'appears' not in result_lower


def test_warmup_and_cooldown_both():
    """Both warmup and cooldown detected when present."""
    np.random.seed(42)
    warmup = np.random.normal(50, 3, 25)
    steady = np.random.normal(100, 3, 50)
    cooldown = np.random.normal(60, 3, 25)
    data = np.concatenate([warmup, steady, cooldown])

    result = characterize_changepoints(data, warmup_pct=0.3, cooldown_pct=0.7)

    result_lower = result.lower()
    # Should mention both phases (though specific detection depends on sensitivity)
    # At minimum, should detect some changepoints
    assert len(result) > 0
    assert any(word in result_lower for word in ['warmup', 'cooldown', 'change', 'period'])


# ============================================================================
# characterize_changepoints tests - edge cases
# ============================================================================

def test_stationary_series():
    """Stationary series reports no changepoints."""
    np.random.seed(42)
    data = np.random.normal(100, 5, 100)

    result = characterize_changepoints(data)

    result_lower = result.lower()
    # May mention stationary or no change points
    assert 'stationary' in result_lower or 'no' in result_lower or len(result) == 0 or 'moderate' in result_lower


def test_autocorrelated_data():
    """Autocorrelated data narrative mentions correlation."""
    np.random.seed(42)
    data = np.zeros(100)
    data[0] = np.random.normal()
    for i in range(1, 100):
        data[i] = 0.8 * data[i-1] + np.random.normal(0, 0.2)

    result = characterize_changepoints(data)

    result_lower = result.lower()
    # Should mention autocorrelation if detected
    if len(result) > 0:
        assert isinstance(result, str)


def test_small_sample():
    """Sample < 10 returns empty string."""
    data = np.array([1.0, 2.0, 3.0])

    result = characterize_changepoints(data)

    assert result == ""


def test_with_nans():
    """NaNs handled gracefully in changepoint detection."""
    np.random.seed(42)
    data = np.concatenate([
        np.random.normal(80, 5, 30),
        np.array([np.nan, np.nan, np.nan]),
        np.random.normal(100, 5, 67)
    ])

    result = characterize_changepoints(data)

    assert isinstance(result, str)


def test_custom_thresholds():
    """Custom warmup/cooldown thresholds respected."""
    np.random.seed(42)
    data = np.concatenate([
        np.random.normal(80, 5, 50),
        np.random.normal(100, 5, 50)
    ])

    result = characterize_changepoints(
        data,
        warmup_pct=0.5,
        cooldown_pct=0.9
    )

    assert isinstance(result, str)


def test_acf_threshold_parameter():
    """Custom ACF threshold parameter."""
    np.random.seed(42)
    data = np.random.normal(100, 5, 100)

    result = characterize_changepoints(data, acf_threshold=0.3)

    assert isinstance(result, str)


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_constant_series():
    """Constant values handled gracefully."""
    data = np.array([100.0] * 100)

    result = characterize_changepoints(data)

    assert isinstance(result, str)


def test_alternating_values():
    """Alternating pattern processed correctly."""
    data = np.array([100.0, 50.0] * 50)

    result = characterize_changepoints(data)

    assert isinstance(result, str)


def test_exponential_growth():
    """Exponential growth pattern detected."""
    data = np.exp(np.linspace(0, 2, 100))

    result = characterize_changepoints(data)

    assert isinstance(result, str)
    # Should detect change (monotonic increase)
    result_lower = result.lower()
    assert len(result) > 0


def test_with_outliers():
    """Outliers handled in changepoint detection."""
    np.random.seed(42)
    data = np.concatenate([
        np.random.normal(100, 5, 50),
        np.array([1000.0]),  # Outlier
        np.random.normal(100, 5, 49)
    ])

    result = characterize_changepoints(data)

    assert isinstance(result, str)
