# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""dominate components for the Profile page."""

import json
from typing import Any

from dominate.dom_tag import dom_tag
from dominate.tags import (
    a,
    button,
    div,
    form,
    h2,
    h3,
    h4,
    h5,
    iframe,
    img,
    input_,
    label,
    li,
    option,
    p,
    section,
    select,
    span,
    strong,
    script,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
    ul,
)
from dominate.util import raw

from src.gui.services.shared import _time_to_seconds


class dialog(dom_tag):  # noqa: N801
    """HTML <dialog> element (not in dominate.tags)."""

    tagname = "dialog"


def profile_page(data: dict[str, Any]) -> str:
    """Render the full Profile page HTML."""
    from .layout import render_shell_with_content

    content = div(cls="profile-root")
    with content:
        if data.get("notice"):
            div(str(data["notice"]), cls="notice-banner")
        if data.get("error"):
            div(str(data["error"]), cls="error-banner")

        with section(cls="profile-controls"):
            with form(action="/ui/profile", method="get", cls="profile-form", id="profile-form"):
                _render_top_controls(data)

        if data.get("source_prompt") and not data.get("show_profile_config"):
            _render_source_prompt_modal(data)
        if data.get("show_profile_config"):
            _render_profile_config_modal(data)
        if data.get("show_mitigation_modal"):
            _render_mitigation_action_modal(data)

        # Main analysis area (only shown when data is loaded)
        if data.get("active_csv") and data.get("metric"):
            _render_analysis_area(data)

    return render_shell_with_content("profile", str(content))


def _render_top_controls(data: dict[str, Any]) -> None:
    """Render the top row of controls (experiment, task, metric, etc.)."""
    with div(cls="profile-top-row"):
        # Experiment selector
        with div(cls="profile-cell"):
            label("Experiment", _for="experiment", cls="field-label")
            with select(id="experiment", name="experiment", cls="field-input"):
                option("(select experiment)", value="")
                selected_exp = str(data.get("experiment") or "")
                for exp in data.get("experiments", []):
                    val = exp["value"] if isinstance(exp, dict) else exp
                    lbl = exp["label"] if isinstance(exp, dict) else exp
                    option(lbl, value=val, selected=val == selected_exp)

        # Task selector (multi-select)
        with div(cls="profile-cell"):
            with div(cls="profile-label-row"):
                label("Task", _for="task", cls="field-label")
                # Keep row-count status on the same row, right-aligned, so
                # controls consume less vertical space.
                rows = data.get("filtered_rows")
                total = data.get("rows")
                if rows is not None and total is not None:
                    status_text = f"✓ {rows}/{total} rows (filtered)" if rows < total else f"✓ {total} rows"
                    p(status_text, cls="profile-status profile-status-inline")
            selected_tasks = set(data.get("all_tasks") or ([str(data.get("task") or "")] if data.get("task") else []))
            with select(
                id="task",
                name="task",
                cls="field-input",
                multiple=True,
            ):
                for task in data.get("tasks", []):
                    option(task["label"], value=task["label"], selected=task["label"] in selected_tasks)

        # Outcome metric
        with div(cls="profile-cell"):
            label("Outcome Metric", _for="metric", cls="field-label")
            with select(
                id="metric",
                name="metric",
                cls="field-input tomselect-single",
                data_search_url="/ui/profile/metrics",
                data_csv_path=str(data.get("active_csv") or data.get("csv_path") or ""),
            ):
                option("(select metric)", value="")
                selected_metric = str(data.get("metric") or "")
                if selected_metric and selected_metric not in data.get("metrics", []):
                    option(selected_metric, value=selected_metric, selected=True)
                for m in data.get("metrics", []):
                    option(m, value=m, selected=m == selected_metric)

        # Lower is better toggle
        with div(cls="profile-cell profile-cell-narrow"):
            label("Lower→Better", _for="lower_is_better", cls="field-label")
            lib = data.get("lower_is_better", True)
            input_(
                type="checkbox",
                id="lower_is_better",
                name="lower_is_better",
                value="1",
                cls="profile-switch",
                checked=lib,
            )
            # Hidden input to ensure "0" is sent when unchecked
            input_(type="hidden", name="lower_is_better_default", value="0")

        # Filter metric (with spacing from Lower->Better)
        with div(cls="profile-cell", style="margin-left: 1rem;"):
            label("Metric to Filter", _for="filter_metric", cls="field-label")
            selected_filter = str(data.get("filter_metric") or "")
            with select(
                id="filter_metric",
                name="filter_metric",
                cls="field-input tomselect-single",
                data_search_url="/ui/profile/filter-metrics",
                data_csv_path=str(data.get("active_csv") or data.get("csv_path") or ""),
            ):
                option("(no filter)", value="")
                if selected_filter:
                    option(selected_filter, value=selected_filter, selected=True)

        # Filter UI (slider or multiselect)
        _render_filter_control(data)

    # Section divider below top-level controls
    div(cls="profile-top-controls-hr")

    # Hidden inputs for non-form state carried through navigation
    input_(type="hidden", name="csv_path", value=data.get("csv_path") or "")
    input_(type="hidden", name="source", value=data.get("source") or "")
    input_(type="hidden", name="excluded_state", value=data.get("excluded_state") or "")
    for cutoff in (data.get("cutoff_values") or []):
        input_(type="hidden", name="cutoff_value", value=str(cutoff))


