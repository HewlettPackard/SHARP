"""
Tests for manual cutoff search functionality.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""
import numpy as np
import polars as pl
import pytest

from src.gui.utils.profile.tree import search_optimal_manual_cutoffs


def test_search_optimal_manual_cutoffs_returns_cutoffs():
    """Test that search_optimal_manual_cutoffs returns valid cutoffs."""
    # Create synthetic data with clear groups
    np.random.seed(42)

    # Create data with 3 distinct groups
    group1 = np.random.normal(1.0, 0.1, 50)
    group2 = np.random.normal(2.0, 0.1, 50)
    group3 = np.random.normal(3.0, 0.1, 50)

    perf_time = np.concatenate([group1, group2, group3])

    # Create some predictors (features)
    feature1 = np.random.rand(150)
    feature2 = np.random.rand(150)
    feature3 = np.random.choice(['A', 'B', 'C'], 150)

    data = pl.DataFrame({
        'perf_time': perf_time,
        'feature1': feature1,
        'feature2': feature2,
        'feature3': feature3
    })

    # Search for optimal cutoffs
    cutoffs = search_optimal_manual_cutoffs(
        data=data,
        metric_col='perf_time',
        exclude=[],
        progress_callback=None,
        lower_is_better=True,
        max_cutoffs=9
    )

    # Should return some cutoffs (not None)
    assert cutoffs is not None
    assert len(cutoffs) > 0
    assert len(cutoffs) <= 9

    # Cutoffs should be sorted
    assert cutoffs == sorted(cutoffs)

    # Cutoffs should be within data range
    min_val = float(np.min(perf_time))
    max_val = float(np.max(perf_time))
    for cutoff in cutoffs:
        assert min_val < cutoff < max_val


def test_search_optimal_manual_cutoffs_with_insufficient_data():
    """Test that search returns None with insufficient data."""
    # Create very small dataset
    data = pl.DataFrame({
        'perf_time': [1.0, 2.0, 3.0],
        'feature1': [0.1, 0.2, 0.3]
    })

    cutoffs = search_optimal_manual_cutoffs(
        data=data,
        metric_col='perf_time',
        exclude=[],
        progress_callback=None,
        lower_is_better=True
    )

    # Should return None for insufficient data
    assert cutoffs is None


def test_search_optimal_manual_cutoffs_finds_reasonable_cutoffs():
    """Test that search finds reasonable cutoffs for bimodal data."""
    np.random.seed(42)

    # Create bimodal distribution
    slow_group = np.random.normal(1.0, 0.05, 75)
    fast_group = np.random.normal(1.5, 0.05, 75)
    perf_time = np.concatenate([slow_group, fast_group])

    # Add predictors that correlate with performance
    feature1 = np.concatenate([
        np.random.normal(10, 1, 75),
        np.random.normal(20, 1, 75)
    ])

    data = pl.DataFrame({
        'perf_time': perf_time,
        'feature1': feature1
    })

    cutoffs = search_optimal_manual_cutoffs(
        data=data,
        metric_col='perf_time',
        exclude=[],
        progress_callback=None,
        lower_is_better=True
    )

    assert cutoffs is not None
    assert len(cutoffs) >= 1

    # For bimodal data, cutoff should be roughly between the modes
    # (around 1.25, between 1.0 and 1.5)
    if len(cutoffs) == 1:
        assert 1.1 < cutoffs[0] < 1.4
