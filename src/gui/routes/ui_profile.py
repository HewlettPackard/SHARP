# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Route handlers for the Profile tab."""

import json

from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

from src.gui.components.profile import profile_page, render_predictors_fragment
from src.gui.models.profile_state import ProfileState
from src.gui.services.explore import _filter_config_for_metric, _load_filtered_dataframe
from src.gui.utils.profile.predictor_stats import DEFAULT_EXCLUDED_PREDICTORS
from src.gui.services.exclusion_store import (
    create_exclusion_state,
    get_excluded_predictors,
    has_custom_exclusions,
)
from src.gui.services.profile import (
    build_source_prompt_data,
    compute_factor_comparison_rows,
    compute_mitigation_comparison,
    get_distribution_meta,
    get_factor_narrative_html,
    default_profile_task_name,
    get_factor_mitigations,
    get_mitigation_metrics,
    get_analyzer_choices,
    get_metric_direction,
    is_profile_csv,
    list_profile_task_choices,
    list_profiling_backends,
    load_mitigation_info,
    load_profile_dataset,
    load_profile_form_data,
    move_distribution_cutoff,
    search_profile_filter_metrics,
    render_mitigation_density_plot_png,
    render_analysis_plot_png,
    render_analysis_tree_html,
    render_distribution_plot_png,
    render_factor_scatter_png,
    resolve_mitigation_paths,
    run_profile_workflow,
    run_mitigation_workflow,
)
from src.gui.services.profile_jobs import get_profile_job
from src.gui.services.profile_jobs import start_profile_job
from src.gui.services.profile_jobs import wait_for_profile_job_update
from src.core.config.settings import Settings
from src.gui.services.shared import search_outcome_metrics

router = APIRouter(prefix="/ui")


def _build_profile_success_redirect_url(workflow: dict[str, Any]) -> str:
    """Build redirect URL for a completed profiling run."""
    prof_csv = str(workflow.get("profile_csv") or "")
    prof_task = Path(prof_csv).stem if prof_csv else ""
    notice = str(workflow.get("notice") or "Profiling completed successfully.")
    backend_warnings = workflow.get("warnings") or []
    if backend_warnings:
        warning_lines = "\n".join(str(w) for w in backend_warnings)
        notice = f"{notice}\n\nWarning: {warning_lines}"
    return _append_redirect_params(
        "/ui/profile",
        {
            "experiment": Path(prof_csv).parent.name if prof_csv else "",
            "task": prof_task,
            "csv_path": prof_csv,
            "notice": notice,
        },
    )


def _build_profile_error_redirect_url(redirect_url: str, csv_path: str, error: str) -> str:
    """Build redirect URL for a failed profiling run."""
    safe_redirect = redirect_url or "/ui/profile"
    return _append_redirect_params(
        safe_redirect,
        {
            "error": str(error or "Profiling failed."),
            "source": "profile",
            "show_profile_config": "1",
            "csv_path": csv_path,
        },
    )


def _no_cache_headers() -> dict[str, str]:
    """Headers that force browsers/proxies to always fetch fresh content."""
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }


def _html_no_cache(content: str) -> HTMLResponse:
    """Build an HTML response with no-cache headers applied."""
    return HTMLResponse(content=content, headers=_no_cache_headers())


def _init_profile_data(state: ProfileState) -> tuple[dict, HTMLResponse | None]:
    """Load form skeleton (experiments, tasks, metrics) and resolve csv_path from task.

    Returns (data, None) normally, or (data, response) for an early exit.
    """
    try:
        data = load_profile_form_data()
    except Exception as exc:  # noqa: BLE001
        data = {
            "experiments": [],
            "tasks": [],
            "metrics": [],
            "filter_metrics": [],
            "analyzer_choices": {},
        }
        data.update(state.to_template_data())
        data["error"] = f"Unable to load profile metadata: {exc}"
        return data, _html_no_cache(profile_page(data))

    data.update(state.to_template_data())
    data["predictor_max_corr"] = Settings().get("profiling.max_correlation", 0.99)

    try:
        data["tasks"] = list_profile_task_choices(state.experiment)
    except Exception as exc:  # noqa: BLE001
        data["tasks"] = []
        data["error"] = f"Unable to load tasks for experiment '{state.experiment}': {exc}"

    # Resolve csv_path from task label when not supplied directly
    if state.experiment and state.task and not state.csv_path:
        for c in data.get("tasks") or []:
            if c["label"] == state.task:
                state.csv_path = c["csv_path"]
                data["csv_path"] = state.csv_path
                break

    # Resolve extra-task CSV paths for multi-task merging
    extra_task_csv_pairs: list[tuple[str, str]] = []
    if state.experiment and state.extra_tasks:
        label_to_csv = {c["label"]: c["csv_path"] for c in (data.get("tasks") or [])}
        # Keep the primary csv_path aligned with the primary task label so a
        # mismatched csv_path in the URL cannot pair the first task with the
        # wrong CSV (which would overlap/duplicate datapoints on merge).
        if state.task in label_to_csv:
            state.csv_path = label_to_csv[state.task]
            data["csv_path"] = state.csv_path
        for extra in state.extra_tasks:
            if extra in label_to_csv:
                extra_task_csv_pairs.append((extra, label_to_csv[extra]))
    data["_extra_task_csv_pairs"] = extra_task_csv_pairs

    # Initial excluded predictors (refined later once dataset is loaded)
    # Custom selections are stored behind a UUID token so the same base URL
    # does not rehydrate stale unsaved state after navigation.
    excluded_predictors = (
        get_excluded_predictors(state.excluded_state, state.csv_path, state.metric)
        if state.csv_path and state.metric
        else list(DEFAULT_EXCLUDED_PREDICTORS)
    )
    data["excluded_count"] = len(excluded_predictors)
    data["excluded_names"] = excluded_predictors

    if state.experiment and state.task and not state.csv_path:
        data["error"] = (
            f"Could not resolve task '{state.task}' in experiment '{state.experiment}'. "
            "Please choose a task from the Task dropdown."
        )

    return data, None


