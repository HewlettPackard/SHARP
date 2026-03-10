"""
Summary tab for SHARP GUI.

Provides dashboard view with KPI cards and recent runs table.
Shows summary statistics and quick navigation to other tabs.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from shiny import ui, reactive, render
from datetime import timedelta
import matplotlib.pyplot as plt

from src.core.config.settings import Settings
from src.gui.utils import scan_runlogs, load_csv, parse_markdown_runtime_options


def summary_ui() -> ui.nav_panel:
    """
    Create Summary tab UI.

    Returns:
        Shiny nav_panel for the summary tab
    """
    return ui.nav_panel(
        "Review",
        ui.tags.style("""
            .activity-row > div {
                display: flex;
                flex-direction: column;
                height: 250px;
            }
            .activity-row .bslib-card {
                display: flex;
                flex-direction: column;
                height: 100%;
            }
            .activity-row .bslib-card .card-body {
                display: flex;
                flex-direction: column;
                flex: 1;
                overflow: hidden;
            }
            .activity-row .bslib-value-box {
                display: flex;
                flex-direction: column;
                height: 100%;
            }
        """),
        ui.layout_columns(
            ui.value_box(
                "Total Runs",
                ui.output_text("total_runs"),
                showcase=ui.tags.i(class_="bi bi-graph-up"),
                theme="primary",
            ),
            ui.value_box(
                "Avg. Execution Time",
                ui.output_text("avg_time"),
                showcase=ui.tags.i(class_="bi bi-stopwatch"),
                theme="info",
            ),
            ui.card(
                "Activity",
                ui.output_plot("activity_graph"),
                full_screen=False,
            ),
            class_="activity-row",
        ),
        ui.hr(),
        ui.layout_columns(
            ui.card(
                ui.card_header("Recent Experiment Runs"),
                ui.output_ui("recent_runs_table"),
            ),
            col_widths=[12],
        ),
        ui.hr(),
        ui.layout_columns(
            ui.input_action_button(
                "quick_launch",
                "Launch New Experiment",
                icon=ui.tags.span(ui.tags.i(class_="bi bi-rocket-takeoff"), "\u00A0"),
                class_="btn-primary btn-lg",
            ),
            col_widths=[12],
        ),
    )


def summary_server(input, output, session, refresh_trigger=None):
    """
    Server logic for Summary tab.

    Args:
        input: Shiny input object
        output: Shiny output object
        session: Shiny session object
        refresh_trigger: Optional reactive value to trigger data refresh
    """
    settings = Settings()
    recent_runs_limit = settings.get("gui.overview.recent_runs_count", 10)

    # Reactive values
    all_runs_data = reactive.value([])  # All runs across all experiments
    recent_runs_data = reactive.value([])  # Limited to recent_runs_count for display

    @reactive.effect
    def _load_all_runs():
        """Load all runs data in background thread."""
        # React to refresh trigger if provided
        if refresh_trigger is not None:
            _ = refresh_trigger.get()  # Create dependency on trigger

        def load_data():
            # Scan all runs for statistics
            all_runs = scan_runlogs(limit=None)
            all_runs_data.set(all_runs)

            # Also get limited runs for table display
            recent_runs = scan_runlogs(limit=recent_runs_limit)
            recent_runs_data.set(recent_runs)

        load_data()

    @render.text
    def total_runs():
        """Render total number of runs (across all experiments)."""
        return str(len(all_runs_data.get()))

    @render.text
    def avg_time():
        """Render average execution time (across all experiments)."""
        runs = all_runs_data.get()

        if not runs:
            return "No data"

        durations = []

        for run in runs:
            # Try duration from metadata first
            if run.get("duration"):
                durations.append(run["duration"])
            # Fall back to loading CSV if no duration in metadata
            elif run.get("csv_path"):
                try:
                    df = load_csv(run["csv_path"])
                    if "outer_time" in df.columns:
                        mean_time = df["outer_time"].mean()
                        if mean_time is not None:
                            durations.append(mean_time)
                except Exception:
                    continue

        if not durations:
            return "No data"

        avg = sum(durations) / len(durations)
        return f"{avg:.2f}s"

    @render.plot
    def activity_graph():
        """Render activity bar chart for last 30 days using matplotlib."""
        runs = all_runs_data.get()

        if not runs:
            # Create empty plot if no data
            fig, ax = plt.subplots(figsize=(5, 2.5))
            ax.text(0.5, 0.5, 'No data available', ha='center', va='center',
                   transform=ax.transAxes, fontsize=10)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            return fig

        # Get the most recent timestamp from data
        timestamps = [run["timestamp"] for run in runs if run.get("timestamp")]
        if not timestamps:
            fig, ax = plt.subplots(figsize=(5, 2.5))
            ax.text(0.5, 0.5, 'No data available', ha='center', va='center',
                   transform=ax.transAxes, fontsize=10)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            return fig

        max_date = max(ts.date() for ts in timestamps)
        start_date = max_date - timedelta(days=29)

        # Count runs per day
        daily_counts = {}
        for i in range(30):
            date = start_date + timedelta(days=i)
            daily_counts[date] = 0

        # Populate counts from runs
        for run in runs:
            if run.get("timestamp"):
                run_date = run["timestamp"].date()
                if start_date <= run_date <= max_date:
                    daily_counts[run_date] += 1

        # Prepare data for plotting
        dates = sorted(daily_counts.keys())
        counts = [daily_counts[date] for date in dates]

        # Create matplotlib bar chart
        fig, ax = plt.subplots(figsize=(5, 2.5))
        ax.bar(range(len(dates)), counts, color='#0d6efd', width=0.8)

        # Configure x-axis with date labels
        ax.set_xticks(range(0, len(dates), 5))  # Show every 5th date
        ax.set_xticklabels([dates[i].strftime("%m/%d") for i in range(0, len(dates), 5)],
                          rotation=45, ha='right', fontsize=7)

        # Configure y-axis
        ax.set_ylabel('Runs', fontsize=8)
        ax.tick_params(axis='y', labelsize=7)

        # Remove top and right spines
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # Adjust layout to prevent x-axis labels from being cropped
        fig.subplots_adjust(left=0.12, right=0.95, top=0.92, bottom=0.25)

        return fig

    @render.ui
    def recent_runs_table():
        """Render recent runs table with action buttons."""
        runs = recent_runs_data.get()

        if not runs:
            return ui.p("No recent experiments found.", class_="text-muted")

        # Create table rows
        rows = []
        for i, run in enumerate(runs):
            backends_str = ", ".join(run["backends"]) if run.get("backends") else "local"
            timestamp_str = run["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if run["timestamp"] else "Unknown"
            benchmark_str = run.get("benchmark") or "Unknown"
            rows_str = str(run["rows"]) if run.get("rows") is not None else "N/A"

            rows.append(
                ui.tags.tr(
                    ui.tags.td(run["experiment"]),
                    ui.tags.td(run["task"]),
                    ui.tags.td(benchmark_str),
                    ui.tags.td(backends_str),
                    ui.tags.td(timestamp_str),
                    ui.tags.td(rows_str),
                    ui.tags.td(
                        ui.tags.a(
                            ui.tags.i(class_="bi bi-arrow-clockwise", style="font-size: 1.2rem;"),
                            href="#",
                            class_="text-success",
                            title="Rerun this experiment",
                            id=f"rerun_{i}",
                            onclick="return false;",  # Prevent navigation
                        ),
                        style="text-align: center; padding: 0.5rem;",
                    ),
                    ui.tags.td(
                        ui.tags.a(
                            ui.HTML('<svg width="1.5em" height="1.5em" viewBox="0 0 16 16" fill="currentColor" style="color: #d63384;" class="bi"><rect x="2" y="10" width="2" height="4" fill="#d63384"/><rect x="5" y="6" width="2" height="8" fill="#d63384"/><rect x="8" y="4" width="2" height="10" fill="#d63384"/><rect x="11" y="7" width="2" height="7" fill="#d63384"/></svg>'),
                            href="#",
                            title="Explore this experiment",
                            id=f"explore_{i}",
                            onclick="return false;",  # Prevent navigation
                        ),
                        style="text-align: center; padding: 0.5rem;",
                    ),
                )
            )

        # Create table with Bootstrap styling
        return ui.div(
            ui.tags.table(
                ui.tags.thead(
                    ui.tags.tr(
                        ui.tags.th("Experiment"),
                        ui.tags.th("Task"),
                        ui.tags.th("Benchmark"),
                        ui.tags.th("Backend"),
                        ui.tags.th("Timestamp"),
                        ui.tags.th("Rows"),
                        ui.tags.th("Rerun", style="text-align: center; width: 80px;"),
                        ui.tags.th("Explore", style="text-align: center; width: 80px;"),
                    )
                ),
                ui.tags.tbody(*rows),
                class_="table table-striped table-hover table-sm",
            ),
            style="max-height: 400px; overflow-y: auto;",
            id="recent_runs_table_container",
        )

    @reactive.effect
    @reactive.event(input.quick_launch)
    def navigate_to_measure():
        """Navigate to measure tab when Quick Launch is clicked."""
        ui.update_navset("main_nav", selected="Measure")

    # Dynamic rerun button handlers
    # Store runs data for access by JavaScript handlers
    @reactive.effect
    def _update_rerun_data():
        """Update stored runs data when recent_runs_data changes."""
        session.rerun_runs_data = recent_runs_data.get()

    # Handle rerun button clicks from JavaScript
    @reactive.effect
    @reactive.event(input.rerun_click)
    async def _handle_rerun_click():
        """Handle rerun_click input value set by JavaScript."""
        try:
            rerun_index = input.rerun_click()
            if rerun_index is not None and rerun_index >= 0:
                runs = recent_runs_data.get()
                if rerun_index < len(runs):
                    run = runs[rerun_index]
                    md_path = run.get("md_path")
                    if md_path:
                        rerun_config = parse_markdown_runtime_options(md_path)
                        # Send config as JSON string to measure tab
                        # Use send_custom_message to send to client, then it will set an input value
                        await session.send_custom_message("populate_measure_form", rerun_config)
                    # Switch to Measure tab
                    ui.update_navset("main_nav", selected="Measure")
        except Exception as e:
            print(f"Error handling rerun: {e}")
            import traceback
            traceback.print_exc()

    # Handle explore button clicks from JavaScript
    @reactive.effect
    @reactive.event(input.explore_click)
    async def _handle_explore_click():
        """Handle explore_click input value set by JavaScript."""
        try:
            explore_index = input.explore_click()
            if explore_index is not None and explore_index >= 0:
                runs = recent_runs_data.get()
                if explore_index < len(runs):
                    run = runs[explore_index]
                    explore_config = {
                        "experiment": run["experiment"],
                        "task": run["task"],
                        "csv_path": str(run.get("csv_path", ""))
                    }
                    # Send config as JSON string to explore tab
                    await session.send_custom_message("populate_explore_form", explore_config)
                    # Switch to Explore tab
                    ui.update_navset("main_nav", selected="Explore")
        except Exception as e:
            print(f"Error handling explore click: {e}")
            import traceback
            traceback.print_exc()
            traceback.print_exc()
