"""
Compare tab for SHARP GUI.

Provides interface for comparing two experiment runs with statistical analysis.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from shiny import ui, reactive, render
import polars as pl

from src.core.config.settings import Settings
from src.core.stats.narrative import generate_comparison_narrative
from src.core.runlogs import load_csv, get_experiments, get_tasks_for_experiment
from src.gui.utils.comparisons import (
    compute_comparison_summary,
    render_density_comparison_plot,
    render_ecdf_comparison_plot
)


def compare_ui():
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
                ui.output_ui('compare_filter_ui'),
            ),
        ),
        ui.hr(),
        ui.row(
            ui.column(3, ui.output_plot('compare_density')),
            ui.column(3, ui.output_plot('compare_ecdf')),
            ui.column(3, ui.output_data_frame('compare_table')),
            ui.column(3, ui.output_ui('compare_narrative')),
        ),
    )


def compare_server(input, output, session):
    """
    Server logic for Compare tab.

    Args:
        input: Shiny input object
        output: Shiny output object
        session: Shiny session object
    """
    # Reactive values for storing loaded data
    baseline_df = reactive.value(None)
    treatment_df = reactive.value(None)
    baseline_loading = reactive.value(False)
    treatment_loading = reactive.value(False)

    # Reactive values for filtered data
    baseline_filtered = reactive.value(None)
    treatment_filtered = reactive.value(None)

    # Initialize experiment dropdowns on startup
    @reactive.effect
    def _init_experiments():
        """Populate experiment dropdowns with all available experiments."""
        experiments = get_experiments()
        # Default selection from settings
        default_exp = Settings().get("gui.default_experiment", "misc")
        default_sel = default_exp if default_exp in experiments else (next(iter(experiments), ""))
        ui.update_select('baseline_experiment', choices=experiments, selected=default_sel)
        ui.update_select('treatment_experiment', choices=experiments, selected=default_sel)

    # Update baseline task dropdown when experiment changes
    @reactive.effect
    @reactive.event(input.baseline_experiment)
    def _update_baseline_tasks():
        """Update baseline task choices when experiment changes."""
        if not (experiment := input.baseline_experiment()):
            return

        tasks = get_tasks_for_experiment(experiment)
        # Auto-select first task if available
        selected = list(tasks.values())[0] if tasks else None
        ui.update_select('baseline_task', choices=tasks, selected=selected)

        # Also sync treatment experiment to match baseline
        ui.update_select('treatment_experiment', selected=experiment)

    # Update treatment task dropdown when experiment changes
    @reactive.effect
    @reactive.event(input.treatment_experiment)
    def _update_treatment_tasks():
        """Update treatment task choices when experiment changes."""
        if not (experiment := input.treatment_experiment()):
            return

        tasks = get_tasks_for_experiment(experiment)
        # Auto-select first task if available
        selected = list(tasks.values())[0] if tasks else None
        ui.update_select('treatment_task', choices=tasks, selected=selected)

    @reactive.effect
    @reactive.event(input.baseline_task)
    def _load_baseline():
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
            # Reset metric when baseline changes
            ui.update_selectize('compare_metric', choices=[], selected=None, server=True)
        except Exception as e:
            print(f'ERROR loading baseline: {e}')
            import traceback
            traceback.print_exc()
            baseline_df.set(None)
            baseline_filtered.set(None)
            baseline_loading.set(False)
            ui.update_selectize('compare_metric', choices=[], selected=None, server=True)

    @reactive.effect
    @reactive.event(input.treatment_task)
    def _load_treatment():
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
            # Reset metric when treatment changes
            ui.update_selectize('compare_metric', choices=[], selected=None, server=True)
        except Exception as e:
            print(f'ERROR loading treatment: {e}')
            import traceback
            traceback.print_exc()
            treatment_df.set(None)
            treatment_filtered.set(None)
            treatment_loading.set(False)
            ui.update_selectize('compare_metric', choices=[], selected=None, server=True)

    @output
    @render.text
    def baseline_status():
        """Show baseline load status."""
        if baseline_loading.get():
            return '⏳ Loading data...'
        df = baseline_df.get()
        if df is None:
            return 'No data loaded'
        return f'✓ Loaded {len(df)} rows'

    @output
    @render.text
    def treatment_status():
        """Show treatment load status."""
        if treatment_loading.get():
            return '⏳ Loading data...'
        df = treatment_df.get()
        if df is None:
            return 'No data loaded'
        return f'✓ Loaded {len(df)} rows'

    @reactive.effect
    @reactive.event(baseline_df, treatment_df)
    def _update_metric_choices():
        """Update metric dropdown when both files are loaded."""
        b_df = baseline_df.get()
        t_df = treatment_df.get()

        if b_df is None or t_df is None:
            return

        # Find common metric columns (exclude metadata columns)
        metadata_cols = {'rank', 'repeat', 'benchmark'}
        b_cols = set(b_df.columns) - metadata_cols
        t_cols = set(t_df.columns) - metadata_cols
        common_metrics = sorted(list(b_cols & t_cols))

        if common_metrics:
            # Prepend empty string sentinel
            PLACEHOLDER = ""
            choices_with_placeholder = [PLACEHOLDER] + common_metrics

            # Prefer inner_time, then outer_time
            default = 'inner_time' if 'inner_time' in common_metrics else (
                'outer_time' if 'outer_time' in common_metrics else common_metrics[0] if common_metrics else PLACEHOLDER
            )
            ui.update_selectize('compare_metric', choices=choices_with_placeholder, selected=default, server=True)

    @reactive.effect
    @reactive.event(input.compare_metric)  # Only trigger when metric changes
    def _update_filter_choices():
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
        from ..utils import get_filterable_columns
        b_filterable = set(get_filterable_columns(b_df))
        t_filterable = set(get_filterable_columns(t_df))
        common_filterable = sorted(list(b_filterable & t_filterable))

        if not common_filterable:
            ui.update_selectize('compare_filter_metric', choices=[], selected=None, server=True)
            return

        # Prepend empty string sentinel for no filter
        PLACEHOLDER = ""
        choices_with_placeholder = [PLACEHOLDER] + common_filterable
        ui.update_selectize('compare_filter_metric', choices=choices_with_placeholder, selected=PLACEHOLDER, server=True)

    @output
    @render.ui
    def compare_filter_ui():
        """Render dynamic filter UI based on selected metric."""
        filter_metric = input.compare_filter_metric()

        # Treat empty string as "no filter selected" (our sentinel value)
        if not filter_metric or filter_metric.strip() == "":
            return None

        # Use baseline data to create filter UI (both datasets should have same structure)
        b_df = baseline_df.get()
        if b_df is None:
            return None

        from ..utils import create_filter_ui
        try:
            return create_filter_ui(b_df, filter_metric, "compare_filter_value")
        except Exception as e:
            return None

    @reactive.effect
    def _apply_filters():
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
            # No filter selected
            baseline_filtered.set(b_df)
            treatment_filtered.set(t_df)
            return

        try:
            filter_value = input.compare_filter_value()
        except Exception as e:
            # Filter value not set yet
            baseline_filtered.set(b_df)
            treatment_filtered.set(t_df)
            return

        # Check if filter_value is actually set (not None, not empty for categorical)
        if filter_value is None:
            baseline_filtered.set(b_df)
            treatment_filtered.set(t_df)
            return

        # For categorical filters (list), check if empty
        if isinstance(filter_value, (list, tuple)):
            if not filter_value or (len(filter_value) == 1 and filter_value[0] == ""):
                baseline_filtered.set(b_df)
                treatment_filtered.set(t_df)
                return

            # For numeric range filters, check if it's the full range (no actual filtering)
            if len(filter_value) == 2 and filter_metric in b_df.columns:
                col = b_df[filter_metric]
                if col.dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
                    try:
                        col_min = float(col.drop_nulls().min())
                        col_max = float(col.drop_nulls().max())
                        if abs(filter_value[0] - col_min) < 1e-9 and abs(filter_value[1] - col_max) < 1e-9:
                            baseline_filtered.set(b_df)
                            treatment_filtered.set(t_df)
                            return
                    except:
                        pass  # If check fails, proceed with filter

        from ..utils import apply_filter
        try:
            b_filtered = apply_filter(b_df, filter_metric, filter_value)
            t_filtered = apply_filter(t_df, filter_metric, filter_value)
            baseline_filtered.set(b_filtered)
            treatment_filtered.set(t_filtered)
        except Exception as e:
            import traceback
            traceback.print_exc()
            baseline_filtered.set(b_df)
            treatment_filtered.set(t_df)

    @output
    @render.plot
    def compare_density():
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
    def compare_ecdf():
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
    def compare_table():
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

            # Create DataFrame for display with percentage change column
            table_data = {
                'Statistic': summary['statistic_names'],
                'Baseline': summary['baseline'],
                'Treatment': summary['treatment'],
                '% Change': summary['pct_change']
            }
            return pl.DataFrame(table_data)
        except Exception as e:
            print(f'Error creating comparison table: {e}')
            import traceback
            traceback.print_exc()
            return None

    @output
    @render.ui
    def compare_narrative():
        """Render comparison narrative with MathJax."""
        b_df = baseline_filtered.get()
        t_df = treatment_filtered.get()
        metric = input.compare_metric()

        if b_df is None or t_df is None or not metric:
            return ui.HTML('<p>Load both baseline and treatment files to see comparison.</p>')

        try:
            b_vals = b_df[metric].to_numpy()
            t_vals = t_df[metric].to_numpy()
            narrative = generate_comparison_narrative(b_vals, t_vals)
            # Include MathJax script for LaTeX rendering with proper styling for line breaks
            html_content = f"""
            <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
            <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
            <style>
            .narrative-container p {{
                margin: 2px 0;
                padding: 0;
                font-size: 0.8em;
            }}
            </style>
            <div class="narrative-container">
            {narrative}
            </div>
            <script>
            if (window.MathJax && window.MathJax.typesetPromise) {{
                MathJax.typesetPromise().catch(err => console.log(err));
            }}
            </script>
            """
            return ui.HTML(html_content)
        except Exception as e:
            print(f'Error generating narrative: {e}')
            import traceback
            traceback.print_exc()
            return ui.HTML(f'<p>Error: {str(e)}</p>')