def _handle_source_selection(state: ProfileState, data: dict) -> HTMLResponse | None:
    """Handle source-type routing for non-prof CSVs; return early response or None."""
    # Mirror old Profile modal: for non-prof CSVs, prompt the user to choose
    # source (use existing data / profile task) before loading data.
    if not is_profile_csv(state.csv_path) and state.source not in {
        "use_existing", "use_original", "profile"
    }:
        prompt = build_source_prompt_data(state.csv_path)
        data.update(prompt)
        data["source_prompt"] = True
        data["profiling_backends"] = list_profiling_backends()
        data["default_profile_task_name"] = default_profile_task_name(prompt.get("original_md") or "")
        return _html_no_cache(profile_page(data))

    if state.source == "use_existing":
        prompt = build_source_prompt_data(state.csv_path)
        data.update(prompt)
        if prompt.get("has_prof_csv"):
            state.csv_path = str(prompt.get("prof_csv") or state.csv_path)
            data["csv_path"] = state.csv_path
            prof_label = ""
            for choice in data.get("tasks", []):
                if choice.get("csv_path") == state.csv_path:
                    prof_label = str(choice.get("label") or "")
                    break
            state.task = prof_label or Path(state.csv_path).stem
            data["task"] = state.task
        else:
            data["error"] = "Profiling data was not found for this task."
            data["source_prompt"] = True
            data["profiling_backends"] = list_profiling_backends()
            data["default_profile_task_name"] = default_profile_task_name(prompt.get("original_md") or "")
            return _html_no_cache(profile_page(data))

    if state.source in {"use_original", "profile"}:
        prompt = build_source_prompt_data(state.csv_path)
        data.update(prompt)
        if state.source == "profile" or state.show_profile_config:
            data["source_prompt"] = True
            data["show_profile_config"] = True
            data["profiling_backends"] = list_profiling_backends()
            data["default_profile_task_name"] = default_profile_task_name(prompt.get("original_md") or "")
            return _html_no_cache(profile_page(data))

    return None


def _compute_auto_excluded(active_csv: str, active_metric: str, max_corr: float) -> list[str]:
    """Return predictors whose correlation exceeds max_corr. Returns [] on any error."""
    try:
        from src.core.runlogs.reader import load_table
        from src.gui.utils.profile.predictor_stats import (
            compute_predictor_stats,
            get_auto_excluded_predictors,
        )
        stats_df = load_table(active_csv)
        raw_stats = compute_predictor_stats(stats_df, active_metric)
        return get_auto_excluded_predictors(raw_stats, max_corr)
    except Exception:
        return []


def _resolve_excluded_predictors(
    state: ProfileState,
    settings: Any,
    active_metric: str,
    active_csv: str,
    data: dict,
) -> list[str]:
    """Determine which predictors to exclude and sync counts into *data*."""
    excluded: list[str] = list(DEFAULT_EXCLUDED_PREDICTORS)
    if not active_metric:
        return excluded

    max_corr = float(data.get("predictor_max_corr", 0.99))
    # Exclusion tokens are stored keyed by the active (merged, in multi-task
    # mode) CSV — matching what the modal and update-exclusions endpoint use —
    # so read them back with active_csv, not the primary state.csv_path.
    if has_custom_exclusions(state.excluded_state, active_csv, active_metric):
        user_excluded = get_excluded_predictors(state.excluded_state, active_csv, active_metric)
        auto_excluded = _compute_auto_excluded(active_csv, active_metric, max_corr)
        excluded = sorted(set(user_excluded) | set(auto_excluded))
    elif settings and settings.default_predictor_exclusions:
        # Saved exclusions take precedence over auto-exclusion; using
        # auto-exclusion here would produce a different set and corrupt
        # the tooltip count.
        excluded = sorted(
            set(DEFAULT_EXCLUDED_PREDICTORS) | set(settings.default_predictor_exclusions)
        )
    else:
        auto_excluded = _compute_auto_excluded(active_csv, active_metric, max_corr)
        excluded = sorted(set(DEFAULT_EXCLUDED_PREDICTORS) | set(auto_excluded))

    data["excluded_count"] = len(excluded)
    data["excluded_names"] = excluded
    return excluded


def _apply_filter_config(
    state: ProfileState,
    settings: Any,
    active_csv: str,
    data: dict,
) -> None:
    """Populate filter UI config and restore saved filter values into *state* and *data*."""
    if not state.filter_metric:
        return

    from src.core.runlogs.reader import load_table
    data["filter_metric"] = state.filter_metric
    df = load_table(active_csv)
    filter_config = _filter_config_for_metric(df, state.filter_metric)
    data.update(filter_config)

    if (
        settings
        and settings.default_filter_value is not None
        and not state.filter_min
        and not state.filter_max
        and not state.filter_values
    ):
        from src.gui.utils.profile.restore import resolve_filter_restore_value
        fv_result = resolve_filter_restore_value(
            data=df,
            filter_metric=state.filter_metric,
            preset_filter_metric=settings.default_filter_metric,
            preset_filter_value=settings.default_filter_value,
        )
        if fv_result is not None:
            kind, value = fv_result
            if kind == "slider" and isinstance(value, list) and len(value) == 2:
                state.filter_min = str(value[0])
                state.filter_max = str(value[1])
                data["filter_min"] = state.filter_min
                data["filter_max"] = state.filter_max
            elif kind == "selectize" and isinstance(value, list):
                state.filter_values = [str(v) for v in value]
                data["filter_values"] = state.filter_values


def _compute_row_count_and_narrative(
    state: ProfileState,
    active_metric: str,
    active_csv: str,
    dataset: dict,
    data: dict,
) -> None:
    """Compute filtered row count and optional distribution narrative into *data*."""
    if not active_metric:
        data["filtered_rows"] = dataset.get("rows", 0)
        return

    filtered_df = _load_filtered_dataframe(
        active_csv,
        state.filter_metric or "",
        None,
        filter_values=state.filter_values,
        filter_min=state.filter_min or None,
        filter_max=state.filter_max or None,
    )
    data["filtered_rows"] = filtered_df.height
    try:
        from src.core.stats.distribution import characterize_distribution
        metric_vals = filtered_df[active_metric].drop_nulls().to_numpy()
        if len(metric_vals) >= 3:
            data["narrative"] = characterize_distribution(metric_vals)
    except Exception:
        pass


def _build_plot_and_fragment_urls(
    state: ProfileState,
    data: dict,
    active_metric: str,
    active_csv: str,
    excluded_predictors: list[str],
) -> None:
    """Build distribution, analysis, and fragment URL strings into *data*."""
    plot_params = _build_common_params(data, active_csv, active_metric)
    for cv in state.cutoff_values:
        plot_params.append(("cutoff_value", str(cv)))

    data["distribution_plot_url"] = (
        "/ui/profile/distribution.png?" + urlencode(plot_params)
    )
    data["distribution_meta"] = get_distribution_meta(
        active_csv,
        active_metric,
        lower_is_better=bool(data.get("lower_is_better", True)),
        num_groups=int(data.get("num_groups", 2)),
        auto_detect=bool(data.get("auto_detect", False)),
        filter_metric=state.filter_metric or None,
        filter_min=state.filter_min or None,
        filter_max=state.filter_max or None,
        filter_values=state.filter_values or None,
        cutoff_values=list(state.cutoff_values) or None,
    )

    analysis_params = plot_params + [("analyzer", state.analyzer)]
    for ep in excluded_predictors:
        analysis_params.append(("excluded_predictor", ep))
    data["analysis_plot_url"] = (
        "/ui/profile/analysis.png?" + urlencode(analysis_params)
    )
    data["analysis_tree_url"] = (
        "/ui/profile/analysis-tree.html?" + urlencode(analysis_params)
    )

    fragment_params = analysis_params[:]
    for key in ("factor", "mitigation", "mitigation_metric", "mitigation_csv"):
        val = getattr(state, key)
        if val:
            fragment_params.append((key, val))
    if state.experiment:
        fragment_params.append(("experiment", state.experiment))
    if state.task:
        fragment_params.append(("task", state.task))
    data["analysis_fragment_url"] = (
        "/ui/profile/analysis-fragment?" + urlencode(fragment_params)
    )