def _render_filter_control(data: dict[str, Any]) -> None:
    """Render the appropriate filter control based on filter kind."""
    filter_kind = data.get("filter_kind", "none")

    if filter_kind == "none":
        return

    with div(cls="profile-cell"):
        label("Filter Range", cls="field-label")

        if filter_kind == "numeric":
            min_bound = data.get("filter_min_bound", 0)
            max_bound = data.get("filter_max_bound", 100)
            start_min = data.get("filter_min") or str(min_bound)
            start_max = data.get("filter_max") or str(max_bound)
            is_integer = data.get("filter_is_integer", False)
            is_timestamp = data.get("filter_is_timestamp_like", False)
            # A column with a single constant value has no range to filter.
            # Rendering a slider would let the handle move but never change the
            # result (every row matches the only value), which is confusing.
            try:
                is_constant = float(min_bound) == float(max_bound)
            except (TypeError, ValueError):
                is_constant = str(min_bound) == str(max_bound)
            if is_constant:
                filter_metric = data.get("filter_metric") or "this column"
                p(
                    f"'{filter_metric}' has a single constant value "
                    f"({min_bound}); there is no range to filter.",
                    cls="muted",
                )
                input_(type="hidden", id="filter_min", name="filter_min", value="")
                input_(type="hidden", id="filter_max", name="filter_max", value="")
                return
            div(
                id="profile-noui-slider",
                cls="noui-slider-target",
                data_min=str(min_bound),
                data_max=str(max_bound),
                data_start_min=str(start_min),
                data_start_max=str(start_max),
                data_kind="numeric",
                data_is_integer="true" if is_integer else "false",
                data_is_timestamp="true" if is_timestamp else "false",
            )
            with div(cls="noui-labels"):
                span("", id="profile-noui-label-min")
                span("", id="profile-noui-label-max")
            input_(type="hidden", id="filter_min", name="filter_min", value=start_min)
            input_(type="hidden", id="filter_max", name="filter_max", value=start_max)

        elif filter_kind == "time":
            min_bound = data.get("filter_min_bound", "00:00:00")
            max_bound = data.get("filter_max_bound", "23:59:59")
            min_bound_num = float(data.get("filter_min_bound_num") or 0)
            max_bound_num = float(data.get("filter_max_bound_num") or 86399)
            cur_min = data.get("filter_min") or str(min_bound)
            cur_max = data.get("filter_max") or str(max_bound)
            # noUiSlider requires numeric values; convert HH:MM:SS bounds to seconds
            try:
                start_min_num = _time_to_seconds(cur_min)
            except Exception:
                start_min_num = min_bound_num
            try:
                start_max_num = _time_to_seconds(cur_max)
            except Exception:
                start_max_num = max_bound_num
            div(
                id="profile-noui-slider",
                cls="noui-slider-target",
                data_min=str(min_bound_num),
                data_max=str(max_bound_num),
                data_start_min=str(start_min_num),
                data_start_max=str(start_max_num),
                data_kind="time",
                data_is_integer="false",
                data_is_timestamp="false",
            )
            with div(cls="noui-labels"):
                span("", id="profile-noui-label-min")
                span("", id="profile-noui-label-max")
            input_(type="hidden", id="filter_min", name="filter_min", value=cur_min)
            input_(type="hidden", id="filter_max", name="filter_max", value=cur_max)

        elif filter_kind == "categorical":
            options = data.get("filter_options", [])
            selected_values = data.get("filter_values", [])
            with select(id="filter_values", name="filter_values", cls="field-input tomselect-multi", multiple=True):
                for opt in options:
                    option(opt, value=opt, selected=opt in selected_values)


def _render_source_prompt_modal(data: dict[str, Any]) -> None:
    """Render source-choice prompt as a pop-out modal."""
    from urllib.parse import urlencode

    experiment = str(data.get("experiment") or "")
    task = str(data.get("task") or "")
    csv_path = str(data.get("csv_path") or "")
    has_prof_csv = bool(data.get("has_prof_csv"))
    prof_filename = str(data.get("prof_filename") or "")

    base_params = {
        "experiment": experiment,
        "task": task,
        "csv_path": csv_path,
    }

    use_existing_url = "/ui/profile?" + urlencode({**base_params, "source": "use_existing"})
    use_original_url = "/ui/profile?" + urlencode({**base_params, "source": "use_original"})
    profile_url = "/ui/profile?" + urlencode({**base_params, "source": "profile", "show_profile_config": "1"})
    cancel_url = "/ui/profile?" + urlencode({"experiment": experiment})

    with div(id="profile-source-modal", cls="modal-shell", role="dialog", aria_modal="true"):
        with div(cls="modal-card"):
            h5("Profiling Data Found" if has_prof_csv else "Profile Options", cls="modal-title")
            if has_prof_csv:
                p("Profiling data found for this task.", cls="modal-copy")
                p(prof_filename, cls="profile-mitigation-refs")
                p("What would you like to do?", cls="modal-copy")
            else:
                p("No profiling data found for this task.", cls="modal-copy")
                p("You can use existing data or add profiling.", cls="modal-copy")

            with div(cls="modal-actions"):
                a("Cancel", href=cancel_url, cls="btn btn-secondary")
                a(
                    "Use Existing" if has_prof_csv else "Use Existing Data",
                    href=use_existing_url if has_prof_csv else use_original_url,
                    cls="btn btn-primary",
                )
                a(
                    "Reprofile Task" if has_prof_csv else "Profile Task",
                    href=profile_url,
                    cls="btn btn-success",
                )


def _render_profile_config_modal(data: dict[str, Any]) -> None:
    """Render profiling configuration as a pop-out modal."""
    from urllib.parse import urlencode

    experiment = str(data.get("experiment") or "")
    task = str(data.get("task") or "")
    csv_path = str(data.get("csv_path") or "")
    prompt_url = "/ui/profile?" + urlencode(
        {
            "experiment": experiment,
            "task": task,
            "csv_path": csv_path,
        }
    )

    with div(id="profile-config-modal", cls="modal-shell", role="dialog", aria_modal="true"):
        with div(cls="modal-card"):
            h5("Configure Profiling", cls="modal-title")
            p("Select profiling backends (in order).", cls="modal-copy")

            with form(action="/ui/profile/run-profiling", method="post", id="profile-config-form"):
                input_(type="hidden", name="original_md", value=data.get("original_md") or "")
                input_(type="hidden", name="csv_path", value=csv_path)
                input_(type="hidden", name="redirect_url", value=prompt_url)

                label("Task name for profiling output", _for="profile_task_name", cls="modal-label")
                input_(
                    type="text",
                    name="profile_task_name",
                    value=data.get("default_profile_task_name") or "",
                    cls="modal-input",
                )

                label("Profiling backends", _for="profiling_backends", cls="modal-label")
                with select(
                    id="profiling_backends",
                    name="profiling_backends",
                    cls="modal-input tomselect-multi",
                    multiple=True,
                    required=True,
                ):
                    for backend in data.get("profiling_backends") or []:
                        option(str(backend), value=str(backend))

                with div(cls="status-strip", id="profile-config-status-strip", hidden=True):
                    p("Profiling status", cls="status-title")
                    p("Starting profiling...", cls="status-copy", id="profile-config-status-copy")
                    with div(cls="status-progress", id="profile-config-status-progress", data_mode="indeterminate"):
                        div(cls="status-progress-fill", id="profile-config-status-progress-fill")

                with div(cls="modal-actions"):
                    a("Cancel", href=prompt_url, cls="btn btn-secondary")
                    button("Start Profiling", type="submit", cls="btn btn-success", id="profile_start_button")


