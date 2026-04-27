"""
Metric selection and predictor statistics utilities.

Functions for selecting default metrics, computing predictor statistics
and correlations, and managing predictor exclusion for decision tree training.

This module provides GUI-specific UI components for predictor management.
Core computation is delegated to src.core.profile.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any
import json
import re
import numpy as np
import polars as pl
from shiny import ui, render, reactive, Inputs, Outputs

from src.core.config.settings import Settings

# Re-export from core for backward compatibility
from .predictor_stats import (
    DEFAULT_EXCLUDED_PREDICTORS,
    compute_predictor_stats,
    filter_predictors_by_correlation as _filter_predictors_for_display,
    get_auto_excluded_predictors as _collect_auto_excluded_predictors,
)

__all__ = [
    "DEFAULT_EXCLUDED_PREDICTORS",
    "compute_predictor_stats",
    "order_exclusions_with_defaults",
    "create_predictor_exclusion_ui",
    "build_predictor_exclusion_modal",
    "reset_exclusions",
    "apply_exclusions",
]


def _sanitize_for_html_id(name: str) -> str:
    """
    Sanitize column name to be a valid HTML element ID.

    Converts any column name to a valid C identifier by replacing
    non-alphanumeric characters with underscores.

    Args:
        name: Original column/predictor name

    Returns:
        Sanitized name safe for use as HTML element ID
    """
    # Replace any non-alphanumeric characters with underscore
    # This allows any CSV column name to be used as a valid HTML ID
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    # Ensure it doesn't start with a digit (HTML5 requirement)
    if sanitized and sanitized[0].isdigit():
        sanitized = '_' + sanitized
    return sanitized


def order_exclusions_with_defaults(excluded: list[str]) -> list[str]:
    """Return exclusions with defaults first, then remaining sorted.

    Ensures the default excluded predictors stay visible at the top of any
    ordered list (e.g., tooltips) even when many predictors are excluded.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for name in DEFAULT_EXCLUDED_PREDICTORS:
        if name in excluded and name not in seen:
            ordered.append(name)
            seen.add(name)
    for name in sorted(excluded):
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered


def _filter_modal_predictors(stats: list[dict[str, Any]], max_preds: int, search: str) -> list[dict[str, Any]]:
    """
    Filter and sort predictors for modal display.

    Filters by search term, sorts by absolute correlation (descending), and limits by max_preds.
    Does NOT filter by correlation threshold to allow users to find and uncheck any predictor.

    Args:
        stats: List of predictor statistics
        max_preds: Maximum number of predictors to display
        search: Search term to filter by predictor name

    Returns:
        Filtered and sorted list of predictor stats
    """
    result = stats
    if search:
        search_lower = search.lower()
        result = [s for s in result if search_lower in s["name"].lower()]

    # Sort by absolute correlation (descending)
    result = sorted(result, key=lambda s: abs(s.get("correlation", 0)), reverse=True)

    # Apply limit, but ensure default excluded predictors are always included
    # (unless filtered out by search criteria)
    limited = result[:max_preds]
    limited_names = {s["name"] for s in limited}

    # Find active default exclusions that would be hidden by the limit
    defaults_to_add = []
    for s in result[max_preds:]:
        if s["name"] in DEFAULT_EXCLUDED_PREDICTORS:
            defaults_to_add.append(s)

    if defaults_to_add:
        limited.extend(defaults_to_add)
        # Re-sort to ensure added items are placed correctly by correlation
        limited = sorted(limited, key=lambda s: abs(s.get("correlation", 0)), reverse=True)

    return limited


# ============================================================================
# Predictor Exclusion UI Helpers
# ============================================================================


