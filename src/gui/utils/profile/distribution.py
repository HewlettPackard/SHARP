"""
Distribution visualization utilities for profile tab.

Provides functions to render distribution plots and narratives.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import numpy as np
import polars as pl
from shiny import ui

from src.core.stats.distribution import create_distribution_plot, characterize_distribution
from src.core.config.settings import Settings


def _create_standby_figure(message: str) -> Figure:
    """
    Create a matplotlib figure with a standby/info message.

    Args:
        message: Message to display

    Returns:
        Matplotlib figure with centered text
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.text(0.5, 0.5, message, ha='center', va='center', fontsize=12, color='#666')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    return fig


def render_distribution_plot(data: pl.DataFrame | None, metric_col: str, cutoff: float | None = None) -> Figure | None:
    """
    Render distribution plot with optional cutoff divider.

    Args:
        data: DataFrame containing the metric
        metric_col: Name of the metric column
        cutoff: Optional cutoff value for classification divider

    Returns:
        Matplotlib figure or None if error
    """
    if data is None or data.is_empty():
        return _create_standby_figure("Please load data and select outcome metric to view distribution")

    if not metric_col or metric_col not in data.columns:
        return _create_standby_figure("Please select an outcome metric to view distribution")

    values = data[metric_col].drop_nulls().to_numpy()
    if len(values) == 0:
        return None

    settings = Settings()
    max_scatter = settings.get("gui.explore.max_scatter_points", 2000)

    # Get color configuration
    dist_colors = settings.get("gui.distribution", {})
    left_color = dist_colors.get("left_color", "#2ca02c")
    right_color = dist_colors.get("right_color", "#ff7f0e")
    divider_color = dist_colors.get("divider_color", "#1f77b4")
    alpha = dist_colors.get("alpha", 0.4)

    return create_distribution_plot(
        values, metric_col,
        divider=cutoff,
        max_scatter_points=max_scatter,
        left_color=left_color,
        right_color=right_color,
        divider_color=divider_color,
        alpha=alpha
    )


def render_distribution_narrative(data: pl.DataFrame | None, metric_col: str) -> ui.TagChild:
    """
    Generate narrative description of distribution characteristics.

    Args:
        data: DataFrame containing the metric
        metric_col: Name of the metric column

    Returns:
        Shiny UI element with narrative text
    """
    if data is None or data.is_empty():
        return ui.div()

    if metric_col not in data.columns:
        return ui.div()

    values = data[metric_col].drop_nulls().to_numpy()
    if len(values) < 3:
        return ui.div(
            ui.tags.p("Insufficient data for characterization",
                     style="color: #666; font-size: 0.9em;")
        )

    try:
        # Sample values if dataset is large for scatter plot consistency
        settings = Settings()
        max_scatter = settings.get("gui.explore.max_scatter_points", 2000)

        sample_values = values
        if len(values) > max_scatter:
            np.random.seed(42)
            indices = np.random.choice(len(values), size=max_scatter, replace=False)
            sample_values = values[indices]

        # Generate narrative
        # Changepoint detection uses adaptive model: RBF for ≤500 points, L2 for larger
        narrative_text = characterize_distribution(sample_values)

        if narrative_text:
            return ui.tags.div(
                ui.tags.p(ui.tags.strong("Distribution Characterization:")),
                ui.markdown(narrative_text),
                style="padding: 10px; background-color: #f8f9fa; border-radius: 5px; margin-top: 10px;"
            )
        else:
            return ui.div()

    except Exception as e:
        return ui.div(
            ui.tags.p(ui.tags.strong("Distribution Characterization:")),
            ui.tags.p(f"Error: {str(e)}", style="color: red; font-size: 0.9em;"),
            style="padding: 10px; background-color: #fff3cd; border-radius: 5px; margin-top: 10px;"
        )
