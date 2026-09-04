"""
Measure tab for SHARP GUI.

Provides interface for launching benchmark experiments with various configurations.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from shiny import ui, reactive, render, Inputs, Outputs, Session
from typing import Dict, Any
import json
import polars as pl
import time

from src.cli.launch import load_backend_options
from src.core.repeaters import REPEATER_REGISTRY
from src.core.execution.orchestrator import ExecutionOrchestrator, ProgressCallbacks
from src.core.config.benchmarks import resolve_benchmark_input, load_benchmark_data
from src.cli.discovery import get_benchmark_names
from src.core.config import discover_backends
from src.core.config.settings import Settings


_REPEATER_SHORT_LABELS: Dict[str, str] = {
    "COUNT": "Exact count",
    "RSE": "Standard error",
    "CI": "Confidence interval",
    "HDI": "High-density interval",
    "BB": "Block bootstrap",
    "GMM": "Gaussian mixture",
    "KS": "Kolmogorov-Smirnov",
    "DC": "Auto-stop",
    "DURATION": "Time duration",
}


def _get_repeater_choices() -> Dict[str, str]:
    """Build repeater choices from REPEATER_REGISTRY with short labels."""
    return {key: _REPEATER_SHORT_LABELS.get(key, key) for key in REPEATER_REGISTRY}


def _get_repeater_tooltip_script() -> str:
    """Return a JS snippet that adds title attributes to stopping-rule <option> elements."""
    descriptions = {k: v["description"] for k, v in REPEATER_REGISTRY.items()}
    js_obj = json.dumps(descriptions)
    return f"""
    (function() {{
        var desc = {js_obj};
        function applyTitles() {{
            document.querySelectorAll('#stopping option').forEach(function(opt) {{
                if (desc[opt.value]) opt.title = desc[opt.value];
            }});
        }}
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', applyTitles);
        }} else {{
            applyTitles();
        }}
        $(document).on('shiny:sessioninitialized', applyTitles);
    }})();
    """


def _get_benchmark_choices() -> Dict[str, str]:
    """Build benchmark choices from discovered benchmarks."""
    try:
        benchmark_map = get_benchmark_names()
        # Return dict mapping benchmark name to itself for display
        return {name: name for name in sorted(benchmark_map.keys())}
    except Exception as e:
        # Return empty dict if discovery fails
        print(f"Warning: Could not discover benchmarks: {e}")
        return {}


def measure_ui() -> Any:
    """
    Create UI for Measure tab.

    Returns:
        Shiny UI panel for experiment measurement
    """
    # Build repeater choices and tooltip script (always available)
    repeater_choices = _get_repeater_choices()
    repeater_tooltip_script = _get_repeater_tooltip_script()

    return ui.nav_panel(
        "Measure",
        ui.layout_sidebar(
            ui.sidebar(
                ui.h4("Experiment Configuration"),
                ui.input_text("experiment", "Experiment name", value="misc"),
                ui.row(
                    ui.column(6, ui.output_ui("bench_selector")),
                    ui.column(6, ui.input_text("task", "Task name (optional)")),
                ),
                ui.row(
                    ui.column(6,
                        ui.input_select(
                            "stopping",
                            "When to stop?",
                            choices=repeater_choices,
                            selected="COUNT",
                        ),
                    ),
                    ui.column(6, ui.input_numeric("n", "Max runs", value=1, min=1)),
                ),
                ui.output_ui("backend_selector"),
                ui.row(
                    ui.column(4, ui.input_numeric("mpl", "Copies", value=1, min=1)),
                    ui.column(4,
                        ui.input_select(
                            "start",
                            "Start",
                            choices={"as-is": "as-is", "cold": "cold", "warm": "warm"},
                            selected="as-is",
                        ),
                    ),
                    ui.column(4, ui.input_numeric("timeout", "Timeout", value=60, min=1)),
                ),
                ui.input_text("moreopts", "Any other arguments to pass along to SHARP?"),
                ui.tags.div(
                    ui.input_action_button(
                        "run_button",
                        "Run",
                        class_="btn btn-success",
                        icon=ui.tags.span(ui.tags.i(class_="bi bi-play-circle"), "\u00A0"),
                    ),
                    style="margin-top: 50px; text-align: right;",
                ),
                ui.tags.script("""
                    $(document).on('keypress', '#bench, #task, #n, #mpl, #timeout', function(e) {
                        if (e.which == 13) {
                            $('#run_button').click();
                            e.preventDefault();
                        }
                    });
                """),
                ui.tags.script(repeater_tooltip_script),
                width=400,
            ),
            ui.output_ui("completion_status_bar"),
            ui.card(
                ui.card_header("Run Results"),
                ui.output_data_frame("run_data"),
                style="height: 40vh; overflow-y: auto; margin-bottom: 20px;",
            ),
            ui.card(
                ui.card_header("Metadata"),
                ui.output_text_verbatim("md_data"),
                style="height: 50vh; overflow-y: auto;",
            ),
        ),
    )


def measure_server(input: Inputs, output: Outputs, session: Session, refresh_trigger: reactive.Value[int] | None = None) -> None:
    """
    Server logic for Measure tab.

    Args:
        input: Shiny input object
        output: Shiny output object
        session: Shiny session object
        refresh_trigger: Optional reactive value to trigger overview refresh
    """
    # Reactive values
    run_results: reactive.Value[pl.DataFrame | None] = reactive.Value(None)
    metadata_text = reactive.value("No results yet. Click Run to start an experiment.")
    backend_choices: reactive.Value[Dict[str, str]] = reactive.Value({})
    bench_value = reactive.value("")  # For prepopulating bench field from rerun
    completion_info: reactive.Value[Dict[str, Any] | None] = reactive.Value(None)  # Stores {duration, experiment, task, csv_path} after successful run

    # Initialize experiment name from settings
    @reactive.effect
    def _init_experiment_name() -> None:
        default_exp = Settings().get("gui.default_experiment", "misc")
        ui.update_text("experiment", value=default_exp)

    # Handle rerun configuration received from overview tab via JavaScript
    @reactive.effect
    @reactive.event(input.rerun_config_data)
    def _receive_rerun_config() -> None:
        """Receive and parse rerun configuration from overview tab."""
        try:
            if config_json := input.rerun_config_data():
                config = json.loads(config_json)
                _apply_rerun_config(config)
                # Switch to measure tab
                ui.update_navset("main_nav", selected="Measure")
        except Exception as e:
            print(f"Error receiving rerun config: {e}")
            import traceback
            traceback.print_exc()

    def _apply_rerun_config(config: dict[str, Any]) -> None:
        """Apply rerun configuration to form fields."""
        if not config:
            return

        try:
            # Populate form fields from config
            if "bench" in config and config["bench"]:
                bench_str = config["bench"]

                # Try to convert absolute path back to benchmark name for better UX
                # This prevents "/home/.../matmul.py 3500" and shows "matmul 3500" instead
                try:
                    from src.core.config.benchmarks import find_benchmark_by_entry_point
                    parts = bench_str.split(maxsplit=1)
                    entry_point = parts[0]
                    args_str = parts[1] if len(parts) > 1 else ""

                    # Try reverse lookup
                    benchmark_name, _, _ = find_benchmark_by_entry_point(entry_point)
                    # Success! Use friendly name instead of absolute path
                    bench_str = f"{benchmark_name} {args_str}".strip()
                except (ValueError, Exception):
                    # Not a known benchmark or lookup failed, use original path
                    pass

                bench_value.set(bench_str)  # Set reactive value, which will trigger re-render
            if "task" in config and config["task"]:
                ui.update_text("task", value=config["task"])
            if "experiment" in config and config["experiment"]:
                ui.update_text("experiment", value=config["experiment"])
            if "start" in config and config["start"]:
                ui.update_select("start", selected=config["start"])
            if "mpl" in config and config["mpl"]:
                ui.update_numeric("mpl", value=config["mpl"])
            if "timeout" in config and config["timeout"]:
                ui.update_numeric("timeout", value=config["timeout"])
            if "max_runs" in config and config["max_runs"]:
                ui.update_numeric("n", value=config["max_runs"])
            if "stopping" in config and config["stopping"]:
                ui.update_select("stopping", selected=config["stopping"])

            # Handle backend: restore single backend from rerun config
            if "backend" in config:
                backends = [config["backend"]] if config["backend"] else []
                ui.update_selectize("backend", selected=backends)

            # Handle backend_flags: prepend to moreopts
            if "backend_flags" in config and config["backend_flags"]:
                current_moreopts = input.moreopts() if input.moreopts() else ""
                new_moreopts = f"{config['backend_flags']} {current_moreopts}".strip()
                ui.update_text("moreopts", value=new_moreopts)

        except Exception as e:
            print(f"Error applying rerun config: {e}")
            import traceback
            traceback.print_exc()

    # Initialize backend choices on first load
    @reactive.effect
    def _init_backends() -> None:
        try:
            backends = discover_backends()
            choices = {name: name for name in backends.keys()}
            backend_choices.set(choices)
        except Exception as e:
            # Fallback to empty choices if discovery fails
            import traceback
            print(f"Backend discovery error: {e}")
            traceback.print_exc()
            backend_choices.set({})

    @render.ui
    def backend_selector() -> ui.TagChild:
        """Render backend selector with available choices."""
        choices = backend_choices.get()
        return ui.input_selectize(
            "backend",
            "Backends to use",
            choices=choices,
            selected=None,
            multiple=True,
            options={"placeholder": "(none — defaults to local)"},
        )

    @render.ui
    def bench_selector() -> ui.TagChild:
        """Render benchmark selector with autocomplete from discovered benchmarks."""
        choices = _get_benchmark_choices()
        # Do NOT read bench_value here — that would re-render the input (and
        # reset value=) on every rerun selection.  Value is pushed via update_text.

        # Create a datalist for HTML5 autocomplete
        # The datalist provides suggestions without restricting input
        datalist_id = "benchmark_list"
        options_html = "".join([
            f'<option value="{name}">' for name in choices.keys()
        ])

        return ui.tags.div(
            ui.input_text("bench", "Benchmark & args", placeholder="e.g., sleep 1 or /bin/ls"),
            ui.tags.datalist(
                ui.HTML(options_html),
                id=datalist_id,
            ),
            ui.tags.script(
                f"""
                document.getElementById('bench').setAttribute('list', '{datalist_id}');
                """
            ),
        )

    @reactive.effect
    def _sync_bench_value() -> None:
        """Push bench_value to the bench input without re-rendering the selector."""
        ui.update_text("bench", value=bench_value.get())

    @reactive.effect
    @reactive.event(input.run_button)
    def _on_run_button() -> None:
        """Handle Run button click - launch experiment via ExecutionOrchestrator."""
        # Validate required fields
        if not input.bench() or input.bench().strip() == "":
            metadata_text.set("✗ Benchmark field is required. Please enter a benchmark name or path.")
            run_results.set(None)
            return

        # Clear previous results immediately when Run is clicked
        run_results.set(None)
        metadata_text.set("Running experiment...")

        # Clear completion status when starting new run
        completion_info.set(None)
        start_time = time.time()

        # Show progress bar using Shiny's built-in Progress API
        with ui.Progress(min=0, max=input.n()) as p:
            p.set(message="Initializing experiment...")

            try:
                # Resolve benchmark input to entry_point, args, and task (shared core logic)
                benchmark_info = resolve_benchmark_input(
                    benchmark_input=input.bench(),
                    override_task=input.task() if input.task() else None
                )

                entry_point = benchmark_info["entry_point"]
                args = benchmark_info["args"]
                task_name = benchmark_info["task"]
            except Exception as e:
                # Handle invalid benchmark gracefully
                metadata_text.set(f"✗ Error resolving benchmark: {str(e)}")
                run_results.set(None)
                return

            # Build repeater config - use CR as the key for COUNT repeater
            stopping_rule = input.stopping()
            print(f"[DEBUG] stopping_rule={stopping_rule!r}, type={type(stopping_rule)}")
            # Ensure stopping_rule is a string
            if stopping_rule is None:
                stopping_rule = "COUNT"
            elif not isinstance(stopping_rule, str):
                stopping_rule = str(stopping_rule)
            repeater_key = "CR" if stopping_rule == "COUNT" else stopping_rule

            config: dict[str, Any] = {}  # Empty config, will be populated by load_backend_options
            try:
                # Handle backend selection: empty tuple/list means default to local
                selected_backends = input.backend()
                backend_names = list(selected_backends) if selected_backends else []
                if backend_names:
                    backend_options = load_backend_options(backend_names, config)
                    # config is modified in-place and now contains full backend_options and metrics
                else:
                    # No backend specified - orchestrator will default to local
                    backend_options = {}
            except Exception as e:
                print(f"Warning: Could not load backend options: {e}")
                import traceback
                traceback.print_exc()
                backend_names = []
                backend_options = {}
                config = {}

            # Build complete options dict
            options = {
                # Benchmark specification
                "entry_point": entry_point,
                "args": args,
                "task": task_name,
                # Backend configuration
                "backend_names": backend_names,
                "backend_options": backend_options,  # Loaded from YAML
                # Repeater configuration
                "repeats": stopping_rule,
                "repeater_options": {
                    repeater_key: {
                        "max": input.n(),
                    }
                },
                # Execution options
                "timeout": input.timeout(),
                "verbose": True,
                "start": input.start(),
                "mpl": input.mpl(),
                "directory": "runlogs",
                "skip_sys_specs": False,
                "mode": "w",
            }

            # Merge in metrics from config (loaded via load_backend_options)
            if "metrics" in config:
                options["metrics"] = config["metrics"]

            # Also load metrics from benchmark YAML if available
            try:
                benchmark_name = input.bench().strip().split()[0]  # First word is benchmark name
                _, benchmark_metrics = load_benchmark_data(benchmark_name)
                print(f"[DEBUG] Loaded benchmark metrics: {list(benchmark_metrics.keys()) if benchmark_metrics else 'None'}")
                if benchmark_metrics:
                    # Benchmark metrics override config metrics
                    if "metrics" not in options:
                        options["metrics"] = {}
                    options["metrics"].update(benchmark_metrics)
            except Exception as e:
                # Non-fatal - continue with whatever metrics are available
                print(f"[DEBUG] Failed to load benchmark metrics: {e}")
                import traceback
                traceback.print_exc()

            try:
                # Create orchestrator
                orchestrator = ExecutionOrchestrator(
                    options=options,
                    experiment_name=input.experiment()
                )

                # Define progress callbacks
                def on_iteration_start(iteration: int) -> None:
                    p.set(iteration, message=f"Running iteration {iteration}/{input.n()}")

                def on_iteration_complete(iteration: int, metrics: Dict[str, Any]) -> None:
                    p.set(iteration, message=f"Completed iteration {iteration}/{input.n()}")

                def on_convergence(status: str) -> None:
                    p.set(message="Finalizing results...")

                def on_error(error: Exception) -> None:
                    # Clear results on error
                    run_results.set(None)
                    metadata_text.set(f"✗ Experiment error: {str(error)}")

                callbacks = ProgressCallbacks(
                    on_iteration_start=on_iteration_start,
                    on_iteration_complete=on_iteration_complete,
                    on_convergence=on_convergence,
                    on_error=on_error
                )

                # Run experiment
                result = orchestrator.run(callbacks)

                # Update UI with results
                p.set(message="Loading results...")
                if result.success:
                    # Calculate duration
                    duration_seconds = time.time() - start_time

                    # Load CSV data if available
                    if 'csv' in result.output_paths:
                        try:
                            df = pl.read_csv(result.output_paths['csv'])
                            p.set(message="Rendering table...")
                            run_results.set(df)

                            # Store completion info for status bar
                            completion_info.set({
                                "duration": duration_seconds,
                                "experiment": input.experiment(),
                                "task": task_name,
                                "csv_path": result.output_paths['csv']
                            })
                        except Exception as e:
                            print(f"Error loading CSV: {e}")
                            import traceback
                            traceback.print_exc()
                            run_results.set(None)
                            metadata_text.set(f"✗ Error loading CSV results: {str(e)}")
                            return

                    # Load markdown metadata if available
                    if 'markdown' in result.output_paths:
                        try:
                            with open(result.output_paths['markdown'], 'r') as f:
                                md_content = f.read()
                            metadata_text.set(md_content)
                        except Exception as e:
                            metadata_text.set(
                                f"✓ Experiment completed successfully\n"
                                f"Iterations: {result.iteration_count}\n"
                                f"Convergence: {result.convergence_info}\n"
                                f"Output files: {result.output_paths}\n\n"
                                f"Error loading markdown: {e}"
                            )
                    else:
                        metadata_text.set(
                            f"✓ Experiment completed successfully\n"
                            f"Iterations: {result.iteration_count}\n"
                            f"Convergence: {result.convergence_info}\n"
                            f"Output files: {result.output_paths}"
                        )

                    # Trigger overview refresh on successful run
                    if refresh_trigger is not None:
                        refresh_trigger.set(refresh_trigger.get() + 1)

                else:
                    # Clear results on failed execution
                    run_results.set(None)
                    metadata_text.set(f"✗ Experiment failed: {result.error_message}")

            except Exception as e:
                # Catch any unexpected errors and clear results
                import traceback
                error_details = traceback.format_exc()
                print(f"Error launching experiment: {e}")
                print(error_details)
                run_results.set(None)
                error_msg = str(e) if str(e) else type(e).__name__
                metadata_text.set(f"✗ Error launching experiment: {error_msg}\n\n{error_details}")

    @render.data_frame
    def run_data() -> Any:
        """Render run results table with pagination."""
        results = run_results.get()
        if results is not None:
            # DataTable with pagination options
            return render.DataTable(results)

    @render.text
    def md_data() -> str:
        """Render metadata text."""
        return metadata_text.get()

    @render.ui
    def completion_status_bar() -> ui.TagChild:
        """Render success status bar with Explore link after run completes."""
        info = completion_info.get()
        if not info:
            return ui.div()  # Hidden when no completion info

        # Format duration
        duration = info["duration"]
        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        seconds = int(duration % 60)

        if hours > 0:
            duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            duration_str = f"{minutes:02d}:{seconds:02d}"

        return ui.tags.div(
            ui.tags.i(class_="bi bi-check-circle-fill me-2", style="color: #198754;"),
            ui.tags.span(
                f"Run completed successfully in {duration_str}",
                style="font-weight: 500;"
            ),
            ui.tags.a(
                "Explore results",
                ui.HTML('<svg width="1.5em" height="1.5em" viewBox="0 0 16 16" fill="currentColor" style="color: #d63384; display: inline; margin-left: 0.35rem; vertical-align: -0.125em;" class="bi"><rect x="2" y="10" width="2" height="4" fill="#d63384"/><rect x="5" y="6" width="2" height="8" fill="#d63384"/><rect x="8" y="4" width="2" height="10" fill="#d63384"/><rect x="11" y="7" width="2" height="7" fill="#d63384"/></svg>'),
                href="#",
                id="explore_completed_run",
                class_="ms-3 text-decoration-none",
                style="font-weight: 500;",
                onclick="return false;",
            ),
            style=(
                "display: flex; align-items: center; "
                "padding: 0.5rem 1rem; background-color: #d1e7dd; "
                "border-bottom: 1px solid #dee2e6;"
            ),
        )

    @reactive.effect
    @reactive.event(input.explore_completed_run_click)
    async def _navigate_to_explore_from_completion() -> None:
        """Navigate to Explore tab when completion status bar link is clicked."""
        try:
            info = completion_info.get()
            if info:
                explore_config = {
                    "experiment": info["experiment"],
                    "task": info["task"],
                    "csv_path": info["csv_path"]
                }
                # Switch to Explore tab first
                ui.update_navset("main_nav", selected="Explore")
                # Then send config as JSON string to explore tab
                await session.send_custom_message("populate_explore_form", explore_config)
        except Exception as e:
            print(f"Error navigating to explore from completion: {e}")
            import traceback
            traceback.print_exc()