def _build_predictor_table_rows(
    filtered_rows: list[dict[str, Any]],
    exclusions: set[str],
) -> list[ui.TagChild]:
    """
    Build HTML table rows for the predictor exclusion modal.

    Args:
        filtered_rows: Filtered list of predictor statistics
        exclusions: Set of predictor names that should be checked (excluded)

    Returns:
        List of Shiny UI table row elements
    """
    table_rows: list[ui.TagChild] = []
    for row in filtered_rows:
        pred_name = row["name"]
        checkbox_id = f"exclude_{_sanitize_for_html_id(pred_name)}"
        correlation = row.get("correlation")
        is_checked = pred_name in exclusions

        table_rows.append(
            ui.tags.tr(
                ui.tags.td(pred_name),
                ui.tags.td(f'{row.get("non_na_count", 0):,}'),
                ui.tags.td(f'{correlation:.2f}' if correlation is not None and not np.isnan(correlation) else "N/A"),
                ui.tags.td(ui.input_checkbox(checkbox_id, None, value=is_checked)),
            )
        )
    return table_rows


def _generate_select_all_script(checkbox_ids: list[str]) -> str:
    """
    Generate JavaScript for Select/Deselect All functionality.

    Args:
        checkbox_ids: List of checkbox IDs to control

    Returns:
        HTML script tag with JavaScript code
    """
    return f"""
    <script>
        $(document).ready(function() {{
            var all_ids = {json.dumps(checkbox_ids)};
            $('#exclude_all_predictors').off('change').on('change', function() {{
                var is_checked = $(this).is(':checked');
                all_ids.forEach(function(id) {{
                    $('#' + id).prop('checked', is_checked).trigger('change');
                }});
            }});
        }});
    </script>
    """


def create_predictor_exclusion_ui(
    input: Inputs,
    output: Outputs,
    excluded_predictors: reactive.Value[list[str]],
    predictor_stats_full: reactive.Value[list[dict[str, Any]]],
    predictor_modal_filters: reactive.Value[dict[str, Any]]
) -> None:
    """
    Create the predictor table UI render function.

    Architecture:
    - On modal open: checkbox_state is copied from excluded_predictors
    - When threshold slider differs from saved max_corr: use auto-exclusions
    - Otherwise: use checkbox_state
    - User toggles are preserved by Shiny (no re-render on checkbox click)
    - On Apply: read checkboxes, save to excluded_predictors

    Key constraint: Never read excluded_predictors() during render.
    """

    @output
    @render.ui
    def predictor_table_ui() -> ui.TagChild:
        """Render the predictor table."""
        stats_rows = predictor_stats_full.get()

        if not stats_rows:
            return ui.div(
                ui.p("Loading predictor statistics...", style="text-align: center; padding: 20px; color: #666;"),
                ui.tags.div(
                    ui.tags.div(class_="spinner-border text-primary", role="status"),
                    style="text-align: center; padding: 20px;"
                )
            )

        # Get current slider/input values
        max_corr = input.predictor_max_corr() if hasattr(input, 'predictor_max_corr') else 0.99
        max_preds = input.predictor_max_preds() if hasattr(input, 'predictor_max_preds') else 100
        search = input.predictor_search() if hasattr(input, 'predictor_search') else ""

        # Read saved modal state (creates reactive dependency for re-render on modal open)
        filters = predictor_modal_filters.get()
        saved_max_corr = filters.get("max_corr") if filters else None
        checkbox_state = filters.get("checkbox_state") if filters else None

        # Filter predictors for display
        filtered_rows = _filter_modal_predictors(stats_rows, max_preds, search)
        if not filtered_rows:
            return ui.p("No predictors match the current filter criteria.")

        # Determine checkbox values:
        # - Slider moved (differs from saved) → use auto-exclusions
        # - Otherwise → use checkbox_state from modal open
        if max_corr != saved_max_corr or checkbox_state is None:
            exclusions = set(_collect_auto_excluded_predictors(stats_rows, max_corr))
        else:
            exclusions = set(checkbox_state)

        # Build table
        table_header = ui.tags.thead(
            ui.tags.tr(
                ui.tags.th("Predictor"),
                ui.tags.th("Non-NA Count"),
                ui.tags.th("Correlation"),
                ui.tags.th("Exclude", ui.input_checkbox("exclude_all_predictors", "All", value=False)),
            )
        )

        table_rows = _build_predictor_table_rows(filtered_rows, exclusions)
        all_checkbox_ids = [f"exclude_{_sanitize_for_html_id(row['name'])}" for row in filtered_rows]
        js_script = _generate_select_all_script(all_checkbox_ids)

        return ui.div(
            ui.tags.div(
                ui.tags.table(table_header, ui.tags.tbody(*table_rows), class_="table table-sm table-striped"),
                style="max-height: 400px; overflow-y: auto;",
                id="predictor_table_container"
            ),
            ui.HTML(js_script)
        )