def _load_profile_dataset_section(state: ProfileState, data: dict) -> None:
    """Load the profile dataset and populate all analysis data into *data*."""
    try:
        # Build task_csv_pairs for multi-task merging (set by _init_profile_data)
        extra_task_csv_pairs: list[tuple[str, str]] = data.pop("_extra_task_csv_pairs", [])
        task_csv_pairs: list[tuple[str, str]] | None = None
        if extra_task_csv_pairs and state.task and state.csv_path:
            task_csv_pairs = [(state.task, state.csv_path)] + extra_task_csv_pairs

        dataset = load_profile_dataset(state.csv_path, task_csv_pairs=task_csv_pairs)
        data.update(dataset)

        active_metric = state.metric or dataset.get("metric") or ""
        state.metric = active_metric
        data["metric"] = active_metric

        active_csv = dataset.get("active_csv", state.csv_path)
        data["active_csv"] = active_csv

        settings = dataset.get("settings")

        # Restore saved max-correlation threshold (not a URL param; always
        # applied when present so the exclusion block below uses the right value).
        if settings and settings.default_max_correlation is not None:
            data["predictor_max_corr"] = settings.default_max_correlation

        # Build available analyzer choices (used both here and by apply_defaults).
        # TE is excluded in classification mode; choices are built before
        # apply_defaults to preserve the existing ordering of operations.
        choices = get_analyzer_choices()
        is_regression = (state.num_groups == 1)
        if not is_regression and "te" in choices:
            choices = {k: v for k, v in choices.items() if k != "te"}

        # Apply ProfileSettings defaults for all fields not explicit in the URL.
        state.apply_defaults(settings, available_analyzers=choices)

        # Reset to tree if selected analyzer is unavailable in current choices
        if not state.analyzer or state.analyzer not in choices:
            state.analyzer = "tree" if "tree" in choices else next(iter(choices), "")
        data["analyzer_choices"] = choices

        # Sync all state changes back to the template data dict
        data.update(state.to_template_data())

        # lower_is_better from markdown (only when not explicit in URL;
        # kept here because it needs the markdown file path from the dataset).
        # Use the originating task's markdown for the metric direction: in
        # multi-task mode md_path points at the dedicated combined-settings
        # file, which carries no metric frontmatter.
        if not state.is_explicit("lower_is_better"):
            direction_md = dataset.get("original_md") or dataset.get("md_path", "")
            if active_metric and direction_md:
                state.lower_is_better = get_metric_direction(active_metric, direction_md)
                data["lower_is_better"] = state.lower_is_better

        excluded_predictors = _resolve_excluded_predictors(
            state, settings, active_metric, active_csv, data
        )
        _apply_filter_config(state, settings, active_csv, data)
        _compute_row_count_and_narrative(state, active_metric, active_csv, dataset, data)

        if active_metric and active_csv:
            _build_plot_and_fragment_urls(state, data, active_metric, active_csv, excluded_predictors)

    except Exception as exc:  # noqa: BLE001
        data["error"] = str(exc)


def _populate_mitigation_modal(state: ProfileState, data: dict) -> None:
    """Fill mitigation-modal fields when the Try-it! overlay is open."""
    if not (state.show_mitigation_modal and data.get("mitigation") and state.csv_path):
        return
    paths = resolve_mitigation_paths(
        str(data.get("csv_path") or state.csv_path), str(data["mitigation"])
    )
    mit_csv = state.mitigation_csv or paths.get("mitigation_csv", "")
    data["mitigation_baseline_md"] = paths.get("baseline_md", "")
    data["mitigation_csv_exists"] = bool(mit_csv and Path(mit_csv).exists())


@router.get("/profile", response_class=HTMLResponse, include_in_schema=False)
def get_profile(request: Request) -> HTMLResponse:
    """Render Profile page with all state from query parameters."""
    state = ProfileState.from_request(request)

    data, early = _init_profile_data(state)
    if early:
        return early

    if state.experiment and state.csv_path:
        # Source-selection prompt is only meaningful for single-task mode
        if not state.extra_tasks:
            early = _handle_source_selection(state, data)
            if early:
                return early
        _load_profile_dataset_section(state, data)
        # Allow an explicit max_corr URL param (e.g. relayed from update_exclusions)
        # to override the saved-settings or global default.
        max_corr_raw = request.query_params.get("max_corr", "")
        if max_corr_raw:
            try:
                data["predictor_max_corr"] = max(0.0, min(1.0, float(max_corr_raw)))
            except ValueError:
                pass

    _populate_mitigation_modal(state, data)
    return _html_no_cache(profile_page(data))


@router.get("/profile/filter-metrics", include_in_schema=False)
def get_profile_filter_metrics(
    csv_path: str = Query(""),
    q: str = Query(""),
    limit: int = Query(150, ge=1, le=500),
) -> JSONResponse:
    """Search filter metrics for large profile datasets."""
    if not csv_path:
        return JSONResponse({"items": []}, headers=_no_cache_headers())

    try:
        matches = search_profile_filter_metrics(csv_path, q, limit)
    except Exception:
        matches = []

    items = [{"value": m, "text": m, "label": m} for m in matches]
    return JSONResponse({"items": items}, headers=_no_cache_headers())


@router.get("/profile/metrics", include_in_schema=False)
def get_profile_metrics(
    csv_path: str = Query(""),
    q: str = Query(""),
    limit: int = Query(150, ge=1, le=500),
) -> JSONResponse:
    """Search outcome (numeric) metrics for large profile datasets."""
    if not csv_path:
        return JSONResponse({"items": []}, headers=_no_cache_headers())

    try:
        matches = search_outcome_metrics(csv_path, q, limit)
    except Exception:
        matches = []

    items = [{"value": m, "text": m, "label": m} for m in matches]
    return JSONResponse({"items": items}, headers=_no_cache_headers())


def _build_common_params(data: dict, active_csv: str, metric: str) -> list[tuple[str, str]]:
    """Build common query parameters for plot URLs."""
    params = [
        ("csv_path", active_csv),
        ("metric", metric),
        ("lower_is_better", "1" if data.get("lower_is_better", True) else "0"),
        ("num_groups", str(data.get("num_groups", 2))),
        ("auto_detect", "1" if data.get("auto_detect", False) else "0"),
        ("filter_metric", data.get("filter_metric") or ""),
        ("filter_min", data.get("filter_min") or ""),
        ("filter_max", data.get("filter_max") or ""),
    ]
    for v in data.get("filter_values") or []:
        params.append(("filter_values", v))
    return params


