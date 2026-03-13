"""
Profile tab for Python Shiny GUI.

Profiling performance to find potential mitigations to reshape distributions

Workflow:
1. User selects experiment and task
2. System checks for <basename>-prof.csv (profiling output)
3. If exists: prompt to Use Existing / Re-Profile / Cancel
4. Derive markdown filename and validate for benchmark_spec + backend_options
5. Display distribution characteristics (plot + narrative)
6. Optional: manual classifier training with feature selection

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from shiny import ui, render, reactive, Inputs, Outputs, Session
from shiny.types import SilentException
import polars as pl
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict
import traceback as tb

from src.core.runlogs import load_csv, get_experiments, get_tasks_for_experiment
from src.gui.utils import apply_filter, get_filterable_columns, create_filter_ui
from src.gui.utils.comparisons import render_density_comparison_plot, compute_comparison_summary
from src.gui.utils.profile.tree import *
from src.gui.utils.profile.metrics import *
from src.gui.utils.profile.files import *
from src.gui.utils.profile.cutoff import *
from src.gui.utils.profile.modals import *
from src.gui.utils.profile.execution import *
from src.gui.utils.profile.distribution import *
from src.gui.utils.profile.factors import *
from src.gui.utils.profile.mitigations import *
from src.core.stats.feature_importance import get_ranked_features
from src.core.config import discover_backends
from src.core.config.backend_loader import validate_backend_chain
from src.core.config.settings import Settings
from src.core.metrics.factors import load_factors


def profile_ui() -> ui.TagChild:
    """Create Profile tab UI."""
    return ui.nav_panel(
        "Profile",
        ui.row(
            ui.column(
                2,
                ui.input_select(
                    "profile_experiment",
                    "Experiment",
                    choices={},
                    selected=""
                )
            ),
            ui.column(
                2,
                ui.input_select(
                    "profile_task",
                    "Task",
                    choices={"": "(select task)"},
                    selected=""
                )
            ),
            ui.column(
                2,
                ui.input_selectize(
                    "profile_metric",
                    "Outcome Metric",
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
                    "profile_filter_metric",
                    "Metric to Filter",
                    choices=[],
                    multiple=False,
                    options={
                        'placeholder': 'Type to search or leave empty for no filter...',
                        'loadThrottle': 300,
                        'searchField': ['value', 'label'],
                        'maxOptions': 100,
                    }
                )
            ),
            ui.column(
                2,
                ui.output_ui("profile_filter_ui")
            ),
        ),
        ui.hr(),
        ui.row(
            ui.column(
                3,
                ui.output_ui("profile_input_panel"),
                ui.output_ui("profile_factor_selector"),
                style="display: flex; flex-direction: column;"
            ),
            ui.column(
                5,
                ui.output_plot("profile_distribution_plot", click=True),
                ui.output_ui("profile_distribution_narrative")
            ),
            ui.column(
                4,
                ui.output_plot("profile_tree_plot")
            ),
            style="display: flex; align-items: stretch;"
        ),
        ui.hr(),
        ui.row(
            ui.column(
                3,
                ui.output_ui("profile_factor_tabset"),
                style="display: flex; flex-direction: column;"
            ),
            ui.column(
                5,
                ui.output_plot("profile_factor_vs_perf_plot")
            ),
            ui.column(
                4,
                ui.output_ui("profile_factor_comparison_table")
            ),
            style="display: flex; align-items: stretch;"
        ),
        ui.hr(),
        ui.row(
            ui.column(
                3,
                ui.input_selectize(
                    "profile_mitigation_compare_metric",
                    "Metric to Compare",
                    choices=[],
                    multiple=False,
                    options={
                        'placeholder': 'Select metric...',
                        'loadThrottle': 300,
                        'searchField': ['label'],
                        'maxOptions': 50,
                    }
                ),
            ),
            ui.column(
                4,
                ui.output_plot("profile_mitigation_density_plot")
            ),
            ui.column(
                5,
                ui.output_data_frame("profile_mitigation_comparison_table")
            ),
            style="display: flex; align-items: stretch;"
        ),
    )


def profile_server(input: Inputs, output: Outputs, session: Session) -> None:
    """Implement Profile tab server logic."""

    # ========== COMPUTED STATE ==========
    # Derive metadata paths from the current task selection using pure function
    @reactive.Calc
    def metadata_paths() -> Dict[str, str | None]:
        """
        Compute file paths from current task selection.

        Returns dict with:
        - original_csv: Path to the originally selected CSV (e.g., matmul.csv)
        - original_md: Path to the original markdown file (e.g., matmul.md)
        - prof_csv: Path to profiling CSV (e.g., matmul-prof.csv) if it exists
        - prof_md: Path to profiling markdown (e.g., matmul-prof.md) if it exists
        """
        if not (task_csv := input.profile_task()):
            return {"original_csv": None, "original_md": None, "prof_csv": None, "prof_md": None}

        # detect_file_state handles both original and -prof files correctly
        _state, paths = detect_file_state(task_csv)

        return {
            "original_csv": str(paths["csv"]),
            "original_md": str(paths["md"]),
            "prof_csv": str(paths["prof_csv"]) if paths.get("prof_csv") else None,
            "prof_md": str(paths["prof_md"]) if paths.get("prof_md") else None,
        }
    # ========== END COMPUTED STATE ==========

    # Reactive value for mitigation data (used for comparison)
    mitigation_data = reactive.value(None)

    # Suppress modal display when we programmatically change the task selection
    suppress_modal = reactive.value(False)

    # Note: We do NOT store all metrics to avoid huge websocket payloads
    # Reactive value for suggested cutoff point
    suggested_cutoff = reactive.value(None)

    # Reactive value for user-selected cutoff (overrides suggested cutoff)
    user_cutoff = reactive.value(None)

    # Reactive value for excluded predictors - initialize with defaults
    excluded_predictors = reactive.value(DEFAULT_EXCLUDED_PREDICTORS.copy())

    # Reactive values for predictor exclusion modal
    predictor_modal_filters = reactive.Value({})
    predictor_stats_full = reactive.Value([])

    # Reactive value for profiling parameters (used when confirming overwrite)
    profiling_params = reactive.value(None)

    # Reactive value for selected factor (from tree node click)
    selected_factor = reactive.value(None)

    # Log module initialization
    try:
        discover_backends(profiling=True)
    except Exception:
        import traceback
        traceback.print_exc()

    def _update_selects_to_file(csv_path: str) -> None:
        """Update experiment and task selects to reflect a loaded CSV file."""
        try:
            csv_path_obj = Path(csv_path)
            if csv_path_obj.exists():
                experiment_name = csv_path_obj.parent.name
                experiments = get_experiments()
                suppress_modal.set(True)
                ui.update_select("profile_experiment", choices=experiments, selected=experiment_name)
                tasks = get_tasks_for_experiment(experiment_name)
                if tasks:
                    ui.update_select("profile_task", choices=tasks, selected=str(csv_path))
        except Exception:
            pass  # Ignore errors when updating from external selection

    # --- UI Initialization ---
    # Initialize experiment dropdown on startup
    @reactive.effect
    def _init_experiments():
        experiments = get_experiments()
        # Use experiments as provided; default selection from settings
        choices = experiments
        default_exp = Settings().get("gui.default_experiment", "misc")
        default_sel = default_exp if default_exp in experiments else (next(iter(experiments), ""))
        ui.update_select("profile_experiment", choices=choices, selected=default_sel)

    # Update task dropdown when experiment changes
    @reactive.effect
    def _update_tasks():
        if not (experiment := input.profile_experiment()):
            ui.update_select("profile_task", choices={"": "(select task)"}, selected="")
            return

        if not (tasks := get_tasks_for_experiment(experiment)):
            ui.update_select("profile_task", choices={"": "(no tasks)"}, selected="")
            return

        # Reset task select to force reactive update
        # metadata_paths will recompute automatically from the new selection
        ui.update_select("profile_task", choices=tasks, selected="")

        # Clear stale data from previous experiment
        mitigation_data.set(None)
        selected_factor.set(None)
        user_cutoff.set(None)
        suggested_cutoff.set(None)

    # --- Modal and Profiling Workflow ---
    # Show modal when task selected
    @reactive.effect
    @reactive.event(input.profile_task)
    def _check_prof_file():
        """Show appropriate modal when task is selected."""
        if not (task_csv := input.profile_task()):
            return

        # Reset user cutoff when task changes
        user_cutoff.set(None)

        # If modal display was suppressed due to programmatic selection, consume flag
        if suppress_modal.get():
            suppress_modal.set(False)
            return

        # If user directly selected a -prof.csv file, don't show modal - they already
        # have the profiling data they want. Just use it directly.
        prof_suffix = Settings().get("profile.prof_suffix", "-prof")
        if Path(task_csv).stem.endswith(prof_suffix):
            return

        # metadata_paths is computed automatically from input.profile_task()
        # Show modal with options based on file state
        paths = metadata_paths()
        prof_csv = paths.get("prof_csv")


        # Show the source selection modal
        modal = build_choose_source_modal(prof_csv if prof_csv and Path(prof_csv).exists() else None)
        ui.modal_show(modal)

    # Handle modal button: Cancel / OK
    @reactive.effect
    @reactive.event(input.modal_cancel)
    def _handle_cancel():
        ui.modal_remove()

    # Handle modal button: Error modal OK
    @reactive.effect
    @reactive.event(input.modal_error_ok, ignore_none=True)
    def _handle_error_ok():
        ui.modal_remove()

    # Handle modal button: Use Existing (State 1)
    @reactive.effect
    @reactive.event(input.modal_use_existing)
    def _handle_use_existing():
        """Handle 'Use Existing' button click in modal."""
        paths = metadata_paths()
        prof_csv_path = paths.get('prof_csv')


        if not prof_csv_path:
            ui.modal_remove()
            return

        # Close modal and update selector to the prof file
        # This triggers reactive data loading through csv_data Calc
        ui.modal_remove()
        _update_selects_to_file(prof_csv_path)

    # Handle modal button: Use Original CSV (State 2)
    @reactive.effect
    @reactive.event(input.modal_use_original)
    def _handle_use_original():
        """Handle 'Use Original CSV' button click in modal."""
        paths = metadata_paths()
        original_csv_path = paths.get('original_csv')

        if not original_csv_path:
            ui.modal_remove()
            return

        # Close modal and update selector to the original file
        # This triggers reactive data loading through csv_data Calc
        ui.modal_remove()
        _update_selects_to_file(original_csv_path)

    # Handle modal button: Run Profiling (Profile Task button from choose source modal)
    @reactive.effect
    @reactive.event(input.modal_run_profiling)
    def _handle_run_profiling():
        paths = metadata_paths()
        md_path = paths.get("original_md")

        if not md_path or not Path(md_path).exists():
            ui.notification_show(
                "Cannot profile: metadata file (.md) not found",
                type="error",
                duration=5
            )
            ui.modal_remove()
        elif not validate_markdown(md_path)[0]:
            ui.notification_show(
                "Cannot profile: metadata file is invalid or incomplete",
                type="error",
                duration=5
            )
            ui.modal_remove()
        else:
            # Show configuration modal
            modal = build_configure_modal(prof_md=md_path)
            ui.modal_show(modal)

    # Handle modal button: Start Profiling (State 4)
    @reactive.effect
    @reactive.event(input.modal_start_profiling)
    def _handle_start_profiling():
        """Handle Start Profiling button - validate, determine task name, and execute."""
        try:
            selected_backends = list(input.profile_backends_selector())
            if not selected_backends:
                return

            paths = metadata_paths()
            md_path = paths.get("original_md")

            if not md_path or not Path(md_path).exists():
                ui.notification_show(
                    "Cannot profile: metadata file not found",
                    type="error",
                    duration=5
                )
                return

            is_valid, error = validate_markdown(md_path)
            if not is_valid:
                ui.notification_show(
                    "Cannot profile: metadata file is invalid or incomplete",
                    type="error",
                    duration=5
                )
                return

            # Validate backend composability
            profiling_backends = discover_backends(profiling=True)
            is_valid, error_msg = validate_backend_chain(selected_backends, profiling_backends)
            if not is_valid:
                modal = build_invalid_backend_modal(error_msg)
                ui.modal_show(modal)
                return

            # Determine task name from user input or use helper
            user_task_name = input.profile_task_name() if hasattr(input, 'profile_task_name') else None
            new_task_name = user_task_name if user_task_name else determine_task_name_for_profiling(md_path)

            # Store parameters and execute immediately
            profiling_params.set({
                "backends": selected_backends,
                "md_path": md_path,
                "task_name": new_task_name
            })

            ui.modal_remove()
            _execute_profiling_run()

        except Exception:
            tb.print_exc()

    # Handle overwrite confirmation: Cancel
    @reactive.effect
    @reactive.event(input.modal_cancel_overwrite)
    def _handle_cancel_overwrite():
        ui.modal_remove()
        profiling_params.set(None)  # Clear stored parameters

    # Handle overwrite confirmation: Confirm
    @reactive.effect
    @reactive.event(input.modal_confirm_overwrite)
    def _handle_confirm_overwrite():
        ui.modal_remove()
        _execute_profiling_run()

    def _execute_profiling_run():
        """Execute the profiling run with stored parameters and update UI."""
        params = profiling_params.get()
        if not params:
            return

        backends = params["backends"]
        md_path = params["md_path"]
        task_name = params["task_name"]

        # Create progress bar
        progress = ui.Progress()
        progress.set(value=0, message=f"Starting profiling with {len(backends)} backend(s)...")

        # Create executor
        executor = ProfilingExecutor(md_path, backends, task_name)

        # Define progress callback
        def on_progress(iteration: int, total: int):
            progress.set(
                value=iteration / total if total > 0 else 0,
                message=f"Profiling: iteration {iteration}/{total}"
            )

        # Define completion callback
        def on_complete(success: bool, result_dict: dict):
            progress.close()

            if success:
                ui.notification_show(
                    "✓ Profiling completed successfully! Loading results...",
                    type="message",
                    duration=5
                )

                # Load profiling results
                prof_csv = result_dict.get("output_paths", {}).get("csv")

                if prof_csv:
                    # Update task selector to point to the new prof file
                    # This triggers metadata_paths recomputation and data loading
                    try:
                        prof_path_obj = Path(prof_csv)
                        if prof_path_obj.exists():
                            experiment_name = prof_path_obj.parent.name
                            experiments = get_experiments()
                            suppress_modal.set(True)
                            ui.update_select("profile_experiment", choices=experiments, selected=experiment_name)
                            tasks = get_tasks_for_experiment(experiment_name)
                            if tasks:
                                ui.update_select("profile_task", choices=tasks, selected=str(prof_csv))

                            ui.notification_show(
                                "✓ Profiling results loaded",
                                type="message",
                                duration=5
                            )
                    except Exception:
                        ui.notification_show(
                            "Profiling completed but failed to load results",
                            type="warning",
                            duration=10
                        )
            else:
                error_msg = result_dict.get("error_message", "Unknown error")
                ui.notification_show(
                    f"✗ Profiling failed: {error_msg}",
                    type="error",
                    duration=10
                )

        # Set callbacks and execute
        executor.set_callbacks(on_progress=on_progress, on_complete=on_complete)
        executor.execute()

    # --- Data Loading and Paths ---
    # Load and validate profiling data when task changes
    @reactive.Calc
    def csv_data():
        """Load CSV data for the currently selected task."""
        if not (task_csv := input.profile_task()):
            return None

        try:
            return load_csv(task_csv)
        except Exception:
            return None

    @reactive.Calc
    def prof_csv_path():
        """Get the prof_csv path if it exists."""
        paths = metadata_paths()
        prof_csv = paths.get("prof_csv")
        # Only return if the file actually exists
        if prof_csv and Path(prof_csv).exists():
            return prof_csv
        return None

    @reactive.Calc
    def prof_csv_data():
        """Load -prof CSV if it exists."""
        if not (prof_path := prof_csv_path()):
            return None

        try:
            return load_csv(prof_path)
        except Exception:
            return None

    @reactive.Calc
    def markdown_path():
        """Derive markdown path from selected CSV."""
        paths = metadata_paths()
        # If we have prof data, use prof_md; otherwise use original_md
        if prof_csv_path():
            return paths.get("prof_md")
        return paths.get("original_md")

    @reactive.Calc
    def markdown_valid():
        """Check if markdown file is valid."""
        if not (md_path := markdown_path()):
            return None

        is_valid, error_msg = validate_markdown(md_path)
        return {"valid": is_valid, "error": error_msg}

    # --- Cutoff Management ---
    @reactive.effect
    def _compute_suggested_cutoff():
        """Compute suggested cutoff whenever profiling data loads."""
        data = active_data()
        metric_col = validated_metric()

        cutoff = compute_suggested_cutoff(data, metric_col)
        suggested_cutoff.set(cutoff)

    @reactive.effect
    def _validate_cutoff_in_range():
        """Reset user cutoff if it's out of range (no points on either side) when filter changes."""
        data = active_data()
        metric_col = validated_metric()
        current_user_cutoff = user_cutoff()

        # Only check if we have data, metric, and a user-set cutoff
        if data is None or not metric_col or current_user_cutoff is None:
            return

        # Check if cutoff is out of range (all points on one side)
        n_below, n_above = validate_cutoff_range(data, metric_col, current_user_cutoff)

        if n_below == 0 or n_above == 0:
            # Reset to suggested cutoff
            user_cutoff.set(None)
            # Trigger recalculation of suggested cutoff
            new_cutoff = compute_suggested_cutoff(data, metric_col)
            suggested_cutoff.set(new_cutoff)

    # --- Metric and Filter Inputs ---
    @reactive.effect
    def _update_metric_choices():
        """Update metric choices when data loads (server-side selectize with empty string sentinel)."""
        try:
            # Use base_data() not active_data() to avoid dependency on filter
            # We want all metrics available regardless of filter
            if (data := base_data()) is None:
                ui.update_selectize("profile_metric", choices=[], selected=None, server=True)
                return

            try:
                is_empty = data.is_empty()
            except:
                is_empty = True


            if is_empty:
                ui.update_selectize("profile_metric", choices=[], selected=None, server=True)
                return

            # Get all numeric columns using utility function
            numeric_cols = get_numeric_columns(data)

            if not numeric_cols:
                ui.update_selectize("profile_metric", choices=[], selected=None, server=True)
                return

            # Prepend empty string as sentinel to prevent auto-selection
            PLACEHOLDER = ""
            choices_with_placeholder = [PLACEHOLDER] + sorted(numeric_cols)

            # Select default metric from preferred list (perf_time, inner_time, outer_time)
            # Returns empty string if none found
            default_metric = select_default_metric(data)
            selected_metric = default_metric if default_metric else PLACEHOLDER

            # Update selectize with server-side rendering
            # Empty string will be auto-selected if no preferred metric found
            try:
                ui.update_selectize("profile_metric", choices=choices_with_placeholder, selected=selected_metric, server=True)
            except Exception:
                import traceback
                traceback.print_exc()

        except Exception:
            import traceback
            traceback.print_exc()
            try:
                ui.update_selectize("profile_metric", choices=[], selected=None, server=True)
            except Exception:
                pass  # Ignore cleanup errors

    @reactive.effect
    @reactive.event(input.profile_metric)  # Only trigger when outcome metric INPUT changes
    def _update_filter_choices():
        """Update filter choices when metric changes (server-side with placeholder to prevent auto-filtering)."""
        try:
            # Only populate filter choices when a valid outcome metric is selected
            metric_col = validated_metric()

            if not metric_col or metric_col.strip() == "":
                ui.update_selectize("profile_filter_metric", choices=[], selected=None, server=True)
                return

            if (data := base_data()) is None:
                ui.update_selectize("profile_filter_metric", choices=[], selected=None, server=True)
                return

            try:
                is_empty = data.is_empty()
            except:
                is_empty = True

            if is_empty:
                ui.update_selectize("profile_filter_metric", choices=[], selected=None, server=True)
                return

            # Get filterable columns using utility function
            filterable = get_filterable_columns(data)

            # Prepend a placeholder option that will be auto-selected but won't trigger filtering
            PLACEHOLDER = ""  # Empty string as placeholder - will be auto-selected but means "no filter"
            choices_with_placeholder = [PLACEHOLDER] + filterable

            # Use server-side selectize with placeholder as first item
            ui.update_selectize("profile_filter_metric", choices=choices_with_placeholder, selected=PLACEHOLDER, server=True)

        except Exception:
            import traceback
            traceback.print_exc()
            # Try to clear the filter choices on error
            try:
                ui.update_selectize("profile_filter_metric", choices=[], selected=None, server=True)
            except:
                pass

    @output
    @render.ui
    def profile_filter_ui():
        """Render dynamic filter UI based on selected metric."""
        filter_metric = input.profile_filter_metric()

        # Treat empty string as "no filter selected" (it's our placeholder to prevent auto-filtering)
        if not filter_metric or filter_metric.strip() == "":
            return None

        data = base_data()
        if data is None:
            return None

        try:
            result = create_filter_ui(data, filter_metric, "profile_filter_value")
            return result
        except Exception:
            import traceback
            traceback.print_exc()
            return None

    # --- Cutoff Interaction ---
    # Handle plot click to set custom cutoff
    @reactive.effect
    def _handle_plot_click():
        """Update cutoff when user clicks on distribution plot."""
        click_data = input.profile_distribution_plot_click()
        if click_data is not None and "x" in click_data:
            # Extract x-coordinate from click event
            new_cutoff = float(click_data["x"])
            user_cutoff.set(new_cutoff)

    # Handle search for cutoff button
    @reactive.effect
    @reactive.event(input.search_cutoff_btn)
    def _search_cutoff_space():
        """Search for effective cutoff point that minimizes AIC."""
        data = active_data()
        metric_col = validated_metric()

        if data is None or data.is_empty() or not metric_col:
            return


        # Get settings
        settings = Settings()
        max_search_points = settings.get("profiling.max_search", 100)

        # Get excluded predictors
        current_exclusions = excluded_predictors()

        # Show progress bar
        with ui.Progress(min=0, max=max_search_points) as p:
            p.set(message=f"Searching {len(data):,} rows...", detail="Starting search...")

            # Define progress callback to update the progress bar
            def update_progress(progress_pct: float, detail: str):
                value = int(progress_pct * max_search_points)
                p.set(value=value, detail=detail)

            # Perform search using utility function
            best_cutoff = search_optimal_cutoff(
                data,
                metric_col,
                current_exclusions,
                max_search_points=max_search_points,
                progress_callback=update_progress
            )

            if best_cutoff is not None:
                user_cutoff.set(best_cutoff)
                p.set(message="Search complete!", value=max_search_points, detail=f"Best cutoff: {best_cutoff:.4f}")
            else:
                p.set(message="No optimal cutoff found", value=max_search_points, detail="")

    # --- Model Training ---
    @reactive.Calc
    def computed_trained_tree():
        """
        Compute trained decision tree whenever metric, cutoff, or exclusions change.
        Only trains after metric is selected.

        Dependencies:
        - input.profile_metric(): outcome metric (changes when dataset changes)
        - excluded_predictors(): excluded predictor list
        - user_cutoff(): manually set cutoff point
        - suggested_cutoff(): automatically computed cutoff
        - prof_csv_path(): current dataset file path
        - active_data(): current dataset
        """
        # EXPLICIT dependencies - reading these creates reactivity
        metric_col = validated_metric()
        current_exclusions = excluded_predictors()
        user_cutoff_val = user_cutoff()
        suggested_cutoff_val = suggested_cutoff()


        # Early exit: metric not selected
        if not metric_col or metric_col.strip() == "":
            return None

        data = active_data()

        # Early exit: no data
        try:
            is_empty = data.is_empty() if data is not None else True
        except:
            is_empty = True

        if data is None or is_empty:
            return None

        # Early exit: metric not in data
        if metric_col not in data.columns:
            return None

        # Get cutoff value (prefer user-set, fall back to suggested)
        cutoff_value = user_cutoff_val if user_cutoff_val is not None else suggested_cutoff_val

        if cutoff_value is None:
            return None

        try:
            # Get max_predictors and max_correlation from modal filters (if set)
            # Otherwise use defaults from settings
            modal_filters = predictor_modal_filters.get()
            max_predictors = modal_filters.get("max_predictors") if modal_filters else None
            max_correlation = modal_filters.get("max_corr") if modal_filters else None

            if max_predictors is None:
                max_predictors = Settings().get("profiling.max_predictors", 100)
            if max_correlation is None:
                max_correlation = Settings().get("profiling.max_correlation", 0.99)

            tree = compute_tree(data, metric_col, float(cutoff_value),
                                   exclude=current_exclusions,
                                   max_predictors=max_predictors,
                                   max_correlation=max_correlation)
            return tree

        except Exception:
            import traceback
            traceback.print_exc()
            return None

    # --- Predictor Exclusion Modal ---

    # Create the predictor table UI renderer
    create_predictor_exclusion_ui(input, output, excluded_predictors, predictor_stats_full, predictor_modal_filters)

    @reactive.Calc
    def base_data():
        """Get the base dataset (prof or csv) without filtering."""
        try:
            return prof_csv_data() if prof_csv_path() else csv_data()
        except Exception:
            return None

    @reactive.Calc
    def original_baseline_data():
        """Get the original baseline dataset (not profiling) for mitigation comparison.

        This loads the original CSV (e.g., matmul.csv) even when viewing profiling data
        (e.g., matmul-prof.csv). Used for comparing mitigation results against the
        original baseline, not against the profiling run.
        """
        try:
            paths = metadata_paths()
            original_csv = paths.get("original_csv") if paths else None

            if not original_csv:
                return None

            # Load the original CSV
            data = load_csv(original_csv)
            return data
        except Exception:
            return None

    def filter_value():
        """Get current filter value, or None if input doesn't exist yet."""
        try:
            return input.profile_filter_value()
        except Exception:
            return None

    @reactive.Calc
    def active_data():
        """Get the currently active dataset (profiling or original), with filtering applied."""
        if (data := base_data()) is None:
            return None
        return apply_filter(data, input.profile_filter_metric(), filter_value())

    @reactive.Calc
    def validated_metric():
        """Get validated metric from active data columns. Returns empty string if invalid."""
        try:
            metric = input.profile_metric()
            if not metric or metric.strip() == "":
                return ""

            # Check active data directly (server-side mode)
            data = active_data()
            if data is None or metric not in data.columns:
                return ""

            # Confirm it's numeric
            dtype = data[metric].dtype
            if dtype not in (pl.Float64, pl.Int64):
                return ""

            return metric
        except Exception:
            import traceback
            traceback.print_exc()
            return ""

    # Reactive computation of predictor stats - automatically recomputes when metric or data changes
    @reactive.Calc
    def predictor_stats():
        """Compute predictor statistics for all potential predictors (after variance filter).

        We compute for all predictors with variance > 0, not just the top N, to ensure
        that any predictor that appears in the tree can be excluded via the modal.
        However, we still apply variance filtering first to eliminate constants.
        """
        data = active_data()
        metric_col = validated_metric()

        if data is None or data.is_empty() or not metric_col:
            return []

        # Get all potential predictors (exclude metric, start, task, and constants)
        # Use Polars batch n_unique() for efficiency instead of per-column loop
        exclude_cols = {metric_col, "start", "task"}
        candidate_cols = [c for c in data.columns if c not in exclude_cols]

        # Batch compute n_unique for all columns at once
        n_unique_expr = [pl.col(c).n_unique().alias(c) for c in candidate_cols]
        n_unique_counts = data.select(n_unique_expr).row(0)

        # Filter to columns with n_unique > 1
        potential_predictors = [
            col for col, n_uniq in zip(candidate_cols, n_unique_counts) if n_uniq > 1
        ]

        # Compute stats for all of them
        # Use sampling to speed up correlation computation (1000 rows like R version)
        stats_rows = compute_predictor_stats(data, metric_col, potential_predictors)

        return stats_rows

    # Eagerly populate predictor_stats_full when stats are computed
    # This ensures the modal table has data immediately when opened
    @reactive.effect
    def _update_predictor_stats_full():
        """Update predictor_stats_full whenever predictor_stats changes."""
        stats = predictor_stats()
        if stats:
            predictor_stats_full.set(stats)

    @reactive.effect
    @reactive.event(input.exclude_predictors_btn)
    def _show_exclude_predictors_modal():
        """Open predictor exclusion modal."""
        data = active_data()
        metric = validated_metric()

        if data is None or data.is_empty() or not metric:
            return

        # Stats should already be in predictor_stats_full thanks to the effect above
        # Just show the modal - the table will render from predictor_stats_full
        build_predictor_exclusion_modal(data, metric, predictor_stats_full, predictor_modal_filters, None)

    @reactive.effect
    @reactive.event(input.apply_predictor_exclusions)
    def _apply_predictor_exclusions():
        """Apply predictor exclusions when Apply button is clicked."""
        apply_exclusions(input, excluded_predictors, predictor_stats_full, predictor_modal_filters)

    # UI outputs

    @output
    @render.ui
    def profile_input_panel():
        """Left panel for user controls and filtering."""
        data = active_data()

        # Only show button if data is loaded
        if data is None or data.is_empty():
            return ui.div(
                ui.tags.p(ui.tags.strong("Analysis Controls"), style="margin-bottom: 15px;"),
                ui.tags.p("Load data to access controls", style="color: #999; font-size: 0.9em;"),
                style="padding: 15px; background-color: #f8f9fa; border-radius: 5px;"
            )

        return ui.div(
            ui.tags.p(ui.tags.strong("Analysis Controls"), style="margin-bottom: 15px;"),
            ui.input_action_button(
                "exclude_predictors_btn",
                "Exclude Predictors",
                class_="btn-secondary btn-sm",
                icon=ui.tags.span(ui.tags.i(class_="bi bi-table"), "\u00A0")
            ),
            ui.tags.p(
                f"Excluded: {len(excluded_predictors())} predictors",
                style="color: #666; font-size: 0.85em; margin-top: 10px;"
            ),
            ui.tags.hr(style="margin: 15px 0;"),
            ui.tags.p("Click on density plot to change cutoff", style="font-size: 0.9em; margin-bottom: 10px;"),
            ui.input_action_button(
                "search_cutoff_btn",
                "Search for Cutoff",
                class_="btn-secondary",
                icon=ui.tags.span(ui.tags.i(class_="bi bi-search"), "\u00A0")
            ),
            ui.tags.p(
                "Exhaustive search to minimize AIC",
                style="color: #666; font-size: 0.85em; margin-top: 10px;"
            ),
            style="padding: 15px; background-color: #f8f9fa; border-radius: 5px;"
        )

    @output
    @render.plot
    def profile_distribution_plot():
        """Render distribution plot using helper function."""
        data = active_data()
        metric_col = validated_metric()

        # Use user-selected cutoff if available, otherwise use suggested cutoff
        cutoff = user_cutoff.get() if user_cutoff.get() is not None else suggested_cutoff.get()

        # Let render_distribution_plot handle standby messages for missing data/metric
        return render_distribution_plot(data, metric_col, cutoff)

    @output
    @render.ui
    def profile_distribution_narrative():
        """Show distribution narrative using helper function."""
        data = active_data()
        metric_col = validated_metric()

        if not metric_col:
            return ui.div()

        return render_distribution_narrative(data, metric_col)

    @output
    @render.plot
    def profile_tree_plot():
        """Render decision tree visualization with custom styling."""
        try:
            # Compute tree on-demand (like R version) - avoids cascade issues
            tree = computed_trained_tree()

            # Get colors from settings
            settings = Settings()
            dist_colors = settings.get("gui.distribution", {})
            left_color = dist_colors.get("left_color", "#2ca02c")  # Better class
            right_color = dist_colors.get("right_color", "#ff7f0e")  # Worse class

            return render_tree_plot(tree, left_color, right_color)
        except Exception:
            import traceback
            traceback.print_exc()
            return None

    @output
    @render.ui
    def profile_factor_selector():
        """Render dropdown selector for factors used in the tree."""
        try:
            tree = computed_trained_tree()
            if tree is None:
                return ui.p(
                    'Train a tree to select factors',
                    style='color: #999; padding: 10px; text-align: center; font-size: 0.9em;'
                )

            # Get feature names from the tree
            if not hasattr(tree, 'feature_names_'):
                return ui.p(
                    'Tree has no feature names',
                    style='color: #999; padding: 10px;'
                )

            feature_names = tree.feature_names_
            if not feature_names:
                return ui.p(
                    'No features in tree',
                    style='color: #999; padding: 10px;'
                )

            # Sort features by importance (descending)
            try:
                ranked_features = get_ranked_features(tree)
                # Extract just the feature names in importance order
                sorted_names = [name for name, score in ranked_features]
            except Exception:
                # Fallback to alphabetical sort
                sorted_names = sorted(feature_names)

            # Create choices dict with empty option first
            choices = {"": "(select a factor)"} | {name: name for name in sorted_names}

            return ui.card(
                ui.input_selectize(
                    "profile_selected_factor",
                    "Select Factor to Analyze:",
                    choices=choices,
                    selected="",
                    options={
                        'placeholder': 'Choose a factor from the tree...',
                        'maxOptions': 100,
                    }
                ),
                style='background-color: #f8f9fa; padding: 10px; flex: 1; display: flex; flex-direction: column;'
            )

        except Exception as e:
            tb.print_exc()
            return ui.p(f'Error: {str(e)}', style='color: red;')

    # Handler for factor selection from dropdown
    @reactive.effect
    @reactive.event(input.profile_selected_factor)
    def _handle_factor_selection():
        """Handle factor selection from dropdown."""
        try:
            factor_name = input.profile_selected_factor()
            if factor_name and factor_name.strip():
                selected_factor.set(factor_name)
        except Exception:
            tb.print_exc()

    @output
    @render.ui
    def profile_factor_tabset():
        """Render factor description and mitigation tabs (only when factor selected)."""
        try:
            factor_name = selected_factor()
            if not factor_name:
                return ui.tags.div()  # Empty div when no factor selected

            return ui.tags.div(
                ui.navset_tab(
                    ui.nav_panel(
                        "Factor description",
                        ui.output_ui("profile_factor_info_card")
                    ),
                    ui.nav_panel(
                        "Suggested mitigations",
                        ui.output_ui("profile_mitigation_selector"),
                        ui.output_ui("profile_mitigation_info_card")
                    ),
                    id="profile_factor_tab"
                ),
                style="flex: 1; display: flex; flex-direction: column;"
            )

        except Exception as e:
            tb.print_exc()
            return ui.p(f'Error: {str(e)}', style='color: red;')

    @output
    @render.ui
    def profile_factor_info_card():
        """Render factor information card using helper function."""
        try:
            factor_name = selected_factor()
            if not factor_name:
                return ui.p(
                    'Click on the tree visualization to select a factor',
                    style='color: #999; padding: 20px; text-align: center;'
                )

            return render_factor_info_card(factor_name)

        except Exception as e:
            tb.print_exc()
            return ui.p(f'Error: {str(e)}', style='color: red;')

    @output
    @render.plot
    def profile_factor_vs_perf_plot():
        """Render scatter plot using helper function."""
        try:
            factor_name = selected_factor()
            if not factor_name:
                # Return empty plot with instruction
                fig, ax = plt.subplots(figsize=(10, 6))
                ax.text(0.5, 0.5, 'Select a factor from the tree to view relationship',
                       ha='center', va='center', fontsize=12, color='#999')
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.axis('off')
                return fig

            data = active_data()
            metric = validated_metric()
            cutoff_val = user_cutoff() if user_cutoff() is not None else suggested_cutoff()

            return render_factor_scatter_plot(data, factor_name, metric, cutoff_val)

        except Exception as e:
            tb.print_exc()
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, f'Error: {str(e)}',
                   ha='center', va='center', fontsize=12, color='red')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            return fig

    @output
    @render.ui
    def profile_factor_comparison_table():
        """Render comparison table using helper function."""
        try:
            factor_name = selected_factor()
            if not factor_name:
                return ui.p(
                    'Select a factor to view group comparison',
                    style='color: #999; padding: 20px; text-align: center;'
                )

            data = active_data()
            metric = validated_metric()
            cutoff_val = user_cutoff() if user_cutoff() is not None else suggested_cutoff()

            return render_factor_comparison_table(data, factor_name, metric, cutoff_val)

        except Exception as e:
            tb.print_exc()
            return ui.p(f'Error: {str(e)}', style='color: red;')

    @output
    @render.ui
    def profile_mitigation_selector():
        """Render dropdown selector for mitigations related to selected factor."""
        try:
            factor_name = selected_factor()
            return render_mitigation_selector(factor_name)

        except Exception as e:
            tb.print_exc()
            return ui.p(f'Error: {str(e)}', style='color: red;')

    @output
    @render.ui
    def profile_mitigation_info_card():
        """Render mitigation information card."""
        try:
            mitigation_name = input.profile_selected_mitigation()
            return render_mitigation_info_card(mitigation_name)
        except SilentException:
            # Input not yet created - this is normal during initial render
            # SilentException MUST be caught BEFORE generic Exception
            return render_mitigation_info_card(None)
        except Exception as e:
            tb.print_exc()
            return ui.p(f'Error: {str(e)}', style='color: red;')

    # Handler for "Try it!" button
    @reactive.effect
    @reactive.event(input.profile_try_mitigation)
    def _handle_try_mitigation():
        """Handle try mitigation button click - check existence and show modal."""
        try:
            mitigation_name = input.profile_selected_mitigation()
            original_md = (metadata_paths() or {}).get('original_md')

            if not mitigation_name:
                return

            if not original_md:
                ui.notification_show(
                    "No experiment data available",
                    type="error",
                    duration=5
                )
                return

            # Construct mitigation filename: <basename>-<mitigation>.csv
            original_md_path = Path(original_md)
            mitigation_csv = original_md_path.parent / f"{original_md_path.stem}-{mitigation_name}.csv"

            # Check if mitigation can be automated (backend_options contains this mitigation)
            all_factors = load_factors()
            mitigations = all_factors.get('mitigations', {})
            mitigation_info = mitigations.get(mitigation_name, {})
            is_automated = mitigation_info.get('backend') is not None

            # Show modal
            m = build_try_mitigation_modal(
                mitigation_exists=mitigation_csv.exists(),
                is_automated=is_automated
            )
            ui.modal_show(m)
        except Exception as e:
            tb.print_exc()
            ui.notification_show(
                f"Error: {str(e)}",
                type="error",
                duration=5
            )

    # Handler for "Use data" button in mitigation modal
    @reactive.effect
    @reactive.event(input.profile_use_mitigation_data)
    def _handle_use_mitigation_data():
        """Load existing mitigation data."""
        try:
            mitigation_name = input.profile_selected_mitigation()
            original_md = (metadata_paths() or {}).get('original_md')

            if not mitigation_name or not original_md:
                return

            original_md_path = Path(original_md)
            mitigation_csv = original_md_path.parent / f"{original_md_path.stem}-{mitigation_name}.csv"

            if mitigation_csv.exists():
                mit_data = load_csv(str(mitigation_csv))
                # Store mitigation data
                mitigation_data.set(mit_data)
                ui.notification_show(
                    f"Loaded mitigation data from {mitigation_csv.name}",
                    type="message",
                    duration=5
                )

            ui.modal_remove()

        except Exception as e:
            tb.print_exc()
            ui.notification_show(
                f"Error loading mitigation data: {str(e)}",
                type="error",
                duration=5
            )

    # Handler for "Run it!" / "Rerun it" button in mitigation modal
    @reactive.effect
    @reactive.event(input.profile_run_mitigation)
    def _handle_run_mitigation():
        """Run SHARP with mitigation applied."""
        try:
            mitigation_name = input.profile_selected_mitigation()
            original_md = (metadata_paths() or {}).get('original_md')

            if not mitigation_name or not original_md:
                return

            md_path = Path(original_md)

            # Construct task name: <basename>-<mitigation>
            task_name = f"{md_path.stem}-{mitigation_name}"

            # Check if mitigation is automated (backend_options contains this mitigation)
            all_factors = load_factors()
            mitigations = all_factors.get('mitigations', {})
            mitigation_info = mitigations.get(mitigation_name, {})
            backend_name = mitigation_info.get('backend')
            is_automated = backend_name is not None

            # Determine backends to use
            backends = [backend_name] if is_automated and backend_name else []

            ui.modal_remove()

            # Show progress bar and run
            progress = ui.Progress()
            progress.set(value=0, message=f"Running benchmark with mitigation: {mitigation_name}...")

            # Create executor
            executor = ProfilingExecutor(str(md_path), backends, task_name)

            # Define progress callback
            def on_progress(iteration: int, total: int):
                progress.set(
                    value=iteration / total if total > 0 else 0,
                    message=f"Mitigation {mitigation_name}: iteration {iteration}/{total}"
                )

            # Define completion callback
            def on_complete(success: bool, result_dict: dict):
                progress.close()

                if success:
                    ui.notification_show(
                        "✓ Mitigation completed! Loading results...",
                        type="message",
                        duration=5
                    )

                    # Load mitigation results
                    mit_csv = md_path.parent / f"{md_path.stem}-{mitigation_name}.csv"

                    if mit_csv.exists():
                        mit_data = load_csv(str(mit_csv))
                        mitigation_data.set(mit_data)
                    else:
                        ui.notification_show(
                            f"Mitigation completed but output file not found: {mit_csv.name}",
                            type="warning",
                            duration=10
                        )
                else:
                    error_msg = result_dict.get("error_message", "Unknown error")
                    ui.notification_show(
                        f"✗ Mitigation failed: {error_msg}",
                        type="error",
                        duration=10
                    )

            # Set callbacks and execute
            executor.set_callbacks(on_progress=on_progress, on_complete=on_complete)
            executor.execute()

        except Exception as e:
            tb.print_exc()
            ui.notification_show(
                f"Error running mitigation: {str(e)}",
                type="error",
                duration=5
            )

    # Handler for "Cancel" button in mitigation modal
    @reactive.effect
    @reactive.event(input.profile_cancel_mitigation)
    def _handle_cancel_mitigation():
        """Cancel mitigation modal."""
        ui.modal_remove()

    # Update mitigation comparison metric choices when data loads
    @reactive.effect
    @reactive.event(mitigation_data)
    def _update_mitigation_metric_choices():
        """Update mitigation comparison metric dropdown when mitigation data loads."""
        mit_data = mitigation_data.get()
        # Use original baseline for comparison, not profiling data
        base = original_baseline_data()

        if mit_data is None or base is None:
            ui.update_selectize('profile_mitigation_compare_metric', choices=[], selected=None, server=True)
            return

        # Find common numeric columns (exclude metadata)
        metadata_cols = {'rank', 'repeat', 'benchmark'}
        base_cols = set(base.columns) - metadata_cols
        mit_cols = set(mit_data.columns) - metadata_cols
        common_metrics = sorted(list(base_cols & mit_cols))

        # Filter to numeric columns only
        numeric_metrics = [m for m in common_metrics if base[m].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32)]

        if numeric_metrics:
            # Default to current selected metric if available, otherwise prefer inner_time
            current_metric = validated_metric()
            default = current_metric if current_metric in numeric_metrics else (
                'inner_time' if 'inner_time' in numeric_metrics else numeric_metrics[0]
            )
            ui.update_selectize('profile_mitigation_compare_metric', choices=numeric_metrics, selected=default, server=True)
        else:
            ui.update_selectize('profile_mitigation_compare_metric', choices=[], selected=None, server=True)

    # Mitigation comparison outputs
    @output
    @render.plot
    def profile_mitigation_density_plot():
        """Render density comparison plot for baseline vs mitigation."""
        mit_data = mitigation_data.get()
        base = original_baseline_data()
        metric = input.profile_mitigation_compare_metric()

        if mit_data is None or base is None or not metric:
            return None

        filter_metric = input.profile_filter_metric()
        fval = filter_value()

        try:
            baseline_vals = apply_filter(base, filter_metric, fval)[metric].to_numpy()
            mitigation_vals = apply_filter(mit_data, filter_metric, fval)[metric].to_numpy()
            return render_density_comparison_plot(baseline_vals, mitigation_vals, metric=metric)
        except Exception as e:
            print(f"[ERROR] profile_mitigation_density_plot: {e}")
            tb.print_exc()
            return None

    @output
    @render.data_frame
    def profile_mitigation_comparison_table():
        """Render comparison statistics table for baseline vs mitigation."""
        mit_data = mitigation_data.get()
        base = original_baseline_data()
        metric = input.profile_mitigation_compare_metric()

        if mit_data is None or base is None or not metric:
            return None

        filter_metric = input.profile_filter_metric()
        fval = filter_value()

        try:
            baseline_vals = apply_filter(base, filter_metric, fval)[metric].to_numpy()
            mitigation_vals = apply_filter(mit_data, filter_metric, fval)[metric].to_numpy()

            # Compute summary statistics
            summary = compute_comparison_summary(baseline_vals, mitigation_vals, digits=10, sig_figs=3)

            # Create DataFrame for display
            table_data = {
                'Statistic': summary['statistic_names'],
                'Baseline': summary['baseline'],
                'Mitigation': summary['treatment'],
                '% Change': summary['pct_change']
            }
            return pl.DataFrame(table_data)

        except Exception as e:
            print(f"[ERROR] profile_mitigation_comparison_table: {e}")
            tb.print_exc()
            return None