def build_predictor_exclusion_modal(
    data: pl.DataFrame,
    metric_col: str,
    predictor_stats_full: reactive.Value[list[dict[str, Any]]],
    predictor_modal_filters: reactive.Value[dict[str, Any]],
    excluded_predictors: reactive.Value[list[str]]
) -> None:
    """
    Build and show the predictor exclusion modal.

    Args:
        data: Polars DataFrame containing the data
        metric_col: Name of the outcome metric column
        predictor_stats_full: Reactive value to store predictor stats
        predictor_modal_filters: Reactive value storing filter state
        excluded_predictors: Reactive value storing excluded predictor names
    """
    if data is None or data.is_empty() or not metric_col:
        return

    # Restore previous filter values or use defaults
    filters = predictor_modal_filters.get()
    max_corr = filters.get("max_corr", Settings().get("profiling.max_correlation", 0.99)) if filters else Settings().get("profiling.max_correlation", 0.99)
    max_preds = filters.get("max_predictors", Settings().get("profiling.max_predictors", 100)) if filters else Settings().get("profiling.max_predictors", 100)
    search_term = filters.get("search_term", "") if filters else ""

    # Initialize modal state: copy excluded_predictors to checkbox_state
    # Setting max_corr here means slider == saved, so render uses checkbox_state
    predictor_modal_filters.set({
        "max_corr": max_corr,
        "max_predictors": max_preds,
        "search_term": search_term,
        "checkbox_state": list(excluded_predictors.get()),
        "user_has_applied": filters.get("user_has_applied", False) if filters else False,
    })

    ui.modal_show(
        ui.modal(
            ui.div(
                ui.row(
                    ui.column(4, ui.input_slider("predictor_max_corr", "Max Correlation:", min=0, max=1, value=max_corr, step=0.01)),
                    ui.column(4, ui.input_numeric("predictor_max_preds", "Max Predictors:", value=max_preds, min=1, max=1000)),
                    ui.column(4, ui.input_text("predictor_search", "Search:", value=search_term)),
                ),
                ui.hr(),
                ui.output_ui("predictor_table_ui"),
            ),
            title="Exclude Predictors",
            size="l",
            easy_close=True,
            footer=ui.div(
                ui.modal_button("Cancel", class_="btn-secondary"),
                ui.input_action_button("reset_predictor_exclusions", "Reset", class_="btn-outline-secondary"),
                ui.input_action_button("apply_predictor_exclusions", "Apply", class_="btn-primary"),
            ),
        )
    )


def _collect_manually_excluded_predictors(input: Inputs, filtered_stats: list[dict[str, Any]]) -> set[str]:
    """
    Collect predictors that are manually checked for exclusion.

    Args:
        input: Shiny inputs object
        filtered_stats: List of predictor stats shown in the modal

    Returns:
        Set of predictor names that are checked
    """
    manually_excluded = set()
    for stat in filtered_stats:
        pred_name = stat["name"]
        checkbox_id = f"exclude_{_sanitize_for_html_id(pred_name)}"
        try:
            if getattr(input, checkbox_id, lambda: False)():
                manually_excluded.add(pred_name)
        except Exception:
            pass
    return manually_excluded


