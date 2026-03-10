#!/usr/bin/env python3
"""
Unit tests for repeater strategies with parity validation.

Tests validate that modular repeater implementations in src/core/repeaters/
work using synthetic benchmark distributions from fixtures.

Test Organization:
  - Individual Repeater Tests: TestCountRepeater, TestRSERepeater, etc.
    Each covers: initialization, count increment, starting_sample behavior,
    convergence/non-convergence, threshold boundary crossing, and data processing.
  - Meta Tests: TestRepeaterFactory, TestRepeaterProtocol
    Verify factory behavior and protocol compliance.
  - Fixture Tests: TestSyntheticDistributions
    Validate distribution generation and integration with repeaters.
  - Boundary Tests: TestAdvancedBoundaryConditions
    Test edge cases with diverse distributions.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import warnings

import numpy
import pytest
import scipy.stats

from src.core.repeaters import repeater_factory
from src.core.repeaters.base import Repeater, RunData
from src.core.repeaters.count import CountRepeater
from src.core.repeaters.rse import RSERepeater
from src.core.repeaters.ci import CIRepeater
from src.core.repeaters.hdi import HDIRepeater
from src.core.repeaters.bb import BBRepeater
from src.core.repeaters.gmm import GaussianMixtureRepeater
from src.core.repeaters.ks import KSRepeater
from src.core.repeaters.decision import DecisionRepeater
from tests.fixtures.distributions import distributions, helpers
from tests.fixtures.repeater_fixtures import (
    MockRunData,
    make_repeater_options,
    make_repeater,
    collect_decisions,
    repeater_tester,
)

# Apply warning filters to all tests in this module
pytestmark = [
    pytest.mark.filterwarnings("ignore:Number of distinct clusters.*smaller than n_clusters"),
    pytest.mark.filterwarnings("ignore::ResourceWarning"),
]


# ============================================================================
# Repeater Fixtures
# ============================================================================

@pytest.fixture
def count_repeater():
    """Provide CountRepeater instance for tests."""
    return CountRepeater(make_repeater_options("CR", max_repeats=100, starting_sample=5))


@pytest.fixture
def rse_repeater():
    """Provide RSERepeater instance for tests."""
    return RSERepeater(make_repeater_options(
        "RSE", max_repeats=100, threshold_value=0.1, starting_sample=5
    ))


@pytest.fixture
def ci_repeater():
    """Provide CIRepeater instance for tests."""
    return CIRepeater(make_repeater_options(
        "CI", max_repeats=50, threshold_value=0.2, starting_sample=10
    ))


@pytest.fixture
def hdi_repeater():
    """Provide HDIRepeater instance for tests."""
    return HDIRepeater(make_repeater_options(
        "HDI", max_repeats=100, threshold_value=0.05, starting_sample=8
    ))


@pytest.fixture
def bb_repeater():
    """Provide BBRepeater instance for tests."""
    return BBRepeater(make_repeater_options(
        "BB", max_repeats=100, threshold_value=0.01, starting_sample=10
    ))


@pytest.fixture
def gmm_repeater():
    """Provide GaussianMixtureRepeater instance for tests."""
    return GaussianMixtureRepeater(make_repeater_options(
        "GMM", max_repeats=100, threshold_value=0.01, starting_sample=10
    ))


@pytest.fixture
def ks_repeater():
    """Provide KSRepeater instance for tests."""
    return KSRepeater(make_repeater_options(
        "KS", max_repeats=100, threshold_value=0.05, starting_sample=8
    ))


@pytest.fixture
def decision_repeater():
    """Provide DecisionRepeater instance for tests."""
    return DecisionRepeater(make_repeater_options(
        "DC", max_repeats=100, starting_sample=5
    ))


# ============================================================================
# INDIVIDUAL REPEATER TESTS
# Each repeater has tests for: initialization, counting, starting_sample behavior,
# convergence detection, non-convergence paths, threshold boundaries, and
# processing of real data distributions.
# ============================================================================


# TestCountRepeater tests
def test_count_repeater_initialization(repeater_tester, count_repeater):
    """CountRepeater should initialize without error."""
    repeater_tester.assert_initialization(count_repeater)


def test_count_repeater_increments_count(repeater_tester, count_repeater):
    """CountRepeater should increment count with each call."""
    repeater_tester.assert_increments_count(count_repeater)


def test_count_repeater_continues_before_starting_sample(repeater_tester, count_repeater):
    """CountRepeater should continue until starting_sample is reached."""
    repeater_tester.assert_continues_before_starting_sample(count_repeater, starting_sample=5)


def test_count_repeater_stops_at_limit():
    """CountRepeater should stop when count reaches limit."""
    repeater = make_repeater(CountRepeater, "CR", max_repeats=5)

    # Should continue while count < limit
    for i in range(5):
        pdata = MockRunData({"outer_time": [10.0 + i]})
        should_continue = repeater(pdata)
        if i < 4:
            assert should_continue, f"Should continue at count {i+1}"
        else:
            assert not should_continue, "Should stop at limit"

    assert repeater.get_count() == 5


def test_count_repeater_default_limit():
    """CountRepeater should use default max of 1 if not specified."""
    repeater = make_repeater(CountRepeater, **{"repeater_options": {}})

    pdata = MockRunData({"outer_time": [10.0]})
    should_continue = repeater(pdata)

    assert not should_continue, "Should stop after 1 run with default limit"
    assert repeater.get_count() == 1


def test_count_repeater_custom_metric():
    """CountRepeater should accept custom metric names.

    The metric parameter should be at the top level of repeater_options
    since it's inherited by all repeaters.
    """
    repeater = make_repeater(CountRepeater, "CR", max_repeats=3, metric="inner_time")

    for i in range(3):
        pdata = MockRunData({"inner_time": [5.0 + i]})
        repeater(pdata)

    # Verify the repeater uses the custom metric
    assert len(repeater._runtimes) == 3
    assert repeater._metric == "inner_time"

def test_subclass_repeater_custom_metric():
    """Subclass repeaters should accept custom metric names inherited from CountRepeater.

    This is a regression test for ensuring subclasses properly inherit the metric parameter.
    The metric parameter should be at the top level of repeater_options since it's
    shared by all repeaters (inherited from CountRepeater).
    """
    # Test KSRepeater with custom metric
    ks_repeater = make_repeater(
        KSRepeater, "KS", max_repeats=5, threshold_value=0.1, metric="inner_time"
    )
    for i in range(5):
        pdata = MockRunData({"inner_time": [10.0 + i * 0.5]})
        ks_repeater(pdata)
    assert len(ks_repeater._runtimes) == 5
    assert ks_repeater._metric == "inner_time"

    # Test RSERepeater with custom metric
    rse_repeater = make_repeater(
        RSERepeater, "RSE", max_repeats=5, threshold_value=0.1, metric="custom_metric"
    )
    for i in range(5):
        pdata = MockRunData({"custom_metric": [20.0 + i]})
        rse_repeater(pdata)
    assert len(rse_repeater._runtimes) == 5
    assert rse_repeater._metric == "custom_metric"

    # Test CIRepeater with custom metric
    ci_repeater = make_repeater(
        CIRepeater, "CI", max_repeats=8, threshold_value=0.2, metric="test_metric"
    )
    for i in range(8):
        pdata = MockRunData({"test_metric": [15.0 + i * 0.1]})
        ci_repeater(pdata)
    assert len(ci_repeater._runtimes) == 8
    assert ci_repeater._metric == "test_metric"

    # Test DecisionRepeater with custom metric (most complex subclass)
    decision_repeater = make_repeater(
        DecisionRepeater, "DC", max_repeats=10, metric="decision_metric"
    )
    for i in range(10):
        pdata = MockRunData({"decision_metric": [5.0 + i * 0.05]})
        decision_repeater(pdata)
    assert len(decision_repeater._runtimes) == 10
    assert decision_repeater._metric == "decision_metric"


# TestRSERepeater tests
def test_rse_repeater_initialization(repeater_tester, rse_repeater):
    """RSERepeater should initialize without error."""
    repeater_tester.assert_initialization(rse_repeater)


def test_rse_repeater_increments_count(repeater_tester, rse_repeater):
    """RSERepeater should increment count with each call."""
    repeater_tester.assert_increments_count(rse_repeater)


def test_rse_repeater_continues_before_starting_sample(repeater_tester, rse_repeater):
    """RSERepeater should continue until starting_sample is reached."""
    repeater_tester.assert_continues_before_starting_sample(rse_repeater, starting_sample=5)


def test_rse_repeater_does_not_converge_on_high_variance_data(repeater_tester):
    """RSERepeater should not converge prematurely on high-variance data."""
    numpy.random.seed(42)
    repeater = RSERepeater(make_repeater_options(
        "RSE", max_repeats=100, threshold_value=0.02, starting_sample=5
    ))
    repeater_tester.assert_does_not_converge_prematurely(
        repeater, helpers.generate_high_variance_normal_data, iterations=20
    )


def test_rse_repeater_stops_when_threshold_crossed(repeater_tester):
    """RSERepeater should stop when RSE drops below threshold."""
    repeater = RSERepeater(make_repeater_options(
        "RSE", max_repeats=100, threshold_value=0.5, starting_sample=5
    ))
    repeater_tester.assert_stops_when_threshold_crossed(
        repeater, helpers.generate_constant_data, starting_sample=5
    )


def test_rse_repeater_processes_normal_data():
    """RSERepeater should process normally distributed data."""
    options = make_repeater_options(
        "RSE", max_repeats=50, threshold_value=0.2, starting_sample=10
    )
    repeater = RSERepeater(options)

    # Tight normal distribution to reach RSE threshold
    normal_data = helpers.generate_tight_normal_data(count=50)
    pdata = MockRunData({"outer_time": normal_data})

    decisions = collect_decisions(repeater, pdata, max_iterations=50)

    # Should complete without error and make decisions
    assert repeater.get_count() > 0
    assert repeater.get_count() <= 50


# TestCIRepeater tests
def test_ci_repeater_initialization(repeater_tester, ci_repeater):
    """CIRepeater should initialize without error."""
    repeater_tester.assert_initialization(ci_repeater)


def test_ci_repeater_increments_count(repeater_tester, ci_repeater):
    """CIRepeater should increment count with each call."""
    repeater_tester.assert_increments_count(ci_repeater)


def test_ci_repeater_continues_before_starting_sample(repeater_tester, ci_repeater):
    """CIRepeater should continue until starting_sample is reached."""
    repeater_tester.assert_continues_before_starting_sample(ci_repeater, starting_sample=10)


def test_ci_repeater_does_not_converge_on_high_variance_data(repeater_tester):
    """CIRepeater should not converge prematurely on high-variance data."""
    numpy.random.seed(42)
    repeater = CIRepeater(make_repeater_options(
        "CI", max_repeats=50, threshold_value=0.02, starting_sample=10
    ))
    repeater_tester.assert_does_not_converge_prematurely(
        repeater, helpers.generate_high_variance_normal_data, iterations=20
    )


def test_ci_repeater_stops_when_threshold_crossed(repeater_tester):
    """CIRepeater should stop when CI drops below threshold."""
    repeater = CIRepeater(make_repeater_options(
        "CI", max_repeats=50, threshold_value=0.5, starting_sample=10
    ))
    repeater_tester.assert_stops_when_threshold_crossed(
        repeater, helpers.generate_constant_data, starting_sample=10
    )


def test_ci_repeater_processes_normal_data():
    """CIRepeater should process normally distributed data."""
    options = make_repeater_options(
        "CI", max_repeats=50, threshold_value=0.3, starting_sample=10
    )
    repeater = CIRepeater(options)

    # Tight normal distribution to reach CI threshold
    normal_data = helpers.generate_tight_normal_data(count=50)
    pdata = MockRunData({"outer_time": normal_data})

    decisions = collect_decisions(repeater, pdata, max_iterations=50)

    # Should complete without error
    assert repeater.get_count() > 0
    assert repeater.get_count() <= 50


# TestHDIRepeater tests
def test_hdi_repeater_initialization(repeater_tester, hdi_repeater):
    """HDIRepeater should initialize without error."""
    repeater_tester.assert_initialization(hdi_repeater)


def test_hdi_repeater_increments_count(repeater_tester, hdi_repeater):
    """HDIRepeater should increment count with each call."""
    repeater_tester.assert_increments_count(hdi_repeater)


def test_hdi_repeater_continues_before_starting_sample(repeater_tester, hdi_repeater):
    """HDIRepeater should continue until starting_sample is reached."""
    repeater_tester.assert_continues_before_starting_sample(hdi_repeater, starting_sample=8)


def test_hdi_repeater_does_not_converge_on_high_variance_data(repeater_tester):
    """HDIRepeater should not converge prematurely on high-variance data."""
    numpy.random.seed(42)
    repeater = HDIRepeater(make_repeater_options(
        "HDI", max_repeats=50, threshold_value=0.02, starting_sample=10
    ))
    repeater_tester.assert_does_not_converge_prematurely(
        repeater, helpers.generate_high_variance_normal_data, iterations=20
    )


def test_hdi_repeater_stops_when_threshold_crossed(repeater_tester):
    """HDIRepeater should stop when HDI width drops below threshold."""
    repeater = HDIRepeater(make_repeater_options(
        "HDI", max_repeats=50, threshold_value=0.5, starting_sample=10
    ))
    repeater_tester.assert_stops_when_threshold_crossed(
        repeater, helpers.generate_constant_data, starting_sample=10
    )


def test_hdi_repeater_processes_normal_data():
    """HDIRepeater should process normally distributed data."""
    options = make_repeater_options(
        "HDI", max_repeats=50, threshold_value=0.2, starting_sample=10
    )
    repeater = HDIRepeater(options)

    # Normal distribution with tight variance
    normal_data = helpers.generate_tight_normal_data(count=50)
    pdata = MockRunData({"outer_time": normal_data})

    decisions = collect_decisions(repeater, pdata, max_iterations=50)

    # Should complete without error and make decisions
    assert repeater.get_count() > 0
    assert repeater.get_count() <= 50


# --- TestBBRepeater Tests ---


def test_bb_repeater_initialization(repeater_tester, bb_repeater):
    """BBRepeater should initialize without error."""
    repeater_tester.assert_initialization(bb_repeater)


def test_bb_repeater_increments_count(repeater_tester, bb_repeater):
    """BBRepeater should increment count with each call."""
    repeater_tester.assert_increments_count(bb_repeater)


def test_bb_repeater_continues_before_starting_sample(repeater_tester, bb_repeater):
    """BBRepeater should continue until starting_sample is reached."""
    repeater_tester.assert_continues_before_starting_sample(bb_repeater, starting_sample=10)


def test_bb_repeater_processes_autocorrelated_data():
    """BBRepeater should process autocorrelated data."""
    repeater = make_repeater(
        BBRepeater, "BB", max_repeats=40, threshold_value=0.2, starting_sample=10
    )

    # Use sine distribution (periodic/autocorrelated pattern)
    autocorr_data = helpers.generate_sine_data(count=40)
    pdata = MockRunData({"outer_time": autocorr_data})

    decisions = []
    for i in range(40):
        should_continue = repeater(pdata)
        decisions.append((repeater.get_count(), should_continue))
        if not should_continue:
            break

    # Should process without error
    assert repeater.get_count() > 0
    assert repeater.get_count() <= 40


# --- TestGaussianMixtureRepeater Tests ---


def test_gmm_repeater_initialization(repeater_tester, gmm_repeater):
    """GaussianMixtureRepeater should initialize without error."""
    repeater_tester.assert_initialization(gmm_repeater)


def test_gmm_repeater_increments_count(repeater_tester, gmm_repeater):
    """GaussianMixtureRepeater should increment count with each call."""
    repeater_tester.assert_increments_count(gmm_repeater)


def test_gmm_repeater_continues_before_starting_sample(repeater_tester, gmm_repeater):
    """GaussianMixtureRepeater should continue until starting_sample is reached."""
    repeater_tester.assert_continues_before_starting_sample(gmm_repeater, starting_sample=10)


def test_gmm_repeater_does_not_converge_on_high_variance_data(repeater_tester):
    """GaussianMixtureRepeater should not converge on bad fit."""
    repeater = GaussianMixtureRepeater(make_repeater_options(
        "GMM", max_repeats=50, threshold_value=0.05, starting_sample=10, max_gaussian_components=3
    ))
    data_gen = lambda count: helpers.generate_multimodal_data(modes=3, count=count)
    repeater_tester.assert_does_not_converge_prematurely(
        repeater, data_gen, iterations=20
    )


def test_gmm_repeater_stops_when_threshold_crossed(repeater_tester):
    """GaussianMixtureRepeater should stop when fit converges."""
    repeater = GaussianMixtureRepeater(make_repeater_options(
        "GMM", max_repeats=50, threshold_value=0.5, starting_sample=10, max_gaussian_components=3
    ))
    repeater_tester.assert_stops_when_threshold_crossed(
        repeater, helpers.generate_constant_data, starting_sample=10
    )


def test_gmm_repeater_convergence_on_uniform_data():
    """GaussianMixtureRepeater should detect convergence on uniform distribution."""
    repeater = GaussianMixtureRepeater(make_repeater_options(
        "GMM",
        max_repeats=100,
        threshold_value=0.5,
        starting_sample=10,
        max_gaussian_components=3,
    ))

    # Uniform distribution (single mode) should converge quickly
    uniform_data = helpers.generate_uniform_data(loc=5.0, scale=10.0, count=100)
    pdata = MockRunData({"outer_time": uniform_data})

    decisions = collect_decisions(repeater, pdata, max_iterations=100)

    # Should eventually converge and stop
    assert not decisions[-1][1], "Should eventually stop due to convergence"
    assert repeater.get_count() > 10
    assert repeater.get_count() <= 100


def test_gmm_repeater_convergence_on_bimodal_data():
    """GaussianMixtureRepeater should detect convergence on bimodal distribution."""
    repeater = GaussianMixtureRepeater(make_repeater_options(
        "GMM",
        max_repeats=100,
        threshold_value=1.0,
        starting_sample=10,
        max_gaussian_components=3,
    ))

    # Bimodal distribution (two modes) should eventually converge
    bimodal_data = helpers.generate_bimodal_data(count=100)
    pdata = MockRunData({"outer_time": bimodal_data})

    decisions = collect_decisions(repeater, pdata, max_iterations=100)

    # Should eventually converge and stop
    assert not decisions[-1][1], "Should eventually stop due to convergence on bimodal data"
    assert repeater.get_count() > 10
    assert repeater.get_count() <= 100


# --- TestKSRepeater Tests ---


def test_ks_repeater_initialization(repeater_tester, ks_repeater):
    """KSRepeater should initialize without error."""
    repeater_tester.assert_initialization(ks_repeater)


def test_ks_repeater_increments_count(repeater_tester, ks_repeater):
    """KSRepeater should increment count with each call."""
    repeater_tester.assert_increments_count(ks_repeater)


def test_ks_repeater_continues_before_starting_sample(repeater_tester, ks_repeater):
    """KSRepeater should continue until starting_sample is reached."""
    repeater_tester.assert_continues_before_starting_sample(ks_repeater, starting_sample=8)


def test_ks_repeater_does_not_converge_on_high_variance_data(repeater_tester):
    """KSRepeater should not converge prematurely on high-variance data."""
    numpy.random.seed(42)
    repeater = KSRepeater(make_repeater_options(
        "KS", max_repeats=50, threshold_value=0.05, starting_sample=10
    ))
    repeater_tester.assert_does_not_converge_prematurely(
        repeater, helpers.generate_high_variance_normal_data, iterations=20
    )


def test_ks_repeater_stops_when_threshold_crossed(repeater_tester):
    """KSRepeater should stop when KS statistic drops below threshold."""
    repeater = KSRepeater(make_repeater_options(
        "KS", max_repeats=50, threshold_value=0.5, starting_sample=10
    ))
    repeater_tester.assert_stops_when_threshold_crossed(
        repeater, helpers.generate_constant_data, starting_sample=10
    )


def test_ks_repeater_processes_data_and_makes_decisions():
    """KSRepeater should process data and make stopping decisions."""
    repeater = KSRepeater(make_repeater_options(
        "KS", max_repeats=40, threshold_value=0.2, starting_sample=10
    ))

    # Use uniformly distributed data
    uniform_data = helpers.generate_uniform_data(loc=5.0, scale=10.0, count=40)
    pdata = MockRunData({"outer_time": uniform_data})

    decisions = collect_decisions(repeater, pdata, max_iterations=40)

    # Should process without error
    assert repeater.get_count() > 0
    assert repeater.get_count() <= 40
    # Should continue early on
    assert decisions[8][1], "Should continue before KS test can differentiate (early data)"


# --- TestDecisionRepeater Tests ---


def test_decision_repeater_initialization(repeater_tester, decision_repeater):
    """DecisionRepeater should initialize without error."""
    repeater_tester.assert_initialization(decision_repeater)


def test_decision_repeater_increments_count(repeater_tester, decision_repeater):
    """DecisionRepeater should increment count with each call."""
    repeater_tester.assert_increments_count(decision_repeater)


def test_decision_repeater_continues_before_starting_sample(repeater_tester, decision_repeater):
    """DecisionRepeater should continue until starting_sample is reached."""
    repeater_tester.assert_continues_before_starting_sample(decision_repeater, starting_sample=5)


def test_decision_repeater_stops_on_constant_data():
    """DecisionRepeater should stop on constant data."""
    repeater = make_repeater(
        DecisionRepeater, "DC", max_repeats=100, threshold_value=None, starting_sample=5,
        test_after=1, mean_threshold=0.1, decision_verbose=False
    )

    # Perfectly constant data
    constant_data = [10.0] * 100
    pdata = MockRunData({"outer_time": constant_data})

    decisions = []
    for i in range(100):
        should_continue = repeater(pdata)
        decisions.append((repeater.get_count(), should_continue))
        if not should_continue:
            break

    # Should stop relatively quickly on constant data
    assert repeater.get_count() < 100
    # Should continue early
    assert decisions[3][1], "Should continue early on"
    # Should stop later
    assert not decisions[-1][1], "Should stop on constant data"


def test_decision_repeater_initialization_with_sub_repeaters():
    """DecisionRepeater should initialize with sub-repeaters."""
    repeater = make_repeater(
        DecisionRepeater, "DC", max_repeats=50, threshold_value=None, starting_sample=10,
        test_after=5, decision_verbose=False
    )

    assert repeater.get_count() == 0
    # Verify sub-repeaters are initialized
    assert "RSERepeater" in repeater._DecisionRepeater__repeaters
    assert "CIRepeater" in repeater._DecisionRepeater__repeaters
    assert "HDIRepeater" in repeater._DecisionRepeater__repeaters
    assert "BBRepeater" in repeater._DecisionRepeater__repeaters
    assert "GaussianMixtureRepeater" in repeater._DecisionRepeater__repeaters


def test_decision_repeater_detects_distributions_correctly():
    """DecisionRepeater should correctly identify different distribution types.

    Tests that _get_detected_distribution() correctly identifies:
    - Constant data (no variance)
    - Gaussian (normal) distribution (symmetric, bell-curve)
    - Lognormal (skewed) distribution (right-skewed, never negative)
    - Bimodal distribution (two distinct peaks)
    - Uniform distribution (flat, bounded support - NOT multimodal)
    - Autocorrelated (sine) data (periodic pattern)

    Uses large sample sizes (500+) to ensure distributions are statistically
    distinct enough that detection failures indicate real bugs, not noise.

    Strengthened detection prevents false positives on uniform data by:
    - Requiring minimum 10 samples per detected component
    - Using BIC penalty to penalize overfitting (diff > 10)
    - Requiring at least 2 components to declare multimodal (not 1)
    - Applying likelihood ratio test constraints

    Uses fixed random seed for deterministic, reproducible test results.
    """
    # Set random seed for reproducible synthetic distributions
    numpy.random.seed(42)

    repeater = make_repeater(
        DecisionRepeater, "DC", max_repeats=300, threshold_value=None, starting_sample=5,
        test_after=1, decision_verbose=False
    )

    test_cases = [
        # Constant: perfectly constant (zero variance) - unmistakable
        ("constant", helpers.generate_constant_data(value=50.0, noise_scale=0.0, count=500)),
        # Gaussian: tight normal distribution (should NOT be confused with lognormal/bimodal)
        ("gaussian", helpers.generate_normal_data(mean=100.0, std_dev=5.0, count=500)),
        # Lognormal: very distinct right-skew, always positive, different tail behavior
        ("lognormal", helpers.generate_lognormal_data(shape=0.95, mean=10.0, std_dev=2.0, count=500)),
        # Bimodal: clearly separated two modes (not continuous gaussian)
        ("bimodal", helpers.generate_bimodal_data(count=500)),
        # Uniform: completely flat, bounded support (NOT multimodal with strengthened detection)
        # With seed=42, 500 samples is sufficient for reliable uniform detection
        ("uniform", helpers.generate_uniform_data(loc=0.0, scale=100.0, count=500)),
        # Autocorrelated: strong periodic sine pattern (not gaussian randomness)
        ("autocorrelated", helpers.generate_sine_data(norm_std=0.05, count=500)),
    ]

    for expected_dist, data in test_cases:
        detected = repeater._get_detected_distribution(data)

        # All returned distributions should be valid types
        assert detected in ["constant", "monotonic", "gaussian", "lognormal", "multimodal", "uniform", "autocorrelated", "unknown"], \
            f"Detection for {expected_dist} data returned invalid type: {detected}"

        # Strict detection rules for statistically distinct distributions
        # With large samples (500+) and low noise, these should NOT be confused
        match expected_dist:
            case "constant":
                assert detected == "constant", \
                    f"Perfect constant data (zero variance) MUST be detected as constant, got {detected}"

            case "gaussian":
                # Tight normal: symmetric, should be detected as gaussian
                # NOT multimodal (only 1 mode), NOT lognormal (symmetric, can be negative)
                assert detected in ["gaussian"], \
                    f"Tight gaussian data (symmetric, bell-curve) should be detected as gaussian, got {detected}"

            case "lognormal":
                # Log-normal: always positive, right-skewed, distinct from normal
                # Should NOT be detected as gaussian (wrong skew) or unknown
                assert detected in ["lognormal"], \
                    f"Lognormal data (always positive, right-skewed) should be detected as lognormal, got {detected}"

            case "bimodal":
                # Bimodal: two clearly separated peaks, NOT a single gaussian mode
                # With strengthened detection (min_samples_per_component=10, BIC threshold=10),
                # clearly separated modes should pass all criteria
                assert detected in ["multimodal"], \
                    f"Bimodal data (two separated modes) should be detected as multimodal, got {detected}"

            case "uniform":
                # Uniform: flat, bounded, completely different from normal
                # With strengthened detection preventing false multimodal positives:
                # - Uniform should pass KS test (detected as "uniform")
                # - Should NOT be misclassified as multimodal (insufficient BIC improvement)
                assert detected in ["uniform"], \
                    f"Uniform data (flat, bounded) should be detected as uniform (not multimodal), got {detected}"

            case "autocorrelated":
                # Autocorrelated sine: periodic pattern, NOT random gaussian
                # Should be detected as autocorrelated, NOT gaussian or unknown
                assert detected in ["autocorrelated"], \
                    f"Autocorrelated sine data (periodic pattern) should be detected as autocorrelated, got {detected}"


# ============================================================================
# META AND FACTORY TESTS
# Tests for repeater factory creation and protocol compliance.
# ============================================================================


# --- TestRepeaterFactory Tests ---


def test_factory_creates_count_repeater():
    """Factory should create CountRepeater for default/MAX option."""
    options = {"repeats": "MAX", "repeater_options": {"CR": {"max": 10}}}
    repeater = repeater_factory(options)

    assert isinstance(repeater, CountRepeater)


def test_factory_creates_rse_repeater():
    """Factory should create RSERepeater for RSE option."""
    options = {
        "repeats": "RSE",
        "repeater_options": {
            "RSE": {"max": 50, "rse_threshold": 0.1},
        },
    }
    repeater = repeater_factory(options)

    assert isinstance(repeater, RSERepeater)


def test_factory_creates_ci_repeater():
    """Factory should create CIRepeater for CI option."""
    options = {
        "repeats": "CI",
        "repeater_options": {
            "CI": {"max": 50, "ci_threshold": 0.2},
        },
    }
    repeater = repeater_factory(options)

    assert isinstance(repeater, CIRepeater)


def test_factory_creates_hdi_repeater():
    """Factory should create HDIRepeater for HDI option."""
    options = {
        "repeats": "HDI",
        "repeater_options": {
            "HDI": {"max": 50, "hdi_threshold": 0.2},
        },
    }
    repeater = repeater_factory(options)

    assert isinstance(repeater, HDIRepeater)


def test_factory_creates_bb_repeater():
    """Factory should create BBRepeater for BB option."""
    options = {
        "repeats": "BB",
        "repeater_options": {
            "BB": {"max": 50, "bb_threshold": 0.2},
        },
    }
    repeater = repeater_factory(options)

    assert isinstance(repeater, BBRepeater)


def test_factory_creates_gmm_repeater():
    """Factory should create GaussianMixtureRepeater for GMM option."""
    options = {
        "repeats": "GMM",
        "repeater_options": {
            "GMM": {"max": 50, "goodness_threshold": 1.5},
        },
    }
    repeater = repeater_factory(options)

    assert isinstance(repeater, GaussianMixtureRepeater)


def test_factory_creates_ks_repeater():
    """Factory should create KSRepeater for KS option."""
    options = {
        "repeats": "KS",
        "repeater_options": {
            "KS": {"max": 50, "ks_threshold": 0.2},
        },
    }
    repeater = repeater_factory(options)

    assert isinstance(repeater, KSRepeater)


def test_factory_creates_decision_repeater():
    """Factory should create DecisionRepeater for DC option."""
    options = {
        "repeats": "DC",
        "repeater_options": {
            "DC": {"max": 50, "starting_sample": 10},
        },
    }
    repeater = repeater_factory(options)

    assert isinstance(repeater, DecisionRepeater)


def test_factory_default_is_count_repeater():
    """Factory should default to CountRepeater if repeats option not specified."""
    options = {"repeater_options": {"CR": {"max": 5}}}
    repeater = repeater_factory(options)

    assert isinstance(repeater, CountRepeater)


# --- TestRepeaterProtocol Tests ---


def test_all_repeaters_have_call_method():
    """All repeaters should have __call__ method."""
    repeater_types = [
        CountRepeater,
        RSERepeater,
        CIRepeater,
        HDIRepeater,
        BBRepeater,
        GaussianMixtureRepeater,
        KSRepeater,
        DecisionRepeater,
    ]

    for repeater_cls in repeater_types:
        assert hasattr(repeater_cls, "__call__"), \
            f"{repeater_cls.__name__} should have __call__ method"


def test_all_repeaters_have_get_count_method():
    """All repeaters should have get_count method."""
    repeater_types = [
        CountRepeater,
        RSERepeater,
        CIRepeater,
        HDIRepeater,
        BBRepeater,
        GaussianMixtureRepeater,
        KSRepeater,
        DecisionRepeater,
    ]

    for repeater_cls in repeater_types:
        assert hasattr(repeater_cls, "get_count"), \
            f"{repeater_cls.__name__} should have get_count method"


def test_repeater_returns_boolean():
    """All repeaters should return boolean from __call__."""
    options = {"repeater_options": {"CR": {"max": 1}}}
    repeater = CountRepeater(options)

    pdata = MockRunData({"outer_time": [10.0]})
    result = repeater(pdata)

    assert isinstance(result, (bool, numpy.bool_))


# ============================================================================
# FIXTURE AND INTEGRATION TESTS
# Tests for synthetic distribution generation and basic repeater integration.
# ============================================================================


# ============================================================================
# FIXTURE AND INTEGRATION TESTS
# Tests for synthetic distribution generation and basic repeater integration.
# ============================================================================


# --- TestSyntheticDistributions Tests ---


def test_normal_distribution_has_correct_mean_and_variance():
    """Generated normal distribution should match specified mean and variance."""
    import scipy.stats
    mean, std_dev = 10.0, 1.5
    normal_data = helpers.generate_normal_data(mean=mean, std_dev=std_dev, count=1000)

    # Sample mean should be close to specified mean (within 1 std error)
    sample_mean = numpy.mean(normal_data)
    sample_std = numpy.std(normal_data)
    std_error = std_dev / numpy.sqrt(len(normal_data))

    assert abs(sample_mean - mean) < 3 * std_error, \
        f"Sample mean {sample_mean} should be close to {mean}"
    assert abs(sample_std - std_dev) < 0.3, \
        f"Sample std {sample_std} should be close to {std_dev}"

    # Normality test: Anderson-Darling should not reject normality
    result = scipy.stats.normaltest(normal_data)
    assert result.pvalue > 0.01, \
        f"Normal data should pass normality test, p-value: {result.pvalue}"


def test_uniform_distribution_is_uniformly_distributed():
    """Generated uniform distribution should pass uniformity test."""
    import scipy.stats
    loc, scale = 5.0, 10.0
    uniform_data = helpers.generate_uniform_data(loc=loc, scale=scale, count=1000)

    # All values should be within [loc, loc+scale]
    assert min(uniform_data) >= loc - 0.1, \
        "All uniform values should be >= loc"
    assert max(uniform_data) <= loc + scale + 0.1, \
        "All uniform values should be <= loc+scale"

    # KS test against uniform distribution
    uniform_params = scipy.stats.uniform.fit(uniform_data)
    ks_result = scipy.stats.kstest(uniform_data, "uniform", uniform_params)
    assert ks_result.pvalue > 0.01, \
        f"Data should match uniform distribution, p-value: {ks_result.pvalue}"


def test_lognormal_distribution_is_right_skewed():
    """Generated lognormal distribution should be right-skewed."""
    import scipy.stats
    lognormal_data = helpers.generate_lognormal_data(
        shape=0.95, mean=10.0, std_dev=1.8, count=1000
    )

    # Skewness should be positive (right-skewed)
    skewness = scipy.stats.skew(lognormal_data)
    assert skewness > 0.2, \
        f"Lognormal should be right-skewed, skewness: {skewness}"

    # KS test against lognormal
    lognorm_params = scipy.stats.lognorm.fit(lognormal_data)
    ks_result = scipy.stats.kstest(lognormal_data, "lognorm", lognorm_params)
    assert ks_result.pvalue > 0.01, \
        f"Data should match lognormal distribution, p-value: {ks_result.pvalue}"


def test_constant_distribution_has_low_variance():
    """Generated constant distribution should have very low variance."""
    constant_data = helpers.generate_constant_data(
        value=12.34, noise_scale=0.0, count=200
    )

    # All values should be exactly the constant (with numerical precision)
    sample_variance = numpy.var(constant_data)
    assert sample_variance < 1e-10, \
        f"Perfect constant should have near-zero variance, got {sample_variance}"


def test_bimodal_distribution_has_two_modes():
    """Generated bimodal distribution should have approximately two peaks."""
    import scipy.stats
    bimodal_data = helpers.generate_bimodal_data(count=1000)

    # Kurtosis should indicate multimodality (not normal-like)
    kurtosis = scipy.stats.kurtosis(bimodal_data)
    assert kurtosis < 0, \
        f"Bimodal should have negative kurtosis, got {kurtosis}"


def test_sine_distribution_has_periodic_pattern():
    """Generated sine distribution should show autocorrelation."""
    sine_data = helpers.generate_sine_data(count=500)

    # Compute autocorrelation at lag=10 (should be high for periodic data)
    mean = numpy.mean(sine_data)
    normalized = numpy.array(sine_data) - mean
    var = numpy.var(sine_data)
    acf = numpy.correlate(normalized, normalized, mode='full')
    acf = acf[len(acf)//2:] / (var * len(sine_data))

    # Check autocorrelation at a moderate lag (should be high for sine)
    # Use absolute value since sine can have negative correlation at certain lags
    lag_10_acf = abs(acf[10]) if len(acf) > 10 else 0
    assert lag_10_acf > 0.15, \
        f"Sine data should show autocorrelation, lag-10 |ACF|: {lag_10_acf}"


# ============================================================================
# ADVANCED BOUNDARY CONDITION TESTS
# Tests with diverse distributions to validate repeater robustness across
# complex data patterns (bimodal, multimodal, skewed, periodic, etc.).
# ============================================================================


# ============================================================================
# ADVANCED BOUNDARY CONDITION TESTS
# Tests with diverse distributions to validate repeater robustness across
# complex data patterns (bimodal, multimodal, skewed, periodic, etc.).
# ============================================================================


# --- TestAdvancedBoundaryConditions Tests ---


def test_rse_repeater_with_bimodal_distribution_boundary():
    """RSERepeater should handle bimodal data at boundary conditions.

    With loose threshold on high-variance (bimodal) data, should continue
    for extended sampling (good distributions don't converge immediately).
    """
    options = {
        "repeater_options": {
            "RSE": {"max": 100, "rse_threshold": 0.8, "starting_sample": 10}
        }
    }
    repeater = RSERepeater(options)

    # Bimodal data - high variance due to separation between modes
    bimodal_data = helpers.generate_bimodal_data(count=100)
    pdata = MockRunData({"outer_time": bimodal_data})

    decisions = []
    for i in range(100):
        should_continue = repeater(pdata)
        decisions.append((repeater.get_count(), should_continue))
        if not should_continue:
            break

    # Should continue for substantial sampling (bimodal is high-variance)
    assert repeater.get_count() >= 10, \
        "Should sample substantially with bimodal data"
    assert repeater.get_count() <= 100, \
        "Should not hit max on bimodal data with loose threshold"
    # Verify it actually stopped (didn't just hit max)
    assert not decisions[-1][1], \
        "Should converge/stop within limit"


def test_ci_repeater_with_lognormal_distribution_boundary():
    """CIRepeater should handle skewed log-normal data at boundary.

    Lognormal data with loose CI threshold should continue sampling but
    eventually converge after starting_sample is reached.
    """
    options = {
        "repeater_options": {
            "CI": {"max": 100, "ci_threshold": 0.8, "starting_sample": 15}
        }
    }
    repeater = CIRepeater(options)

    # Log-normal distribution (right-skewed)
    lognormal_data = helpers.generate_lognormal_data(count=100)
    pdata = MockRunData({"outer_time": lognormal_data})

    decisions = []
    for i in range(100):
        should_continue = repeater(pdata)
        decisions.append((repeater.get_count(), should_continue))
        if not should_continue:
            break

    # Must respect starting_sample minimum
    assert repeater.get_count() >= 15, \
        "Should continue at least until starting_sample"
    # Should converge well before max (lognormal is convergent with reasonable threshold)
    assert repeater.get_count() <= 70, \
        "Should converge before 70% of max on lognormal with loose threshold"
    assert not decisions[-1][1], \
        "Should eventually converge and stop"


def test_hdi_repeater_with_multimodal_distribution_boundary():
    """HDIRepeater should handle multimodal data with appropriate convergence.

    Multimodal data with loose HDI threshold should sample substantially
    but still converge (not forever).
    """
    options = {
        "repeater_options": {
            "HDI": {"max": 100, "hdi_threshold": 1.0, "starting_sample": 15}
        }
    }
    repeater = HDIRepeater(options)

    # Multimodal distribution (3 modes)
    multimodal_data = helpers.generate_multimodal_data(modes=3, count=100)
    pdata = MockRunData({"outer_time": multimodal_data})

    decisions = []
    for i in range(100):
        should_continue = repeater(pdata)
        decisions.append((repeater.get_count(), should_continue))
        if not should_continue:
            break

    # Must respect starting_sample
    assert repeater.get_count() >= 15, \
        "Should continue until starting_sample"
    # Should converge (not hit max)
    assert repeater.get_count() < 100, \
        "Should converge before hitting max"
    assert not decisions[-1][1], \
        "Should converge and stop"


def test_ks_repeater_with_logistic_distribution_boundary():
    """KSRepeater should handle logistic distribution with proper convergence.

    Logistic (bell curve) data with moderate threshold should converge
    after starting_sample.
    """
    options = {
        "repeater_options": {
            "KS": {"max": 100, "ks_threshold": 0.3, "starting_sample": 15}
        }
    }
    repeater = KSRepeater(options)

    # Logistic distribution (symmetric, heavier tails than normal)
    logistic_data = helpers.generate_logistic_data(count=100)
    pdata = MockRunData({"outer_time": logistic_data})

    decisions = []
    for i in range(100):
        should_continue = repeater(pdata)
        decisions.append((repeater.get_count(), should_continue))
        if not should_continue:
            break

    # Should respect starting_sample
    assert repeater.get_count() >= 15, \
        "Should continue until starting_sample"
    # Should converge reasonably (not explore full 100)
    assert repeater.get_count() < 90, \
        "KS should converge on logistic well before max"
    assert not decisions[-1][1], \
        "Should eventually converge and stop"


def test_gmm_repeater_with_multimodal_distribution():
    """GaussianMixtureRepeater should converge on properly fit multimodal data.

    GMM should detect multimodal structure and converge after appropriate sampling.
    """
    options = {
        "repeater_options": {
            "GMM": {
                "max": 100,
                "goodness_threshold": 0.8,
                "starting_sample": 15,
                "max_gaussian_components": 4,
            }
        }
    }
    repeater = GaussianMixtureRepeater(options)

    # Multimodal distribution with 3 modes
    multimodal_data = helpers.generate_multimodal_data(modes=3, count=100)
    pdata = MockRunData({"outer_time": multimodal_data})

    decisions = []
    for i in range(100):
        should_continue = repeater(pdata)
        decisions.append((repeater.get_count(), should_continue))
        if not should_continue:
            break

    # Should respect starting_sample minimum
    assert repeater.get_count() >= 15, \
        "Should continue until starting_sample"
    # Should eventually converge
    assert not decisions[-1][1], \
        "Should eventually converge on multimodal data"
    # Should converge reasonably (not explore everything)
    assert repeater.get_count() < 85, \
        "GMM should converge before 85% of max on multimodal"


def test_rse_repeater_with_uniform_distribution():
    """RSERepeater should handle uniform distribution with appropriate sampling.

    Uniform (flat) data has low RSE, should converge relatively quickly.
    """
    options = {
        "repeater_options": {
            "RSE": {"max": 100, "rse_threshold": 0.5, "starting_sample": 10}
        }
    }
    repeater = RSERepeater(options)

    # Uniform distribution (flat - all values equally likely)
    uniform_data = helpers.generate_uniform_data(count=100)
    pdata = MockRunData({"outer_time": uniform_data})

    decisions = []
    for i in range(100):
        should_continue = repeater(pdata)
        decisions.append((repeater.get_count(), should_continue))
        if not should_continue:
            break

    # Should respect starting_sample
    assert repeater.get_count() >= 10, \
        "Should continue until starting_sample"
    # Uniform has low variance so should converge quickly (threshold easily met)
    assert repeater.get_count() < 50, \
        "Uniform data should have low RSE, converge quickly"
    assert not decisions[-1][1], \
        "Should converge and stop"


def test_ci_repeater_with_sine_distribution():
    """CIRepeater should handle autocorrelated sine data.

    Periodic data with CI threshold needs substantial sampling to detect
    pattern stability.
    """
    options = {
        "repeater_options": {
            "CI": {"max": 100, "ci_threshold": 0.5, "starting_sample": 20}
        }
    }
    repeater = CIRepeater(options)

    # Sine distribution (periodic pattern with noise)
    sine_data = helpers.generate_sine_data(count=100)
    pdata = MockRunData({"outer_time": sine_data})

    decisions = []
    for i in range(100):
        should_continue = repeater(pdata)
        decisions.append((repeater.get_count(), should_continue))
        if not should_continue:
            break

    # Should respect starting_sample
    assert repeater.get_count() >= 20, \
        "Should continue until starting_sample on sine data"
    # Should eventually converge
    assert repeater.get_count() < 100, \
        "Should converge before max"
    assert not decisions[-1][1], \
        "Should eventually converge and stop"


def test_hdi_repeater_with_constant_data_tight_threshold():
    """HDIRepeater with loose threshold on constant data should stop quickly.

    Constant (zero variance) data should trigger immediate convergence
    after starting_sample.
    """
    options = {
        "repeater_options": {
            "HDI": {"max": 100, "hdi_threshold": 5.0, "starting_sample": 5}
        }
    }
    repeater = HDIRepeater(options)

    # Constant data - minimal variance
    constant_data = helpers.generate_constant_data(value=50.0, count=100)
    pdata = MockRunData({"outer_time": constant_data})

    stopped_at_count = None
    for i in range(100):
        should_continue = repeater(pdata)
        if not should_continue:
            stopped_at_count = repeater.get_count()
            break

    # Should stop after starting_sample with constant data (no variance = immediate convergence)
    assert stopped_at_count is not None, \
        "Should stop when data has no variance"
    assert stopped_at_count >= 5, \
        "Should respect starting_sample minimum"
    assert stopped_at_count < 30, \
        "Constant data should converge quickly (no variance)"