@router.get("/profile/analysis-fragment", response_class=HTMLResponse, include_in_schema=False)
def get_analysis_fragment(
    csv_path: str = "",
    metric: str = "",
    lower_is_better: str = "1",
    num_groups: int = 2,
    auto_detect: str = "0",
    analyzer: str = "tree",
    filter_metric: str = "",
    filter_min: str = "",
    filter_max: str = "",
    filter_values: list[str] = Query(default=[]),
    cutoff_value: list[str] = Query(default=[]),
    factor: str = "",
    mitigation: str = "",
    mitigation_metric: str = "",
    mitigation_csv: str = "",
    excluded_predictor: list[str] = Query(default=[]),
    experiment: str = "",
    task: str = "",
) -> HTMLResponse:
    """Return analysis results as an HTMX HTML fragment (loaded async).

    This endpoint runs the potentially-slow analysis and returns the
    factor list, quality info, and mitigation data as a ready-to-swap
    HTML fragment. The main page loads instantly and this fills in later.
    """
    from src.gui.services.profile import _compute_profile_analysis_cached
    from src.gui.components.profile import render_analysis_fragment

    if not csv_path or not metric:
        return _html_no_cache('<p class="muted">No analysis to run.</p>')

    parsed_cutoffs: list[float] | None = None
    if cutoff_value:
        try:
            parsed_cutoffs = [float(v) for v in cutoff_value]
        except (TypeError, ValueError):
            parsed_cutoffs = None

    analysis = _compute_profile_analysis_cached(
        csv_path=csv_path,
        metric=metric,
        lower_is_better=lower_is_better != "0",
        num_groups=num_groups,
        auto_detect=auto_detect != "0",
        analyzer_name=analyzer,
        filter_metric=filter_metric or None,
        filter_min=filter_min or None,
        filter_max=filter_max or None,
        filter_values=filter_values or None,
        excluded_predictors=excluded_predictor or None,
        cutoff_values=parsed_cutoffs,
    )

    fragment_data: dict = {
        "analyzer": analyzer,
        "csv_path": csv_path,
        "metric": metric,
        "lower_is_better": lower_is_better != "0",
        "factor": factor,
        "mitigation": mitigation,
        "mitigation_metric": mitigation_metric,
        "experiment": experiment,
        "task": task,
    }

    if not analysis.get("error"):
        fragment_data["factors"] = analysis.get("factors", [])
        fragment_data["quality"] = analysis.get("quality")
        fragment_data["analysis_error"] = None
        fragment_data["cleaned_columns"] = [
            str(c) for c in (analysis.get("cleaned_columns") or [])
        ]
    else:
        fragment_data["factors"] = []
        fragment_data["analysis_error"] = analysis["error"]

    # Factor scatter plot and comparison table
    if factor and not analysis.get("error"):
        plot_params = [
            ("csv_path", csv_path),
            ("metric", metric),
            ("lower_is_better", lower_is_better),
            ("num_groups", str(num_groups)),
            ("auto_detect", auto_detect),
            ("filter_metric", filter_metric),
            ("filter_min", filter_min),
            ("filter_max", filter_max),
        ]
        for v in filter_values or []:
            plot_params.append(("filter_values", v))
        scatter_params = plot_params + [("factor_name", factor)]
        fragment_data["factor_scatter_url"] = (
            "/ui/profile/factor_scatter.png?" + urlencode(scatter_params)
        )

        # Compute factor comparison table rows
        fragment_data["factor_comparison_rows"] = compute_factor_comparison_rows(
            csv_path=csv_path,
            metric=metric,
            factor_name=factor,
            lower_is_better=lower_is_better != "0",
            num_groups=num_groups,
            auto_detect=auto_detect != "0",
            filter_metric=filter_metric or None,
            filter_min=filter_min or None,
            filter_max=filter_max or None,
            filter_values=filter_values or None,
        )

        # Load factor description/info
        from src.core.metrics.factors import get_factor_info
        factor_info = get_factor_info(factor)
        if factor_info:
            fragment_data["factor_info"] = factor_info

        # Generate analysis narrative for the selected factor
        fragment_data["factor_narrative_html"] = get_factor_narrative_html(
            analysis, factor
        )

    # Mitigation section
    if factor:
        mitigation_choices = get_factor_mitigations(factor)
        fragment_data["mitigation_choices"] = mitigation_choices

        # Show info/refs/"Try it" for the first mitigation even before the user
        # picks one.  Use "preview_mitigation" (not "mitigation") for the
        # auto-selected value so the <select> stays at "(select a mitigation)"
        # and the auto-preview does NOT get submitted with the main form.
        display_mitigation = mitigation or (mitigation_choices[0] if mitigation_choices else "")
        if display_mitigation:
            fragment_data["mitigation_info"] = load_mitigation_info(display_mitigation)
            if mitigation:
                fragment_data["mitigation"] = mitigation
            else:
                fragment_data["preview_mitigation"] = display_mitigation

        if mitigation:
            paths = resolve_mitigation_paths(csv_path, mitigation)
            baseline_csv = paths.get("baseline_csv", "")
            mitigation_csv_resolved = mitigation_csv or paths.get("mitigation_csv", "")

            fragment_data["mitigation_baseline_csv"] = baseline_csv
            fragment_data["mitigation_baseline_md"] = paths.get("baseline_md", "")
            fragment_data["mitigation_csv"] = mitigation_csv_resolved
            fragment_data["mitigation_csv_exists"] = bool(
                mitigation_csv_resolved and Path(mitigation_csv_resolved).exists()
            )

            if fragment_data["mitigation_csv_exists"]:
                mitigation_metrics = get_mitigation_metrics(
                    baseline_csv, mitigation_csv_resolved
                )
                fragment_data["mitigation_metrics"] = mitigation_metrics

                selected_mit_metric = (
                    mitigation_metric
                    if mitigation_metric in mitigation_metrics
                    else "inner_time"
                    if "inner_time" in mitigation_metrics
                    else "outer_time"
                    if "outer_time" in mitigation_metrics
                    else metric
                    if metric in mitigation_metrics
                    else (mitigation_metrics[0] if mitigation_metrics else "")
                )
                fragment_data["mitigation_metric"] = selected_mit_metric

                if selected_mit_metric:
                    mit_plot_params = [
                        ("baseline_csv", baseline_csv),
                        ("mitigation_csv", mitigation_csv_resolved),
                        ("metric", selected_mit_metric),
                        ("filter_metric", filter_metric),
                        ("filter_min", filter_min),
                        ("filter_max", filter_max),
                    ]
                    for v in filter_values or []:
                        mit_plot_params.append(("filter_values", v))
                    fragment_data["mitigation_plot_url"] = (
                        "/ui/profile/mitigation_density.png?" + urlencode(mit_plot_params)
                    )

                    mitigation_comparison = compute_mitigation_comparison(
                        baseline_csv=baseline_csv,
                        mitigation_csv=mitigation_csv_resolved,
                        metric=selected_mit_metric,
                        lower_is_better=lower_is_better != "0",
                        filter_metric=filter_metric or None,
                        filter_min=filter_min or None,
                        filter_max=filter_max or None,
                        filter_values=filter_values or None,
                    )
                    fragment_data["mitigation_comparison_error"] = mitigation_comparison.get("error")
                    fragment_data["mitigation_narrative"] = mitigation_comparison.get("narrative")
                    fragment_data["mitigation_rows"] = mitigation_comparison.get("rows") or []

    return _html_no_cache(render_analysis_fragment(fragment_data))