def _render_mitigation_action_modal(data: dict[str, Any]) -> None:
    """Render mitigation action chooser as a pop-out modal."""
    mitigation_name = str(data.get("mitigation") or "")
    if not mitigation_name:
        return

    close_url = _current_url(data)
    with div(id="profile-mitigation-modal", cls="modal-shell", role="dialog", aria_modal="true"):
        with div(cls="modal-card"):
            h5("Attempt Mitigation", cls="modal-title")

            if data.get("mitigation_csv_exists"):
                p("A mitigation data file already exists. Use it or rerun mitigation?", cls="modal-copy")
            else:
                info = data.get("mitigation_info") or {}
                if info.get("is_automated", False):
                    p("Are you sure you want to rerun benchmark? This could take a while.", cls="modal-copy")
                else:
                    p(
                        "This mitigation cannot be automated. Apply it manually and then run this action to collect new data.",
                        cls="modal-copy",
                    )

            with form(action="/ui/profile/mitigation/run", method="post"):
                input_(type="hidden", name="md_path", value=data.get("mitigation_baseline_md") or "")
                input_(type="hidden", name="csv_path", value=data.get("csv_path") or "")
                input_(type="hidden", name="mitigation", value=mitigation_name)
                input_(type="hidden", name="redirect_url", value=close_url)

                with div(cls="modal-actions"):
                    a("Cancel", href=close_url, cls="btn btn-secondary")
                    if data.get("mitigation_csv_exists"):
                        button(
                            "Use data",
                            type="submit",
                            name="action",
                            value="use",
                            cls="btn btn-primary",
                        )
                        button(
                            "Rerun it",
                            type="submit",
                            name="action",
                            value="run",
                            cls="btn btn-success",
                        )
                    else:
                        button(
                            "Run it!",
                            type="submit",
                            name="action",
                            value="run",
                            cls="btn btn-success",
                        )


def _render_analysis_area(data: dict[str, Any]) -> None:
    """Render the main analysis area with plots and controls."""
    # --- Section 1: Distribution + Influence Analysis ---
    with div(cls="profile-grid"):
        # Left sidebar: analysis controls
        with div(cls="profile-sidebar"):
            _render_sidebar_controls(data)

        # Main content area
        with div(cls="profile-main"):
            _render_plots_row(data)

    # --- Section 2: Factor Analysis (loaded via HTMX) ---
    div(cls="profile-section-hr")
    fragment_url = data.get("analysis_fragment_url")
    if fragment_url:
        div(
            p("Loading analysis…", cls="muted htmx-indicator"),
            id="analysis-results",
            cls="profile-analysis-results",
            **{
                "hx-get": fragment_url,
                "hx-trigger": "load, refresh",
                "hx-swap": "innerHTML",
            },
        )
    else:
        div(id="analysis-results", cls="profile-analysis-results")

    # ── Modal dialogs (hidden; opened by JS) ─────────────────────────────────
    _render_search_cutoff_modal(data)
    _render_exclude_predictors_modal(data)


def _render_search_cutoff_modal(data: dict[str, Any]) -> None:
    """Render the search-for-optimal-cutoffs <dialog> modal."""
    with dialog(id="search-cutoff-modal", cls="profile-modal"):
        with div(cls="profile-modal-header"):
            h3("Search for Optimal Cutoffs", cls="profile-modal-title")
            button(
                raw("&times;"),
                type="button",
                cls="profile-modal-close",
                **{"data-close-modal": "search-cutoff-modal"},
            )
        with div(cls="profile-modal-body"):
            p(
                "This will search for the cutoff values that best separate "
                "performance groups by minimising decision-tree entropy.",
            )
            with div(cls="profile-modal-hint"):
                strong("Tip: "), raw(
                    "Enable \u201cAuto detect\u201d in the sidebar to let the "
                    "algorithm choose the optimal number of groups automatically."
                )
        with div(cls="profile-modal-footer"):
            button(
                "Cancel",
                type="button",
                cls="btn-sm",
                **{"data-close-modal": "search-cutoff-modal"},
            )
            with form(
                action="/ui/profile/search-cutoffs",
                method="post",
                cls="profile-modal-form",
                id="search-cutoff-form",
            ):
                # Preserve current query params as hidden fields
                for key in ("csv_path", "metric", "analyzer", "num_groups", "factor",
                             "filter_metric", "filter_min", "filter_max",
                             "lower_is_better", "experiment"):
                    val = data.get(key) or ""
                    if val:
                        input_(type="hidden", name=key, value=str(val))
                # Emit all selected tasks (multi-task aware)
                for t in (data.get("all_tasks") or ([data.get("task")] if data.get("task") else [])):
                    if t:
                        input_(type="hidden", name="task", value=str(t))
                input_(type="hidden", name="auto_detect",
                       value="1" if data.get("auto_detect", False) else "0")
                for fv in (data.get("filter_values") or []):
                    input_(type="hidden", name="filter_values", value=str(fv))
                for ep in data.get("excluded_names") or []:
                    input_(type="hidden", name="excluded_predictor", value=str(ep))
                # Build redirect_url so the endpoint can navigate back to this page
                redirect_url = _current_url(data)
                input_(type="hidden", name="redirect_url", value=redirect_url)
                button(
                    "Run search",
                    type="submit",
                    cls="btn-sm profile-modal-submit",
                )