def reset_exclusions(
    excluded_predictors: reactive.Value[list[str]],
    predictor_stats_full: reactive.Value[list[dict[str, Any]]],
    predictor_modal_filters: reactive.Value[dict[str, Any]]
) -> None:
    """
    Reset exclusions and threshold to defaults (same as reload).

    Resets to: DEFAULT_EXCLUDED_PREDICTORS + auto-exclusions at default threshold.

    Args:
        excluded_predictors: Reactive value storing list of excluded predictor names
        predictor_stats_full: Reactive value storing full predictor statistics
        predictor_modal_filters: Reactive value storing filter state
    """
    default_max_corr = Settings().get("profiling.max_correlation", 0.99)
    default_max_preds = Settings().get("profiling.max_predictors", 100)

    # Compute default exclusions: always include the 4 defaults + auto-excluded
    stats = predictor_stats_full.get()
    new_exclusions = set(DEFAULT_EXCLUDED_PREDICTORS)
    if stats:
        new_exclusions.update(_collect_auto_excluded_predictors(stats, default_max_corr))
    new_exclusions_list = sorted(new_exclusions)

    # Reset modal state and clear user_has_applied flag
    # checkbox_state=new_exclusions_list so render shows correct checkboxes
    predictor_modal_filters.set({
        "max_corr": default_max_corr,
        "max_predictors": default_max_preds,
        "search_term": "",
        "checkbox_state": new_exclusions_list,
        "user_has_applied": False,
    })

    excluded_predictors.set(new_exclusions_list)


def apply_exclusions(
    input: Inputs,
    excluded_predictors: reactive.Value[list[str]],
    predictor_stats_full: reactive.Value[list[dict[str, Any]]],
    predictor_modal_filters: reactive.Value[dict[str, Any]]
) -> None:
    """
    Apply predictor exclusions when Apply button is clicked.

    Reads checkbox states from the modal and saves to excluded_predictors.

    Args:
        input: Shiny inputs object
        excluded_predictors: Reactive value storing list of excluded predictor names
        predictor_stats_full: Reactive value storing full predictor statistics
        predictor_modal_filters: Reactive value storing filter state
    """
    all_stats = predictor_stats_full.get()
    if not all_stats:
        ui.modal_remove()
        return

    # Get current filter values
    max_corr = input.predictor_max_corr()
    max_preds = input.predictor_max_preds()
    search = input.predictor_search() if hasattr(input, 'predictor_search') else ""

    # Get visible predictors and read their checkbox states
    filtered_stats = _filter_modal_predictors(all_stats, max_preds, search)
    visible_names = {stat["name"] for stat in filtered_stats}
    visible_checked = _collect_manually_excluded_predictors(input, filtered_stats)

    # Preserve exclusions for predictors not shown in the current view.
    # Only change exclusions for predictors that are visible in the modal.
    # If the threshold slider changed, use fresh auto-exclusions as the base.
    saved_filters = predictor_modal_filters.get()
    saved_threshold = saved_filters.get("max_corr") if saved_filters else None

    if saved_threshold is not None and abs(float(max_corr) - float(saved_threshold)) < 1e-9:
        base_exclusions = set(excluded_predictors.get())
    else:
        base_exclusions = set(_collect_auto_excluded_predictors(all_stats, max_corr))

    # Apply visible checkbox changes: checked => excluded, unchecked => included
    visible_current = base_exclusions & visible_names
    new_exclusions = base_exclusions | visible_checked
    new_exclusions -= (visible_current - visible_checked)

    # Final result
    new_exclusions_list = sorted(new_exclusions)

    # Save filter state and mark that user has applied (prevents auto-overwrite)
    predictor_modal_filters.set({
        "max_corr": max_corr,
        "max_predictors": max_preds,
        "search_term": search,
        "checkbox_state": None,  # Will be set from excluded_predictors on next modal open
        "user_has_applied": True,
    })

    excluded_predictors.set(new_exclusions_list)
    ui.modal_remove()