@router.get("/profile/distribution.png", include_in_schema=False)
def get_distribution_plot(
    csv_path: str,
    metric: str,
    lower_is_better: str = "1",
    num_groups: int = 2,
    auto_detect: str = "0",
    filter_metric: str = "",
    filter_min: str = "",
    filter_max: str = "",
    filter_values: list[str] = Query(default=[]),
    cutoff_value: list[str] = Query(default=[]),
) -> Response:
    """Render profile distribution plot as PNG."""
    parsed_cutoffs: list[float] | None = None
    if cutoff_value:
        try:
            parsed_cutoffs = [float(v) for v in cutoff_value]
        except ValueError:
            parsed_cutoffs = None
    content = render_distribution_plot_png(
        csv_path=csv_path,
        metric=metric,
        lower_is_better=lower_is_better != "0",
        num_groups=num_groups,
        auto_detect=auto_detect != "0",
        filter_metric=filter_metric or None,
        filter_min=filter_min or None,
        filter_max=filter_max or None,
        filter_values=filter_values,
        cutoff_values=parsed_cutoffs,
    )
    return Response(content=content, media_type="image/png", headers=_no_cache_headers())


@router.post("/profile/move-cutoff", include_in_schema=False)
def post_move_cutoff(
    csv_path: str = Form(""),
    metric: str = Form(""),
    click_x: float = Form(...),
    lower_is_better: str = Form("1"),
    num_groups: int = Form(2),
    auto_detect: str = Form("0"),
    filter_metric: str = Form(""),
    filter_min: str = Form(""),
    filter_max: str = Form(""),
    filter_values_json: str = Form("[]"),
    redirect_url: str = Form(""),
) -> RedirectResponse:
    """Move the nearest cutoff to *click_x* and redirect with cutoff_value params."""
    try:
        filter_values: list[str] = []
        current_cutoffs: list[float] = []
        try:
            import json as _json
            filter_values = _json.loads(filter_values_json) or []
        except Exception:
            pass

        split = urlsplit(redirect_url or "/ui/profile")
        for key, value in parse_qsl(split.query, keep_blank_values=True):
            if key not in {"cutoff_value", "cutoff_values"}:
                continue
            try:
                current_cutoffs.append(float(value))
            except (TypeError, ValueError):
                continue

        new_cutoffs = move_distribution_cutoff(
            csv_path=csv_path,
            metric=metric,
            click_x=click_x,
            lower_is_better=lower_is_better != "0",
            num_groups=num_groups,
            auto_detect=auto_detect != "0",
            filter_metric=filter_metric or None,
            filter_min=filter_min or None,
            filter_max=filter_max or None,
            filter_values=filter_values or None,
            cutoff_values=current_cutoffs or None,
        )
        target = redirect_url or "/ui/profile"
        split = urlsplit(target)
        # Strip old cutoff_value params and old num_groups; we will re-inject
        # num_groups from the authoritative form value so the guard on the
        # subsequent GET can validate the cutoff count correctly even when
        # the original URL did not include num_groups.
        query_items = [
            (k, v)
            for k, v in parse_qsl(split.query, keep_blank_values=True)
            if k not in {"cutoff_value", "cutoff_values", "num_groups"}
        ]
        query_items.insert(0, ("num_groups", str(num_groups)))
        for cutoff in new_cutoffs:
            query_items.append(("cutoff_value", str(cutoff)))
        target = urlunsplit((split.scheme, split.netloc, split.path, urlencode(query_items), split.fragment))
        return RedirectResponse(url=target, status_code=303)
    except Exception:
        pass  # On error just redirect without changing state

    target = redirect_url or "/ui/profile"
    return RedirectResponse(url=target, status_code=303)


@router.get("/profile/analysis.png", include_in_schema=False)
def get_analysis_plot(
    csv_path: str,
    metric: str,
    lower_is_better: str = "1",
    num_groups: int = 2,
    auto_detect: str = "0",
    analyzer: str = "Tree",
    filter_metric: str = "",
    filter_min: str = "",
    filter_max: str = "",
    filter_values: list[str] = Query(default=[]),
    cutoff_value: list[str] = Query(default=[]),
    excluded_predictor: list[str] = Query(default=[]),
) -> Response:
    """Render profile analysis/tree plot as PNG."""
    parsed_cutoffs: list[float] | None = None
    if cutoff_value:
        try:
            parsed_cutoffs = [float(v) for v in cutoff_value]
        except (TypeError, ValueError):
            parsed_cutoffs = None
    content = render_analysis_plot_png(
        csv_path=csv_path,
        metric=metric,
        lower_is_better=lower_is_better != "0",
        num_groups=num_groups,
        auto_detect=auto_detect != "0",
        analyzer_name=analyzer,
        filter_metric=filter_metric or None,
        filter_min=filter_min or None,
        filter_max=filter_max or None,
        filter_values=filter_values,
        cutoff_values=parsed_cutoffs,
        excluded_predictors=excluded_predictor or None,
    )
    return Response(content=content, media_type="image/png", headers=_no_cache_headers())


@router.get("/profile/analysis-tree.html", response_class=HTMLResponse, include_in_schema=False)
def get_analysis_tree_html(
    csv_path: str,
    metric: str,
    lower_is_better: str = "1",
    num_groups: int = 2,
    auto_detect: str = "0",
    analyzer: str = "tree",
    filter_metric: str = "",
    filter_min: str = "",
    filter_max: str = "",
    filter_values: list[str] = Query(default=[]),
    cutoff_value: list[str] = Query(default=[]),
    excluded_predictor: list[str] = Query(default=[]),
) -> HTMLResponse:
    """Render interactive old-GUI tree visualization as embeddable HTML."""
    parsed_cutoffs: list[float] | None = None
    if cutoff_value:
        try:
            parsed_cutoffs = [float(v) for v in cutoff_value]
        except (TypeError, ValueError):
            parsed_cutoffs = None
    content = render_analysis_tree_html(
        csv_path=csv_path,
        metric=metric,
        lower_is_better=lower_is_better != "0",
        num_groups=num_groups,
        auto_detect=auto_detect != "0",
        analyzer_name=analyzer,
        filter_metric=filter_metric or None,
        filter_min=filter_min or None,
        filter_max=filter_max or None,
        filter_values=filter_values,
        cutoff_values=parsed_cutoffs,
        excluded_predictors=excluded_predictor or None,
    )
    return _html_no_cache(content)