def _render_exclude_predictors_modal(data: dict[str, Any]) -> None:
    """Render the exclude-predictors <dialog> modal.

    The predictor list is server-side rendered via HTMX from
    /ui/profile/predictors-fragment, which returns a table with predictor
    names, non-NA counts, correlation to the outcome metric, and checkboxes.
    The form POSTs to /ui/profile/update-exclusions which stores state
    server-side (avoiding thousands of URL params).
    """
    from urllib.parse import urlencode as _urlencode

    with dialog(id="exclude-predictors-modal", cls="profile-modal"):
        with div(cls="profile-modal-header"):
            h3("Exclude Predictors", cls="profile-modal-title")
            button(
                raw("&times;"),
                type="button",
                cls="profile-modal-close",
                **{"data-close-modal": "exclude-predictors-modal"},
            )
        with div(cls="profile-modal-body"):
            p("Select predictors to exclude from factor analysis:",
              cls="profile-modal-desc")
            with form(
                action="/ui/profile/update-exclusions",
                method="post",
                cls="profile-modal-form",
                id="exclude-predictors-form",
            ):
                # Use the active (merged) CSV so multi-task analysis exposes
                # predictors; fall back to the primary CSV for single-task mode.
                active_csv = str(data.get("active_csv") or data.get("csv_path") or "")
                # Hidden fields the POST endpoint needs to store state + redirect
                input_(type="hidden", name="csv_path", value=active_csv)
                input_(type="hidden", name="metric", value=str(data.get("metric") or ""))
                input_(type="hidden", name="redirect_url", value=_current_url(data))

                # Build URL for HTMX predictors fragment
                frag_params: list[tuple[str, str]] = []
                for key in ("metric", "filter_metric", "filter_min", "filter_max"):
                    val = data.get(key) or ""
                    if val:
                        frag_params.append((key, str(val)))
                if active_csv:
                    frag_params.insert(0, ("csv_path", active_csv))
                frag_params.append(("max_corr", f"{float(data.get('predictor_max_corr', 0.99)):.2f}"))

                # Build excluded_state token if needed (for initial load or after applying exclusions)
                excluded_state = data.get("excluded_state")
                if not excluded_state and data.get("excluded_names"):
                    # First load: create a token from the initial excluded_names list
                    from src.gui.services.exclusion_store import create_exclusion_state
                    excluded_state = create_exclusion_state(
                        active_csv,
                        data.get("metric") or "",
                        data.get("excluded_names") or []
                    )

                if excluded_state:
                    frag_params.append(("excluded_state", excluded_state))
                    # Pass excluded_state to the form so update-exclusions can
                    # merge new selections with previously excluded predictors
                    input_(type="hidden", name="excluded_state", value=excluded_state)

                frag_params.append((
                    "lower_is_better", "1" if data.get("lower_is_better", True) else "0"
                ))
                # Do NOT add individual excluded_predictor params here — they bloat the URL
                # beyond the 8KB HTTP header limit for large datasets. Instead, rely on
                # excluded_state which encodes all exclusions in a compact token.
                predictors_url = "/ui/profile/predictors-fragment?" + _urlencode(frag_params)

                # HTMX container — loads the predictor table when the modal opens
                div(
                    p("Loading predictors\u2026", cls="muted"),
                    id="exclude-predictors-list",
                    cls="profile-predictor-list",
                    **{
                        "hx-get": predictors_url,
                        "hx-trigger": "load",
                        "hx-swap": "innerHTML",
                        "data-initial-url": predictors_url,
                    },
                )
                with div(cls="profile-modal-footer"):
                    button(
                        "Cancel",
                        type="button",
                        cls="btn-sm",
                        **{"data-close-modal": "exclude-predictors-modal"},
                    )
                    button(
                        "Apply",
                        type="submit",
                        cls="btn-sm profile-modal-submit",
                    )


def _render_sidebar_controls(data: dict[str, Any]) -> None:
    """Render the left sidebar with performance groups, analyzer, and factor controls."""
    from src.core.profile.analyzers.registry import create_analyzer_registry

    # --- Performance Groups header with save icon ---
    with div(cls="profile-sidebar-section"):
        with div(cls="profile-sidebar-header"):
            label("PERFORMANCE GROUPS", cls="field-label field-label-bold")
            md_path = data.get("md_path", "")
            if md_path:
                with form(
                    action="/ui/profile/save-settings",
                    method="post",
                    cls="profile-save-icon-form",
                ):
                    input_(type="hidden", name="md_path", value=md_path)
                    input_(type="hidden", name="metric", value=data.get("metric") or "")
                    input_(type="hidden", name="filter_metric", value=data.get("filter_metric") or "")
                    input_(type="hidden", name="filter_min", value=data.get("filter_min") or "")
                    input_(type="hidden", name="filter_max", value=data.get("filter_max") or "")
                    for fv in (data.get("filter_values") or []):
                        input_(type="hidden", name="filter_values", value=str(fv))
                    input_(type="hidden", name="num_groups", value=str(data.get("num_groups", 2)))
                    input_(type="hidden", name="auto_detect", value="1" if data.get("auto_detect", False) else "0")
                    input_(type="hidden", name="analyzer", value=data.get("analyzer") or "")
                    input_(type="hidden", name="max_corr",
                           value=f"{float(data.get('predictor_max_corr', 0.99)):.2f}")
                    for cv in (data.get("cutoff_values") or []):
                        input_(type="hidden", name="cutoff_value", value=str(cv))
                    for ep in (data.get("excluded_names") or []):
                        input_(type="hidden", name="excluded_predictor", value=str(ep))
                    input_(type="hidden", name="redirect_url", value=_current_url(data))
                    button(
                        raw("&#x1f4be;"),
                        type="submit",
                        cls="profile-save-icon-btn",
                        title="Save current profile settings to markdown",
                    )

        # Auto groups / Fixed # row with vertical divider
        auto = data.get("auto_detect", False)
        auto_tooltip = (
            "Auto: automatically detects performance groups using temporal phase "
            "detection, tail isolation (IQR), and body clustering (Jenks breaks)."
        )
        groups_tooltip = (
            "Number of performance groups: "
            "1 = regression, 2 = binary FAST/SLOW, 3-10 = quantile groups"
        )
        with div(cls="profile-groups-row"):
            with div(cls="profile-groups-left", title=auto_tooltip):
                input_(
                    type="checkbox",
                    id="auto_detect",
                    name="auto_detect",
                    value="1",
                    checked=auto,
                    form="profile-form",
                )
                label("Auto groups", _for="auto_detect", cls="profile-auto-label")
            with div(cls="profile-groups-right", title=groups_tooltip):
                span("Fixed #", cls="profile-fixed-label")
                input_(
                    type="number",
                    id="num_groups",
                    name="num_groups",
                    value=str(data.get("num_groups", 2)),
                    min="1",
                    max="10",
                    cls="profile-num-groups",
                    disabled=auto,
                    form="profile-form",
                )

    # --- Search for optimal tree button ---
    with div(cls="profile-sidebar-section"):
        search_disabled = auto
        with div(cls="profile-action-row"):
            button(
                "🔍 Search for optimal tree",
                type="button",
                cls="btn-sm profile-action-btn" + (" disabled" if search_disabled else ""),
                id="search_cutoff_btn",
                disabled=search_disabled,
                title=(
                    "Search is not available in Auto mode."
                    if search_disabled
                    else "Search finds the optimal cutoff positions that minimize tree entropy."
                ),
            )

    # --- Predictors button + exclusion count ---
    with div(cls="profile-sidebar-section"):
        excluded_count = data.get("excluded_count", 4)
        excluded_names = data.get("excluded_names") or []
        if excluded_names:
            excluded_tooltip = "Excluded predictors:\n" + "\n".join(excluded_names)
        elif excluded_count:
            excluded_tooltip = f"{excluded_count} predictors excluded"
        else:
            excluded_tooltip = "No predictors excluded"
        with div(cls="profile-action-row"):
            button(
                "📊 Exclude predictors",
                type="button",
                cls="btn-sm profile-action-btn",
                id="exclude_predictors_btn",
                title="Click to determine which predictors are included or excluded",
            )
            span(
                f"({excluded_count} excluded)",
                cls="profile-excluded-badge",
                title=excluded_tooltip,
            )

    # --- Horizontal rule ---
    div(cls="profile-sidebar-hr")

    # --- Influence Analyzer dropdown ---
    with div(cls="profile-sidebar-section"):
        label("Influence analyzer", _for="analyzer", cls="field-label")
        analyzer_choices = data.get("analyzer_choices", {})
        selected_analyzer = data.get("analyzer", "")
        try:
            tooltips = create_analyzer_registry().get_analyzer_tooltips()
        except Exception:
            tooltips = {}
        with select(
            id="analyzer",
            name="analyzer",
            cls="field-input profile-analyzer-select",
            form="profile-form",
        ):
            for name, lbl in analyzer_choices.items():
                tip = tooltips.get(name, "")
                if tip:
                    option(lbl, value=name, selected=name == selected_analyzer, title=tip)
                else:
                    option(lbl, value=name, selected=name == selected_analyzer)

    # --- Factor selector dropdown ---
    with div(cls="profile-sidebar-section"):
        label("Select factor to inspect:", _for="factor", cls="field-label")
        factors = data.get("factors") or []
        with select(
            id="factor",
            name="factor",
            cls="field-input profile-factor-select",
            form="profile-form",
        ):
            option("(run analysis to select factors)", value="")
            selected_factor = str(data.get("factor") or "")
            for f in factors:
                fname = f.name if hasattr(f, "name") else str(f)
                option(fname, value=fname, selected=fname == selected_factor)


