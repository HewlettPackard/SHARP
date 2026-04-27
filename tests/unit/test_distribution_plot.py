"""
Unit tests for distribution plotting functionality.

Tests verify that distribution plots correctly render classification results,
handle NaN values, and draw cutoff lines appropriately.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import matplotlib.pyplot as plt
from src.core.stats.distribution import create_distribution_plot


def test_create_distribution_plot_with_labels():
    """Test that class labels result in multi-colored scatter points."""
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    labels = np.array(["A", "A", "B", "B", "A"])
    colors = {"A": "red", "B": "blue"}

    fig = create_distribution_plot(
        values=values,
        metric="test_metric",
        class_labels=labels,
        class_colors=colors
    )

    # Verify plot was created
    assert isinstance(fig, plt.Figure)
    ax = fig.axes[0]

    # Verify scatter plot has data (should have points from both classes)
    scatter_collections = [c for c in ax.collections if hasattr(c, 'get_offsets')]
    assert len(scatter_collections) > 0, "Should have scatter plot data"

    # Verify legend entries for both classes
    legend = ax.get_legend()
    assert legend is not None, "Should have legend"
    labels_in_legend = [text.get_text() for text in legend.get_texts()]
    assert "A" in labels_in_legend, "Class A should be in legend"
    assert "B" in labels_in_legend, "Class B should be in legend"

    plt.close(fig)


def test_create_distribution_plot_with_labels_and_nans():
    """Test that NaN filtering preserves label synchronization."""
    values = np.array([1.0, np.nan, 3.0, 4.0, 5.0])
    labels = np.array(["A", "A", "B", "B", "A"])
    colors = {"A": "red", "B": "blue"}

    fig = create_distribution_plot(
        values=values,
        metric="test_metric",
        class_labels=labels,
        class_colors=colors
    )

    assert isinstance(fig, plt.Figure)
    ax = fig.axes[0]

    # After NaN filtering, should still have valid scatter data
    scatter_collections = [c for c in ax.collections if hasattr(c, 'get_offsets')]
    assert len(scatter_collections) > 0, "Should have scatter data after NaN filtering"

    # Check that we still have both classes represented
    legend = ax.get_legend()
    assert legend is not None
    labels_in_legend = [text.get_text() for text in legend.get_texts()]
    assert len(labels_in_legend) >= 2, "Should have multiple classes after NaN filtering"

    plt.close(fig)


def test_create_distribution_plot_with_cutoffs():
    """Test that cutoff values are drawn as vertical lines."""
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    labels = np.array(["A", "A", "B", "B", "B"])
    colors = {"A": "green", "B": "orange"}

    fig = create_distribution_plot(
        values=values,
        metric="test_metric",
        class_labels=labels,
        class_colors=colors,
        cutoffs=[2.5]
    )

    assert isinstance(fig, plt.Figure)
    ax = fig.axes[0]

    # Verify vertical line for cutoff exists
    vlines = [line for line in ax.get_lines() if line.get_xdata()[0] == line.get_xdata()[1]]
    assert len(vlines) > 0, "Should have vertical cutoff line"

    # Verify cutoff is at correct x-position
    cutoff_lines = [line for line in vlines if abs(line.get_xdata()[0] - 2.5) < 0.01]
    assert len(cutoff_lines) > 0, "Should have cutoff line at x=2.5"

    plt.close(fig)


def test_create_distribution_plot_without_classification():
    """Test basic plot without classification (backward compatibility)."""
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

    fig = create_distribution_plot(
        values=values,
        metric="test_metric"
    )

    assert isinstance(fig, plt.Figure)
    ax = fig.axes[0]

    # Should still have histogram
    patches = ax.patches
    assert len(patches) > 0, "Should have histogram bars"

    # Should have scatter data (default black points)
    scatter_collections = [c for c in ax.collections if hasattr(c, 'get_offsets')]
    assert len(scatter_collections) > 0, "Should have scatter data"

    plt.close(fig)
