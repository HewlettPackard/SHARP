"""
Explore tab for Python Shiny GUI.

Interactive data exploration with file selection, filtering,
distribution visualization, and pairwise comparisons.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from shiny import ui, render, reactive, Inputs, Outputs, Session
import polars as pl
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

from src.core.runlogs import load_csv, get_experiments, get_tasks_for_experiment
from src.core.stats.distribution import compute_summary, characterize_distribution, create_distribution_plot
from src.core.config.settings import Settings


def explore_ui() -> ui.TagChild:
    """Create Explore tab UI."""
    return ui.nav_panel(
        "Explore",
        ui.row(
            ui.column(
                2,
                ui.input_select(
                    "explore_experiment",
                    "Experiment",
                    choices={"": "(select experiment)"},
                    selected=""
                )
            ),
            ui.column(
                2,
                ui.input_select(
                    "explore_task",
                    "Task",
                    choices={"": "(select task)"},
                    selected=""
                )
            ),
            ui.column(
                2,
                ui.input_selectize(
                    "explore_metric",
                    "Metric to visualize",
                    choices=[],
                    multiple=False,
                    options={
                        'placeholder': 'Type to search metrics...',
                        'loadThrottle': 300,
                        'searchField': ['value', 'label'],
                        'maxOptions': 100,
                    }
                )
            ),
            ui.column(
                2,
                ui.input_selectize(
                    "explore_compare_metrics",
                    "Metrics to compare",
                    choices=[],
                    selected=[],
                    multiple=True,
                    options={
                        'placeholder': 'Type to search metrics...',
                        'loadThrottle': 300,
                        'searchField': ['value', 'label'],
                        'maxOptions': 100,
                    }
                )
            ),
            ui.column(
                2,
                ui.input_selectize(
                    "explore_filter_metric",
                    "Metric to Filter",
                    choices=[],
                    multiple=False,
                    options={
                        'placeholder': 'Type to search or leave empty...',
                        'loadThrottle': 300,
                        'searchField': ['value', 'label'],
                        'maxOptions': 100,
                    }
                )
            ),
            ui.column(2, ui.output_ui("explore_filter_ui")),
            ui.column(2, ui.output_text("explore_load_status")),
        ),
        ui.hr(),
        ui.row(
            ui.column(
                7,
                ui.output_plot("explore_plot", click=True),
                ui.output_text("explore_characteristics")
            ),
            ui.column(
                5,
                ui.h4("Summary statistics"),
                ui.output_data_frame("explore_table")
            ),
        ),
        ui.hr(),
        ui.row(
            ui.h4("Pairwise comparisons"),
            ui.output_plot("explore_cor_plot"),
        ),
    )


def explore_server(input: Inputs, output: Outputs, session: Session):
    """Server logic for Explore tab."""
    # Reactive values for data storage
    raw_data = reactive.value(None)
    filtered_data = reactive.value(None)
    data_loading = reactive.value(False)
    preload_data = reactive.value(None)  # Stores preload config from other tabs

    # Handle preload data received via custom message from other tabs
    @reactive.effect
    @reactive.event(input.explore_preload_config)
    def _receive_preload_config():
        """Receive and process explore preload configuration."""
        try:
            import json
            if config_json := input.explore_preload_config():
                config = json.loads(config_json)
                # Store preload in reactive value to trigger downstream effect
                preload_data.set(config)
        except Exception as e:
            print(f"Error receiving explore preload config: {e}")
            import traceback
            traceback.print_exc()

    # Initialize experiment dropdown on startup (default from settings)
    @reactive.effect
    def _init_experiments():
        experiments = get_experiments()
        # Add empty option at the beginning to allow no selection
        choices = {"" : "(select experiment)"} | experiments
        default_exp = Settings().get("gui.default_experiment", "misc")
        default = default_exp if default_exp in experiments else ""
        ui.update_select("explore_experiment", choices=choices, selected=default)

    # Apply preload when preload data is set
    @reactive.effect
    def _apply_preload():
        """Apply preload data to dropdowns and load CSV."""
        preload = preload_data.get()
        if preload:
            # Clear immediately to allow repeated preloads
            preload_data.set(None)

            # Set pending task before changing experiment
            # This way when _update_tasks() runs, it will apply this selection
            if "csv_path" in preload and preload["csv_path"]:
                session.pending_task_selection = preload["csv_path"]

            # Update experiment - this will trigger _update_tasks()
            # First reset to empty to ensure the event fires even if experiment doesn't change
            if "experiment" in preload:
                ui.update_select("explore_experiment", selected="")
                ui.update_select("explore_experiment", selected=preload["experiment"])

    # Update task dropdown when experiment changes
    @reactive.effect
    @reactive.event(input.explore_experiment)
    def _update_tasks():
        if not (experiment := input.explore_experiment()):
            # Reset task dropdown when no experiment selected
            ui.update_select("explore_task", choices={"": "(select task)"}, selected="")
            return

        # Get tasks for this experiment
        tasks = get_tasks_for_experiment(experiment)
        choices = {"": "(select task)"} | tasks

        # Determine which task to select
        selected_task = ""
        if hasattr(session, 'pending_task_selection') and session.pending_task_selection:
            # Use pending task from preload if available
            task_path = session.pending_task_selection
            session.pending_task_selection = None  # Clear after using
            if task_path in tasks:
                selected_task = task_path

        # Always reset and update to ensure selection is cleared and refreshed
        # This prevents old selections from persisting when experiment changes
        ui.update_select("explore_task", choices=choices, selected=selected_task)

    # Load CSV when task is selected
    @reactive.effect
    @reactive.event(input.explore_task)
    def _():
        if not (csv_path := input.explore_task()):
            # Reset data
            raw_data.set(None)
            filtered_data.set(None)
            ui.update_selectize("explore_metric", choices=[], selected=None, server=True)
            ui.update_selectize("explore_compare_metrics", choices=[], selected=[], server=True)
            ui.update_selectize("explore_filter_metric", choices=[], selected=None, server=True)
            return

        try:
            data_loading.set(True)
            _load_csv_file(csv_path)
        finally:
            data_loading.set(False)

    def _load_csv_file(file_path: str | Path):
        """Load CSV file and update reactive values."""
        try:
            ui.notification_show("Loading data...", type="message", duration=None, id="explore_load_msg")

            df = load_csv(file_path)

            # Get metric names (numeric columns)
            metric_cols = [col for col in df.columns if df[col].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32)]

            # Set default metric
            default_metric = "inner_time" if "inner_time" in metric_cols else ("outer_time" if "outer_time" in metric_cols else metric_cols[0] if metric_cols else "")

            # Get filterable columns using reusable utility
            from ..utils import get_filterable_columns
            filterable_cols = get_filterable_columns(df)

            # Store data FIRST (before UI updates) so render functions see valid data
            raw_data.set(df)
            filtered_data.set(df)

            # Show "Processing data..." message while plots/tables render
            ui.notification_show("Processing data...", type="message", duration=None, id="explore_load_msg")

            # Prepend empty string sentinel to prevent auto-selection issues
            PLACEHOLDER = ""
            metric_choices = [PLACEHOLDER] + sorted(metric_cols)
            filterable_choices = [PLACEHOLDER] + filterable_cols

            # Update UI inputs with server-side selectize and sentinel values
            # Metric to visualize: prepend empty string, select default if found
            selected_metric = default_metric if default_metric in metric_cols else PLACEHOLDER
            ui.update_selectize("explore_metric", choices=metric_choices, selected=selected_metric, server=True)

            # Metrics to compare: multiple selection, start empty
            ui.update_selectize("explore_compare_metrics", choices=metric_choices, selected=[], server=True)

            # Filter metric: prepend empty string, select placeholder (no filter by default)
            ui.update_selectize("explore_filter_metric", choices=filterable_choices, selected=PLACEHOLDER, server=True)

            # Remove the message after rendering completes
            ui.notification_remove(id="explore_load_msg")

        except Exception as e:
            import traceback
            traceback.print_exc()
            ui.notification_show(f"Error loading CSV: {e}", type="error", duration=10)
            raise

    @output
    @render.ui
    def explore_filter_ui():
        """Render dynamic filter UI based on selected metric."""
        filter_metric = input.explore_filter_metric()

        # Treat empty string as "no filter selected" (our sentinel value)
        if not filter_metric or filter_metric.strip() == "":
            return None

        df = raw_data.get()
        if df is None:
            return None

        from ..utils import create_filter_ui
        try:
            return create_filter_ui(df, filter_metric, "explore_filter_value")
        except Exception as e:
            return None

    @reactive.effect
    def update_filtered_data():
        """Update filtered data when filter changes."""
        df = raw_data.get()
        if df is None:
            return

        filter_metric = input.explore_filter_metric()

        # Treat empty string as "no filter selected" (our sentinel value)
        if not filter_metric or filter_metric.strip() == "":
            filtered_data.set(df)
            return

        try:
            filter_value = input.explore_filter_value()
        except Exception:
            filtered_data.set(df)
            return

        # Check if filter_value is actually set (not None, not empty for categorical)
        if filter_value is None:
            filtered_data.set(df)
            return

        # For categorical filters (list), check if empty
        if isinstance(filter_value, (list, tuple)):
            if not filter_value or (len(filter_value) == 1 and filter_value[0] == ""):
                filtered_data.set(df)
                return

            # For numeric range filters, check if it's the full range (no actual filtering)
            if len(filter_value) == 2 and filter_metric in df.columns:
                col = df[filter_metric]
                if col.dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
                    try:
                        col_min = float(col.drop_nulls().min())
                        col_max = float(col.drop_nulls().max())
                        if abs(filter_value[0] - col_min) < 1e-9 and abs(filter_value[1] - col_max) < 1e-9:
                            filtered_data.set(df)
                            return
                    except:
                        pass  # If check fails, proceed with filter

        from ..utils import apply_filter
        try:
            filtered_df = apply_filter(df, filter_metric, filter_value)
            filtered_data.set(filtered_df)
        except Exception as e:
            filtered_data.set(df)

    @output
    @render.text
    def explore_load_status():
        """Show loading status indicator."""
        if data_loading.get():
            return "⏳ Loading..."
        elif raw_data.get() is not None:
            return f"✓ Loaded ({raw_data.get().shape[0]} rows)"
        else:
            return ""

    @output
    @render.data_frame
    def explore_table():
        """Render summary statistics using Shiny data_frame renderer (Polars native)."""
        df = filtered_data.get()
        metric = input.explore_metric()

        if df is None or not metric or metric not in df.columns:
            return pl.DataFrame({"Statistic": [], "Value": []})

        try:
            values = df[metric].drop_nulls().to_numpy()
            if len(values) == 0:
                return pl.DataFrame({"Statistic": [], "Value": []})

            stats = compute_summary(values, digits=4)

            # Cast all values to string for consistent display (avoids mixed dtypes edge cases)
            stat_names = list(stats.keys())
            stat_vals = [str(v) for v in stats.values()]
            return pl.DataFrame({"Statistic": stat_names, "Value": stat_vals})
        except Exception:
            return pl.DataFrame({"Statistic": [], "Value": []})

    @output
    @render.text
    def explore_characteristics():
        """Render distribution characteristics."""
        if filtered_data() is None:
            return "No data loaded."

        if not (metric := input.explore_metric()):
            return "No metric selected."

        # Check if metric exists in data
        if metric not in filtered_data().columns:
            return f"Metric '{metric}' not found in data."

        # Get max_changepoint_points setting
        settings = Settings()
        max_changepoint_points = settings.get("gui.explore.max_changepoint_points", 5000)

        values = filtered_data()[metric].to_numpy()
        result = characterize_distribution(values, max_changepoint_points=max_changepoint_points)
        return result

    @output
    @render.plot
    def explore_plot():
        """Render distribution plot."""
        df = filtered_data.get()
        metric = input.explore_metric()

        if df is None or not metric or metric not in df.columns:
            return None

        try:
            values = df[metric].drop_nulls().to_numpy()

            if len(values) == 0:
                return None
            # Load configuration for plot optimization
            settings = Settings()
            max_scatter = settings.get("gui.explore.max_scatter_points", 2000)

            result = create_distribution_plot(values, metric, max_scatter_points=max_scatter)
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

    @output
    @render.plot
    def explore_cor_plot():
        """Render pairwise correlation plot."""
        df = filtered_data.get()
        compare_metrics = input.explore_compare_metrics()

        if df is None or not compare_metrics or len(compare_metrics) == 0:
            return None

        # Build scatter matrix manually without pandas/seaborn
        try:
            subset = df.select(compare_metrics)
            cols = subset.columns
            n = len(cols)
            if n == 0:
                return None

            # Extract numpy arrays once
            arrays = {c: subset[c].drop_nulls().to_numpy() for c in cols}

            # Increase figure size to avoid cutoff and improve readability
            fig, axes = plt.subplots(n, n, figsize=(4 * n, 4 * n))
            if n == 1:
                ax = axes if hasattr(axes, 'hist') else axes[0, 0]
                ax.hist(arrays[cols[0]], bins=30, color='steelblue', alpha=0.75, edgecolor='black')
                ax.set_xlabel(cols[0], fontsize=11)
                ax.set_ylabel('Frequency', fontsize=11)
            else:
                for i, ycol in enumerate(cols):
                    for j, xcol in enumerate(cols):
                        ax = axes[i, j]
                        xvals = arrays[xcol]
                        yvals = arrays[ycol]
                        if i == j:
                            ax.hist(xvals, bins=30, color='steelblue', alpha=0.75, edgecolor='black')
                        else:
                            ax.scatter(xvals, yvals, s=20, alpha=0.55, color='black', rasterized=True)
                            # Correlation annotation
                            if len(xvals) > 2 and len(yvals) > 2:
                                try:
                                    r = np.corrcoef(xvals, yvals)[0, 1]
                                    ax.text(0.05, 0.9, f"r={r:.2f}", transform=ax.transAxes, fontsize=10,
                                            bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))
                                except Exception:
                                    pass
                        # Axis labels (outer only) with larger font
                        if i == n - 1:
                            ax.set_xlabel(xcol, fontsize=11)
                        else:
                            ax.set_xticklabels([], fontsize=9)
                        if j == 0:
                            ax.set_ylabel(ycol, fontsize=11)
                        else:
                            ax.set_yticklabels([], fontsize=9)
                        ax.tick_params(labelsize=9)
            # Use subplots_adjust to ensure bottom margins don't get cut off
            plt.tight_layout(pad=1.0)
            plt.subplots_adjust(bottom=0.08, left=0.08, top=0.95, right=0.95)
            return fig
        except Exception as e:
            print(f"Error creating correlation plot (manual): {e}")
            import traceback
            traceback.print_exc()
            return None