def _render_plots_row(data: dict[str, Any]) -> None:
    """Render the top plots row (distribution + analysis)."""
    with div(cls="profile-plots-row"):
        # Distribution plot
        with div(cls="profile-plot-cell"):
            with div(cls="profile-plot-title-row"):
                h4("Performance Distribution", cls="profile-plot-title")
                if int(data.get("num_groups", 2) or 2) > 1:
                    span(
                        "Click on plot to move nearest cutoff",
                        cls="profile-plot-helper",
                    )
            dist_url = data.get("distribution_plot_url")
            if dist_url:
                meta = data.get("distribution_meta") or {}
                xmin = meta.get("xmin", 0.0)
                xmax = meta.get("xmax", 1.0)
                plot_left = meta.get("plot_left", 0.0)
                plot_right = meta.get("plot_right", 1.0)
                auto_detect = bool(data.get("auto_detect", False))
                wrapper_attrs = {
                    "cls": "profile-dist-wrapper",
                    "data-xmin": str(xmin),
                    "data-xmax": str(xmax),
                    "data-plot-left": str(plot_left),
                    "data-plot-right": str(plot_right),
                    "data-mutable": "0" if auto_detect else "1",
                    "data-csv-path": data.get("csv_path") or "",
                    "data-metric": data.get("metric") or "",
                    "data-lower-is-better": "1" if data.get("lower_is_better", True) else "0",
                    "data-num-groups": str(data.get("num_groups", 2)),
                    "data-auto-detect": "1" if auto_detect else "0",
                    "data-filter-metric": data.get("filter_metric") or "",
                    "data-filter-min": data.get("filter_min") or "",
                    "data-filter-max": data.get("filter_max") or "",
                    "data-filter-values-json": json.dumps(data.get("filter_values") or []),
                }
                with div(**wrapper_attrs):
                    with div(
                        cls="profile-plot-loading",
                        **{"data-loading-label": "Rendering distribution…"},
                    ):
                        img(
                            src=dist_url,
                            cls="profile-plot-img profile-dist-img",
                            alt="Distribution plot",
                            onload="this.closest('.profile-plot-loading').classList.add('loaded')",
                        )
                    div(
                        id="dist-tooltip",
                        cls="profile-dist-tooltip",
                        style="display:none;",
                    )
            else:
                p("Select a metric to view distribution", cls="muted")

        # Analysis/tree plot — all analyzers now serve HTML via the same endpoint
        with div(cls="profile-plot-cell"):
            with div(cls="profile-plot-title-row"):
                h4("Influence Analysis", cls="profile-plot-title")
                if str(data.get("analyzer") or "").lower() == "tree":
                    span("Use scrollwheel to zoom", cls="profile-plot-helper")
            analysis_tree_url = data.get("analysis_tree_url")
            if analysis_tree_url:
                with div(
                    cls="profile-plot-loading",
                    **{"data-loading-label": "Building decision tree…"},
                ):
                    iframe(
                        src=analysis_tree_url,
                        id="profile-influence-plot",
                        cls="profile-plot-iframe",
                        title="Influence analysis",
                        onload="this.closest('.profile-plot-loading').classList.add('loaded')",
                    )
            else:
                p("Select a metric to run analysis", cls="muted")

    # Distribution narrative
    narrative = data.get("narrative")
    if narrative:
        with div(cls="profile-narrative"):
            raw(f"<p><strong>Distribution Characterization:</strong></p><p>{narrative}</p>")


