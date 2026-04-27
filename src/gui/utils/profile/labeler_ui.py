"""
Labeler state management for profile tab.

Handles initialization, updates, and interactions with performance labelers.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""
from shiny import reactive, Inputs, ui
from shiny.types import SilentException
import numpy as np
import polars as pl
from typing import Any

from src.core.profile.labeler import (
    PerformanceLabeler,
    BinaryLabeler,
    TertileLabeler,
    QuartileLabeler,
    AutoLabeler,
    ManualLabeler
)
from src.gui.utils.profile.tree import search_for_cutoff
from src.gui.utils.profile.distribution import update_labeler_from_click
from src.core.config.settings import Settings


def initialize_labeler_effect(
    input: Inputs,
    active_data: reactive.Calc,
    validated_metric: reactive.Calc,
    lower_is_better_setting: reactive.Value,
    current_labeler: reactive.Value
) -> None:
    """
    Create a reactive effect to initialize labeler when data/metric/strategy changes.

    Args:
        input: Shiny inputs
        active_data: Reactive calc returning current dataframe
        validated_metric: Reactive calc returning validated metric column name
        lower_is_better_setting: Reactive value for lower_is_better flag
        current_labeler: Reactive value to store the labeler
    """
    # Track previous strategy to detect mode changes
    prev_strategy = reactive.Value(None)

    @reactive.effect
    def _initialize_labeler() -> None:
        """Initialize labeler when data/metric/lower_is_better/strategy changes."""
        data = active_data()
        metric_col = validated_metric()

        # Reset if no data or metric
        if data is None or not metric_col or metric_col not in data.columns:
            current_labeler.set(None)
            prev_strategy.set(None)
            return

        # Get metric values
        values = data[metric_col].drop_nulls().to_numpy()
        if len(values) < 2:
            current_labeler.set(None)
            prev_strategy.set(None)
            return

        # Get lower_is_better setting
        lower_is_better = lower_is_better_setting.get()

        # Get strategy
        try:
            strategy = input.classification_strategy()
        except SilentException:
            strategy = "binary"

        # Check if we're staying in manual mode (no strategy change)
        # If so, don't recreate - let handle_num_cutoffs_change_effect handle it
        if strategy == "manual" and prev_strategy.get() == "manual":
            # Keep existing ManualLabeler, don't reinitialize
            # The handle_num_cutoffs_change_effect will handle num_cutoffs changes
            return

        # Update previous strategy
        prev_strategy.set(strategy)

        # Initialize labeler based on strategy
        try:
            match strategy:
                case "auto":
                    # Auto labeling can be slow - use ui.notification to show progress
                    with ui.Progress(min=0, max=1) as p:
                        p.set(message="Analyzing distribution...", detail="Running changepoint detection and clustering")
                        labeler = AutoLabeler(values, lower_is_better)
                case "manual":
                    # Get num_cutoffs if available, default to 1
                    try:
                        num_cutoffs = int(input.manual_num_cutoffs())
                    except (SilentException, ValueError):
                        num_cutoffs = 1
                    labeler = ManualLabeler(values, lower_is_better, num_cutoffs)
                case "tertile":
                    labeler = TertileLabeler(values, lower_is_better)
                case "quartile":
                    labeler = QuartileLabeler(values, lower_is_better)
                case _:  # binary (default)
                    labeler = BinaryLabeler(values, lower_is_better)
            current_labeler.set(labeler)
        except Exception:
            current_labeler.set(None)
            prev_strategy.set(None)



def handle_plot_click_effect(
    input: Inputs,
    current_labeler: reactive.Value,
    lower_is_better_setting: reactive.Value
) -> None:
    """
    Create a reactive effect to handle plot clicks for cutoff adjustment.

    Args:
        input: Shiny inputs
        current_labeler: Reactive value storing the current labeler
        lower_is_better_setting: Reactive value for lower_is_better flag
    """
    @reactive.effect
    @reactive.event(input.profile_distribution_plot_click)
    def _handle_plot_click() -> None:
        """Move the nearest cutoff to the click location (only for mutable labelers)."""
        click_data = input.profile_distribution_plot_click()
        if click_data is None or "x" not in click_data:
            return

        labeler = current_labeler.get()

        # Only allow cutoff adjustment for mutable labelers
        if labeler is None or not (hasattr(labeler, 'is_mutable') and labeler.is_mutable):
            return

        click_x = float(click_data["x"])
        lower_is_better = lower_is_better_setting.get()

        # Update labeler using helper function
        new_labeler = update_labeler_from_click(click_x, labeler, lower_is_better)
        current_labeler.set(new_labeler)


def handle_cutoff_search_effect(
    input: Inputs,
    active_data: reactive.Calc,
    validated_metric: reactive.Calc,
    excluded_predictors: reactive.Value,
    current_labeler: reactive.Value,
    lower_is_better_setting: reactive.Value
) -> None:
    """
    Create a reactive effect to handle cutoff search button.

    Args:
        input: Shiny inputs
        active_data: Reactive calc returning current dataframe
        validated_metric: Reactive calc returning validated metric column name
        excluded_predictors: Reactive value with excluded predictor list
        current_labeler: Reactive value storing the current labeler
        lower_is_better_setting: Reactive value for lower_is_better flag
    """
    from shiny import ui

    @reactive.effect
    @reactive.event(input.search_cutoff_btn)
    def _search_cutoff_space() -> None:
        """Search for effective cutoff point(s) that minimize AIC."""
        labeler = current_labeler.get()

        # Only allow cutoff search for mutable labelers
        if labeler is None or not (hasattr(labeler, 'is_mutable') and labeler.is_mutable):
            return

        data = active_data()
        metric_col = validated_metric()

        if data is None or data.is_empty() or not metric_col:
            return

        # Get settings
        settings = Settings()
        max_search_points = settings.get("profiling.max_search", 100)

        # Get excluded predictors
        current_exclusions = excluded_predictors()

        # Get lower_is_better setting
        lower_is_better = lower_is_better_setting.get()

        # Check if this is a ManualLabeler
        is_manual = isinstance(labeler, ManualLabeler)

        # Show progress bar
        with ui.Progress(min=0, max=max_search_points) as p:
            if is_manual:
                # Manual labeler: search for optimal number of cutoffs and their values
                p.set(message=f"Searching optimal cutoffs...", detail="Trying different configurations...")

                # Use search_optimal_manual_cutoffs
                from src.gui.utils.profile.tree import search_optimal_manual_cutoffs

                def update_progress(progress_pct: float, detail: str) -> None:
                    value = int(progress_pct * max_search_points)
                    p.set(value=value, detail=detail)

                optimal_cutoffs = search_optimal_manual_cutoffs(
                    data=data,
                    metric_col=metric_col,
                    exclude=current_exclusions,
                    progress_callback=update_progress,
                    lower_is_better=lower_is_better
                )

                if optimal_cutoffs is not None and len(optimal_cutoffs) > 0:
                    new_labeler = ManualLabeler.with_cutoffs(optimal_cutoffs, lower_is_better)
                    # Set labeler FIRST so handle_num_cutoffs_change_effect sees the new cutoffs
                    current_labeler.set(new_labeler)
                    # Update the input after - the effect will see new_num == len(cutoffs) and skip
                    ui.update_select("manual_num_cutoffs", selected=str(len(optimal_cutoffs)))
                    p.set(message="Search complete!", value=max_search_points,
                          detail=f"Found {len(optimal_cutoffs)} cutoffs")
                else:
                    p.set(message="No optimal cutoffs found", value=max_search_points, detail="")
            else:
                # Binary labeler: single cutoff search
                p.set(message=f"Searching {len(data):,} rows...", detail="Starting search...")

                # Define progress callback to update the progress bar
                def update_progress(progress_pct: float, detail: str) -> None:
                    value = int(progress_pct * max_search_points)
                    p.set(value=value, detail=detail)

                # Perform search using utility function
                best_cutoff = search_for_cutoff(
                    data=data,
                    metric_col=metric_col,
                    exclude=current_exclusions,
                    max_search_points=max_search_points,
                    progress_callback=update_progress,
                    lower_is_better=lower_is_better
                )

                if best_cutoff is not None:
                    current_labeler.set(BinaryLabeler.with_cutoff(best_cutoff, lower_is_better))
                    p.set(message="Search complete!", value=max_search_points, detail=f"Best cutoff: {best_cutoff:.4f}")
                else:
                    p.set(message="No optimal cutoff found", value=max_search_points, detail="")


def handle_num_cutoffs_change_effect(
    input: Inputs,
    active_data: reactive.Calc,
    validated_metric: reactive.Calc,
    current_labeler: reactive.Value
) -> None:
    """
    Create a reactive effect to handle changes in num_cutoffs for Manual labeler.

    Args:
        input: Shiny inputs
        active_data: Reactive calc returning current dataframe
        validated_metric: Reactive calc returning validated metric column name
        current_labeler: Reactive value storing the current labeler
    """
    @reactive.effect
    @reactive.event(input.manual_num_cutoffs, ignore_none=True)
    def _handle_num_cutoffs_change() -> None:
        """Adjust number of cutoffs when user changes the select input."""
        # Use isolate to read both labeler and current input to avoid loops
        with reactive.isolate():
            labeler = current_labeler.get()
            try:
                new_num = int(input.manual_num_cutoffs())
            except (SilentException, ValueError, TypeError):
                return

        # Only handle for ManualLabeler
        if labeler is None or not isinstance(labeler, ManualLabeler):
            return

        # Check if the number actually changed
        if new_num == len(labeler.get_cutoffs()):
            return

        # Get data range for placing new cutoffs
        data = active_data()
        metric_col = validated_metric()
        if data is None or not metric_col or metric_col not in data.columns:
            return

        values = data[metric_col].drop_nulls().to_numpy()
        if len(values) < 2:
            return

        data_range = (float(np.min(values)), float(np.max(values)))

        # Update labeler with new number of cutoffs
        new_labeler = labeler.set_num_cutoffs(new_num, data_range)
        current_labeler.set(new_labeler)


def get_cutoff_display_info(labeler: PerformanceLabeler | None) -> tuple[str, bool]:
    """
    Get cutoff display string and control visibility from labeler.

    Args:
        labeler: Current performance labeler

    Returns:
        Tuple of (cutoff_display_string, show_cutoff_controls)
    """
    if labeler is not None:
        cutoffs = labeler.get_cutoffs()
        cutoff_display = ", ".join(f"{c:.4g}" for c in cutoffs) if cutoffs else "N/A (quantile-based)"
        show_cutoff_controls = hasattr(labeler, 'is_mutable') and labeler.is_mutable
        return cutoff_display, show_cutoff_controls
    else:
        return "Initializing...", False


def render_cutoff_controls(
    input: Inputs,
    strategy: str,
    cutoff_display: str,
    show_cutoff_controls: bool,
    excluded_names: list[str] | None = None,
    labeler: PerformanceLabeler | None = None
) -> list[ui.TagChild]:
    """
    Render complete analysis controls including strategy selector and cutoff controls.

    Args:
        input: Shiny inputs object
        strategy: Current classification strategy
        cutoff_display: Formatted string showing current cutoffs
        show_cutoff_controls: Whether to show cutoff adjustment controls
        excluded_names: List of names of excluded predictors (optional, for tooltip)
        labeler: Current labeler (optional, needed for Manual strategy)

    Returns:
        List of UI elements for the entire control panel
    """
    # Determine if we're in manual mode
    is_manual = strategy == "manual"

    # Get current num_cutoffs for manual labeler
    current_num_cutoffs = 1
    if is_manual and isinstance(labeler, ManualLabeler):
        current_num_cutoffs = len(labeler.get_cutoffs())

    return [
        ui.tags.p(ui.tags.strong("Analysis Controls"), style="margin-bottom: 15px;"),
        ui.input_select(
            "classification_strategy",
            "Performance labeling strategy",
            choices={
                "binary": "Binary (FAST/SLOW)",
                "tertile": "Tertiles (3 groups)",
                "quartile": "Quartiles (4 groups)",
                "auto": "Auto (Hybrid Detection)",
                "manual": "Manual (Custom Groups)"
            },
            selected=strategy
        ),
        # Row with select dropdown aligned horizontally next to label
        ui.div(
            ui.tags.span("# Cutoffs:", style="margin-right: 8px; font-size: 0.9em; line-height: 2.2;"),
            ui.input_select(
                "manual_num_cutoffs",
                None,
                choices={str(i): str(i) for i in range(1, 10)},
                selected=str(current_num_cutoffs),
                width="60px"
            ),
            style=f"margin-top: 10px; display: {'flex' if is_manual else 'none'}; align-items: center;"
        ),
        ui.tags.p(
            "Click near cutoff to move it",
            style=f"font-size: 0.9em; margin-top: 5px; margin-bottom: 5px; {'display: none;' if not show_cutoff_controls else ''}"
        ),
        ui.div(
            ui.input_action_button(
                "search_cutoff_btn",
                "Search for Cutoff" if not is_manual else "Find Cutoffs",
                class_="btn-secondary btn-sm",
                icon=ui.tags.span(ui.tags.i(class_="bi bi-search"), "\u00A0"),
                width="100%"
            ),
            style=f"margin-top: 5px; {'display: none;' if not show_cutoff_controls else ''}"
        ),
        ui.tags.hr(style="margin: 15px 0;"),
        ui.input_action_button(
            "exclude_predictors_btn",
            "Exclude Predictors",
            class_="btn-secondary btn-sm",
            icon=ui.tags.span(ui.tags.i(class_="bi bi-table"), "\u00A0")
        ),
        ui.tags.p(
            ui.tags.span(
                f"Excluded: {len(excluded_names) if excluded_names else 0} predictors",
                title=(
                    "Excluded predictors:\n" + "\n".join(excluded_names)
                    if excluded_names and len(excluded_names) > 0
                    else "No predictors excluded"
                ),
                style="cursor: help; border-bottom: 1px dotted #999;"
            ),
            style="color: #666; font-size: 0.85em; margin-top: 10px;"
        ),
    ]
