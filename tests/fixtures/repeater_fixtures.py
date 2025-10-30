#!/usr/bin/env python3
"""
Shared test fixtures for repeater unit tests.

Provides MockRunData mock and RepeaterTestMixin for common repeater testing
patterns. Can be extracted to conftest.py after pytest migration.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any, Dict, List

import pytest

from src.core.repeaters.base import Repeater, RunData


class MockRunData(RunData):
    """Mock RunData for testing without actual benchmark execution."""

    def __init__(self, metrics: Dict[str, List[float]]):
        """Initialize with synthetic metrics."""
        self.metrics = metrics
        self.metadata = {}

    def get_metric(self, metric_name: str) -> List[float]:
        """Return synthetic metric values."""
        if metric_name not in self.metrics:
            raise KeyError(f"Metric {metric_name} not found in mock data")
        return self.metrics.get(metric_name, [])

    def set_metric(self, metric_name: str, values: List[float]) -> None:
        """Set metric values."""
        self.metrics[metric_name] = values


# ============================================================================
# Standalone Helper Functions
# ============================================================================

def make_repeater_options(
    repeater_key: str,
    max_repeats: int,
    threshold_value: float = None,
    starting_sample: int = 5,
    **extra_options
) -> Dict[str, Any]:
    """Create standardized repeater options dict.

    Args:
        repeater_key: Repeater type key (e.g., 'RSE', 'CI', 'HDI', 'KS', etc.)
        max_repeats: Max iterations
        threshold_value: Threshold parameter (rse_threshold, ci_threshold, etc).
                       Not used for 'CR' (Count) or 'DC' (Decision).
        starting_sample: Minimum samples before threshold test
        extra_options: Additional repeater-specific options (including metric if needed)

    Returns:
        Options dict ready for repeater initialization.
        The 'metric' parameter (if provided) is placed at the top level of repeater_options
        since it's shared by all repeaters (inherited from CountRepeater).
    """
    # Map repeater key to threshold parameter name
    threshold_names = {
        "RSE": "rse_threshold",
        "CI": "ci_threshold",
        "HDI": "hdi_threshold",
        "KS": "ks_threshold",
        "BB": "bb_threshold",
        "GMM": "goodness_threshold",
        "DC": None,  # Decision repeater doesn't use threshold
        "CR": None,  # Count repeater doesn't use threshold
    }

    threshold_key = threshold_names.get(repeater_key)

    # Extract metric from extra_options if present (shared parameter for all repeaters)
    metric = extra_options.pop("metric", None)

    options_dict = {
        "max": max_repeats,
        "starting_sample": starting_sample,
    }

    if threshold_key:
        options_dict[threshold_key] = threshold_value

    # Add remaining extra_options to repeater-specific dict
    options_dict.update(extra_options)

    result = {
        "repeater_options": {
            repeater_key: options_dict
        }
    }

    # Place metric at top level of repeater_options (shared by all repeaters)
    if metric is not None:
        result["repeater_options"]["metric"] = metric

    return result


def collect_decisions(
    repeater: Repeater, data: MockRunData, max_iterations: int = 100
) -> List[tuple]:
    """Collect repeater decisions until convergence or max iterations.

    Returns list of (count, should_continue) tuples. Stops early when
    repeater returns False (convergence).

    Args:
        repeater: Repeater instance
        data: MockRunData to feed
        max_iterations: Max decisions to collect

    Returns:
        List of (count, should_continue) tuples
    """
    decisions = []
    for _ in range(max_iterations):
        should_continue = repeater(data)
        decisions.append((repeater.get_count(), should_continue))
        if not should_continue:
            break
    return decisions


def make_repeater(
    repeater_class: type,
    repeater_key: str = None,
    **options
) -> Repeater:
    """Create and return a repeater instance with options dict.

    Convenience method combining make_repeater_options and constructor call.

    Args:
        repeater_class: Repeater class (RSERepeater, CIRepeater, etc.)
        repeater_key: Optional repeater key if options don't already have
                     'repeater_options' dict. If not provided, assumes
                     options already contain 'repeater_options' key.
        **options: Either:
          - Full options dict with 'repeater_options' key: make_repeater(RSERepeater, **full_options)
          - Parameters for make_repeater_options: make_repeater(RSERepeater, 'RSE', max_repeats=100, ...)

    Returns:
        Initialized repeater instance
    """
    # If repeater_key provided, assume options are parameters for make_repeater_options
    if repeater_key is not None:
        options_dict = make_repeater_options(repeater_key, **options)
    else:
        # Otherwise assume options already has 'repeater_options' key
        options_dict = options

    return repeater_class(options_dict)


# ============================================================================
# RepeaterTester Fixture Class
# ============================================================================

class RepeaterTester:
    """Pytest fixture class for common repeater test patterns.

    Provides assertion methods that validate repeater behavior.
    Takes repeater instances as parameters (created by tests).
    """

    def assert_initialization(self, repeater: Repeater) -> None:
        """Assert repeater initializes without error.

        Args:
            repeater: Initialized repeater instance to test

        Validates:
            - Initial count is 0
            - Initial runtimes list is empty
        """
        assert repeater.get_count() == 0, "Initial count should be 0"
        assert len(repeater._runtimes) == 0, "Initial runtimes should be empty"

    def assert_increments_count(self, repeater: Repeater) -> None:
        """Assert repeater increments count with each call.

        Args:
            repeater: Initialized repeater instance to test

        Validates:
            - Count increments by 1 after each call
        """
        initial_count = repeater.get_count()
        pdata = MockRunData({"outer_time": [10.0]})

        for _ in range(3):
            repeater(pdata)
            initial_count += 1
            assert repeater.get_count() == initial_count, \
                f"Count should be {initial_count} after call"

    def assert_continues_before_starting_sample(self, repeater: Repeater, starting_sample: int) -> None:
        """Assert repeater continues until starting_sample is reached.

        Args:
            repeater: Initialized repeater instance to test
            starting_sample: Expected starting_sample value from repeater config

        Validates:
            - Repeater continues before starting_sample
            - Count equals starting_sample - 1 after feeding that many samples
        """
        # Feed constant data before starting_sample
        for i in range(starting_sample - 1):
            pdata = MockRunData({"outer_time": [10.0]})
            should_continue = repeater(pdata)
            assert should_continue, \
                f"Should continue at count {i+1} (before starting_sample={starting_sample})"

        assert repeater.get_count() == starting_sample - 1, \
            f"Count should be {starting_sample - 1}"

    def assert_does_not_converge_prematurely(
        self,
        repeater: Repeater,
        data_gen,
        iterations: int = 20
    ) -> None:
        """Assert repeater does not converge prematurely on high-variance data.

        Args:
            repeater: Initialized repeater instance to test
            data_gen: Function that generates high-variance data
            iterations: Number of iterations to test (default 20)

        Validates:
            - Repeater continues for multiple iterations with high-variance data
            - Does not converge immediately
        """
        # High-variance data
        high_variance_data = data_gen(count=50)
        pdata = MockRunData({"outer_time": high_variance_data})

        # Collect early decisions
        early_decisions = []
        for _ in range(iterations):
            should_continue = repeater(pdata)
            early_decisions.append((repeater.get_count(), should_continue))

        # Should continue for multiple iterations, not converge immediately
        continuing_count = len([d for d in early_decisions if d[1]])
        assert continuing_count > 5, \
            f"Should continue for many iterations with high variance, but only continued {continuing_count}/{iterations}"

    def assert_stops_when_threshold_crossed(
        self,
        repeater: Repeater,
        data_gen,
        starting_sample: int
    ) -> None:
        """Assert repeater stops when threshold is crossed on convergent data.

        Args:
            repeater: Initialized repeater instance to test
            data_gen: Function that generates convergent/constant data
            starting_sample: Expected starting_sample from repeater config

        Validates:
            - Repeater stops when threshold crossed on convergent data
            - Count is at least starting_sample
        """
        # Convergent data (constant or simple)
        convergent_data = data_gen(count=100)
        pdata = MockRunData({"outer_time": convergent_data})

        # Run until convergence
        stopped_early = False
        for _ in range(100):
            should_continue = repeater(pdata)
            if not should_continue:
                stopped_early = True
                break

        assert stopped_early, "Repeater should stop when threshold is crossed"
        assert repeater.get_count() >= starting_sample, \
            f"Should continue until starting_sample={starting_sample}"


# ============================================================================
# Pytest Fixture
# ============================================================================

@pytest.fixture
def repeater_tester():
    """Provide RepeaterTester instance for all tests."""
    return RepeaterTester()