def _render_factor_detail(data: dict[str, Any]) -> None:
    """Render the factor detail section (scatter + table)."""
    factor = data.get("factor", "")
    if not factor:
        return

    with div(cls="profile-factor-detail"):
        h4(f"Factor: {factor}", cls="profile-factor-title")

        with div(cls="profile-factor-cols"):
            # Factor scatter plot
            with div(cls="profile-factor-plot"):
                scatter_url = data.get("factor_scatter_url")
                if scatter_url:
                    img(src=scatter_url, cls="profile-plot-img", alt=f"{factor} scatter")
                else:
                    p("No scatter data", cls="muted")

            # Factor info/stats (placeholder for now)
            with div(cls="profile-factor-info"):
                factors = data.get("factors", [])
                for f in factors:
                    fname = f.name if hasattr(f, "name") else str(f)
                    if fname == factor:
                        _render_factor_card(f)
                        break

        _render_mitigation_section(data)


def _render_mitigation_section(data: dict[str, Any]) -> None:
    """Render mitigation comparison: metric selector, density plot, and stats table."""
    with div(cls="profile-mitigation"):
        h5("Mitigation Comparison", cls="profile-mitigation-title")

        metrics = data.get("mitigation_metrics") or []
        if metrics:
            with div(cls="profile-mitigation-metric-row"):
                label("Comparison metric", _for="mitigation_metric", cls="field-label")
                with select(
                    id="mitigation_metric",
                    name="mitigation_metric",
                    cls="field-input tomselect-single",
                    form="profile-form",
                ):
                    selected_metric = str(data.get("mitigation_metric") or "")
                    for metric_name in metrics:
                        option(metric_name, value=metric_name, selected=(metric_name == selected_metric))

        if data.get("mitigation_comparison_error"):
            div(str(data.get("mitigation_comparison_error")), cls="error-banner")
        else:
            with div(cls="profile-mitigation-results"):
                with div(cls="profile-mitigation-plot-col"):
                    plot_url = data.get("mitigation_plot_url")
                    if plot_url:
                        img(src=plot_url, cls="profile-plot-img", alt="Mitigation density plot")
                    narrative = data.get("mitigation_narrative")
                    if narrative:
                        with div(cls="profile-narrative"):
                            raw(f"<p>{narrative}</p>")

                with div(cls="profile-mitigation-table-col"):
                    rows = data.get("mitigation_rows") or []
                    if rows:
                        with div(cls="compare-table-wrap"):
                            with table(cls="compare-table"):
                                with thead():
                                    with tr():
                                        th("Statistic")
                                        th("Baseline")
                                        th("Mitigation")
                                        th("% Change")
                                        th("P-value")
                                with tbody():
                                    for row in rows:
                                        with tr():
                                            td(str(row.get("statistic") or ""))
                                            td(str(row.get("baseline") or ""))
                                            td(str(row.get("mitigation") or ""))
                                            td(str(row.get("pct_change") or ""))
                                            td(str(row.get("p_value") or ""))


def _render_factor_card(factor_obj: Any) -> None:
    """Render a factor information card."""
    with div(cls="result-card"):
        with table(cls="profile-factor-table"):
            with tbody():
                if hasattr(factor_obj, "name"):
                    with tr():
                        th("Factor")
                        td(factor_obj.name)
                if hasattr(factor_obj, "strength"):
                    with tr():
                        th("Strength")
                        td(f"{factor_obj.strength:.4f}")
                if hasattr(factor_obj, "direction") and factor_obj.direction:
                    with tr():
                        th("Direction")
                        td(str(factor_obj.direction.name if hasattr(factor_obj.direction, "name") else factor_obj.direction))
                if hasattr(factor_obj, "confidence_interval") and factor_obj.confidence_interval:
                    ci = factor_obj.confidence_interval
                    with tr():
                        th("95% CI")
                        td(f"[{ci[0]:.4f}, {ci[1]:.4f}]")
                if hasattr(factor_obj, "p_value") and factor_obj.p_value is not None:
                    with tr():
                        th("p-value")
                        td(f"{factor_obj.p_value:.4f}")


def _current_url(data: dict[str, Any]) -> str:
    """Build the current profile page URL from data state for redirect."""
    from src.gui.models.profile_state import ProfileState
    return ProfileState.from_dict(data).to_url()


