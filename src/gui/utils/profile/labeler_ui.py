"""
Labeler state management for profile tab.

Handles initialization, updates, and interactions with performance labelers.

© Copyright 2025--2026 Hewlett Packard Enterprise Development LP
"""
from typing import Any

from shiny import reactive, Inputs, ui
from shiny.types import SilentException
import numpy as np

from src.core.profile.labeler import (
    PerformanceLabeler,
    BinaryLabeler,
    CutoffBasedLabeler,
    TertileLabeler,
    QuartileLabeler,
    AutoLabeler,
    ManualLabeler,
    RegressionLabeler,
)
from src.gui.utils.profile.tree import search_for_cutoff
from src.gui.utils.profile.distribution import update_labeler_from_click
from src.core.config.settings import Settings


def initialize_labeler_effect(
    input: Inputs,
    active_data: Any,
    validated_metric: Any,
    lower_is_better_setting: Any,
    current_labeler: Any
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
    @reactive.effect
    def _initialize_labeler() -> None:
        """Initialize labeler when data/metric/lower_is_better/perf_auto_detect changes.

        num_perf_groups is read via isolate so it does NOT trigger this effect;
        group-count changes are handled exclusively by handle_num_cutoffs_change_effect.
        """
        data = active_data()
        metric_col = validated_metric()

        if data is None or not metric_col or metric_col not in data.columns:
            current_labeler.set(None)
            return

        values = data[metric_col].drop_nulls().to_numpy()
        if len(values) < 2:
            current_labeler.set(None)
            return

        lower_is_better = lower_is_better_setting.get()

        try:
            is_auto = bool(input.perf_auto_detect())
        except SilentException:
            is_auto = False

        # Read num_groups without registering a reactive dependency — group-count
        # transitions are handled by handle_num_cutoffs_change_effect.
        with reactive.isolate():
            try:
                num_groups = int(input.num_perf_groups() or "2")
            except (SilentException, ValueError, TypeError):
                num_groups = 2
            num_groups = max(1, min(10, num_groups))

        try:
            labeler: PerformanceLabeler
            if is_auto:
                with ui.Progress(min=0, max=1) as p:
                    p.set(message="Analyzing distribution...",
                          detail="Running changepoint detection and clustering")
                    labeler = AutoLabeler(values, lower_is_better)
            elif num_groups <= 1:
                labeler = RegressionLabeler(values, lower_is_better)
            elif num_groups == 2:
                labeler = BinaryLabeler(values, lower_is_better)
            else:
                labeler = ManualLabeler(values, lower_is_better, num_groups - 1)
            current_labeler.set(labeler)
        except Exception:
            current_labeler.set(None)



def handle_plot_click_effect(
    input: Inputs,
    current_labeler: Any,
    lower_is_better_setting: Any
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
    active_data: Any,
    validated_metric: Any,
    excluded_predictors: Any,
    current_labeler: Any,
    lower_is_better_setting: Any,
    settings: Any | None = None,
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
        settings: Settings instance or callable returning settings (optional)
    """
    from shiny import ui

    resolved_settings = settings

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
        runtime_settings = resolved_settings
        if runtime_settings is None:
            runtime_settings = Settings()
        elif callable(runtime_settings):
            runtime_settings = runtime_settings()
        max_search_points = runtime_settings.get("profiling.max_search", 100)

        # Get excluded predictors
        current_exclusions = excluded_predictors()

        # Get lower_is_better setting
        lower_is_better = lower_is_better_setting.get()

        # Check if this is a ManualLabeler
        is_manual = isinstance(labeler, ManualLabeler)

        # Show progress bar
        with ui.Progress(min=0, max=max_search_points) as p:
            if is_manual:
                # Manual labeler: keep cutoff count fixed, optimize cutoff positions.
                target_num_cutoffs = len(labeler.get_cutoffs())
                p.set(
                    message=f"Searching optimal cutoffs...",
                    detail=f"Optimizing {target_num_cutoffs + 1} groups...",
                )

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
                    lower_is_better=lower_is_better,
                    fixed_num_cutoffs=target_num_cutoffs,
                )

                if optimal_cutoffs is not None and len(optimal_cutoffs) > 0:
                    new_labeler = ManualLabeler.with_cutoffs(optimal_cutoffs, lower_is_better)
                    current_labeler.set(new_labeler)
                    # The rendered panel re-derives num_groups_selected from the new labeler,
                    # so no separate ui.update_select call is needed.
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
    active_data: Any,
    validated_metric: Any,
    current_labeler: Any
) -> None:
    """
    Create a reactive effect to handle changes in the num_perf_groups dropdown.

    Handles all group-count transitions while preserving existing cutoff positions
    where possible (ManualLabeler → ManualLabeler with different count).

    Args:
        input: Shiny inputs
        active_data: Reactive calc returning current dataframe
        validated_metric: Reactive calc returning validated metric column name
        current_labeler: Reactive value storing the current labeler
    """
    @reactive.effect
    @reactive.event(input.num_perf_groups, ignore_none=True)
    def _handle_num_groups_change() -> None:
        """Adjust labeler when the user changes the number of performance groups."""
        with reactive.isolate():
            try:
                is_auto = bool(input.perf_auto_detect())
            except SilentException:
                is_auto = False

            if is_auto:
                return  # Auto mode: labeler is managed by initialize_labeler_effect

            try:
                num_groups = int(input.num_perf_groups() or "2")
            except (SilentException, ValueError, TypeError):
                return
            num_groups = max(1, min(10, num_groups))

            labeler = current_labeler.get()

        data = active_data()
        metric_col = validated_metric()
        if data is None or not metric_col or metric_col not in data.columns:
            return

        values = data[metric_col].drop_nulls().to_numpy()
        if len(values) < 2:
            return

        lower_is_better = (
            labeler.lower_is_better
            if labeler is not None and hasattr(labeler, "lower_is_better")
            else True
        )

        if num_groups <= 1:
            if not isinstance(labeler, RegressionLabeler):
                current_labeler.set(RegressionLabeler(values, lower_is_better))
            return

        num_cutoffs = num_groups - 1

        if isinstance(labeler, ManualLabeler):
            if len(labeler.get_cutoffs()) == num_cutoffs:
                return  # Already correct
            if num_cutoffs == 1:
                # Transition to binary: fresh auto-placed cutoff
                current_labeler.set(BinaryLabeler(values, lower_is_better))
            else:
                # Adjust cutoff count, preserving existing positions where possible
                data_range = (float(np.min(values)), float(np.max(values)))
                current_labeler.set(labeler.set_num_cutoffs(num_cutoffs, data_range))
            return

        if isinstance(labeler, BinaryLabeler):
            if num_cutoffs == 1:
                return  # Already correct
            # Grow to multi-group: fresh quantile-based ManualLabeler
            current_labeler.set(ManualLabeler(values, lower_is_better, num_cutoffs))
            return

        # Any other labeler type (Auto, Regression, legacy Tertile/Quartile): create fresh
        if num_cutoffs == 1:
            current_labeler.set(BinaryLabeler(values, lower_is_better))
        else:
            current_labeler.set(ManualLabeler(values, lower_is_better, num_cutoffs))


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
    labeler: PerformanceLabeler | None,
    excluded_names: list[str] | None = None,
) -> list[ui.TagChild]:
    """
    Render the Performance groups control row and associated action buttons.

    The UI shows a single row with an "Auto" checkbox and a "# groups" dropdown
    (1-10). The dropdown is disabled while Auto is checked. A Search button is
    always visible but grayed out when Auto or regression mode is active.

    Args:
        labeler: Current performance labeler (None if not yet initialized)
        excluded_names: Excluded predictor names for the tooltip badge

    Returns:
        List of UI elements for the control panel
    """
    # --- Derive UI state from the current labeler ---
    is_auto = isinstance(labeler, AutoLabeler)
    is_regression = isinstance(labeler, RegressionLabeler)
    is_mutable = (
        not is_auto
        and not is_regression
        and labeler is not None
        and isinstance(labeler, CutoffBasedLabeler)
        and labeler.is_mutable
    )
    search_disabled = is_auto or is_regression or labeler is None

    # Determine the selected value for the groups dropdown
    if is_auto or labeler is None:
        num_groups_selected = "2"  # sensible default when Auto is unchecked
    elif is_regression:
        num_groups_selected = "1"
    elif isinstance(labeler, BinaryLabeler):
        num_groups_selected = "2"
    elif (cutoffs := labeler.get_cutoffs()) is not None:
        num_groups_selected = str(len(cutoffs) + 1)
    else:
        num_groups_selected = "2"

    auto_tooltip = (
        "Auto: automatically detects performance groups using temporal phase "
        "detection, tail isolation (IQR), and body clustering (Jenks breaks). "
        "The number and positions of groups are determined by the data; "
        "manual adjustment is not available in this mode."
    )
    groups_tooltip = (
        "Number of performance groups:\n"
        "1 = regression (no splitting)\n"
        "2 = binary FAST/SLOW\n"
        "3–10 = equal-quantile groups, adjustable by clicking or Search"
    )

    if is_auto:
        search_title = "Search is not available in Auto mode."
    elif is_regression:
        search_title = "Search is not available in regression mode (1 group)."
    elif is_mutable:
        search_title = (
            "Search finds the optimal cutoff positions that minimize tree entropy. "
            "Clicking on the distribution plot moves the nearest cutoff manually."
        )
    else:
        search_title = ""

    btn_class = "btn-secondary btn-sm" + (" disabled" if search_disabled else "")

    number_input_style = (
        "width: 48px; font-size: 0.85em; height: 26px; text-align: center;"
        " padding: 1px 4px; display: inline-block;"
    )
    if is_auto:
        number_input_style += " opacity: 0.4;"

    stepper_control = ui.div(
        ui.tags.input(
            id="num_perf_groups",
            type="number",
            min="1",
            max="10",
            step="1",
            value=num_groups_selected,
            disabled=is_auto,
            class_="form-control form-control-sm",
            style=number_input_style,
            title=groups_tooltip,
        ),
        style="display: flex; align-items: center;",
    )

    return [
        ui.tags.p(ui.tags.strong("Performance groups"), style="margin-bottom: 4px;"),
        # Two-column row: col-6 Auto checkbox | col-6 dropdown
        ui.row(
            ui.column(
                6,
                ui.div(
                    ui.input_checkbox("perf_auto_detect", "Auto groups", value=is_auto),
                    title=auto_tooltip,
                ),
            ),
            ui.column(
                6,
                ui.div(
                    ui.tags.span(
                        "Fixed #",
                        style="font-size: 0.85em; margin-right: 4px; white-space: nowrap;",
                    ),
                    stepper_control,
                    title=groups_tooltip,
                    style="display: flex; align-items: center;",
                ),
                style="border-left: 1px solid #ddd; padding-left: 8px;",
            ),
            style="margin-bottom: 5px;",
        ),
        # Search button + click hint (always visible; search grayed for Auto/regression)
        ui.div(
            ui.input_action_button(
                "search_cutoff_btn",
                "Search for optimal tree",
                class_=btn_class,
                icon=ui.tags.i(class_="bi bi-search"),
            ),
            title=search_title,
            style="display: flex; align-items: center; margin-top: 2px;",
        ),
        # Predictors button + exclusion count badge
        ui.div(
            ui.input_action_button(
                "exclude_predictors_btn",
                "Predictors",
                class_="btn-secondary btn-sm",
                icon=ui.tags.i(class_="bi bi-table"),
            ),
            ui.tags.span(
                f"({len(excluded_names) if excluded_names else 0} excluded)",
                title=(
                    "Excluded predictors:\n" + "\n".join(excluded_names)
                    if excluded_names and len(excluded_names) > 0
                    else "No predictors excluded"
                ),
                style=(
                    "cursor: help; border-bottom: 1px dotted #999; "
                    "font-size: 0.8em; color: #666; margin-left: 6px;"
                ),
            ),
            title="Click here to determine which predictors are included or excluded from the factor analysis",
            style="display: flex; align-items: center; gap: 0; margin-top: 5px;",
        ),
    ]
