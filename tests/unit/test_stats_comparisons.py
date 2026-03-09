"""
Unit tests for comparison statistics module.

Tests mann_whitney_test, ecdf_comparison, density_comparison, and comparison_table.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import pytest

from src.core.stats.comparisons import (
    mann_whitney_test,
    ecdf_comparison,
    density_comparison,
    comparison_table,
)


# ============================================================================
# Mann-Whitney U Test
# ============================================================================

def test_mann_whitney_identical_distributions():
    """Test with identical distributions (no difference)."""
    np.random.seed(42)
    data = np.random.normal(100, 10, 50)
    result = mann_whitney_test(data, data.copy())

    assert 'statistic' in result
    assert 'p_value' in result
    assert 'effect_size' in result
    assert result['p_value'] > 0.05  # No significant difference


def test_mann_whitney_different_distributions():
    """Test with clearly different distributions."""
    np.random.seed(42)
    baseline = np.random.normal(80, 5, 50)
    treatment = np.random.normal(120, 5, 50)
    result = mann_whitney_test(baseline, treatment)

    assert 'statistic' in result
    assert 'p_value' in result
    assert result['p_value'] < 0.05  # Significant difference


def test_mann_whitney_with_nans():
    """Test that NaNs are properly excluded."""
    baseline = np.array([1.0, 2.0, np.nan, 4.0, 5.0] * 10)
    treatment = np.array([1.5, 2.5, 3.5, 4.5, 5.5] * 10)
    result = mann_whitney_test(baseline, treatment)

    assert 'statistic' in result
    assert 'p_value' in result


def test_mann_whitney_insufficient_data():
    """Test with too few samples."""
    baseline = np.array([1.0, 2.0])
    treatment = np.array([3.0, 4.0])
    result = mann_whitney_test(baseline, treatment)

    assert 'error' in result or 'statistic' in result


def test_mann_whitney_alternative_hypothesis():
    """Test different alternative hypotheses."""
    np.random.seed(42)
    baseline = np.random.normal(100, 10, 50)
    treatment = np.random.normal(110, 10, 50)

    result_two_sided = mann_whitney_test(baseline, treatment, alternative='two-sided')
    result_less = mann_whitney_test(baseline, treatment, alternative='less')

    assert 'p_value' in result_two_sided
    assert 'p_value' in result_less


# ============================================================================
# ECDF Comparison
# ============================================================================

def test_ecdf_basic():
    """Test ECDF comparison on two datasets."""
    np.random.seed(42)
    baseline = np.random.normal(100, 10, 50)
    treatment = np.random.normal(100, 10, 50)
    result = ecdf_comparison(baseline, treatment, 'latency_ms')

    assert 'baseline_ecdf' in result
    assert 'treatment_ecdf' in result
    assert 'ks_statistic' in result
    assert 'ks_p_value' in result
    assert result['metric'] == 'latency_ms'


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_ecdf_structure():
    """Test ECDF output structure."""
    baseline = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    treatment = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
    result = ecdf_comparison(baseline, treatment, 'test_metric')

    assert 'values' in result['baseline_ecdf']
    assert 'cumprob' in result['baseline_ecdf']
    assert len(result['baseline_ecdf']['values']) == len(result['baseline_ecdf']['cumprob'])


def test_ecdf_monotonically_increasing():
    """Test that ECDF probabilities are monotonically increasing."""
    baseline = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    treatment = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
    result = ecdf_comparison(baseline, treatment, 'test_metric')

    baseline_cumprob = result['baseline_ecdf']['cumprob']
    treatment_cumprob = result['treatment_ecdf']['cumprob']

    # Check monotonically increasing
    assert all(baseline_cumprob[i] <= baseline_cumprob[i+1]
               for i in range(len(baseline_cumprob)-1))
    assert all(treatment_cumprob[i] <= treatment_cumprob[i+1]
               for i in range(len(treatment_cumprob)-1))


def test_ecdf_valid_probability_bounds():
    """Test that ECDF probabilities are in [0, 1]."""
    baseline = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    treatment = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
    result = ecdf_comparison(baseline, treatment, 'test_metric')

    baseline_cumprob = np.array(result['baseline_ecdf']['cumprob'])
    treatment_cumprob = np.array(result['treatment_ecdf']['cumprob'])

    # All probabilities should be in [0, 1]
    assert np.all(baseline_cumprob >= 0) and np.all(baseline_cumprob <= 1)
    assert np.all(treatment_cumprob >= 0) and np.all(treatment_cumprob <= 1)

    # Last value should be 1.0 (or very close due to floating point)
    assert np.isclose(baseline_cumprob[-1], 1.0)
    assert np.isclose(treatment_cumprob[-1], 1.0)


def test_ecdf_sorted_values():
    """Test that ECDF x values are sorted."""
    baseline = np.array([3.0, 1.0, 4.0, 1.0, 5.0])
    treatment = np.array([2.0, 7.0, 1.0, 8.0, 2.0])
    result = ecdf_comparison(baseline, treatment, 'test_metric')

    baseline_values = result['baseline_ecdf']['values']
    treatment_values = result['treatment_ecdf']['values']

    # Values should be sorted
    assert all(baseline_values[i] <= baseline_values[i+1]
               for i in range(len(baseline_values)-1))
    assert all(treatment_values[i] <= treatment_values[i+1]
               for i in range(len(treatment_values)-1))


def test_ecdf_with_nans():
    """Test that NaNs are handled."""
    baseline = np.array([1.0, np.nan, 3.0, 4.0, 5.0])
    treatment = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
    result = ecdf_comparison(baseline, treatment, 'metric')

    assert 'baseline_ecdf' in result


def test_ecdf_empty_data():
    """Test with empty data."""
    baseline = np.array([])
    treatment = np.array([1.0, 2.0, 3.0])
    result = ecdf_comparison(baseline, treatment, 'metric')

    assert 'error' in result or 'baseline_ecdf' in result


# ============================================================================
# Density Comparison (KDE)
# ============================================================================

def test_density_basic_kde():
    """Test KDE comparison."""
    np.random.seed(42)
    baseline = np.random.normal(100, 10, 50)
    treatment = np.random.normal(100, 10, 50)
    result = density_comparison(baseline, treatment, 'latency_ms')

    assert 'baseline_kde' in result
    assert 'treatment_kde' in result
    assert result['metric'] == 'latency_ms'


def test_density_kde_structure():
    """Test KDE output structure."""
    baseline = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    treatment = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
    result = density_comparison(baseline, treatment, 'test_metric')

    assert 'x' in result['baseline_kde']
    assert 'density' in result['baseline_kde']
    assert len(result['baseline_kde']['x']) == len(result['baseline_kde']['density'])


def test_density_kde_non_negative():
    """Test that KDE density values are non-negative."""
    baseline = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    treatment = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
    result = density_comparison(baseline, treatment, 'test_metric')

    baseline_density = np.array(result['baseline_kde']['density'])
    treatment_density = np.array(result['treatment_kde']['density'])

    # Density should be non-negative
    assert np.all(baseline_density >= 0)
    assert np.all(treatment_density >= 0)


def test_density_kde_x_sorted():
    """Test that KDE x values are sorted."""
    baseline = np.array([3.0, 1.0, 4.0, 1.0, 5.0])
    treatment = np.array([2.0, 7.0, 1.0, 8.0, 2.0])
    result = density_comparison(baseline, treatment, 'test_metric')

    baseline_x = result['baseline_kde']['x']
    treatment_x = result['treatment_kde']['x']

    # X values should be sorted
    assert all(baseline_x[i] <= baseline_x[i+1]
               for i in range(len(baseline_x)-1))
    assert all(treatment_x[i] <= treatment_x[i+1]
               for i in range(len(treatment_x)-1))


def test_density_insufficient_data():
    """Test with too few samples for KDE."""
    baseline = np.array([1.0, 2.0])
    treatment = np.array([1.5, 2.5])
    result = density_comparison(baseline, treatment, 'metric')

    assert 'error' in result or 'baseline_kde' in result


def test_density_custom_bw_method():
    """Test with custom bandwidth method."""
    np.random.seed(42)
    baseline = np.random.normal(100, 10, 50)
    treatment = np.random.normal(100, 10, 50)
    result = density_comparison(baseline, treatment, 'metric', bw_method='scott')

    assert 'baseline_kde' in result or 'error' in result


# ============================================================================
# Comparison Table
# ============================================================================

def test_comparison_table_basic():
    """Test comparison table generation."""
    np.random.seed(42)
    baseline = np.random.normal(100, 10, 50)
    treatment = np.random.normal(105, 10, 50)
    result = comparison_table(baseline, treatment, 'latency_ms', better='lower')

    assert isinstance(result, dict)
    assert 'metric' in result
    assert 'baseline_median' in result
    assert 'treatment_median' in result
    assert 'median_diff' in result


def test_comparison_table_keys():
    """Test all expected keys in comparison table."""
    baseline = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    treatment = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
    result = comparison_table(baseline, treatment, 'test')

    expected_keys = [
        'metric', 'baseline_n', 'baseline_median', 'baseline_mean', 'baseline_stddev',
        'treatment_n', 'treatment_median', 'treatment_mean', 'treatment_stddev',
        'median_diff', 'pct_change', 'improved',
        'mann_whitney_u', 'p_value', 'effect_size'
    ]
    for key in expected_keys:
        assert key in result, f"Missing key: {key}"


def test_comparison_table_better_lower():
    """Test 'better: lower' scenario."""
    baseline = np.array([10.0] * 50)
    treatment = np.array([8.0] * 50)
    result = comparison_table(baseline, treatment, 'latency', better='lower')

    assert bool(result['improved']) is True


def test_comparison_table_better_higher():
    """Test 'better: higher' scenario."""
    baseline = np.array([100.0] * 50)
    treatment = np.array([120.0] * 50)
    result = comparison_table(baseline, treatment, 'throughput', better='higher')

    assert bool(result['improved']) is True


def test_comparison_table_not_improved():
    """Test when treatment is worse."""
    baseline = np.array([100.0] * 50)
    treatment = np.array([120.0] * 50)
    result = comparison_table(baseline, treatment, 'latency', better='lower')

    assert bool(result['improved']) is False


def test_comparison_table_with_nans():
    """Test with NaN values."""
    baseline = np.array([1.0, 2.0, np.nan, 4.0, 5.0] * 10)
    treatment = np.array([1.5, 2.5, 3.5, 4.5, 5.5] * 10)
    result = comparison_table(baseline, treatment, 'metric')

    assert isinstance(result, dict)
    assert result['baseline_n'] < 50  # Some excluded due to NaN


def test_comparison_table_percent_change():
    """Test percent change calculation."""
    baseline = np.array([100.0] * 50)
    treatment = np.array([110.0] * 50)
    result = comparison_table(baseline, treatment, 'metric', better='higher')

    assert 'pct_change' in result
    assert abs(result['pct_change'] - 10.0) < 0.1  # Should be ~10%
