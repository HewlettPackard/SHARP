"""
Factor analysis UI state management for profile tab.

Handles reactive effects and output rendering for factor selection,
analysis cards, scatter plots, comparison tables, and bootstrap CI
computation.  Follows the same extraction pattern as labeler_ui.py.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import traceback as tb
from dataclasses import replace
from typing import Any, Callable

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from shiny import reactive, render, ui, Inputs, Outputs, Session
from shiny.types import SilentException

from src.core.profile.analyzers.registry import create_analyzer_registry, DataContext
from src.gui.utils.profile.analysis import (
    compute_tree_factor_bootstrap_ci,
    get_bootstrap_ci_sample_count,
)
from src.gui.utils.profile.factors import (
    factor_key,
    factor_label,
    get_factor_by_key,
    render_factor_scatter_plot,
    render_factor_comparison_table,
    render_factor_info_card,
)
from src.gui.utils.profile.labeler_ui import render_cutoff_actions
from src.gui.utils.profile.mitigations import (
    render_mitigation_selector,
    render_mitigation_info_card,
)
from src.gui.utils.profile.visualizers import (
    get_visualizer_for,
    build_analysis_narrative_html,
)


def _build_data_context(
    data: Any,
    labeler: Any,
    settings: Any,
) -> DataContext:
    """Derive data characteristics for analyzer ranking from the current UI state.

    Detects timestamp presence, row/predictor counts, and regression vs.
    classification mode so the analyzer dropdown can be ordered by fit.

    Args:
        data: Active DataFrame (may be None or empty).
        labeler: Current PerformanceLabeler (None when no data is loaded).
        settings: Settings view from the active experiment markdown.

    Returns:
        :class:`DataContext` summarising the key data properties.
    """
    import polars as pl
    from src.core.profile.labeler import RegressionLabeler

    if data is None:
        return DataContext()
    try:
        if data.is_empty():
            return DataContext()
    except Exception:
        return DataContext()

    # Detect a usable timestamp column.
    has_timestamp = "timestamp" in data.columns
    if not has_timestamp:
        for col in data.columns:
            try:
                if data[col].dtype in (
                    pl.Datetime,
                    pl.Date,
                    pl.Time,
                ):
                    has_timestamp = True
                    break
            except Exception:
                pass
    if not has_timestamp and settings is not None:
        try:
            ts_col = settings.get(
                "profiling.lag_detection.timestamp_column", None
            )
            has_timestamp = isinstance(ts_col, str) and ts_col in data.columns
        except Exception:
            pass

    n_rows = data.shape[0]
    n_predictors = max(0, data.shape[1] - 1)
    outcome_mode = "regression" if isinstance(labeler, RegressionLabeler) else "classification"

    return DataContext(
        has_timestamp=has_timestamp,
        n_rows=n_rows,
        n_predictors=n_predictors,
        outcome_mode=outcome_mode,
    )


def _generate_analyzer_tooltips_script() -> str:
    """
    Generate JavaScript code to attach analyzer tooltips to dropdown options.

    Dynamically creates the JavaScript from the registry metadata to ensure
    it stays in sync with analyzer descriptions.

    Returns:
        JavaScript code as a string
    """
    tooltips = create_analyzer_registry().get_analyzer_tooltips()

    tooltips_js = ", ".join(
        f"'{name}': '{desc}'"
        for name, desc in tooltips.items()
    )

    return (
        "$(function() {"
        "  var tips = {"
        f"    {tooltips_js}"
        "  };"
        "  $('#profile_influence_analyzer option').each(function() {"
        "    var t = tips[$(this).val()];"
        "    if (t) $(this).attr('title', t);"
        "  });"
        "})"
    )


def register_factor_outputs(
    input: Inputs,
    output: Outputs,
    session: Session,
    *,
    selected_factor: reactive.Value,
    computed_analysis_result: Callable,
    current_labeler: reactive.Value,
    factor_ci_overrides: reactive.Value,
    factor_ci_computing: reactive.Value,
    validated_metric: Callable,
    reduced_data: Callable,
    active_data: Callable,
    excluded_predictors: reactive.Value,
    profile_md_settings: Callable,
    order_exclusions_fn: Callable,
    pending_restore: Any = None,
) -> None:
    """
    Register all factor-analysis reactive effects and output renderers.

    Args:
        input: Shiny inputs
        output: Shiny outputs
        session: Shiny session
        selected_factor: Reactive value tracking which factor key is selected
        computed_analysis_result: Reactive Calc returning analysis dict
        current_labeler: Reactive value for the current PerformanceLabeler
        factor_ci_overrides: Reactive value for on-demand CI overrides
        factor_ci_computing: Reactive value tracking CI computation state
        validated_metric: Reactive Calc returning validated metric column name
        reduced_data: Reactive Calc returning reduced DataFrame
        active_data: Reactive Calc returning active (filtered) DataFrame
        excluded_predictors: Reactive value with excluded predictor list
        profile_md_settings: Reactive Calc returning ProfileSettings
        order_exclusions_fn: Callable to order exclusion names for display
        pending_restore: Reactive value holding ProfileSettings snapshot during restore
    """

    # ---- Factor selection handler ----

    @reactive.effect
    @reactive.event(input.profile_selected_factor)
    def _handle_factor_selection() -> None:
        """Handle factor selection from dropdown."""
        try:
            factor_name = input.profile_selected_factor()
            if factor_name and factor_name.strip():
                selected_factor.set(factor_name)
        except Exception:
            tb.print_exc()

    # ---- Factor selector / control panel ----

    @output
    @render.ui
    def profile_factor_selector() -> ui.TagChild:
        """Render analysis controls and factor selector in one card.

        This render has NO reactive dependencies so it fires exactly once.
        Source inputs (perf_auto_detect, num_perf_groups) are created here
        and never destroyed.  Task-switch resets happen via ui.update_*
        calls in _check_prof_file; saved-value restores happen via
        ui.update_* in _restore_labeler_from_markdown.

        Derived content (action buttons, analyzer dropdown, factor list)
        lives in nested @render.ui outputs that re-render independently.
        """
        try:
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
                "3\u201310 = equal-quantile groups, adjustable by clicking or Search"
            )
            return ui.card(
                ui.tags.style("""
                    .profile-controls-col .card,
                    .profile-controls-col .card-body {
                        overflow: visible !important;
                    }
                    #profile_selected_factor {
                        width: 100% !important;
                    }
                    #profile_selected_factor + .selectize-control .selectize-dropdown {
                        font-size: 0.85em !important;
                        line-height: 1.2 !important;
                    }
                    #profile_selected_factor + .selectize-control .selectize-dropdown .option {
                        padding: 4px 8px !important;
                    }
                    #profile_selected_factor + .selectize-control .selectize-input {
                        font-size: 0.9em !important;
                    }
                    .num-perf-groups-wrap .form-group {
                        margin-bottom: 0 !important;
                    }
                    .num-perf-groups-wrap input#num_perf_groups {
                        width: 48px !important;
                        font-size: 0.85em !important;
                        height: 26px !important;
                        text-align: center !important;
                        padding: 1px 4px !important;
                        display: inline-block !important;
                    }
                    #profile_save_settings_btn {
                        padding: 2px 6px !important;
                        margin-left: 8px !important;
                        text-decoration: none !important;
                        color: #666 !important;
                        opacity: 0.75 !important;
                        line-height: 1 !important;
                        background: none !important;
                        border: none !important;
                        box-shadow: none !important;
                        font-size: 1.1em !important;
                    }
                    #profile_save_settings_btn:hover {
                        opacity: 1 !important;
                        color: #333 !important;
                        background-color: rgba(0, 0, 0, 0.05) !important;
                        border-radius: 3px !important;
                    }
                """),
                # Header: "Performance groups" + save button
                ui.tags.div(
                    ui.tags.label(
                        "Performance groups",
                        style="white-space: nowrap; margin-bottom: 0; font-weight: bold;",
                    ),
                    ui.input_action_button(
                        "profile_save_settings_btn",
                        "\U0001f4be",
                        class_="btn btn-link btn-sm",
                        title="Save current profile settings (filter, groups, analyzer) to markdown",
                    ),
                    style=(
                        "display: flex; align-items: center; margin-bottom: 4px; "
                        "white-space: nowrap; flex-wrap: nowrap; gap: 0;"
                    ),
                ),
                # Stable source inputs — NO reactive value= bindings.
                # Downstream state changes re-render the nested outputs below
                # without destroying these inputs.
                ui.row(
                    ui.column(
                        6,
                        ui.div(
                            ui.input_checkbox("perf_auto_detect", "Auto groups"),
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
                            ui.tags.div(
                                ui.input_numeric(
                                    "num_perf_groups",
                                    "",
                                    value=2,
                                    min=1,
                                    max=10,
                                    step=1,
                                    width="48px",
                                ),
                                style="display: flex; align-items: center;",
                                class_="num-perf-groups-wrap",
                            ),
                            title=groups_tooltip,
                            style="display: flex; align-items: center;",
                        ),
                        style="border-left: 1px solid #ddd; padding-left: 8px;",
                    ),
                    style="margin-bottom: 5px;",
                ),
                # Nested renders — re-render independently on labeler/analysis changes
                ui.output_ui("profile_cutoff_actions"),
                ui.hr(style="margin: 10px 0;"),
                # Static analyzer dropdown — choices updated via @reactive.effect
                ui.div(
                    ui.input_select(
                        "profile_influence_analyzer",
                        "Influence analyzer",
                        choices=create_analyzer_registry().get_analyzer_choices(),
                        selected="tree",
                    ),
                    ui.tags.script(_generate_analyzer_tooltips_script()),
                ),
                # Static factor dropdown — choices updated after analysis runs
                ui.input_selectize(
                    "profile_selected_factor",
                    "Select factor to inspect:",
                    choices={"": "(run analysis to select factors)"},
                    selected="",
                    width="100%",
                    options={
                        "placeholder": "Choose a factor from analysis...",
                        "maxOptions": 100,
                    },
                ),
                style=(
                    "background-color: #f8f9fa; padding: 10px; flex: 1;"
                    " display: flex; flex-direction: column; overflow: visible !important;"
                ),
            )

        except Exception as e:
            tb.print_exc()
            return ui.p(f"Error: {str(e)}", style="color: red;")

    # ---- Nested renders for derived content ----

    @output
    @render.ui
    def profile_cutoff_actions() -> ui.TagChild:
        """Render search/predictors buttons — re-renders on labeler change."""
        labeler = current_labeler.get()
        return ui.div(
            *render_cutoff_actions(
                labeler=labeler,
                excluded_names=order_exclusions_fn(excluded_predictors()),
            ),
        )

    @reactive.effect
    def _update_analyzer_select() -> None:
        """Update influence analyzer choices and selection when labeler/data changes."""
        labeler = current_labeler.get()
        data = active_data()
        if data is None or data.is_empty():
            return

        settings_view = profile_md_settings().settings_view
        context = _build_data_context(data, labeler, settings_view)
        registry = create_analyzer_registry()
        ranked_choices = registry.get_ranked_analyzer_choices(context)

        with reactive.isolate():
            snapshot = pending_restore.get() if pending_restore is not None else None
            try:
                selected_analyzer: str | None = input.profile_influence_analyzer()
            except SilentException:
                selected_analyzer = None

        if snapshot or selected_analyzer is None or labeler is None:
            default_analyzer = snapshot.default_influence_analyzer if snapshot else None
            if default_analyzer and default_analyzer in ranked_choices:
                selected_analyzer = default_analyzer
            else:
                selected_analyzer = (
                    registry.best_analyzer_for_context(context)
                    or settings_view.get("profiling.influence_analyzer", "tree")
                )

        if selected_analyzer not in ranked_choices:
            selected_analyzer = (
                registry.best_analyzer_for_context(context)
                or settings_view.get("profiling.influence_analyzer", "tree")
            )

        ui.update_select(
            "profile_influence_analyzer",
            choices=ranked_choices,
            selected=selected_analyzer,
        )

    @reactive.effect
    def _update_factor_dropdown() -> None:
        """Update factor dropdown choices when analysis results change."""
        analysis = computed_analysis_result()
        factors = analysis.get("factors", []) if analysis else []
        if not factors:
            ui.update_selectize(
                "profile_selected_factor",
                choices={"": "(run analysis to select factors)"},
                selected="",
            )
            return

        name_counts: dict[str, int] = {}
        for factor in factors:
            name_counts[factor.name] = name_counts.get(factor.name, 0) + 1

        sorted_factors = sorted(
            factors, key=lambda x: (x.rank or 10_000, -x.strength)
        )
        choices = {"": "(select a factor)"} | {
            factor_key(factor): factor_label(factor, name_counts)
            for factor in sorted_factors
        }
        ui.update_selectize(
            "profile_selected_factor",
            choices=choices,
            selected="",
        )

    # ---- Factor tabset (description, analysis, mitigations) ----

    @output
    @render.ui
    def profile_factor_tabset() -> ui.TagChild:
        """Render factor description and mitigation tabs (only when factor selected)."""
        try:
            factor_name = selected_factor()
            if not factor_name:
                return ui.tags.div()

            return ui.tags.div(
                ui.navset_tab(
                    ui.nav_panel(
                        "Factor analysis",
                        ui.output_ui("profile_factor_analysis_card"),
                    ),
                    ui.nav_panel(
                        "Description",
                        ui.output_ui("profile_factor_info_card"),
                    ),
                    ui.nav_panel(
                        "Mitigations",
                        ui.output_ui("profile_mitigation_selector"),
                        ui.output_ui("profile_mitigation_info_card"),
                    ),
                    id="profile_factor_tab",
                ),
                style="flex: 1; display: flex; flex-direction: column;",
            )

        except Exception as e:
            tb.print_exc()
            return ui.p(f"Error: {str(e)}", style="color: red;")

    # ---- Factor analysis card (narrative + CI) ----

    @output
    @render.ui
    def profile_factor_analysis_card() -> ui.TagChild:
        """Render analysis narrative for the selected factor."""
        try:
            fkey = selected_factor()
            if not fkey:
                return ui.p(
                    "Select a factor to view its analysis",
                    style="color: #999; padding: 20px; text-align: center;",
                )

            analysis = computed_analysis_result()
            if analysis is None:
                return ui.p(
                    "No analysis available",
                    style="color: #999; padding: 10px;",
                )

            factors = analysis.get("factors", [])
            analyzer_name = analysis.get("analyzer_name", "tree")
            ci_overrides = factor_ci_overrides.get()
            ci_computing = factor_ci_computing.get()

            selected = get_factor_by_key(factors, fkey)
            if selected is None:
                return ui.p(
                    "Selected factor is no longer available.",
                    style="color: #999; padding: 10px;",
                )

            name_counts: dict[str, int] = {}
            for factor in factors:
                name_counts[factor.name] = name_counts.get(factor.name, 0) + 1
            display_label = factor_label(selected, name_counts)

            if ci_overrides:
                override_ci = ci_overrides.get(fkey, "__missing__")
                if override_ci != "__missing__":
                    metadata = dict(selected.metadata or {})
                    metadata["bootstrap_ci_enabled"] = True
                    selected = replace(
                        selected,
                        confidence_interval=override_ci,
                        metadata=metadata,
                    )

            visualizer = get_visualizer_for(
                analyzer_name=analyzer_name,
                tree=analysis.get("tree"),
                metric_col=validated_metric(),
                labeler=current_labeler.get(),
            )
            narrative_map = visualizer.generate_narrative(
                factors=[selected],
                class_names=analysis.get("class_names", []),
            )
            narrative_html = build_analysis_narrative_html(
                narrative_map=narrative_map,
                selected_factor=selected.name,
            )

            footer = None
            if ci_computing and analyzer_name == "tree":
                footer = ui.tags.p(
                    "Computing 95% CI...",
                    style="margin-top: 10px; color: #666; font-style: italic;",
                )

            return ui.card(
                ui.card_header(f"Factor: {display_label}"),
                ui.HTML(narrative_html),
                footer,
            )
        except Exception as e:
            tb.print_exc()
            return ui.p(f"Error: {str(e)}", style="color: red;")

    # ---- Bootstrap CI computation ----

    @reactive.effect
    def _compute_factor_bootstrap_ci_for_selected_factor() -> None:
        """Auto-compute bootstrap CI for selected tree factor when needed."""
        try:
            active_tab = input.profile_factor_tab()
        except SilentException:
            return

        if active_tab != "Factor analysis":
            return

        analysis = computed_analysis_result()
        fkey = selected_factor()
        if analysis is None or not fkey:
            return

        if analysis.get("analyzer_name") != "tree":
            return

        if factor_ci_computing.get():
            return

        cached = factor_ci_overrides.get()
        if fkey in cached:
            return

        factors = analysis.get("factors", [])
        selected = get_factor_by_key(factors, fkey)
        if selected is None:
            return

        if selected.confidence_interval is not None:
            overrides = dict(cached)
            overrides[fkey] = selected.confidence_interval
            factor_ci_overrides.set(overrides)
            return

        analyzer = analysis.get("analyzer")
        data = analysis.get("data")
        labels = analysis.get("labels")
        exclude_cols = analysis.get("exclude_cols", [])
        max_predictors = int(analysis.get("max_predictors", 100))
        max_correlation = float(analysis.get("max_correlation", 0.99))

        if analyzer is None or data is None or labels is None:
            return

        n_samples = get_bootstrap_ci_sample_count(len(data))

        factor_ci_computing.set(True)
        try:
            with ui.Progress(min=0, max=1) as p:
                p.set(
                    value=0,
                    message=f"Computing 95% CI for {selected.name}...",
                    detail=f"Bootstrap samples: {n_samples}",
                )

                def on_progress(iteration: int, total: int) -> None:
                    progress = iteration / total if total > 0 else 0
                    p.set(
                        value=progress,
                        message=f"Computing 95% CI for {selected.name}...",
                        detail=f"Bootstrap sample {iteration}/{total}",
                    )

                ci = compute_tree_factor_bootstrap_ci(
                    analyzer=analyzer,
                    data=data,
                    labels=labels,
                    selected_factor=selected,
                    exclude_cols=exclude_cols,
                    max_predictors=max_predictors,
                    max_correlation=max_correlation,
                    settings=profile_md_settings().settings_view,
                    progress_callback=on_progress,
                )

            overrides = dict(factor_ci_overrides.get())
            overrides[fkey] = ci
            factor_ci_overrides.set(overrides)

            if ci is None:
                ui.notification_show(
                    "95% CI unavailable for this factor"
                    " (bootstrap did not produce stable estimates).",
                    type="warning",
                    duration=5,
                )
        except Exception as e:
            tb.print_exc()
            ui.notification_show(
                f"Error computing 95% CI: {str(e)}",
                type="error",
                duration=5,
            )
        finally:
            factor_ci_computing.set(False)

    # ---- Factor info card ----

    @output
    @render.ui
    def profile_factor_info_card() -> ui.TagChild:
        """Render factor information card using helper function."""
        try:
            fkey = selected_factor()
            if not fkey:
                return ui.p(
                    "Click on the tree visualization to select a factor",
                    style="color: #999; padding: 20px; text-align: center;",
                )

            analysis = computed_analysis_result()
            factors = analysis.get("factors", []) if analysis else []
            selected = get_factor_by_key(factors, fkey)
            if selected is None:
                return ui.p(
                    "Selected factor not found",
                    style="color: #999; padding: 10px;",
                )

            name_counts: dict[str, int] = {}
            for factor in factors:
                name_counts[factor.name] = name_counts.get(factor.name, 0) + 1
            display_label = factor_label(selected, name_counts)

            return render_factor_info_card(selected.name, display_name=display_label)

        except Exception as e:
            tb.print_exc()
            return ui.p(f"Error: {str(e)}", style="color: red;")

    # ---- Factor scatter plot ----

    @output
    @render.plot
    def profile_factor_vs_perf_plot() -> Figure | None:
        """Render scatter plot using helper function."""
        try:
            fkey = selected_factor()
            if not fkey:
                fig, ax = plt.subplots(figsize=(10, 6))
                ax.text(
                    0.5, 0.5,
                    "Select a factor from the tree to view relationship",
                    ha="center", va="center", fontsize=12, color="#999",
                )
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.axis("off")
                return fig

            analysis = computed_analysis_result()
            factors = analysis.get("factors", []) if analysis else []
            selected = get_factor_by_key(factors, fkey)
            if selected is None:
                return None

            data = reduced_data()
            if data is None:
                return None

            metric = validated_metric()
            labeler = current_labeler.get()

            name_counts: dict[str, int] = {}
            for factor in factors:
                name_counts[factor.name] = name_counts.get(factor.name, 0) + 1
            display_label = factor_label(selected, name_counts)

            return render_factor_scatter_plot(
                data,
                selected.name,
                metric,
                labeler,
                display_name=display_label,
            )

        except Exception as e:
            tb.print_exc()
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(
                0.5, 0.5, f"Error: {str(e)}",
                ha="center", va="center", fontsize=12, color="red",
            )
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis("off")
            return fig

    # ---- Factor comparison table ----

    @output
    @render.ui
    def profile_factor_comparison_table() -> ui.TagChild:
        """Render comparison table using helper function."""
        try:
            fkey = selected_factor()
            if not fkey:
                return ui.p(
                    "Select a factor to view group comparison",
                    style="color: #999; padding: 20px; text-align: center;",
                )

            analysis = computed_analysis_result()
            factors = analysis.get("factors", []) if analysis else []
            selected = get_factor_by_key(factors, fkey)
            if selected is None:
                return ui.div()

            data = reduced_data()
            if data is None:
                return ui.div()

            metric = validated_metric()
            labeler = current_labeler.get()

            name_counts: dict[str, int] = {}
            for factor in factors:
                name_counts[factor.name] = name_counts.get(factor.name, 0) + 1
            display_label = factor_label(selected, name_counts)

            return render_factor_comparison_table(
                data,
                selected.name,
                metric,
                labeler,
                display_name=display_label,
            )

        except Exception as e:
            tb.print_exc()
            return ui.p(f"Error: {str(e)}", style="color: red;")

    # ---- Mitigation selector and info card (within factor tabset) ----

    @output
    @render.ui
    def profile_mitigation_selector() -> ui.TagChild:
        """Render dropdown selector for mitigations related to selected factor."""
        try:
            fkey = selected_factor()
            analysis = computed_analysis_result()
            factors = analysis.get("factors", []) if analysis else []
            selected = get_factor_by_key(factors, fkey)
            factor_name = selected.name if selected else None
            return render_mitigation_selector(factor_name)

        except Exception as e:
            tb.print_exc()
            return ui.p(f"Error: {str(e)}", style="color: red;")

    @output
    @render.ui
    def profile_mitigation_info_card() -> ui.TagChild:
        """Render mitigation information card."""
        try:
            mitigation_name = input.profile_selected_mitigation()
            return render_mitigation_info_card(mitigation_name)
        except SilentException:
            return render_mitigation_info_card(None)
        except Exception as e:
            tb.print_exc()
            return ui.p(f"Error: {str(e)}", style="color: red;")
