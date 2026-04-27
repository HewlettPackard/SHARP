"""
Compare tab for SHARP GUI.

Provides interface for comparing two experiment runs with statistical analysis.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from pathlib import Path

from shiny import ui, reactive, render, Inputs, Outputs, Session
import polars as pl
from matplotlib.figure import Figure
from typing import Any, Dict, List

from src.core.config.settings import Settings
from src.core.stats.narrative import generate_comparison_narrative
from src.core.runlogs import load_csv
from src.core.runlogs.metadata_compare import compare_metadata
from src.gui.utils.comparisons import *
from src.gui.utils.ui_helpers import *
from src.gui.utils.filters import *
from src.gui.utils import apply_filter, get_filterable_columns, create_filter_ui


from typing import Any

def compare_ui() -> Any:
    """
    Create UI for Compare tab.

    Returns:
        Shiny UI panel for comparison
    """
    # Get initial experiment choices (will be populated by server)
    # Start empty for consistency with Profile and Explore tabs

    return ui.nav_panel(
        'Compare',
        ui.row(
            ui.column(
                3,
                ui.tags.h5('Baseline Run'),
                ui.input_select('baseline_experiment', 'Experiment', choices={"": "(select experiment)"}),
                ui.input_select('baseline_task', 'Task', choices={}),
                ui.output_text('baseline_status'),
            ),
            ui.column(
                3,
                ui.tags.h5('Treatment Run'),
                ui.input_select('treatment_experiment', 'Experiment', choices={"": "(select experiment)"}),
                ui.input_select('treatment_task', 'Task', choices={}),
                ui.output_text('treatment_status'),
            ),
            ui.column(
                3,
                ui.input_selectize(
                    'compare_metric',
                    'Metric to visualize',
                    choices=[],
                    multiple=False,
                    options={
                        'placeholder': 'Type to search metrics...',
                        'loadThrottle': 300,
                        'searchField': ['value', 'label'],
                        'maxOptions': 100,
                    }
                ),
                ui.input_selectize(
                    'compare_filter_metric',
                    'Metric to Filter',
                    choices=[],
                    multiple=False,
                    options={
                        'placeholder': 'Type to search or leave empty...',
                        'loadThrottle': 300,
                        'searchField': ['value', 'label'],
                        'maxOptions': 100,
                    }
                ),
                ui.div(
                    ui.output_ui('compare_filter_ui'),
                    ui.output_text('compare_filter_value_time_display'),
                    style="display: flex; flex-direction: column; gap: 4px; line-height: 1.15;"
                ),
            ),
        ),
        ui.tags.hr(style="margin: 0.5rem 0;"),
        ui.row(
            ui.column(
                8,
                ui.row(
                    ui.column(6, ui.output_plot('compare_density')),
                    ui.column(6, ui.output_plot('compare_ecdf')),
                ),
                ui.row(
                    ui.column(12, ui.output_ui('compare_narrative')),
                ),
            ),
            ui.column(
                4,
                ui.output_data_frame('compare_table')
            ),
        ),
        ui.tags.hr(style="margin: 0.5rem 0;"),
        ui.row(
            ui.column(12, ui.output_ui('metadata_comparison')),
        ),
    )


def compare_server(input: Inputs, output: Outputs, session: Session) -> None:
    """
    Server logic for Compare tab.

    Args:
        input: Shiny input object
        output: Shiny output object
        session: Shiny session object
    """
    # Reactive values for storing loaded data
    baseline_df: reactive.Value[pl.DataFrame | None] = reactive.Value(None)
    treatment_df: reactive.Value[pl.DataFrame | None] = reactive.Value(None)
    baseline_loading = reactive.value(False)
    treatment_loading = reactive.value(False)

    # Reactive values for filtered data
    baseline_filtered: reactive.Value[pl.DataFrame | None] = reactive.Value(None)
    treatment_filtered: reactive.Value[pl.DataFrame | None] = reactive.Value(None)

    # Initialize experiment dropdowns on startup
    @reactive.effect
    def _init_experiments() -> None:
        """Populate experiment dropdowns with all available experiments."""
        init_experiment_selector(session, 'baseline_experiment', include_empty=True)
        init_experiment_selector(session, 'treatment_experiment', include_empty=True)

    # Update baseline task dropdown when experiment changes
    @reactive.effect
    @reactive.event(input.baseline_experiment)
    def _update_baseline_tasks() -> None:
        """Update baseline task choices when experiment changes."""
        experiment = input.baseline_experiment()
        update_task_selector(
            session,
            experiment,
            'baseline_task',
            include_empty=True,
            select_first=False
        )

        # Also sync treatment experiment to match baseline if baseline changed
        if experiment:
            ui.update_select('treatment_experiment', selected=experiment)

    # Update treatment task dropdown when experiment changes
    @reactive.effect
    @reactive.event(input.treatment_experiment)
    def _update_treatment_tasks() -> None:
        """Update treatment task choices when experiment changes."""
        experiment = input.treatment_experiment()

        update_task_selector(
            session,
            experiment,
            'treatment_task',
            include_empty=True,
            select_first=False
        )



    @reactive.effect
    @reactive.event(input.baseline_task)
    def _load_baseline() -> None:
        """Load baseline CSV file."""
        csv_path = input.baseline_task()

        if not csv_path:
            baseline_df.set(None)
            baseline_filtered.set(None)
            baseline_loading.set(False)
            return

        # Show loading state
        baseline_loading.set(True)

        try:
            df = load_csv(csv_path)
            baseline_df.set(df)
            baseline_filtered.set(df)  # Initialize filtered data
            baseline_loading.set(False)
        except Exception as e:
            print(f'ERROR loading baseline: {e}')
            import traceback
            traceback.print_exc()
            baseline_df.set(None)
            baseline_filtered.set(None)
            baseline_loading.set(False)

    @reactive.effect
    @reactive.event(input.treatment_task)
    def _load_treatment() -> None:
        """Load treatment CSV file."""
        csv_path = input.treatment_task()

        if not csv_path:
            treatment_df.set(None)
            treatment_filtered.set(None)
            treatment_loading.set(False)
            return

        # Show loading state
        treatment_loading.set(True)

        try:
            df = load_csv(csv_path)
            treatment_df.set(df)
            treatment_filtered.set(df)  # Initialize filtered data
            treatment_loading.set(False)
        except Exception as e:
            print(f'ERROR loading treatment: {e}')
            import traceback
            traceback.print_exc()
            treatment_df.set(None)
            treatment_filtered.set(None)
            treatment_loading.set(False)

    @output
    @render.text
    def baseline_status() -> str:
        """Show baseline load status."""
        if baseline_loading.get():
            return '⏳ Loading data...'
        try:
            df = baseline_df.get()
            if df is None:
                return 'No data loaded'
            return f'✓ Loaded {len(df)} rows'
        except Exception as e:
            return f'✗ Error: {str(e)}'

    @output
    @render.text
    def treatment_status() -> str:
        """Show treatment load status."""
        if treatment_loading.get():
            return '⏳ Loading data...'
        try:
            df = treatment_df.get()
            if df is None:
                return 'No data loaded'
            return f'✓ Loaded {len(df)} rows'
        except Exception as e:
            return f'✗ Error: {str(e)}'

    @reactive.effect
    @reactive.event(baseline_df, treatment_df)
    def _update_metric_choices() -> None:
        """Update metric dropdown when both files are loaded."""
        b_df = baseline_df.get()
        t_df = treatment_df.get()

        if b_df is None or t_df is None:
            return

        # Find common metric columns (exclude metadata columns)
        # Use get_numeric_columns to ensure we only get numeric types
        b_metrics = get_numeric_columns(b_df)
        t_metrics = get_numeric_columns(t_df)

        common_keys = sorted(list(set(b_metrics.keys()) & set(t_metrics.keys())))
        common_choices = {k: k for k in common_keys}

        if common_keys:
            # Prefer inner_time, then outer_time
            default = select_preferred_metric(common_choices)

            update_metric_selector(
                session,
                'compare_metric',
                common_choices,
                selected=default,
                placeholder=""
            )

    @reactive.effect
    @reactive.event(input.compare_metric)  # Only trigger when metric changes
    def _update_filter_choices() -> None:
        """Update filter metric choices when metric to visualize is selected (server-side with sentinel)."""
        metric = input.compare_metric()

        # Clear filter if no metric selected (empty string sentinel)
        if not metric or metric.strip() == "":
            ui.update_selectize('compare_filter_metric', choices=[], selected=None, server=True)
            return

        b_df = baseline_df.get()
        t_df = treatment_df.get()

        if b_df is None or t_df is None:
            ui.update_selectize('compare_filter_metric', choices=[], selected=None, server=True)
            return

        # Get filterable columns from both datasets (use intersection to ensure compatibility)
        b_filterable = set(get_filterable_columns(b_df))
        t_filterable = set(get_filterable_columns(t_df))
        common_filterable = sorted(list(b_filterable & t_filterable))
        common_choices = {k: k for k in common_filterable}

        if not common_filterable:
            ui.update_selectize('compare_filter_metric', choices=[], selected=None, server=True)
            return

        # Prepend empty string sentinel for no filter
        update_metric_selector(
            session,
            'compare_filter_metric',
            common_choices,
            selected=None,
            placeholder=""
        )

    @output
    @render.ui
    def compare_filter_ui() -> ui.TagChild | None:
        """Render dynamic filter UI based on selected metric."""
        filter_metric = input.compare_filter_metric()

        # Treat empty string as "no filter selected" (our sentinel value)
        if not filter_metric or filter_metric.strip() == "":
            return None

        # Use baseline data to create filter UI (both datasets should have same structure)
        b_df = baseline_df.get()
        if b_df is None:
            return None

        try:
            return create_filter_ui(b_df, filter_metric, "compare_filter_value")
        except Exception:
            return None

    @output
    @render.text
    def compare_filter_value_time_display() -> str:
        """Display the selected time range in HH:MM:SS format (only for time columns)."""
        return get_time_filter_display(
            data=baseline_df.get(),
            filter_metric=input.compare_filter_metric(),
            filter_value=get_filter_value(input, "compare_filter_value")
        )

    @reactive.effect
    def _apply_filters() -> None:
        """Apply filter to both baseline and treatment data."""
        b_df = baseline_df.get()
        t_df = treatment_df.get()

        # Default to unfiltered data if either is None
        if b_df is None:
            baseline_filtered.set(None)
        if t_df is None:
            treatment_filtered.set(None)

        if b_df is None or t_df is None:
            return

        filter_metric = input.compare_filter_metric()

        # Treat empty string as "no filter selected" (our sentinel value)
        if not filter_metric or filter_metric.strip() == "":
            baseline_filtered.set(b_df)
            treatment_filtered.set(t_df)
            return

        try:
            filter_value = get_filter_value(input, "compare_filter_value")
        except Exception:
            baseline_filtered.set(b_df)
            treatment_filtered.set(t_df)
            return

        # Check if filter should actually be applied
        if not should_apply_filter(filter_value, b_df, filter_metric):
            baseline_filtered.set(b_df)
            treatment_filtered.set(t_df)
            return

        # Apply filter to both datasets
        try:
            b_filtered = apply_filter(b_df, filter_metric, filter_value)
            t_filtered = apply_filter(t_df, filter_metric, filter_value)
            baseline_filtered.set(b_filtered)
            treatment_filtered.set(t_filtered)
        except Exception:
            import traceback
            traceback.print_exc()
            baseline_filtered.set(b_df)
            treatment_filtered.set(t_df)

    @output
    @render.plot
    def compare_density() -> Figure | None:
        """Render density comparison plot."""
        b_df = baseline_filtered.get()
        t_df = treatment_filtered.get()
        metric = input.compare_metric()

        if b_df is None or t_df is None or not metric:
            return None

        b_vals = b_df[metric].to_numpy()
        t_vals = t_df[metric].to_numpy()
        return render_density_comparison_plot(b_vals, t_vals, metric=metric)

    @output
    @render.plot
    def compare_ecdf() -> Figure | None:
        """Render ECDF comparison plot."""
        b_df = baseline_filtered.get()
        t_df = treatment_filtered.get()
        metric = input.compare_metric()

        if b_df is None or t_df is None or not metric:
            return None

        b_vals = b_df[metric].to_numpy()
        t_vals = t_df[metric].to_numpy()
        return render_ecdf_comparison_plot(b_vals, t_vals, metric=metric)

    @output
    @render.data_frame
    def compare_table() -> pl.DataFrame | None:
        """Render comparison statistics table."""
        b_df = baseline_filtered.get()
        t_df = treatment_filtered.get()
        metric = input.compare_metric()

        if b_df is None or t_df is None or not metric:
            return None

        try:
            b_vals = b_df[metric].to_numpy()
            t_vals = t_df[metric].to_numpy()

            # Use refactored comparison summary function
            summary = compute_comparison_summary(b_vals, t_vals, digits=10, sig_figs=3)

            # Create DataFrame for display with percentage change and p-value columns
            table_data = {
                'Statistic': summary['statistic_names'],
                'Baseline': summary['baseline'],
                'Treatment': summary['treatment'],
                '% Change': summary['pct_change'],
                'P-value': summary['p_value']
            }
            return pl.DataFrame(table_data)
        except Exception as e:
            print(f'Error creating comparison table: {e}')
            import traceback
            traceback.print_exc()
            return None

    @output
    @render.ui
    def compare_narrative() -> ui.TagChild:
        """Render comparison narrative."""
        b_df = baseline_filtered.get()
        t_df = treatment_filtered.get()
        metric = input.compare_metric()

        if b_df is None or t_df is None or not metric:
            return ui.HTML('<p>Load both baseline and treatment files to see comparison.</p>')

        try:
            b_vals = b_df[metric].to_numpy()
            t_vals = t_df[metric].to_numpy()
            narrative = generate_comparison_narrative(b_vals, t_vals, lower_is_better=None)
            return ui.HTML(f'<p style="margin-top: 10px; font-size: 0.9em;">{narrative}</p>')
        except Exception as e:
            print(f'Error generating qualitative narrative: {e}')
            import traceback
            traceback.print_exc()
            return ui.HTML(f'<p>Error: {str(e)}</p>')

    @output
    @render.ui
    def metadata_comparison() -> ui.TagChild:
        """Render metadata comparison between baseline and treatment runs."""
        # Get CSV paths directly from inputs
        baseline_csv = input.baseline_task()
        treatment_csv = input.treatment_task()

        if not baseline_csv or not treatment_csv:
            return ui.HTML('')

        # Convert to .md paths
        baseline_md = Path(baseline_csv).with_suffix('.md')
        treatment_md = Path(treatment_csv).with_suffix('.md')

        if not baseline_md.exists() or not treatment_md.exists():
            return ui.HTML('')

        try:
            # Get metadata comparison in markdown format
            # Note: Using show_all=False to only show significant differences
            comparison_md = compare_metadata(
                treatment_md=treatment_md,
                baseline_md=baseline_md,
                show_all=False,
                format='md',
                treatment_launch_id=None,
                baseline_launch_id=None,
            )

            if not comparison_md:
                return ui.HTML('<p><i>No significant metadata differences detected.</i></p>')

            # Convert markdown to HTML for rendering
            # The markdown output from compare_metadata uses markdown tables
            # Shiny's ui.markdown() handles this conversion
            return ui.markdown(comparison_md)
        except Exception as e:
            print(f'Error comparing metadata: {e}')
            import traceback
            traceback.print_exc()
            return ui.HTML(f'<p>Error comparing metadata: {str(e)}</p>')