@router.get("/profile/factor_scatter.png", include_in_schema=False)
def get_factor_scatter_plot(
    csv_path: str,
    metric: str,
    factor_name: str,
    lower_is_better: str = "1",
    num_groups: int = 2,
    auto_detect: str = "0",
    filter_metric: str = "",
    filter_min: str = "",
    filter_max: str = "",
    filter_values: list[str] = Query(default=[]),
) -> Response:
    """Render factor vs performance scatter plot as PNG."""
    content = render_factor_scatter_png(
        csv_path=csv_path,
        metric=metric,
        factor_name=factor_name,
        lower_is_better=lower_is_better != "0",
        num_groups=num_groups,
        auto_detect=auto_detect != "0",
        filter_metric=filter_metric or None,
        filter_min=filter_min or None,
        filter_max=filter_max or None,
        filter_values=filter_values,
    )
    return Response(content=content, media_type="image/png", headers=_no_cache_headers())


@router.get("/profile/mitigation_density.png", include_in_schema=False)
def get_mitigation_density_plot(
    baseline_csv: str,
    mitigation_csv: str,
    metric: str,
    filter_metric: str = "",
    filter_min: str = "",
    filter_max: str = "",
    filter_values: list[str] = Query(default=[]),
) -> Response:
    """Render baseline-vs-mitigation density comparison as PNG."""
    content = render_mitigation_density_plot_png(
        baseline_csv=baseline_csv,
        mitigation_csv=mitigation_csv,
        metric=metric,
        filter_metric=filter_metric or None,
        filter_min=filter_min or None,
        filter_max=filter_max or None,
        filter_values=filter_values,
    )
    return Response(content=content, media_type="image/png", headers=_no_cache_headers())


def _append_redirect_params(url: str, extra_params: dict[str, str]) -> str:
    """Append query parameters to an existing redirect URL."""
    split = urlsplit(url)
    query_items = parse_qsl(split.query, keep_blank_values=True)
    for key, value in extra_params.items():
        if value is None:
            continue
        query_items = [(k, v) for k, v in query_items if k != key]
        query_items.append((key, value))
    new_query = urlencode(query_items)
    return urlunsplit((split.scheme, split.netloc, split.path, new_query, split.fragment))


@router.post("/profile/mitigation/run", include_in_schema=False)
def run_mitigation(
    md_path: str = Form(""),
    csv_path: str = Form(""),
    mitigation: str = Form(""),
    action: str = Form("run"),
    redirect_url: str = Form("/ui/profile"),
) -> RedirectResponse:
    """Run or load mitigation data, then redirect back to profile page."""
    safe_redirect = redirect_url or "/ui/profile"

    if not mitigation:
        url = _append_redirect_params(
            safe_redirect,
            {"error": "No mitigation selected."},
        )
        return RedirectResponse(url=url, status_code=303)

    resolved = resolve_mitigation_paths(csv_path, mitigation)
    mitigation_csv = resolved.get("mitigation_csv", "")
    baseline_md = resolved.get("baseline_md", "")
    active_md = md_path or baseline_md

    if action == "use":
        if mitigation_csv and Path(mitigation_csv).exists():
            url = _append_redirect_params(
                safe_redirect,
                {
                    "mitigation": mitigation,
                    "mitigation_csv": mitigation_csv,
                    "notice": f"Loaded mitigation data: {Path(mitigation_csv).name}",
                },
            )
            return RedirectResponse(url=url, status_code=303)

        url = _append_redirect_params(
            safe_redirect,
            {
                "mitigation": mitigation,
                "error": "Mitigation CSV not found. Run mitigation first.",
            },
        )
        return RedirectResponse(url=url, status_code=303)

    result = run_mitigation_workflow(active_md, mitigation)
    if result.get("success"):
        result_csv = str(result.get("mitigation_csv") or mitigation_csv)
        url = _append_redirect_params(
            safe_redirect,
            {
                "mitigation": mitigation,
                "mitigation_csv": result_csv,
                "notice": str(result.get("notice") or "Mitigation run completed."),
            },
        )
        return RedirectResponse(url=url, status_code=303)

    err = str(result.get("error") or "Mitigation run failed.")
    url = _append_redirect_params(
        safe_redirect,
        {
            "mitigation": mitigation,
            "error": err,
        },
    )
    return RedirectResponse(url=url, status_code=303)


@router.post("/profile/run-profiling", include_in_schema=False)
def run_profiling(
    original_md: str = Form(""),
    csv_path: str = Form(""),
    profile_task_name: str = Form(""),
    profiling_backends: list[str] = Form(default=[]),
    redirect_url: str = Form("/ui/profile"),
) -> RedirectResponse:
    """Run profiling from source-choice prompt and redirect to prof results."""
    safe_redirect = redirect_url or "/ui/profile"

    if not original_md:
        url = _append_redirect_params(
            safe_redirect,
            {"error": "Cannot profile: metadata file (.md) not found."},
        )
        return RedirectResponse(url=url, status_code=303)

    task_name = profile_task_name.strip() or default_profile_task_name(original_md)
    result = run_profile_workflow(original_md, profiling_backends, task_name)
    if result.get("success"):
        url = _build_profile_success_redirect_url(result)
        return RedirectResponse(url=url, status_code=303)

    url = _build_profile_error_redirect_url(
        safe_redirect,
        csv_path,
        str(result.get("error") or "Profiling failed."),
    )
    return RedirectResponse(url=url, status_code=303)


@router.post("/profile/start-profiling", include_in_schema=False)
def start_profiling(
    original_md: str = Form(""),
    csv_path: str = Form(""),
    profile_task_name: str = Form(""),
    profiling_backends: list[str] = Form(default=[]),
    redirect_url: str = Form("/ui/profile"),
) -> JSONResponse:
    """Start profiling in the background and return run id for SSE progress stream."""
    run_id = start_profile_job(
        {
            "original_md": original_md,
            "csv_path": csv_path,
            "profile_task_name": profile_task_name,
            "profiling_backends": profiling_backends,
            "redirect_url": redirect_url,
        }
    )
    return JSONResponse(content={"run_id": run_id})


