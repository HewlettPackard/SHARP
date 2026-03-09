"""
Unit tests for distribution statistics module.

Tests compute_summary and characterize_distribution functions
with various edge cases and data patterns.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import pytest

from src.core.stats.distribution import (
    compute_summary,
    characterize_distribution,
)


# ============================================================================
# compute_summary tests
# ============================================================================

def test_basic_statistics():
    """Compute summary returns all expected statistics for normal data."""
    data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

    result = compute_summary(data)

    assert result['mean'] == 5.5
    assert result['median'] == 5.5
    assert result['stddev'] == pytest.approx(3.0276503540974917, rel=1e-5)
    assert result['min'] == 1
    assert result['max'] == 10
    assert result['CI95_low'] < result['mean'] < result['CI95_high']


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_single_value():
    """Compute summary handles degenerate case of single repeated value."""
    data = np.array([5, 5, 5, 5, 5])

    result = compute_summary(data)

    assert result['mean'] == 5
    assert result['median'] == 5
    assert result['stddev'] == 0
    assert result['min'] == 5
    assert result['max'] == 5


def test_identical_values():
    """Compute summary correctly handles array of identical values."""
    data = np.full(100, 42.0)

    result = compute_summary(data)

    assert result['mean'] == 42.0
    assert result['median'] == 42.0
    assert result['stddev'] == 0.0


def test_confidence_interval():
    """Confidence intervals correctly capture true mean with high probability."""
    np.random.seed(42)
    # Generate data from known normal distribution
    true_mean = 100
    true_std = 15
    data = np.random.normal(true_mean, true_std, 1000)

    result = compute_summary(data)

    # 95% CI should contain true mean (probabilistic but with n=1000, highly likely)
    assert result['CI95_low'] < true_mean < result['CI95_high']
    # Estimated mean should be close to true mean
    assert abs(result['mean'] - true_mean) < 2  # Within 2 units


def test_with_nan_values():
    """Compute summary correctly handles data containing NaN values."""
    data = np.array([1.0, 2.0, np.nan, 4.0, 5.0])

    result = compute_summary(data)

    # Should compute statistics ignoring NaN
    assert not np.isnan(result['mean'])
    assert result['mean'] == pytest.approx(3.0, rel=1e-5)


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_with_inf_values():
    """Compute summary handles inf values gracefully."""
    data = np.array([1.0, 2.0, np.inf, 4.0])

    result = compute_summary(data)

    # Result should exist and contain finite measures
    assert isinstance(result, dict)
    assert 'mean' in result


# ============================================================================
# characterize_distribution tests
# ============================================================================

def test_narrative_structure():
    """Characterize distribution returns structured narrative with key metrics."""
    np.random.seed(42)
    data = np.random.normal(0, 1, 100)

    result = characterize_distribution(data)

    # Should be non-empty string
    assert isinstance(result, str)
    assert len(result) > 0
    # Should mention key distribution characteristics
    result_lower = result.lower()
    assert any(word in result_lower for word in ['skew', 'kurtosis', 'normal'])


def test_detects_right_skew():
    """Characterize distribution identifies and describes right-skewed data."""
    np.random.seed(42)
    # Create right-skewed data (exponential distribution)
    data = np.random.exponential(2, 1000)

    result = characterize_distribution(data)

    # Should mention skewness
    result_lower = result.lower()
    assert 'skew' in result_lower
    # Should indicate direction (right/positive)
    assert 'right' in result_lower or 'positive' in result_lower


def test_detects_heavy_tails():
    """Characterize distribution mentions kurtosis for heavy-tailed data."""
    np.random.seed(42)
    # Create heavy-tailed data
    data = np.random.standard_t(3, 1000)

    result = characterize_distribution(data)

    # Should mention kurtosis or tails
    result_lower = result.lower()
    assert 'kurtosis' in result_lower or 'tail' in result_lower


def test_normality_assessment():
    """Characterize distribution correctly assesses normality."""
    np.random.seed(42)
    # Normal data
    normal_data = np.random.normal(0, 1, 200)

    result = characterize_distribution(normal_data)

    # Should mention normality
    result_lower = result.lower()
    assert 'normal' in result_lower
    # Should indicate consistency with normal distribution
    assert not ('deviates' in result_lower or 'non-normal' in result_lower)


def test_log_normality_detection():
    """Characterize distribution detects and reports log-normal distributions."""
    np.random.seed(42)
    # Log-normal data
    data = np.random.lognormal(0, 0.5, 200)

    result = characterize_distribution(data)

    # Should mention log-normal or logarithmic transformation
    result_lower = result.lower()
    assert 'log' in result_lower

import numpy as np
import pytest
from src.core.stats.distribution import (
    compute_summary,
    detect_change_points,
    estimate_acf_lag,
    characterize_distribution,
    _test_normality,
)


# ============================================================================
# compute_summary tests
# ============================================================================

def test_basic_statistics():
    """Test basic summary statistics on normal data."""
    data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    result = compute_summary(data)

    assert result['n'] == 5
    assert result['min'] == 1.0
    assert result['max'] == 5.0
    assert result['median'] == 3.0
    assert abs(result['mean'] - 3.0) < 0.01
    assert result['p95'] >= 4.0
    assert result['p99'] >= 4.0


def test_with_nans():
    """Test that NaNs are properly handled."""
    data = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
    result = compute_summary(data)

    assert result['n'] == 4  # NaN excluded
    assert result['min'] == 1.0
    assert result['max'] == 5.0


def test_confidence_interval():
    """Test 95% CI computation."""
    data = np.random.normal(100, 10, 100)
    result = compute_summary(data)

    assert 'CI95_low' in result
    assert 'CI95_high' in result
    assert result['CI95_low'] < result['mean'] < result['CI95_high']


def test_single_value():
    """Test with single value."""
    data = np.array([5.0])
    result = compute_summary(data)

    assert result['n'] == 1
    assert result['min'] == 5.0
    assert result['max'] == 5.0
    assert result['median'] == 5.0
    assert result['mean'] == 5.0


def test_large_dataset():
    """Test with larger dataset."""
    data = np.random.normal(50, 5, 1000)
    result = compute_summary(data)

    assert result['n'] == 1000
    assert 40 < result['mean'] < 60  # Should be close to 50
    assert result['stderr'] < result['stddev']  # SE should be smaller than SD


# ============================================================================
# detect_change_points tests
# ============================================================================

def test_stationary_series():
    """Test detection on stationary series (no change points)."""
    data = np.random.normal(100, 5, 100)
    result = detect_change_points(data)

    assert 'cps' in result
    assert 'min_size' in result


def test_series_with_changepoint():
    """Test detection on series with clear change point."""
    data = np.concatenate([
        np.random.normal(80, 5, 50),
        np.random.normal(120, 5, 50)
    ])
    result = detect_change_points(data)

    assert 'cps' in result
    assert len(result['cps']) > 0


def test_insufficient_data():
    """Test with very small dataset."""
    data = np.array([1.0, 2.0])
    result = detect_change_points(data)

    assert 'cps' in result or 'error' in result


def test_custom_parameters():
    """Test with custom model/penalty parameters."""
    data = np.concatenate([
        np.random.normal(80, 5, 50),
        np.random.normal(120, 5, 50)
    ])
    result = detect_change_points(data, model="rbf", pen=1.0, min_size=5)

    assert 'cps' in result


# ============================================================================
# estimate_acf_lag tests
# ============================================================================

def test_acf_on_random_data():
    """Test ACF on random (low autocorrelation) data."""
    data = np.random.normal(0, 1, 100)
    result = estimate_acf_lag(data)

    assert 'max_acf' in result
    assert 'lag' in result
    assert result['max_acf'] < 0.5


def test_acf_on_correlated_data():
    """Test ACF on autocorrelated data."""
    data = np.zeros(100)
    data[0] = np.random.normal()
    for i in range(1, 100):
        data[i] = 0.8 * data[i-1] + np.random.normal(0, 0.2)

    result = estimate_acf_lag(data)

    assert 'max_acf' in result
    assert result['max_acf'] > 0.3


def test_acf_with_threshold():
    """Test ACF with custom threshold."""
    data = np.random.normal(0, 1, 100)
    result = estimate_acf_lag(data, threshold=0.1)

    assert 'max_acf' in result
    assert 'lag' in result


def test_acf_small_sample():
    """Test ACF with small sample."""
    data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    result = estimate_acf_lag(data)

    assert 'max_acf' in result or 'error' in result


# ============================================================================
# _test_normality tests
# ============================================================================

def test_normal_distribution():
    """Test normality detection on normal data."""
    data = np.random.normal(100, 15, 100)
    result = _test_normality(data)

    assert result is not None
    assert "normality" in result.lower()


def test_lognormal_distribution():
    """Test log-normality detection."""
    data = np.random.lognormal(3, 0.5, 100)
    result = _test_normality(data)

    assert result is not None
    assert "log-normal" in result.lower() or "log" in result.lower()


def test_uniform_distribution():
    """Test non-normal distribution."""
    data = np.random.uniform(0, 100, 100)
    result = _test_normality(data)

    assert result is not None


def test_with_negative_values():
    """Test log-normality with negative values (should skip)."""
    data = np.concatenate([
        np.random.normal(-5, 2, 50),
        np.random.normal(5, 2, 50)
    ])
    result = _test_normality(data)

    assert result is not None
    assert "log-normal" not in result.lower() or "not applicable" in result.lower()


def test_small_sample():
    """Test with sample < 20 (Shapiro-Wilk minimum)."""
    data = np.random.normal(0, 1, 10)
    result = _test_normality(data)

    assert result is None


# ============================================================================
# characterize_distribution tests
# ============================================================================

def test_normal_distribution_characterize():
    """Test characterization of normal distribution."""
    data = np.random.normal(100, 15, 100)
    result = characterize_distribution(data)

    assert isinstance(result, str)
    assert len(result) > 0
    assert "distribution" in result.lower()


def test_lognormal_distribution_characterize():
    """Test characterization of log-normal distribution."""
    data = np.random.lognormal(3, 0.5, 100)
    result = characterize_distribution(data)

    assert isinstance(result, str)
    assert len(result) > 0


def test_skewed_distribution():
    """Test characterization reports skewness."""
    data = np.concatenate([np.random.normal(100, 5, 80), np.random.normal(150, 10, 20)])
    result = characterize_distribution(data)

    assert isinstance(result, str)
    assert "skew" in result.lower() or "symmetric" in result.lower()


def test_characterize_with_nans():
    """Test that NaNs are handled."""
    data = np.array([1.0, 2.0, np.nan, 4.0, 5.0] * 20)
    result = characterize_distribution(data)

    assert isinstance(result, str)


def test_characterize_small_sample():
    """Test with very small sample."""
    data = np.array([1.0, 2.0, 3.0])
    result = characterize_distribution(data)

    assert isinstance(result, str)


def test_with_changepoints():
    """Test with changepoint detection enabled."""
    data = np.concatenate([
        np.random.normal(80, 5, 50),
        np.random.normal(120, 5, 50)
    ])
    result = characterize_distribution(data)

    assert isinstance(result, str)


def test_returns_narrative_string():
    """Test that result is human-readable narrative."""
    data = np.random.normal(100, 10, 100)
    result = characterize_distribution(data)

    assert any(word in result.lower() for word in ['distribution', 'skew', 'kurtosis', 'normality'])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