def render_predictors_fragment(
    stats: list[dict[str, Any]],
    excluded_names: set[str],
    search: str,
    base_params: list[tuple[str, str]],
    max_corr: float,
    default_excluded_names: set[str],
) -> str:
    """Render predictor table HTML for the exclude-predictors modal.

    Returns a standalone HTML fragment containing a search box, Select All /
    Deselect All / Reset buttons, and a scrollable table of predictor stats
    (name, non-NA count, correlation, exclude checkbox).
    Each checkbox uses name="excluded_predictor" so the enclosing form can
    collect them on submit.

    Args:
        stats: Predictor statistics from compute_predictor_stats.
        excluded_names: Set of predictor names currently excluded.
        search: Current search term for filtering.
        base_params: URL params to rebuild the hx-get URL for search.
    """
    from urllib.parse import urlencode as _urlencode

    container = div(id="predictors-fragment-content")

    # Compute the hx-get base URL (for search box reloads)
    base_qs = _urlencode(base_params)
    reload_url = f"/ui/profile/predictors-fragment?{base_qs}"

    with container:
        # Toolbar: Search box + action buttons
        with div(cls="profile-predictor-toolbar"):
            input_(
                type="search",
                name="search",
                value=search,
                placeholder="Filter predictors\u2026",
                cls="profile-predictor-search-input",
                id="predictor-search-input",
                **{
                    "hx-get": reload_url,
                    "hx-trigger": "keyup changed delay:300ms",
                    "hx-target": "#predictors-fragment-content",
                    "hx-swap": "outerHTML",
                    "hx-include": "#predictor-search-input,#predictor-max-corr",
                },
            )
            with div(cls="profile-predictor-actions"):
                label("Max correlation", _for="predictor-max-corr", cls="field-label")
                input_(
                    type="range",
                    id="predictor-max-corr",
                    name="max_corr",
                    min="0",
                    max="1",
                    step="0.01",
                    value=f"{max_corr:.2f}",
                    cls="profile-predictor-corr-slider",
                    **{
                        "hx-get": reload_url,
                        "hx-trigger": "change, input delay:120ms",
                        "hx-target": "#predictors-fragment-content",
                        "hx-swap": "outerHTML",
                        "hx-include": "#predictor-search-input,#predictor-max-corr",
                    },
                )
                span(f"{max_corr:.2f}", cls="profile-predictor-summary")
            with div(cls="profile-predictor-actions"):
                button(
                    "Select All",
                    type="button",
                    cls="btn-sm",
                    id="predictor-select-all",
                )
                button(
                    "Deselect All",
                    type="button",
                    cls="btn-sm",
                    id="predictor-deselect-all",
                )
                button(
                    "Reset to Defaults",
                    type="button",
                    cls="btn-sm",
                    id="predictor-reset-defaults",
                )

        if not stats:
            p("No predictor data available.", cls="muted")
            return str(container)

        # Sort by absolute correlation descending, NaN last
        sorted_stats = sorted(
            stats,
            key=lambda r: abs(r.get("correlation") or 0.0)
            if r.get("correlation") is not None and r.get("correlation") == r.get("correlation")
            else -1.0,
            reverse=True,
        )

        if search:
            sl = search.lower()
            sorted_stats = [r for r in sorted_stats if sl in r["name"].lower()]

        if not sorted_stats:
            p("No predictors match the search.", cls="muted")
            return str(container)

        # Summary
        n_excluded = sum(1 for r in sorted_stats if r["name"] in excluded_names)
        span(
            f"Showing {len(sorted_stats)} predictors, {n_excluded} excluded",
            cls="profile-predictor-summary",
        )

        # Scrollable table
        with div(cls="profile-predictor-table-wrapper"):
            with table(cls="profile-predictor-table"):
                with thead():
                    with tr():
                        th("Predictor")
                        th("Non-NA")
                        th("Correlation")
                        th("Exclude")
                with tbody():
                    for row in sorted_stats:
                        name = row["name"]
                        corr = row.get("correlation")
                        non_na = row.get("non_na_count", 0)
                        checked = name in excluded_names
                        corr_str = f"{corr:.3f}" if corr is not None and corr == corr else "N/A"
                        with tr(cls="profile-predictor-row"):
                            td(name)
                            td(f"{non_na:,}" if isinstance(non_na, int) else str(non_na))
                            td(corr_str, cls="profile-predictor-corr")
                            with td():
                                input_(
                                    type="checkbox",
                                    name="excluded_predictor",
                                    value=name,
                                    checked=checked,
                                )

        # Hidden inputs recording which predictors are currently visible.
        # update-exclusions uses this to merge with previously excluded
        # predictors that are not visible in the current (filtered) view.
        for row in sorted_stats:
            input_(type="hidden", name="visible_predictor", value=row["name"])

        # Inline JS for Select All / Deselect All / Reset
        defaults_json = json.dumps(sorted(default_excluded_names))
        script(raw(
            "(function(){"
            "var list=document.getElementById('predictors-fragment-content');"
            "if(!list)return;"
            "list.querySelector('#predictor-select-all')"
            ".addEventListener('click',function(){"
            "list.querySelectorAll('input[name=excluded_predictor]')"
            ".forEach(function(cb){cb.checked=true;});});"
            "list.querySelector('#predictor-deselect-all')"
            ".addEventListener('click',function(){"
            "list.querySelectorAll('input[name=excluded_predictor]')"
            ".forEach(function(cb){cb.checked=false;});});"
            "list.querySelector('#predictor-reset-defaults')"
            ".addEventListener('click',function(){"
            f"var defaults={defaults_json};"
            "list.querySelectorAll('input[name=excluded_predictor]')"
            ".forEach(function(cb){"
            "cb.checked=defaults.indexOf(cb.value)>=0;});});"
            "})()"
        ))

    return str(container)


def render_analysis_fragment(data: dict[str, Any]) -> str:
    """Render the analysis results HTML fragment (returned by HTMX endpoint).

    Contains: factor analysis (scatter + comparison table) and mitigation section.
    Laid out as two horizontal-rule-separated groups matching the old GUI.
    """
    container = div(cls="analysis-fragment")
    with container:
        # Error message
        if data.get("analysis_error"):
            div(str(data["analysis_error"]), cls="error-banner")
            return str(container)

        # Quality info
        quality = data.get("quality")
        if quality:
            with div(cls="profile-quality"):
                if hasattr(quality, "accuracy"):
                    span(f"Model accuracy: {quality.accuracy:.1%}", cls="profile-quality-text")
                if hasattr(quality, "rank_auc"):
                    span(f" | Rank-AUC: {quality.rank_auc:.3f}", cls="profile-quality-text")

        # --- Factor Analysis Group ---
        factor = data.get("factor", "")
        factors = data.get("factors", [])

        if factor:
            with div(cls="profile-factor-group"):
                h4(f"Factor Analysis: {factor}", cls="profile-section-title")
                with div(cls="profile-factor-three-col"):
                    # Column 1: 3-tab card (narrative / description / mitigations)
                    with div(cls="profile-factor-tabs-col"):
                        _render_factor_tabset(data)

                    # Column 2: Scatter plot
                    with div(cls="profile-factor-scatter-col"):
                        scatter_url = data.get("factor_scatter_url")
                        if scatter_url:
                            img(src=scatter_url, cls="profile-plot-img", alt=f"{factor} scatter")
                        else:
                            p("No scatter data available", cls="muted")

                    # Column 3: Comparison table
                    with div(cls="profile-factor-comparison-col"):
                        _render_factor_comparison(data)
        elif factors:
            with div(cls="profile-factor-group"):
                p("Select a factor from the sidebar to view detailed analysis.", cls="muted")

        # --- Mitigation Group (only if mitigation data exists) ---
        if data.get("mitigation_csv_exists"):
            div(cls="profile-section-hr")
            _render_mitigation_section(data)

        # Emit JS to populate the sidebar factor selector with analysis results
        if factors:
            factor_names = []
            for f in factors:
                fname = f.name if hasattr(f, "name") else str(f)
                factor_names.append(fname)
            selected = str(data.get("factor") or "")
            js_factors = json.dumps(factor_names)
            js_selected = json.dumps(selected)
            script(raw(
                f"(function(){{"
                f"var sel=document.getElementById('factor');"
                f"if(!sel)return;"
                f"var ts=sel.tomselect;"
                f"if(ts){{"
                f"ts.clear(true);ts.clearOptions();"
                f"var factors={js_factors};"
                f"factors.forEach(function(f){{ts.addOption({{value:f,text:f}});}});"
                f"if({js_selected})ts.setValue({js_selected},true);"
                f"}}else{{"
                f"var factors={js_factors};"
                f"sel.innerHTML='<option value=\"\">(choose a factor)</option>';"
                f"factors.forEach(function(f){{"
                f"var o=document.createElement('option');"
                f"o.value=f;o.textContent=f;"
                f"if(f==={js_selected})o.selected=true;"
                f"sel.appendChild(o);"
                f"}});"
                f"}}"
                f"}})()"
            ))

        # Hidden element: cleaned column names for the exclude-predictors modal.
        # JavaScript reads this after the HTMX fragment loads (htmx:afterSwap)
        # to populate the modal's checkbox list dynamically.
        cleaned_cols = data.get("cleaned_columns") or []
        if cleaned_cols:
            div(
                id="profile-cleaned-columns",
                data_columns=json.dumps(cleaned_cols),
                style="display:none",
            )

    return str(container)