@router.get("/profile/stream", include_in_schema=False)
def stream_profile(run_id: str) -> StreamingResponse:
    """Stream profile progress events via SSE until completion."""
    initial = get_profile_job(run_id)
    if not initial:
        return StreamingResponse(iter(["event: error\ndata: {\"error\": \"missing run\"}\n\n"]), media_type="text/event-stream")

    def _stream():
        current = initial
        version = int(current.get("version") or 0)

        while current is not None:
            payload: dict[str, Any] = {
                "status": str(current.get("status") or ""),
                "current": int(current.get("current") or 0),
                "total": current.get("total"),
                "message": str(current.get("message") or ""),
            }

            status = str(current.get("status") or "")
            form = current.get("form") or {}
            if status == "completed":
                workflow = current.get("workflow")
                if isinstance(workflow, dict):
                    payload["redirect_url"] = _build_profile_success_redirect_url(workflow)
            elif status == "failed":
                payload["error_url"] = _build_profile_error_redirect_url(
                    str(form.get("redirect_url") or "/ui/profile"),
                    str(form.get("csv_path") or ""),
                    str(current.get("error") or "Profiling failed"),
                )

            yield f"data: {json.dumps(payload)}\n\n"

            if status in {"completed", "failed"}:
                break

            updated = wait_for_profile_job_update(run_id, version, timeout=10.0)
            if updated is None:
                yield ": keepalive\n\n"
                current = get_profile_job(run_id)
                if current is None:
                    break
                version = int(current.get("version") or version)
                continue

            current = updated
            version = int(current.get("version") or version)

    sse_headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(_stream(), media_type="text/event-stream", headers=sse_headers)


@router.post("/profile/update-exclusions", include_in_schema=False)
def update_exclusions(
    csv_path: str = Form(""),
    metric: str = Form(""),
    excluded_predictor: list[str] = Form(default=[]),
    excluded_state: str = Form(""),
    visible_predictor: list[str] = Form(default=[]),
    max_corr: str = Form(""),
    redirect_url: str = Form("/ui/profile"),
) -> RedirectResponse:
    """Store the user's exclusion selection behind a URL-scoped token.

    This avoids passing potentially thousands of excluded_predictor query params
    through the URL while keeping unsaved state tied to the redirect URL.
    """
    target = redirect_url or "/ui/profile"
    params: dict[str, str] = {}
    if csv_path and metric:
        if excluded_state and visible_predictor:
            # The form only contains checkboxes for the currently visible (possibly
            # filtered/searched) predictors.  Merge with the previously excluded set
            # so that predictors excluded before the search was applied are not lost.
            prev_excluded = set(get_excluded_predictors(excluded_state, csv_path, metric))
            visible_set = set(visible_predictor)
            merged = sorted((prev_excluded - visible_set) | set(excluded_predictor))
            state_token = create_exclusion_state(csv_path, metric, merged)
        else:
            state_token = create_exclusion_state(csv_path, metric, excluded_predictor)
        params["excluded_state"] = state_token
    if max_corr:
        try:
            val = max(0.0, min(1.0, float(max_corr)))
            params["max_corr"] = f"{val:.2f}"
        except ValueError:
            pass
    if params:
        target = _append_redirect_params(target, params)
    return RedirectResponse(url=target, status_code=303)


@router.get("/profile/predictors-fragment", response_class=HTMLResponse, include_in_schema=False)
def get_predictors_fragment(
    csv_path: str = "",
    metric: str = "",
    lower_is_better: str = "1",
    filter_metric: str = "",
    filter_min: str = "",
    filter_max: str = "",
    filter_values: list[str] = Query(default=[]),
    excluded_predictor: list[str] = Query(default=[]),
    excluded_state: str = "",
    search: str = "",
    max_corr: str = "",
) -> HTMLResponse:
    """Return an HTML fragment with a predictor stats table for the exclude-predictors modal.

    Shows predictor name, non-NA count, correlation to the outcome metric, and a
    checkbox (name='excluded_predictor') for each predictor.  Supports server-side
    filtering via the 'search' query param.
    """
    if not csv_path or not metric:
        return _html_no_cache("<p class='muted'>No analysis loaded.</p>")

    try:
        from src.gui.utils.profile.predictor_stats import (
            DEFAULT_EXCLUDED_PREDICTORS,
            compute_predictor_stats,
            get_auto_excluded_predictors,
        )
        from src.gui.utils.profile.data_pipeline import (
            compute_outcome_correlations,
            compute_cleaned_columns,
        )

        df = _load_filtered_dataframe(
            csv_path,
            filter_metric or "",
            None,
            filter_values=filter_values or [],
            filter_min=filter_min or None,
            filter_max=filter_max or None,
        )

        if df.height == 0 or metric not in df.columns:
            return _html_no_cache("<p class='muted'>No data available.</p>")

        # Apply column cleaning (C1+C2) to reduce from potentially thousands of
        # columns down to hundreds, then compute correlations only on cleaned
        # columns. This matches the main profile analysis pipeline and avoids
        # expensive correlation computations on all raw columns.
        cleaned_cols = compute_cleaned_columns(df)
        correlations, stats = compute_outcome_correlations(df, metric, cleaned_cols)

        # Fallback to simple correlation on all columns if cleaning left no
        # candidates (e.g. in unit tests with minimal mock data)
        if not stats:
            stats = compute_predictor_stats(df, metric)
    except Exception as exc:  # noqa: BLE001
        return _html_no_cache(f"<p class='error-banner'>Error loading predictors: {exc}</p>")

    settings = Settings()
    try:
        corr_threshold = float(max_corr) if str(max_corr).strip() else float(settings.get("profiling.max_correlation", 0.99))
    except ValueError:
        corr_threshold = float(settings.get("profiling.max_correlation", 0.99))
    corr_threshold = max(0.0, min(1.0, corr_threshold))

    auto_excluded = get_auto_excluded_predictors(stats, corr_threshold)
    default_excluded_names = set(DEFAULT_EXCLUDED_PREDICTORS) | set(auto_excluded)

    # Determine the user's saved/explicit exclusions (without the threshold-based
    # auto-exclusions baked in).  Then always add the current auto_excluded on top
    # so that changing the slider immediately checks/unchecks the right rows.
    if has_custom_exclusions(excluded_state, csv_path, metric):
        user_excluded = set(get_excluded_predictors(excluded_state, csv_path, metric))
    elif excluded_predictor:
        user_excluded = set(excluded_predictor)
    else:
        user_excluded = set(DEFAULT_EXCLUDED_PREDICTORS)
    # Always merge with auto_excluded at the current threshold so the slider
    # change is reflected immediately without needing an Apply.
    excluded_names = user_excluded | set(auto_excluded)

    # Base params to rebuild the reload URL inside the fragment's search box
    base_params: list[tuple[str, str]] = [("csv_path", csv_path), ("metric", metric)]
    if filter_metric:
        base_params.append(("filter_metric", filter_metric))
    if filter_min:
        base_params.append(("filter_min", filter_min))
    if filter_max:
        base_params.append(("filter_max", filter_max))
    if excluded_state:
        base_params.append(("excluded_state", excluded_state))
    base_params.append(("max_corr", f"{corr_threshold:.2f}"))
    base_params.append(("lower_is_better", lower_is_better))
    # Do NOT add individual excluded_predictor params here — they bloat the URL
    # beyond the 8KB HTTP header limit. The excluded_state parameter already
    # encodes all exclusions in a compact token.

    html = render_predictors_fragment(
        stats,
        excluded_names,
        search,
        base_params,
        max_corr=corr_threshold,
        default_excluded_names=default_excluded_names,
    )
    return _html_no_cache(html)


