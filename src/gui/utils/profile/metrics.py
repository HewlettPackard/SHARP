"""
Metric selection and predictor statistics utilities.

Functions for selecting default metrics, computing predictor statistics
and correlations, and managing predictor exclusion for decision tree training.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Optional, List, Dict
import json
import numpy as np
import polars as pl
from shiny import ui, render, reactive, Inputs, Outputs

from src.core.stats.correlations import compute_generalized_correlation
from src.core.config.settings import Settings


# Default predictors to exclude from tree training
DEFAULT_EXCLUDED_PREDICTORS = ["repeat", "inner_time", "outer_time", "perf_time"]


def get_numeric_columns(data: pl.DataFrame) -> list[str]:
    """
    Get list of numeric columns from a DataFrame.

    Args:
        data: Polars DataFrame

    Returns:
        List of column names with numeric types (Float64, Int64)
    """
    if data is None or data.is_empty():
        return []

    try:
        numeric_cols = data.select(pl.col(pl.Float64, pl.Int64)).columns
        return list(numeric_cols)
    except Exception:
        return []


def select_default_metric(
    data: pl.DataFrame,
    preferred_metrics: Optional[list[str]] = None
) -> str:
    """
    Select default outcome metric with preference order.

    Args:
        data: Polars dataframe with numeric columns
        preferred_metrics: List of metrics to prefer, in order

    Returns:
        Selected metric name, or empty string if none of preferred metrics found
    """
    if preferred_metrics is None:
        preferred_metrics = ["perf_time", "inner_time", "outer_time"]

    # Get all numeric columns
    numeric_cols = data.select(pl.col(pl.Float64, pl.Int64)).columns

    if not numeric_cols:
        return ""

    # Check preferred metrics in order
    for pref in preferred_metrics:
        if pref in numeric_cols:
            return pref

    # Return empty string if no preferred metrics found (user must select)
    return ""


# ============================================================================
# Predictor Statistics and Exclusion
# ============================================================================

def compute_predictor_stats(data, metric_col: str, predictor_list: list = None) -> List[Dict]:
    """
    Compute statistics for potential predictors.

    Uses row sampling (1000 rows) for correlation computation to match R version performance.

    Args:
        data: Polars DataFrame containing the data
        metric_col: Name of the outcome metric column
        predictor_list: Optional list of predictor names. If None, uses all columns.

    Returns:
        List of dicts with keys: name, non_na_count, correlation
    """
    # Get columns to compute stats for
    if predictor_list is not None:
        potential_predictors = predictor_list
    else:
        # Get all columns that could be predictors
        potential_predictors = [
            c for c in data.columns
            if c not in [metric_col, "start", "task"] and data[c].n_unique() > 1
        ]

    # Sample rows for faster correlation (like R version uses 1000 rows)
    sample_size = 1000
    if len(data) > sample_size:
        np.random.seed(42)
        sample_indices = np.random.choice(len(data), sample_size, replace=False)
        sampled_data = data[sorted(sample_indices)]
    else:
        sampled_data = data

    stats_rows = []
    y_series = sampled_data[metric_col].to_numpy()

    for pred in potential_predictors:
        try:
            x_series = sampled_data[pred].to_numpy()
            correlation = compute_generalized_correlation(x_series, y_series)
            non_na_count = data[pred].drop_nulls().len()  # Use full data for count
            stats = {
                "name": pred,
                "non_na_count": non_na_count,
                "correlation": correlation,
            }
            stats_rows.append(stats)
        except Exception:
            pass  # Skip predictors that fail correlation computation

    return stats_rows


# ============================================================================
# Predictor Exclusion UI Helpers
# ============================================================================

def _filter_predictors_for_display(stats_rows: List[Dict], max_corr: float,
                                   max_preds: int, search: str) -> List[Dict]:
    """
    Filter and sort predictor stats for display in the exclusion modal.

    Args:
        stats_rows: List of predictor statistics dictionaries
        max_corr: Maximum correlation threshold
        max_preds: Maximum number of predictors to display
        search: Search term to filter predictor names

    Returns:
        Filtered and sorted list of predictor stats
    """
    # Make a copy for filtering
    filtered = list(stats_rows)

    # Sort by absolute correlation, descending, with NAs last
    filtered.sort(
        key=lambda r: abs(r["correlation"]) if r["correlation"] is not None and not np.isnan(r["correlation"]) else -1,
        reverse=True
    )

    # Apply search filter
    if search:
        search_lower = search.lower()
        filtered = [r for r in filtered if search_lower in r["name"].lower()]

    # Apply max_correlation filter: exclude predictors with |corr| >= max_corr
    # These will be auto-excluded, so we filter them out of the table entirely
    filtered = [
        r for r in filtered
        if r.get("correlation") is None or np.isnan(r.get("correlation")) or abs(r.get("correlation")) < max_corr
    ]

    # Limit number of predictors shown (after correlation filtering)
    if len(filtered) > max_preds:
        filtered = filtered[:max_preds]

    return filtered


def _build_predictor_table_rows(filtered_rows: List[Dict],
                                current_exclusions: List[str]) -> List:
    """
    Build HTML table rows for the predictor exclusion modal.

    Args:
        filtered_rows: Filtered list of predictor statistics
        current_exclusions: List of currently excluded predictor names

    Returns:
        List of Shiny UI table row elements
    """
    table_rows = []
    for row in filtered_rows:
        pred_name = row["name"]
        checkbox_id = f"exclude_{pred_name}"
        correlation = row.get("correlation")

        # Check if predictor is in current exclusions
        is_checked = pred_name in current_exclusions

        table_rows.append(
            ui.tags.tr(
                ui.tags.td(pred_name),
                ui.tags.td(f'{row.get("non_na_count", 0):,}'),
                ui.tags.td(f'{correlation:.2f}' if correlation is not None and not np.isnan(correlation) else "N/A"),
                ui.tags.td(ui.input_checkbox(checkbox_id, None, value=is_checked)),
            )
        )
    return table_rows


def _generate_select_all_script(checkbox_ids: List[str]) -> str:
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
    excluded_predictors: reactive.Value,
    predictor_stats_full: reactive.Value,
    predictor_modal_filters: reactive.Value
) -> None:
    """
    Create the predictor table UI render function.

    Args:
        input: Shiny inputs object
        output: Shiny outputs object
        excluded_predictors: Reactive value storing list of excluded predictor names
        predictor_stats_full: Reactive value storing full predictor statistics
        predictor_modal_filters: Reactive value storing filter state
    """
    @output
    @render.ui
    def predictor_table_ui():
        """Dynamically render the predictor table based on current filter inputs."""
        stats_rows = predictor_stats_full.get()

        if not stats_rows:
            return ui.div(
                ui.p("Loading predictor statistics...", style="text-align: center; padding: 20px; color: #666;"),
                ui.tags.div(
                    ui.tags.div(class_="spinner-border text-primary", role="status"),
                    style="text-align: center; padding: 20px;"
                )
            )

        # Get current filter values from inputs
        max_corr = input.predictor_max_corr() if hasattr(input, 'predictor_max_corr') else 0.99
        max_preds = input.predictor_max_preds() if hasattr(input, 'predictor_max_preds') else 100
        search = input.predictor_search() if hasattr(input, 'predictor_search') else ""

        # Filter predictors for display
        filtered_rows = _filter_predictors_for_display(stats_rows, max_corr, max_preds, search)

        if not filtered_rows:
            return ui.p("No predictors match the current filter criteria.")

        # Build table header
        table_header = ui.tags.thead(
            ui.tags.tr(
                ui.tags.th("Predictor"),
                ui.tags.th("Non-NA Count"),
                ui.tags.th("Correlation"),
                ui.tags.th(
                    "Exclude",
                    ui.input_checkbox("exclude_all_predictors", "All", value=False),
                ),
            )
        )

        # Build table rows
        current_exclusions = excluded_predictors()
        table_rows = _build_predictor_table_rows(filtered_rows, current_exclusions)

        # Generate JavaScript for Select All
        all_checkbox_ids = [f"exclude_{row['name']}" for row in filtered_rows]
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
    data,
    metric_col: str,
    predictor_stats_full: reactive.Value,
    predictor_modal_filters: reactive.Value,
    predictor_stats_calc = None
) -> None:
    """
    Build and show the predictor exclusion modal.

    Args:
        data: Polars DataFrame containing the data
        metric_col: Name of the outcome metric column
        predictor_stats_full: Reactive value to store predictor stats
        predictor_modal_filters: Reactive value storing filter state
        predictor_stats_calc: Not used - stats should already be in predictor_stats_full
    """
    if data is None or data.is_empty() or not metric_col:
        return

    # Restore previous filter values or use defaults from settings
    filters = predictor_modal_filters.get()
    max_corr = filters.get("max_corr", Settings().get("profiling.max_correlation", 0.99))
    max_preds = filters.get("max_predictors", Settings().get("profiling.max_predictors", 100))
    search_term = filters.get("search_term", "")

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
                ui.input_action_button("apply_predictor_exclusions", "Apply", class_="btn-primary"),
            ),
        )
    )


def _collect_auto_excluded_predictors(all_stats: List[Dict], max_corr: float) -> set:
    """
    Collect predictors that should be auto-excluded based on correlation threshold.

    Args:
        all_stats: List of all predictor statistics
        max_corr: Maximum correlation threshold

    Returns:
        Set of predictor names to auto-exclude
    """
    auto_excluded = set()
    for stat in all_stats:
        correlation = stat.get("correlation")
        if correlation is not None and not np.isnan(correlation) and abs(correlation) >= max_corr:
            auto_excluded.add(stat["name"])
    return auto_excluded


def _collect_manually_excluded_predictors(input: Inputs, filtered_stats: List[Dict]) -> set:
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
        checkbox_id = f"exclude_{pred_name}"

        try:
            is_checked = getattr(input, checkbox_id, lambda: False)()
            if is_checked:
                manually_excluded.add(pred_name)
        except Exception:
            pass  # Checkbox not found or not accessible

    return manually_excluded


def apply_exclusions(
    input: Inputs,
    excluded_predictors: reactive.Value,
    predictor_stats_full: reactive.Value,
    predictor_modal_filters: reactive.Value
) -> None:
    """
    Apply predictor exclusions when Apply button is clicked.

    Args:
        input: Shiny inputs object
        excluded_predictors: Reactive value storing list of excluded predictor names
        predictor_stats_full: Reactive value storing full predictor statistics
        predictor_modal_filters: Reactive value storing filter state
    """
    # Save the current filter values for the next time the modal is opened
    predictor_modal_filters.set({
        "max_corr": input.predictor_max_corr(),
        "max_predictors": input.predictor_max_preds(),
        "search_term": input.predictor_search(),
    })

    # Get the full list of predictors that were calculated when the modal opened
    all_stats = predictor_stats_full.get()
    if not all_stats:
        ui.modal_remove()
        return

    # Start with default exclusions
    new_exclusions = set(DEFAULT_EXCLUDED_PREDICTORS)

    # Auto-exclude all predictors with |correlation| >= max_corr
    max_corr = input.predictor_max_corr()
    auto_excluded = _collect_auto_excluded_predictors(all_stats, max_corr)
    new_exclusions.update(auto_excluded)

    # Get the filtered predictors shown in the modal (same filtering logic as UI)
    max_preds = input.predictor_max_preds()
    search = input.predictor_search() if hasattr(input, 'predictor_search') else ""
    filtered_stats = _filter_predictors_for_display(all_stats, max_corr, max_preds, search)

    # Collect manually checked predictors
    manually_excluded = _collect_manually_excluded_predictors(input, filtered_stats)
    new_exclusions.update(manually_excluded)

    excluded_predictors.set(sorted(list(new_exclusions)))
    ui.modal_remove()