def _render_mitigation_tab_content(data: dict[str, Any]) -> None:
    """Render the Mitigations tab content inside the factor tabset."""
    factor = str(data.get("factor") or "")
    mitigations = data.get("mitigation_choices") or []

    if not mitigations:
        p(f"No mitigations suggested for {factor}.", cls="muted")
        return

    with div(cls="profile-mitigation-compact"):
        label("Choose mitigation", _for="mitigation", cls="field-label")
        with div(cls="profile-mitigation-action-row"):
            with div(cls="profile-mitigation-select-wrap"):
                with select(
                    id="mitigation",
                    name="mitigation",
                    cls="field-input",
                    form="profile-form",
                ):
                    selected_mitigation = str(data.get("mitigation") or "")
                    option("(select a mitigation)", value="", selected=(not selected_mitigation))
                    for mitigation_name in mitigations:
                        option(
                            mitigation_name,
                            value=mitigation_name,
                            selected=(mitigation_name == selected_mitigation),
                        )

            # Use preview_mitigation when the user hasn't explicitly chosen one
            # (auto-preview of the first choice) to show info / "Try it!" without
            # submitting an unintended value with the main profile form.
            active_mitigation = str(data.get("mitigation") or data.get("preview_mitigation") or "")
            if active_mitigation:
                from urllib.parse import urlencode as _ue
                modal_url = _current_url(data)
                extra: list[tuple[str, str]] = []
                if not data.get("mitigation") and data.get("preview_mitigation"):
                    extra.append(("mitigation", active_mitigation))
                extra.append(("show_mitigation_modal", "1"))
                sep = "&" if "?" in modal_url else "?"
                a(
                    "Try it!",
                    href=f"{modal_url}{sep}{_ue(extra)}",
                    cls="btn btn-primary profile-mitigation-btn",
                )

        info = data.get("mitigation_info")
        if isinstance(info, dict):
            with div(cls="profile-mitigation-info"):
                p(str(info.get("description") or ""), cls="profile-mitigation-desc")
                refs = info.get("references") or {}
                if refs:
                    with p(cls="profile-mitigation-refs"):
                        span("References: ", cls="profile-mitigation-label")
                        first = True
                        for ref_name, ref_url in refs.items():
                            if not first:
                                span(" \u00b7 ")
                            a(str(ref_name), href=str(ref_url), target="_blank", rel="noopener")
                            first = False
                if not info.get("is_automated", False):
                    p(
                        "Not automated. Apply manually, then use existing data.",
                        cls="profile-mitigation-manual",
                    )


def _render_factor_comparison(data: dict[str, Any]) -> None:
    """Render factor statistics-by-group comparison table."""
    rows = data.get("factor_comparison_rows") or []
    if not rows:
        p("No group comparison available", cls="muted")
        return

    with div(cls="compare-table-wrap"):
        with table(cls="compare-table"):
            with thead():
                with tr():
                    th("Group")
                    th("Count")
                    th("Mean")
                    th("Std Dev")
                    th("Median")
            with tbody():
                for row in rows:
                    row_color = str(row.get("color") or "")
                    row_style = f"background-color:{row_color};" if row_color else ""
                    with tr(style=row_style):
                        td(str(row.get("group", "")))
                        td(str(row.get("count", "")))
                        td(str(row.get("mean", "")))
                        td(str(row.get("std", "")))
                        td(str(row.get("median", "")))


def _render_factor_tabset(data: dict[str, Any]) -> None:
    """Render the tabbed card matching old GUI: Factor analysis / Description / Mitigations."""
    factor = str(data.get("factor") or "")
    tab_id = "factor-tabs"

    # Tab navigation
    with ul(cls="profile-tab-nav", role="tablist"):
        li("Factor analysis", cls="profile-tab active", role="tab",
           **{"data-tab": f"{tab_id}-analysis"})
        li("Description", cls="profile-tab", role="tab",
           **{"data-tab": f"{tab_id}-desc"})
        li("Mitigations", cls="profile-tab", role="tab",
           **{"data-tab": f"{tab_id}-mitigations"})

    # Tab panels
    with div(cls="profile-tab-panels"):
        # Panel 1: Factor analysis (narrative)
        with div(cls="profile-tab-panel active", id=f"{tab_id}-analysis"):
            narrative_html = data.get("factor_narrative_html") or ""
            if narrative_html:
                raw(narrative_html)
            else:
                p("No analysis narrative available.", cls="muted")

        # Panel 2: Description
        with div(cls="profile-tab-panel", id=f"{tab_id}-desc"):
            factor_info = data.get("factor_info")
            if factor_info and isinstance(factor_info, dict):
                desc = factor_info.get("description", "")
                refs = factor_info.get("references", {})
                if desc:
                    p(str(desc), cls="profile-factor-desc")
                if refs:
                    with p(cls="profile-factor-refs"):
                        span("References: ", cls="profile-factor-refs-label")
                        first = True
                        for ref_name, ref_url in refs.items():
                            if not first:
                                span(" \u00b7 ")
                            a(ref_name, href=str(ref_url), target="_blank", rel="noopener")
                            first = False
            else:
                p("No description available for this factor.", cls="muted")

        # Panel 3: Mitigations
        with div(cls="profile-tab-panel", id=f"{tab_id}-mitigations"):
            _render_mitigation_tab_content(data)