@router.post("/profile/search-cutoffs", include_in_schema=False)
def search_cutoffs(
    csv_path: str = Form(""),
    metric: str = Form(""),
    lower_is_better: str = Form("1"),
    num_groups: int = Form(2),
    auto_detect: str = Form("0"),
    analyzer: str = Form("tree"),
    filter_metric: str = Form(""),
    filter_min: str = Form(""),
    filter_max: str = Form(""),
    filter_values: list[str] = Form(default=[]),
    excluded_predictor: list[str] = Form(default=[]),
    redirect_url: str = Form("/ui/profile"),
) -> RedirectResponse:
    """Run cutoff search algorithm and redirect back with optimal cutoff_values params."""
    safe_redirect = redirect_url or "/ui/profile"

    if not csv_path or not metric:
        url = _append_redirect_params(safe_redirect, {"error": "Missing csv_path or metric."})
        return RedirectResponse(url=url, status_code=303)

    try:
        from src.gui.utils.profile.tree import search_optimal_manual_cutoffs, search_for_cutoff
        from src.gui.services.profile import _load_filtered_dataframe

        df = _load_filtered_dataframe(
            csv_path,
            filter_metric or "",
            None,
            filter_values=filter_values or None,
            filter_min=filter_min or None,
            filter_max=filter_max or None,
        )

        if df.height == 0 or metric not in df.columns:
            url = _append_redirect_params(safe_redirect, {"error": "No data available."})
            return RedirectResponse(url=url, status_code=303)

        exclude = [v for v in excluded_predictor if v]
        lb = lower_is_better != "0"

        if num_groups == 2:
            # Binary labeler — single cutoff search
            cutoff = search_for_cutoff(df, metric, exclude, lower_is_better=lb)
            optimal_cutoffs = [cutoff] if cutoff is not None else None
        else:
            # ManualLabeler — multi-cutoff search (num_groups - 1 cutoffs)
            optimal_cutoffs = search_optimal_manual_cutoffs(
                df, metric, exclude,
                lower_is_better=lb,
                fixed_num_cutoffs=num_groups - 1,
            )

        if not optimal_cutoffs:
            url = _append_redirect_params(safe_redirect, {"error": "Cutoff search found no valid result."})
            return RedirectResponse(url=url, status_code=303)

        # Build redirect URL: strip any old cutoff params and append new ones
        split = urlsplit(safe_redirect)
        from urllib.parse import parse_qsl
        query_items = [(k, v) for k, v in parse_qsl(split.query, keep_blank_values=True)
                       if k not in {"cutoff_value", "cutoff_values"}]
        for c in optimal_cutoffs:
            query_items.append(("cutoff_value", str(c)))
        from urllib.parse import urlencode as _urlencode
        new_query = _urlencode(query_items)
        redirect_dest = urlunsplit((split.scheme, split.netloc, split.path, new_query, split.fragment))
        return RedirectResponse(url=redirect_dest, status_code=303)

    except Exception as exc:  # noqa: BLE001
        url = _append_redirect_params(safe_redirect, {"error": f"Search failed: {exc}"})
        return RedirectResponse(url=url, status_code=303)


@router.post("/profile/save-settings", include_in_schema=False)
def save_profile_settings(
    md_path: str = Form(...),
    metric: str = Form(""),
    filter_metric: str = Form(""),
    filter_min: str = Form(""),
    filter_max: str = Form(""),
    filter_values: list[str] = Form(default=[]),
    num_groups: int = Form(2),
    auto_detect: str = Form("1"),
    cutoff_value: list[str] = Form(default=[]),
    cutoff_values: list[str] = Form(default=[]),
    excluded_predictor: list[str] = Form(default=[]),
    max_corr: str = Form(""),
    analyzer: str = Form(""),
    redirect_url: str = Form(""),
) -> RedirectResponse:
    """Save current profile settings to the markdown file."""
    from pathlib import Path
    from src.core.runlogs.profile_settings import (
        build_profile_settings_payload,
        update_markdown_profile_settings,
    )

    if not md_path or not Path(md_path).exists():
        return RedirectResponse(
            url=redirect_url or "/ui/profile",
            status_code=303,
        )

    filter_value = None
    if filter_metric:
        if filter_min or filter_max:
            filter_value = [filter_min, filter_max]
        elif filter_values:
            filter_value = list(filter_values)

    def _parse_cutoff_list(values: list[str]) -> list[float]:
        parsed: list[float] = []
        for raw in values:
            if raw in (None, ""):
                continue
            try:
                parsed.append(float(raw))
            except (TypeError, ValueError):
                continue
        return parsed

    cutoffs = _parse_cutoff_list(cutoff_value)
    if not cutoffs:
        cutoffs = _parse_cutoff_list(cutoff_values)

    # Some clients or stale pages can submit incomplete cutoff form fields.
    # Recover from redirect_url query params to preserve the exact visible state.
    expected_cutoffs = max(0, num_groups - 1) if auto_detect == "0" else 0
    if redirect_url and expected_cutoffs and len(cutoffs) < expected_cutoffs:
        split = urlsplit(redirect_url)
        url_cutoffs: list[float] = []
        for key, value in parse_qsl(split.query, keep_blank_values=True):
            if key not in {"cutoff_value", "cutoff_values"}:
                continue
            try:
                url_cutoffs.append(float(value))
            except (TypeError, ValueError):
                continue
        if len(url_cutoffs) >= len(cutoffs):
            cutoffs = url_cutoffs

    excluded_extra = sorted(
        set(excluded_predictor) - set(DEFAULT_EXCLUDED_PREDICTORS)
    ) if excluded_predictor else []

    payload = build_profile_settings_payload(
        filter_metric=filter_metric or None,
        filter_value=filter_value,
        num_perf_groups=0 if auto_detect != "0" else num_groups,
        cutoff_values=cutoffs or None,
        influence_analyzer=analyzer or None,
        outcome_metric=metric or None,
        excluded_predictors=excluded_extra or None,
        max_correlation=float(max_corr) if max_corr else None,
    )

    update_markdown_profile_settings(md_path, payload)

    return RedirectResponse(
        url=redirect_url or "/ui/profile",
        status_code=303,
    )
