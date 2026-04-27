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
from typing import List

from src.core.stats.distribution import create_distribution_plot, characterize_distribution
from src.core.config.settings import Settings
from src.core.profile.labeler import PerformanceLabeler, BinaryLabeler, CutoffBasedLabeler


def get_class_colors(class_names: List[str]) -> List[str]:
    """
    Map class names to colors from settings.

    Recognizes FAST/SLOW labels from settings and maps them to configured colors.
    All other classes use the configured Seaborn palette.

    Args:
        class_names: List of class names (e.g., ["FAST", "SLOW"])

    Returns:
        List of hex color strings matching class_names order
    """
    import seaborn as sns

    settings = Settings()
    dist_colors = settings.get("gui.distribution", {})
    fast_color = dist_colors.get("fast_color", "#2ca02c")
    slow_color = dist_colors.get("slow_color", "#ff7f0e")
    fast_label = dist_colors.get("fast_label", "FAST")
    slow_label = dist_colors.get("slow_label", "SLOW")

    # Check if we have only FAST/SLOW labels
    if set(class_names) == {fast_label, slow_label}:
        # Use configured fast/slow colors
        color_map = {fast_label: fast_color, slow_label: slow_color}
        return [color_map[name] for name in class_names]

    # For all other cases (including AutoLabeler classes), use configured palette
    palette_name = dist_colors.get("palette", "dark")
    palette = sns.color_palette(palette_name, n_colors=len(class_names))
    colors = ['#{:02x}{:02x}{:02x}'.format(int(r*255), int(g*255), int(b*255)) for r, g, b in palette]

    return colors


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


def render_distribution_plot(data: pl.DataFrame | None, metric_col: str,
                           labeler: PerformanceLabeler | None = None) -> Figure | None:
    """
    Render distribution plot with classification coloring.

    Args:
        data: DataFrame containing the metric
        metric_col: Name of the metric column
        labeler: Optional labeler to color points by class

    Returns:
        Matplotlib figure or None if error
    """
    if data is None or data.is_empty():
        return _create_standby_figure("Please load data and select outcome metric to view distribution")

    if not metric_col or metric_col not in data.columns:
        return _create_standby_figure("Please select an outcome metric to view distribution")

    values = data[metric_col].to_numpy() # Keep NaNs for alignment, create_distribution_plot handles them
    if len(values) == 0:
        return None

    settings = Settings()
    max_scatter = settings.get("gui.explore.max_scatter_points", 2000)
    dist_colors = settings.get("gui.distribution", {})
    divider_color = dist_colors.get("divider_color", "#1f77b4")
    alpha = dist_colors.get("alpha", 0.4)

    # Use labeler if provided
    if labeler is not None:
        # Get class names and colors
        class_names = labeler.get_class_names()
        palette = get_class_colors(class_names)

        return _render_with_labeler(
            values, metric_col, labeler,
            max_scatter, divider_color, alpha,
            palette=palette
        )

    # Fallback: No labeler -> just plot distribution without colors
    return create_distribution_plot(
        values, metric_col,
        max_scatter_points=max_scatter,
        divider_color=divider_color,
        alpha=alpha
    )


def _render_with_labeler(values: np.ndarray, metric_col: str,
                          labeler: PerformanceLabeler,
                          max_scatter: int,
                          divider_color: str, alpha: float,
                          palette: list[str] | None = None) -> Figure | None:
    """Helper to render distribution plot using a labeler."""
    # Classify all values (including NaNs, labeler should handle or we filter)
    # labeler expects clean data usually.
    mask = ~np.isnan(values)
    clean_values = values[mask]

    if len(clean_values) == 0:
        return None

    labels = labeler.label(clean_values)

    # Reconstruct full labels array with None/NaN for missing values to match input length
    # This is needed because create_distribution_plot expects aligned arrays
    full_labels = np.empty(len(values), dtype=object)
    full_labels[mask] = labels

    # Get class names and cutoffs
    class_names = labeler.get_class_names()
    cutoffs = labeler.get_cutoffs()

    class_colors = {}

    if palette is not None:
        if len(palette) != len(class_names):
            raise ValueError(f"Palette length ({len(palette)}) must match number of classes ({len(class_names)})")

        for name, color in zip(class_names, palette):
            class_colors[name] = color
    else:
        # Default palette (viridis)
        import matplotlib.cm as cm
        cmap = cm.get_cmap('viridis')

        n_classes = len(class_names)
        if n_classes <= 1:
             colors = [cmap(0.5)]
        else:
             # Sample evenly from the colormap
             colors = [cmap(i / (n_classes - 1)) for i in range(n_classes)]

        for name, color in zip(class_names, colors):
            class_colors[name] = color

    return create_distribution_plot(
        values, metric_col,
        class_labels=full_labels,
        class_colors=class_colors,
        class_names_order=class_names,
        cutoffs=cutoffs,
        max_scatter_points=max_scatter,
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


def update_labeler_from_click(click_x: float,
                                labeler: PerformanceLabeler | None,
                                lower_is_better: bool) -> PerformanceLabeler:
    """
    Update labeler by moving nearest cutoff to click location.

    Pure function that creates a new labeler based on user click interaction.
    If no labeler exists, creates one at the click location.
    If labeler exists, finds the nearest cutoff and moves it to the click location.

    Args:
        click_x: X-coordinate of the click (new cutoff location)
        labeler: Current labeler, or None if no labeler exists
        lower_is_better: Whether lower values are better for this metric

    Returns:
        New labeler with updated cutoff(s)
    """
    from src.core.profile.labeler import ManualLabeler

    # No labeler yet - create one at click location
    if labeler is None:
        return BinaryLabeler.with_cutoff(click_x, lower_is_better)

    # Get current cutoffs
    current_cutoffs = labeler.get_cutoffs()
    if not current_cutoffs:
        # No cutoffs in labeler - create new one
        return BinaryLabeler.with_cutoff(click_x, lower_is_better)

    # Find nearest cutoff and move it
    cutoff_array = np.array(current_cutoffs)
    nearest_idx = int(np.argmin(np.abs(cutoff_array - click_x)))

    # Update that cutoff
    new_cutoffs = current_cutoffs.copy()
    new_cutoffs[nearest_idx] = click_x
    new_cutoffs.sort()  # Keep sorted

    # Create new labeler with updated cutoffs, preserving labeler type
    if isinstance(labeler, ManualLabeler):
        # ManualLabeler - use with_cutoffs
        return ManualLabeler.with_cutoffs(new_cutoffs, lower_is_better)
    elif len(new_cutoffs) == 1:
        # Binary labeler
        return BinaryLabeler.with_cutoff(new_cutoffs[0], lower_is_better)
    else:
        # Multi-cutoff labeler - use generic CutoffBasedLabeler
        class_names = labeler.get_class_names()
        return CutoffBasedLabeler(new_cutoffs, class_names, lower_is_better)

