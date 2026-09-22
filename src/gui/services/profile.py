# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Profile-page service helpers."""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import polars as pl

from src.core.runlogs.reader import load_table
from src.core.profile import (
    PerformanceLabeler,
    BinaryLabeler,
    TertileLabeler,
    QuartileLabeler,
    AutoLabeler,
    RegressionLabeler,
)
from src.core.profile.analyzers.registry import (
    create_analyzer_registry,
)
from src.core.config import discover_backends
from src.core.config.settings import Settings
from src.core.config.backend_loader import validate_backend_chain
from src.core.stats.narrative import generate_comparison_narrative
from src.core.metrics.factors import (
    get_factor_info,
    get_mitigation_backend,
    get_mitigation_info,
)
from src.gui.utils.profile.data_pipeline import (
    compute_cleaned_columns,
    compute_outcome_correlations,
    compute_reduced_columns,
)
from src.core.profile.data_reduction import reduce_rows
from src.gui.utils.profile.files import (
    check_prof_file_exists,
    combined_profile_md_path,
    detect_file_state,
    get_file_paths,
    load_and_merge_tasks,
)
from src.gui.utils.profile.restore import (
    ProfileSettings,
    extract_profile_settings_from_md,
)
from src.gui.utils.profile.execution import ProfilingExecutor
from src.gui.utils.comparisons import (
    compute_comparison_summary,
    render_density_comparison_plot,
)

from .experiments import list_experiments, list_tasks
from .shared import (
    search_filter_metrics,
    _filter_kind,
    _load_filtered_dataframe,
    _numeric_columns,
    _filterable_columns,
)

METRIC_PREFERENCES = ["perf_time", "inner_time", "outer_time"]
_ANALYSIS_CACHE: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def not_implemented_message(operation: str) -> str:
    """Return a consistent placeholder message for unimplemented profile routes."""
    return f"{operation} is planned for a later phase of the FastAPI UI migration."


def _select_preferred_metric(columns: list[str]) -> str:
    """Pick the best default metric from available columns."""
    for pref in METRIC_PREFERENCES:
        if pref in columns:
            return pref
    # Sort alphabetically as fallback to match old GUI behaviour
    # (avoids selecting wall-clock columns like "timestamp" before latency metrics)
    return sorted(columns)[0] if columns else ""


def load_profile_form_data() -> dict[str, Any]:
    """Load initial form scaffold (experiment list)."""
    experiments = list_experiments()
    return {
        "experiments": [{"value": e.name, "label": e.name} for e in experiments.experiments],
        "tasks": [],
        "metrics": [],
        "filter_metrics": [],
        "analyzer_choices": {},
    }


def list_profile_task_choices(experiment: str) -> list[dict[str, str]]:
    """Return task choices for the profile experiment selector."""
    if not experiment:
        return []
    return [
        {"csv_path": t.csv_path, "md_path": t.md_path, "label": t.task}
        for t in list_tasks(experiment).tasks
    ]


def _load_active_dataframe_and_paths(
    csv_path: str,
    task_csv_pairs: list[tuple[str, str]] | None = None,
) -> tuple[pl.DataFrame, str, str, str, str, str, str, bool]:
    """Load the active DataFrame and derive related file paths.

    Returns (active_df, active_csv, md_path, original_csv, original_md, file_state, prof_csv_path, has_prof_csv).

    For multi-task: merges all CSVs and returns settings from first task's markdown.
    For single-task: detects file state and loads prof variant if available.
    """
    if task_csv_pairs and len(task_csv_pairs) > 1:
        # Multi-task: merge all CSVs, skip per-task state detection
        _, active_csv = load_and_merge_tasks(task_csv_pairs)
        active_df = load_table(active_csv)
        file_state = "state2"
        prof_csv_path = ""
        has_prof_csv = False
        # Combined-profile settings are persisted to a dedicated, order-
        # independent markdown file (keyed on the sorted task set) rather than
        # any single task's markdown.  Create an empty stub on first load so
        # both save-settings (which requires the file to exist) and restore use
        # the same file regardless of task order.
        md = combined_profile_md_path(task_csv_pairs)
        if not md.exists():
            md.parent.mkdir(parents=True, exist_ok=True)
            md.write_text("# Combined profile settings\n", encoding="utf-8")
        md_path = str(md)
        _, first_paths = detect_file_state(task_csv_pairs[0][1])
        original_csv = str(first_paths.get("csv") or "")
        original_md = str(first_paths.get("md") or "")
    else:
        df = load_table(csv_path)

        # Derive file paths and state
        file_state, paths = detect_file_state(csv_path)
        prof_csv_path = str(paths.get("prof_csv", "")) if paths.get("prof_csv") else ""
        has_prof_csv = bool(prof_csv_path and Path(prof_csv_path).exists())

        # If prof CSV exists, use it as the data source
        active_csv = prof_csv_path if has_prof_csv else csv_path
        active_df = load_table(active_csv) if active_csv != csv_path else df

        md_path = str(paths.get("prof_md") or paths.get("md") or "")
        original_csv = str(paths.get("csv") or "")
        original_md = str(paths.get("md") or "")

    return active_df, active_csv, md_path, original_csv, original_md, file_state, prof_csv_path, has_prof_csv


def load_profile_dataset(
    csv_path: str,
    task_csv_pairs: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Load a profile dataset and derive metric/filter choices and file state.

    When *task_csv_pairs* contains more than one entry the CSVs are merged via
    :func:`~src.gui.utils.profile.files.load_and_merge_tasks` before any
    downstream processing.  The rest of the pipeline receives a single unified
    DataFrame regardless of how many tasks were selected.

    Returns dict with:
      - metrics, filter_metrics, metric (default)
      - file_state, paths (prof_csv existence info)
      - prof_csv_path, has_prof_csv
      - settings (from markdown if available)
      - rows (row count of active data)
    """
    active_df, active_csv, md_path, original_csv, original_md, file_state, prof_csv_path, has_prof_csv = \
        _load_active_dataframe_and_paths(csv_path, task_csv_pairs)

    # Initial page load should derive metric/filter choices from reduced columns
    # on very wide datasets, matching old GUI behavior and avoiding expensive
    # full-width filter option derivation.
    reduction_settings = Settings()
    cleaned_cols = compute_cleaned_columns(active_df, settings=reduction_settings)
    cleaned_set = set(cleaned_cols) if cleaned_cols else set()
    ui_cols = [c for c in active_df.columns if c in cleaned_set] if cleaned_set else []
    ui_df = active_df.select(ui_cols) if ui_cols and len(ui_cols) < active_df.width else active_df

    active_metrics = _numeric_columns(ui_df)
    active_filter_metrics = _filterable_columns(ui_df)

    # Load markdown settings if available
    settings = _load_settings(md_path) if md_path and Path(md_path).exists() else None

    # Default metric from settings or preference heuristic
    default_metric = ""
    if settings and settings.default_outcome_metric:
        if settings.default_outcome_metric in active_metrics:
            default_metric = settings.default_outcome_metric
    if not default_metric:
        default_metric = _select_preferred_metric(active_metrics)

    return {
        "metrics": active_metrics,
        "filter_metrics": active_filter_metrics,
        "metric": default_metric,
        "file_state": file_state,
        "prof_csv_path": prof_csv_path,
        "has_prof_csv": has_prof_csv,
        "active_csv": active_csv,
        "md_path": md_path,
        "original_csv": original_csv,
        "original_md": original_md,
        "settings": settings,
        "rows": active_df.height,
    }


def search_profile_filter_metrics(csv_path: str, query: str, limit: int = 150) -> list[str]:
    """Search filter metrics for very wide profile datasets."""
    return search_filter_metrics(csv_path, query, limit)


def is_profile_csv(csv_path: str) -> bool:
    """Return True when selected CSV already has profile suffix."""
    prof_suffix = Settings().get("profile.prof_suffix", "-prof")
    return Path(csv_path).stem.endswith(prof_suffix)


def build_source_prompt_data(csv_path: str) -> dict[str, Any]:
    """Build source-choice prompt info for a non-prof selected task."""
    file_state, paths = detect_file_state(csv_path)
    prof_csv = str(paths.get("prof_csv") or "")
    has_prof_csv = bool(prof_csv and Path(prof_csv).exists())

    return {
        "file_state": file_state,
        "original_csv": str(paths.get("csv") or csv_path),
        "original_md": str(paths.get("md") or ""),
        "prof_csv": prof_csv,
        "has_prof_csv": has_prof_csv,
        "prof_filename": Path(prof_csv).name if has_prof_csv else "",
    }


def list_profiling_backends() -> list[str]:
    """List profiling backends available for configuration UI."""
    backends = discover_backends(profiling=True)
    return sorted(backends.keys())


def default_profile_task_name(original_md_path: str) -> str:
    """Build default profiling output task name from selected markdown path."""
    md = Path(original_md_path)
    base_name = md.stem.replace("-prof", "")
    return f"{base_name}-prof"


def run_profile_workflow(
    original_md_path: str,
    selected_backends: list[str],
    task_name: str,
    progress_callback: Callable[[int, int | None], None] | None = None,
) -> dict[str, Any]:
    """Run profiling workflow and return result payload for redirects."""
    md = Path(original_md_path)
    if not md.exists():
        return {"success": False, "error": "Cannot profile: metadata file (.md) not found."}

    if not selected_backends:
        return {"success": False, "error": "Select at least one profiling backend."}

    profiling_backends = discover_backends(profiling=True)
    validation_backends: dict[str, dict[str, Any]] = {}
    for name, config in profiling_backends.items():
        if name in config.backend_options:
            opt = config.backend_options[name]
            validation_backends[name] = opt.model_dump() if hasattr(opt, "model_dump") else opt.dict()

    valid_chain, error_msg = validate_backend_chain(selected_backends, validation_backends)
    if not valid_chain:
        return {"success": False, "error": error_msg}

    executor = ProfilingExecutor(str(md), selected_backends, task_name)
    result_box: dict[str, Any] = {}

    def _on_complete(success: bool, result_dict: dict[str, Any]) -> None:
        result_box["success"] = success
        result_box["result"] = result_dict

    def _on_error(exc: Exception) -> None:
        result_box["success"] = False
        result_box["result"] = {"error_message": str(exc)}

    def _on_progress(current: int, total: int) -> None:
        if progress_callback is not None:
            progress_callback(max(0, int(current)), max(0, int(total)))

    try:
        executor.set_callbacks(on_progress=_on_progress, on_complete=_on_complete, on_error=_on_error)
        executor.execute()
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    success = bool(result_box.get("success"))
    result_dict = result_box.get("result") or {}
    if not success:
        return {"success": False, "error": str(result_dict.get("error_message") or "Profiling failed")}

    output_csv = str(result_dict.get("output_paths", {}).get("csv") or "")
    if not output_csv or not Path(output_csv).exists():
        prof_candidate = md.parent / f"{task_name}.csv"
        if prof_candidate.exists():
            output_csv = str(prof_candidate)

    if not output_csv:
        return {
            "success": False,
            "error": "Profiling completed but output CSV could not be resolved.",
        }

    workflow_result: dict[str, Any] = {
        "success": True,
        "profile_csv": output_csv,
        "notice": "Profiling completed successfully.",
    }
    backend_warnings = result_dict.get("warnings") or []
    if backend_warnings:
        workflow_result["warnings"] = backend_warnings
    return workflow_result


def get_factor_mitigations(factor_name: str) -> list[str]:
    """Return mitigation names associated with a selected factor."""
    if not factor_name:
        return []
    info = get_factor_info(factor_name)
    if not info:
        return []
    mitigations = info.get("mitigations", [])
    if not isinstance(mitigations, list):
        return []
    return [str(name) for name in mitigations if str(name).strip()]


def load_mitigation_info(mitigation_name: str) -> dict[str, Any] | None:
    """Load mitigation metadata and execution capability."""
    if not mitigation_name:
        return None

    info = get_mitigation_info(mitigation_name)
    if not info:
        return None

    backend = get_mitigation_backend(mitigation_name)
    references = info.get("references", {})
    if not isinstance(references, dict):
        references = {}

    return {
        "name": mitigation_name,
        "description": str(info.get("description") or "No description available."),
        "references": {str(k): str(v) for k, v in references.items()},
        "is_automated": backend is not None,
    }


def resolve_mitigation_paths(csv_path: str, mitigation_name: str) -> dict[str, str]:
    """Resolve baseline/mitigation file paths for the selected mitigation."""
    if not csv_path or not mitigation_name:
        return {
            "baseline_csv": "",
            "baseline_md": "",
            "mitigation_csv": "",
            "mitigation_md": "",
        }

    _, paths = detect_file_state(csv_path)
    baseline_csv = Path(paths.get("csv") or csv_path)
    baseline_md = baseline_csv.with_suffix(".md")
    mitigation_stem = f"{baseline_csv.stem}-{mitigation_name}"
    mitigation_csv = baseline_csv.parent / f"{mitigation_stem}.csv"
    mitigation_md = baseline_csv.parent / f"{mitigation_stem}.md"

    return {
        "baseline_csv": str(baseline_csv),
        "baseline_md": str(baseline_md),
        "mitigation_csv": str(mitigation_csv),
        "mitigation_md": str(mitigation_md),
    }


def run_mitigation_workflow(md_path: str, mitigation_name: str) -> dict[str, Any]:
    """Execute an automated mitigation run and return status payload."""
    if not md_path or not mitigation_name:
        return {"success": False, "error": "Missing markdown path or mitigation name."}

    md = Path(md_path)
    if not md.exists():
        return {"success": False, "error": f"Markdown file not found: {md_path}"}

    backend = get_mitigation_backend(mitigation_name)
    if backend is None:
        return {
            "success": False,
            "error": (
                f"Mitigation '{mitigation_name}' is not automated. "
                "Apply it manually and load the generated CSV."
            ),
            "manual_required": True,
        }

    task_name = f"{md.stem}-{mitigation_name}"
    executor = ProfilingExecutor(str(md), [mitigation_name], task_name)

    try:
        executor.execute()
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    mitigation_csv = md.parent / f"{md.stem}-{mitigation_name}.csv"
    if not mitigation_csv.exists():
        return {
            "success": False,
            "error": (
                "Mitigation run completed but output CSV was not found: "
                f"{mitigation_csv.name}"
            ),
        }

    return {
        "success": True,
        "mitigation_csv": str(mitigation_csv),
        "notice": f"Mitigation completed: {mitigation_csv.name}",
    }


def get_mitigation_metrics(
    baseline_csv: str,
    mitigation_csv: str,
) -> list[str]:
    """List common numeric metrics between baseline and mitigation datasets."""
    if not baseline_csv or not mitigation_csv:
        return []
    if not Path(baseline_csv).exists() or not Path(mitigation_csv).exists():
        return []

    baseline_df = load_table(baseline_csv)
    mitigation_df = load_table(mitigation_csv)
    metadata_cols = {"rank", "repeat", "benchmark"}

    base_numeric = set(_numeric_columns(baseline_df)) - metadata_cols
    mit_numeric = set(_numeric_columns(mitigation_df)) - metadata_cols
    return sorted(base_numeric & mit_numeric)


def compute_mitigation_comparison(
    baseline_csv: str,
    mitigation_csv: str,
    metric: str,
    lower_is_better: bool = True,
    filter_metric: str | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
    filter_values: list[str] | None = None,
) -> dict[str, Any]:
    """Compute mitigation comparison narrative and summary rows."""
    if not baseline_csv or not mitigation_csv or not metric:
        return {"error": "Missing mitigation comparison inputs."}
    if not Path(mitigation_csv).exists():
        return {"error": "Mitigation CSV does not exist yet."}

    try:
        baseline_df = _load_filtered_dataframe(
            baseline_csv,
            filter_metric or "",
            None,
            filter_values=filter_values or [],
            filter_min=filter_min,
            filter_max=filter_max,
        )
        mitigation_df = _load_filtered_dataframe(
            mitigation_csv,
            filter_metric or "",
            None,
            filter_values=filter_values or [],
            filter_min=filter_min,
            filter_max=filter_max,
        )

        if metric not in baseline_df.columns or metric not in mitigation_df.columns:
            return {"error": f"Metric '{metric}' is missing from baseline or mitigation data."}

        baseline_vals = baseline_df[metric].cast(float, strict=False).drop_nulls().to_numpy()
        mitigation_vals = mitigation_df[metric].cast(float, strict=False).drop_nulls().to_numpy()

        if len(baseline_vals) == 0 or len(mitigation_vals) == 0:
            return {"error": "No valid rows remain after filtering for mitigation comparison."}

        narrative = generate_comparison_narrative(
            baseline_vals,
            mitigation_vals,
            lower_is_better=lower_is_better,
        )
        summary = compute_comparison_summary(baseline_vals, mitigation_vals, digits=10, sig_figs=3)
        rows = [
            {
                "statistic": stat,
                "baseline": baseline,
                "mitigation": treatment,
                "pct_change": pct,
                "p_value": pval,
            }
            for stat, baseline, treatment, pct, pval in zip(
                summary["statistic_names"],
                summary["baseline"],
                summary["treatment"],
                summary["pct_change"],
                summary["p_value"],
            )
        ]
        return {
            "error": None,
            "narrative": narrative,
            "rows": rows,
            "baseline_count": len(baseline_vals),
            "mitigation_count": len(mitigation_vals),
        }
    except Exception as exc:
        return {"error": str(exc)}


def render_mitigation_density_plot_png(
    baseline_csv: str,
    mitigation_csv: str,
    metric: str,
    filter_metric: str | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
    filter_values: list[str] | None = None,
) -> bytes:
    """Render mitigation density comparison plot as PNG bytes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    baseline_df = _load_filtered_dataframe(
        baseline_csv,
        filter_metric or "",
        None,
        filter_values=filter_values or [],
        filter_min=filter_min,
        filter_max=filter_max,
    )
    mitigation_df = _load_filtered_dataframe(
        mitigation_csv,
        filter_metric or "",
        None,
        filter_values=filter_values or [],
        filter_min=filter_min,
        filter_max=filter_max,
    )

    baseline_vals = (
        baseline_df[metric].cast(float, strict=False).drop_nulls().to_numpy()
        if metric in baseline_df.columns
        else np.array([])
    )
    mitigation_vals = (
        mitigation_df[metric].cast(float, strict=False).drop_nulls().to_numpy()
        if metric in mitigation_df.columns
        else np.array([])
    )

    fig = None
    if len(baseline_vals) > 0 and len(mitigation_vals) > 0:
        fig = render_density_comparison_plot(baseline_vals, mitigation_vals, metric=metric)

    if fig is None:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "No mitigation data", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    finally:
        plt.close(fig)
    return buf.getvalue()


def _load_settings(md_path: str) -> ProfileSettings | None:
    """Load profile settings from markdown, returning None on failure."""
    try:
        return extract_profile_settings_from_md(md_path)
    except Exception:
        return None


def build_labeler(
    num_groups: int,
    auto_detect: bool,
    metric_values: np.ndarray | None = None,
    lower_is_better: bool = True,
    cutoff_values: list[float] | None = None,
) -> PerformanceLabeler | None:
    """Build a labeler from UI parameters.

    If *auto_detect* is True, AutoLabeler is used and *cutoff_values* are
    ignored (the user clicked "Auto groups", so any restored cutoffs must not
    override the auto path).

    If *cutoff_values* is provided (and auto_detect is False) the function
    returns a Binary/ManualLabeler with those explicit cutoffs.
    """
    from src.core.profile.labeler import ManualLabeler

    if metric_values is None or len(metric_values) == 0:
        return None

    # auto_detect takes absolute priority - even over num_groups==1 (regression).
    # If the user clicked "Auto groups" while the stepper was frozen at 1, we
    # must run AutoLabeler, not fall into regression mode.
    if auto_detect:
        labeler = AutoLabeler(metric_values, lower_is_better=lower_is_better)
        # If AutoLabeler collapses to a single class (e.g. homogeneous data
        # triggers the BODY-only path), fall back to binary classification so
        # the analysis always has at least two meaningful groups.
        if len(labeler.get_class_names()) < 2:
            return BinaryLabeler(metric_values, lower_is_better=lower_is_better)
        return labeler

    if num_groups == 1:
        return RegressionLabeler(metric_values, lower_is_better=lower_is_better)

    if cutoff_values:
        if len(cutoff_values) == 1:
            return BinaryLabeler.with_cutoff(cutoff_values[0], lower_is_better)
        return ManualLabeler.with_cutoffs(cutoff_values, lower_is_better)

    if num_groups == 2:
        return BinaryLabeler(metric_values, lower_is_better=lower_is_better)
    elif num_groups == 3:
        return TertileLabeler(metric_values, lower_is_better=lower_is_better)
    elif num_groups == 4:
        return QuartileLabeler(metric_values, lower_is_better=lower_is_better)
    else:
        return ManualLabeler(
            metric_values,
            lower_is_better=lower_is_better,
            num_cutoffs=num_groups - 1,
        )


def get_analyzer_choices() -> dict[str, str]:
    """Return available analyzer name->label mapping."""
    try:
        registry = create_analyzer_registry()
        return registry.get_analyzer_choices()
    except Exception:
        return {"Tree": "Decision Tree"}


def get_metric_direction(metric_col: str, md_path: str | None) -> bool:
    """Determine if lower values are better for the given metric."""
    if not md_path or not Path(md_path).exists():
        return True
    try:
        from src.core.runlogs.parser import extract_metrics_from_markdown
        metrics = extract_metrics_from_markdown(Path(md_path))
        if metric_col in metrics:
            metric_def = metrics[metric_col]
            if isinstance(metric_def, dict):
                return bool(metric_def.get("lower_is_better", True))
        return True
    except Exception:
        return True


def _analysis_cache_key(
    csv_path: str,
    metric: str,
    lower_is_better: bool,
    num_groups: int,
    auto_detect: bool,
    analyzer_name: str,
    filter_metric: str | None,
    filter_min: str | None,
    filter_max: str | None,
    filter_values: list[str] | None,
    excluded_predictors: list[str] | None,
    cutoff_values: list[float] | None = None,
) -> tuple[Any, ...]:
    return (
        csv_path,
        metric,
        bool(lower_is_better),
        int(num_groups),
        bool(auto_detect),
        str(analyzer_name).lower(),
        filter_metric or "",
        filter_min or "",
        filter_max or "",
        tuple(filter_values or []),
        tuple(excluded_predictors or []),
        tuple(cutoff_values or []),
    )


def _compute_profile_analysis_cached(
    csv_path: str,
    metric: str,
    lower_is_better: bool = True,
    num_groups: int = 2,
    auto_detect: bool = True,
    analyzer_name: str = "tree",
    filter_metric: str | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
    filter_values: list[str] | None = None,
    excluded_predictors: list[str] | None = None,
    cutoff_values: list[float] | None = None,
) -> dict[str, Any]:
    """Return cached profile analysis result for short-lived duplicate requests."""
    key = _analysis_cache_key(
        csv_path=csv_path,
        metric=metric,
        lower_is_better=lower_is_better,
        num_groups=num_groups,
        auto_detect=auto_detect,
        analyzer_name=analyzer_name,
        filter_metric=filter_metric,
        filter_min=filter_min,
        filter_max=filter_max,
        filter_values=filter_values,
        excluded_predictors=excluded_predictors,
        cutoff_values=cutoff_values,
    )

    settings = Settings()
    ttl_seconds = float(settings.get("gui.profile.analysis_cache_ttl_seconds", 15.0))
    max_entries = int(settings.get("gui.profile.analysis_cache_max_entries", 32))
    now = time.monotonic()

    # Purge expired entries opportunistically
    expired_keys = [
        cache_key
        for cache_key, (ts, _value) in _ANALYSIS_CACHE.items()
        if now - ts > ttl_seconds
    ]
    for cache_key in expired_keys:
        _ANALYSIS_CACHE.pop(cache_key, None)

    cached = _ANALYSIS_CACHE.get(key)
    if cached and now - cached[0] <= ttl_seconds:
        return cached[1]

    result = compute_profile_analysis(
        csv_path=csv_path,
        metric=metric,
        lower_is_better=lower_is_better,
        num_groups=num_groups,
        auto_detect=auto_detect,
        analyzer_name=analyzer_name,
        filter_metric=filter_metric,
        filter_min=filter_min,
        filter_max=filter_max,
        filter_values=filter_values,
        excluded_predictors=excluded_predictors,
        cutoff_values=cutoff_values,
    )

    _ANALYSIS_CACHE[key] = (now, result)
    while len(_ANALYSIS_CACHE) > max_entries:
        oldest_key = next(iter(_ANALYSIS_CACHE))
        _ANALYSIS_CACHE.pop(oldest_key, None)

    return result


def compute_profile_analysis(
    csv_path: str,
    metric: str,
    lower_is_better: bool = True,
    num_groups: int = 2,
    auto_detect: bool = True,
    analyzer_name: str = "tree",
    filter_metric: str | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
    filter_values: list[str] | None = None,
    excluded_predictors: list[str] | None = None,
    cutoff_values: list[float] | None = None,
) -> dict[str, Any]:
    """Run the full profile analysis pipeline and return results."""
    try:
        df = _load_filtered_dataframe(
            csv_path,
            filter_metric or "",
            None,
            filter_values=filter_values or [],
            filter_min=filter_min,
            filter_max=filter_max,
        )

        if df.height == 0 or metric not in df.columns:
            return {"error": "No data available after filtering", "factors": []}

        metric_values = df[metric].drop_nulls().to_numpy()
        if len(metric_values) == 0:
            return {"error": "No valid metric values", "factors": []}

        # Compute cleaned columns (C1+C2)
        cleaned_cols = compute_cleaned_columns(df)

        # Compute correlations
        correlations, predictor_stats = compute_outcome_correlations(
            df, metric, cleaned_cols
        )

        # Apply exclusions
        excluded = set(excluded_predictors or [])
        candidate_cols = [c for c in cleaned_cols if c not in excluded and c != metric]

        if not candidate_cols:
            return {
                "error": (
                    "All available predictors have been excluded. "
                    "Open 'Exclude Predictors' and uncheck some predictors to enable analysis."
                ),
                "factors": [],
            }

        # Compute reduced columns (C3)
        reduced_cols = compute_reduced_columns(df, metric, candidate_cols, correlations)

        if not reduced_cols:
            return {
                "error": (
                    "No predictors remain after column reduction. "
                    "The remaining predictors may not have sufficient correlation with "
                    "the metric (try excluding fewer predictors or lowering the "
                    "correlation threshold)."
                ),
                "factors": [],
            }

        # R1/R2/R3 row reduction (parity with old GUI):
        # R1 always: remove completely uninformative rows (fast, safe).
        # R2/R3 opt-in via settings, only kick in above 50K rows.
        df = reduce_rows(df, metric, reduced_cols)

        # Derive metric values from the row-reduced DataFrame and build the
        # labeler on this reduced data.  AutoLabeler is expensive (changepoint
        # detection + Jenks clustering), so building it on the full dataset
        # before row-reduction would be slow and cause a second re-run inside
        # label() because the lengths would differ.
        metric_values = df[metric].drop_nulls().to_numpy()
        if len(metric_values) == 0:
            return {"error": "No valid metric values after row reduction", "factors": []}

        labeler = build_labeler(num_groups, auto_detect, metric_values, lower_is_better, cutoff_values)

        # Build analysis DataFrame: only the metric and the columns that
        # survived the full reduction pipeline (cleaned + outcome-relevant).
        # Keeping C1/C2-rejected columns here would let the analyzer see
        # tens of thousands of uninformative columns, blowing up correlation
        # computation and causing the tree to hang on wide datasets.
        reduced_set = set(reduced_cols)
        analysis_df = df.select(
            [c for c in df.columns if c == metric or c in reduced_set]
        )

        # Run analysis
        registry = create_analyzer_registry()
        context = {
            "has_timestamp": "timestamp" in analysis_df.columns or "time" in analysis_df.columns,
            "n_rows": analysis_df.height,  # row-reduced count
            "n_predictors": len(reduced_cols),
            "outcome_mode": "classification" if (num_groups > 1 or auto_detect) else "regression",
            # Explicit allow-list/exclude-list for analyzers that support them.
            "predictors": list(reduced_cols),
            "exclude_cols": sorted(excluded | {metric}),
        }

        # Label data
        labels = None
        numeric_labels = None
        class_names = []
        is_classification = num_groups > 1 or auto_detect
        if labeler and is_classification:
            try:
                labels = labeler.label(metric_values)
                class_names = labeler.get_class_names()
                # Convert string labels to numeric for the analyzer
                if labels.dtype.kind in ("U", "S", "O"):
                    label_to_int = {lbl: i for i, lbl in enumerate(class_names)}
                    numeric_labels = np.array([label_to_int.get(l, 0) for l in labels])
                else:
                    numeric_labels = labels.astype(int)
            except Exception:
                labels = None
                numeric_labels = None
        elif labeler and not is_classification:
            # Regression mode
            numeric_labels = metric_values.astype(float)

        # Set shared state and run
        try:
            registry.set_shared_state(
                data=analysis_df,
                labels=numeric_labels,
                settings=None,
                outcome_col=metric,
                context=context,
            )
            factors = registry.analyze_single(analyzer_name.lower(), fallback="tree")
        except Exception:
            factors = []

        # Quality
        quality = None
        try:
            analyzer = registry.get_analyzer(analyzer_name)
            if analyzer and hasattr(analyzer, "evaluate_quality"):
                quality = analyzer.evaluate_quality()
        except Exception:
            pass

        return {
            "factors": factors,
            "labeler": labeler,
            "labels": labels,
            "quality": quality,
            "analysis_data": analysis_df,
            "reduced_columns": reduced_cols,
            "cleaned_columns": cleaned_cols,
            "correlations": correlations,
            "predictor_stats": predictor_stats,
            "analyzer_name": analyzer_name,
            "_registry": registry,
            "error": None,
        }
    except Exception as exc:
        return {"error": str(exc), "factors": []}


def render_distribution_plot_png(
    csv_path: str,
    metric: str,
    lower_is_better: bool = True,
    num_groups: int = 2,
    auto_detect: bool = True,
    filter_metric: str | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
    filter_values: list[str] | None = None,
    cutoff_values: list[float] | None = None,
) -> bytes:
    """Render the distribution plot as PNG bytes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from src.gui.utils.profile.distribution import render_distribution_plot

    df = _load_filtered_dataframe(
        csv_path,
        filter_metric or "",
        None,
        filter_values=filter_values or [],
        filter_min=filter_min,
        filter_max=filter_max,
    )

    metric_values = df[metric].drop_nulls().to_numpy() if metric in df.columns else np.array([])
    # For AutoLabeler on large datasets, subsample the df itself so that:
    # (a) AutoLabeler fits on a manageable number of points, and
    # (b) label() receives the same data it was trained on (fast path, no re-run).
    if auto_detect and not cutoff_values and df.height > 50_000:
        step = max(1, df.height // 50_000)
        df = df[::step]
        metric_values = df[metric].drop_nulls().to_numpy() if metric in df.columns else np.array([])
    labeler = build_labeler(num_groups, auto_detect, metric_values, lower_is_better, cutoff_values)

    fig = render_distribution_plot(df, metric, labeler)
    if fig is None:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    finally:
        plt.close(fig)
    return buf.getvalue()


def get_distribution_meta(
    csv_path: str,
    metric: str,
    lower_is_better: bool = True,
    num_groups: int = 2,
    auto_detect: bool = False,
    filter_metric: str | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
    filter_values: list[str] | None = None,
    cutoff_values: list[float] | None = None,
) -> dict[str, Any]:
    """Return axis limits for the distribution plot.

    Used by the browser to map pixel coordinates to data coordinates for
    click-to-move-cutoff and hover interactions.

    Returns a dict with:
      xmin, xmax  - axis extent (data range with 5 % matplotlib padding)
      plot_left, plot_right - x-axis drawing bounds as fractions of the final
        cropped PNG width, including savefig padding, for accurate browser
        click mapping.
    """
    from src.gui.utils.profile.distribution import render_distribution_plot

    df = _load_filtered_dataframe(
        csv_path,
        filter_metric or "",
        None,
        filter_values=filter_values or [],
        filter_min=filter_min,
        filter_max=filter_max,
    )

    if metric not in df.columns or df.height == 0:
        return {"xmin": 0.0, "xmax": 1.0, "plot_left": 0.0, "plot_right": 1.0}

    raw = df[metric].drop_nulls().to_numpy().astype(float)
    finite = raw[np.isfinite(raw)]
    if len(finite) == 0:
        return {"xmin": 0.0, "xmax": 1.0, "plot_left": 0.0, "plot_right": 1.0}

    data_min = float(finite.min())
    data_max = float(finite.max())
    data_range = data_max - data_min
    if data_range == 0:
        data_range = max(abs(data_min), 1.0)

    # Replicate matplotlib's default 5 % axis margin
    margin = 0.05 * data_range
    xmin = data_min - margin
    xmax = data_max + margin
    plot_left = 0.0
    plot_right = 1.0

    try:
        # Render a tiny fixed sample with a simple BinaryLabeler solely to
        # measure the plot's axis bounding box.  AutoLabeler (changepoint
        # detection + Jenks) is far too expensive here - the bbox values it
        # produces are effectively identical to those from a BinaryLabeler
        # because both render the same axes extents.
        sample_size = min(200, df.height)
        sample_df = df.sample(sample_size, seed=0) if df.height > sample_size else df
        sample_vals = sample_df[metric].drop_nulls().to_numpy()
        fast_labeler = build_labeler(2, False, sample_vals, lower_is_better, cutoff_values)
        fig = render_distribution_plot(sample_df, metric, fast_labeler)
        if fig is not None and fig.axes:
            import matplotlib

            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            ax_bbox = fig.axes[0].get_window_extent(renderer)
            tight_bbox = fig.get_tightbbox(renderer)
            pad_px = float(fig.dpi) * float(matplotlib.rcParams.get("savefig.pad_inches", 0.1))
            tight_x0 = float(tight_bbox.x0 * fig.dpi) - pad_px
            tight_x1 = float(tight_bbox.x1 * fig.dpi) + pad_px
            tight_width = max(tight_x1 - tight_x0, 1.0)
            plot_left = max(0.0, min(1.0, float((ax_bbox.x0 - tight_x0) / tight_width)))
            plot_right = max(plot_left, min(1.0, float((ax_bbox.x1 - tight_x0) / tight_width)))
    except Exception:
        plot_left = 0.0
        plot_right = 1.0
    finally:
        try:
            import matplotlib.pyplot as plt
            if 'fig' in locals() and fig is not None:
                plt.close(fig)
        except Exception:
            pass

    return {
        "xmin": xmin,
        "xmax": xmax,
        "plot_left": plot_left,
        "plot_right": plot_right,
    }


def move_distribution_cutoff(
    csv_path: str,
    metric: str,
    click_x: float,
    lower_is_better: bool,
    num_groups: int,
    auto_detect: bool,
    filter_metric: str | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
    filter_values: list[str] | None = None,
    cutoff_values: list[float] | None = None,
) -> list[float]:
    """Move the nearest cutoff to *click_x* and return the updated cutoff list.

    If no manual cutoffs are provided, derives an initial labeler from
    *num_groups* / *auto_detect*, finds its cutoffs, then moves the nearest
    one.  Delegates to the same logic as the old GUI's
    ``update_labeler_from_click``.
    """
    from src.gui.utils.profile.distribution import update_labeler_from_click

    existing_cutoffs = [float(v) for v in (cutoff_values or [])]
    if existing_cutoffs:
        # Build a ManualLabeler from stored cutoffs and move nearest
        from src.core.profile.labeler import ManualLabeler
        labeler = ManualLabeler.with_cutoffs(existing_cutoffs, lower_is_better)
    else:
        # Derive initial labeler from current UI settings
        df = _load_filtered_dataframe(
            csv_path,
            filter_metric or "",
            None,
            filter_values=filter_values or [],
            filter_min=filter_min,
            filter_max=filter_max,
        )
        metric_values = (
            df[metric].drop_nulls().to_numpy() if metric in df.columns else np.array([])
        )
        labeler = build_labeler(num_groups, auto_detect, metric_values, lower_is_better)

    new_labeler = update_labeler_from_click(click_x, labeler, lower_is_better)
    return new_labeler.get_cutoffs()


def _compact_tree_for_viz(sklearn_tree: Any) -> Any:
    """Return a copy of *sklearn_tree* remapped to only the split-node features.

    Trees trained on many columns (e.g. max_predictors=200) typically use
    only 1-10 of those columns in actual split nodes.  Supertree embeds the
    full X matrix as JSON, so passing 200 columns produces MB-scale HTML
    that can take 20+ seconds for the browser to parse.  Compacting to only
    the split-node columns reduces the payload to tens of KB.

    The original tree is not modified; a deep copy is used.
    Falls back to the original tree if anything goes wrong.
    """
    import copy
    try:
        from sklearn.tree._tree import TREE_LEAF  # type: ignore
        tree_ = sklearn_tree.tree_
        feature_names = list(getattr(sklearn_tree, "feature_names_", None) or [])
        if not feature_names or len(feature_names) != tree_.n_features:
            return sklearn_tree

        # Collect indices of features actually used in split nodes
        used = sorted({
            int(tree_.feature[i])
            for i in range(tree_.node_count)
            if tree_.feature[i] >= 0 and int(tree_.feature[i]) != TREE_LEAF
        })
        if not used or len(used) >= len(feature_names):
            return sklearn_tree  # already compact or pure-leaf tree

        old_to_new = {old: new for new, old in enumerate(used)}
        compact = copy.deepcopy(sklearn_tree)
        for i in range(compact.tree_.node_count):
            fi = int(compact.tree_.feature[i])
            if fi in old_to_new:
                compact.tree_.feature[i] = old_to_new[fi]
        compact.n_features_in_ = len(used)
        compact.feature_names_ = [feature_names[i] for i in used]
        orig = list(getattr(sklearn_tree, "original_predictors_", None) or [])
        compact.original_predictors_ = (
            [p for p in orig if p in set(compact.feature_names_)]
            or compact.feature_names_
        )
        for attr in ("class_names_", "training_data_", "outcome_mode_"):
            if (v := getattr(sklearn_tree, attr, None)) is not None:
                setattr(compact, attr, v)
        return compact
    except Exception:
        return sklearn_tree  # safe fallback


def render_analysis_tree_html(
    csv_path: str,
    metric: str,
    lower_is_better: bool = True,
    num_groups: int = 2,
    auto_detect: bool = True,
    analyzer_name: str = "tree",
    filter_metric: str | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
    filter_values: list[str] | None = None,
    cutoff_values: list[float] | None = None,
    excluded_predictors: list[str] | None = None,
) -> str:
    """Render influence-analysis visualization as embeddable HTML.

    For tree: the old-GUI interactive tree.
    For consensus: a scrollable rank-agreement table.
    For other analyzers: a scrollable ranked factor list.
    """
    import html as html_module
    from src.gui.utils.profile.tree import render_tree_for_ui

    result = _compute_profile_analysis_cached(
        csv_path=csv_path,
        metric=metric,
        lower_is_better=lower_is_better,
        num_groups=num_groups,
        auto_detect=auto_detect,
        analyzer_name=analyzer_name,
        filter_metric=filter_metric,
        filter_min=filter_min,
        filter_max=filter_max,
        filter_values=filter_values,
        excluded_predictors=excluded_predictors,
        cutoff_values=cutoff_values,
    )

    if result.get("error"):
        message = html_module.escape(str(result.get("error") or "No analysis results"))
        return _wrap_analysis_html(
            f"<p style='color:#a00;'>{message}</p>", analyzer_name
        )

    # ── Tree: interactive HTML ────────────────────────────────────────────────
    if analyzer_name.lower() == "tree":
        registry = result.get("_registry")
        labeler = result.get("labeler")
        data = result.get("analysis_data")
        trained_model = None
        if registry:
            analyzer_obj = registry.get_analyzer(analyzer_name)
            if analyzer_obj and hasattr(analyzer_obj, "trained_model"):
                trained_model = analyzer_obj.trained_model

        if trained_model is None:
            return _wrap_analysis_html(
                "<p style='color:#666;'>No decision tree is available for the current configuration.</p>",
                analyzer_name,
            )

        sklearn_tree = trained_model.model
        if not getattr(sklearn_tree, "feature_names_", None):
            sklearn_tree.feature_names_ = trained_model.feature_names
        if not getattr(sklearn_tree, "original_predictors_", None):
            sklearn_tree.original_predictors_ = trained_model.original_predictors

        class_names = labeler.get_class_names() if labeler else []
        if class_names:
            sklearn_tree.class_names_ = class_names

        if isinstance(data, pl.DataFrame):
            sklearn_tree.training_data_ = data

        # Compact the tree for visualization: remap internal feature indices
        # to only the columns that appear in split nodes so Supertree embeds
        # a small X matrix (a few columns) rather than all max_predictors.
        sklearn_tree = _compact_tree_for_viz(sklearn_tree)

        tree_html = render_tree_for_ui(
            tree=sklearn_tree,
            data=data,
            metric_col=metric,
            labeler=labeler,
        )

        sizing_css = (
            "<style>"
            "html,body{width:100%!important;height:100%!important;margin:0!important;"
            "padding:0!important;overflow:hidden!important;background:#fff!important;}"
            "#chart,#tree,.tree,.tree-container,.st-container,.st-tree,svg"
            "{width:100%!important;height:100%!important;max-width:none!important;display:block!important;}"
            "</style>"
        )

        if "</head>" in tree_html:
            return tree_html.replace("</head>", sizing_css + "</head>", 1)
        if "<html" in tree_html:
            return tree_html + sizing_css
        return (
            "<html><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"{sizing_css}</head><body>{tree_html}</body></html>"
        )

    # ── Consensus: HTML rank-agreement table ─────────────────────────────────
    if analyzer_name.lower() == "consensus":
        return _render_consensus_html(result)

    # ── Other analyzers: HTML factor list ────────────────────────────────────
    return _render_factor_list_html(result, analyzer_name)


def _wrap_analysis_html(body: str, analyzer_name: str = "") -> str:
    """Wrap a body fragment in a minimal HTML page with scrolling."""
    return (
        "<html><head><meta charset='utf-8'>"
        "<style>body{margin:0;padding:12px;font-family:sans-serif;font-size:14px;"
        "overflow:auto;background:#fff;color:#333;}</style>"
        f"</head><body>{body}</body></html>"
    )


def _render_consensus_html(result: dict) -> str:
    """Render a scrollable HTML rank-agreement table for the consensus analyzer."""
    import html as ht
    factors = result.get("factors") or []

    if not factors:
        return _wrap_analysis_html("<p style='color:#999;'>No consensus factors available.</p>")

    # Collect vote keys in order of first appearance
    vote_keys: list[str] = []
    seen: set[str] = set()
    for f in factors[:20]:
        for key in (f.metadata or {}).get("consensus_votes", {}):
            if key not in seen:
                seen.add(key)
                vote_keys.append(key)

    # Try to get display labels from registry
    try:
        from src.core.profile.analyzers.registry import create_analyzer_registry
        reg = create_analyzer_registry()
        col_labels = {
            k: (reg.get_analyzer(k).label if reg.get_analyzer(k) else k.title())
            for k in vote_keys
        }
    except Exception:
        col_labels = {k: k.title() for k in vote_keys}

    def rank_style(rank: int | None) -> str:
        if rank is None:
            return "background:#f5f5f5;color:#bbb;"
        if rank <= 3:
            return "background:#c8f0c8;color:#1a6b1a;font-weight:bold;"
        if rank <= 7:
            return "background:#e8f5e8;color:#2a5f2a;"
        return "background:#f8f8f8;color:#555;"

    th_s = "padding:6px 10px;border:1px solid #ddd;background:#f0f0f0;font-weight:600;white-space:nowrap;text-align:center;"
    td_s = "padding:5px 10px;border:1px solid #ddd;white-space:nowrap;"

    header = (
        f"<th style='{th_s}text-align:left;'>Factor</th>"
        f"<th style='{th_s}'>Agreement</th>"
    )
    for col in vote_keys:
        header += f"<th style='{th_s}'>{ht.escape(col_labels[col])}</th>"

    rows_html = ""
    for f in factors[:20]:
        votes = (f.metadata or {}).get("consensus_votes", {})
        agreement = (f.metadata or {}).get("agreement", 0)
        row = (
            f"<td style='{td_s}'>{ht.escape(f.name)}</td>"
            f"<td style='{td_s}text-align:center;font-weight:600;'>"
            f"{agreement}/{len(vote_keys)}</td>"
        )
        for col in vote_keys:
            vote_info = votes.get(col)
            rank = vote_info["rank"] if vote_info else None
            display = str(rank) if rank is not None else "-"
            row += f"<td style='{rank_style(rank)}padding:5px 10px;border:1px solid #ddd;text-align:center;'>{display}</td>"
        rows_html += f"<tr>{row}</tr>"

    subtitle = (
        "Factors ranked by Weighted RRF across all analyzers. "
        "Numbers show rank per analyzer; - = not ranked. "
        "<span style='background:#c8f0c8;color:#1a6b1a;padding:1px 4px;border-radius:2px;'>Green = top 3</span>."
    )

    body = (
        "<p style='font-weight:600;margin:0 0 4px;'>Consensus ranking (all analyzers)</p>"
        f"<p style='color:#666;font-size:0.9em;margin:0 0 10px;'>{subtitle}</p>"
        "<div style='overflow:auto;max-height:calc(100vh - 80px);'>"
        f"<table style='border-collapse:collapse;font-size:13px;'>"
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table></div>"
    )
    return _wrap_analysis_html(body)


def _render_factor_list_html(result: dict, analyzer_name: str) -> str:
    """Render a scrollable HTML factor list for non-tree, non-consensus analyzers."""
    import html as ht
    from src.core.profile.base import CausalDirection

    factors = result.get("factors") or []

    titles = {
        "granger": ("Granger Causality",
                    "Tests whether past values of each predictor forecast the outcome. "
                    "Sorted by forward Granger F-statistic."),
        "ccf": ("Cross-Correlation (CCF)",
                "Peak correlation between each predictor and the outcome across time lags."),
        "pcmci": ("Causal Graph (PCMCI)",
                  "Direct causal parents of the outcome. "
                  "Green = p &lt; 0.01, orange = p &lt; 0.05."),
        "te": ("Transfer Entropy",
               "Directed information flow (Schreiber 2000). "
               "TE is only meaningful for regression mode (continuous outcome)."),
        "hybrid": ("Hybrid Ensemble",
                   "Combined signal from multiple analyzers. Sorted by aggregate score."),
    }
    title, subtitle = titles.get(analyzer_name.lower(), (f"{analyzer_name} Analysis", ""))

    if not factors:
        # Informative empty-state messages per analyzer
        empty_msgs = {
            "te": (
                "Transfer Entropy was not run for this data. "
                "TE is only enabled for regression mode (continuous outcome) "
                "with detectable temporal dependence. "
                "In classification mode TE is skipped. "
                "Consider Granger, Hybrid, or Tree for this dataset."
            ),
            "pcmci": (
                "PCMCI found no significant causal parents for the outcome. "
                "This can happen with temporally independent (i.i.d.) data or "
                "when the significance threshold is not met. "
                "Try Granger or Tree as alternatives."
            ),
        }
        msg = empty_msgs.get(analyzer_name.lower(),
                              f"No factors returned by {title}.")
        body = (
            f"<p style='font-weight:600;margin:0 0 4px;'>{ht.escape(title)}</p>"
            f"<p style='color:#666;font-size:0.9em;margin:0 0 10px;'>{subtitle}</p>"
            f"<p style='color:#999;font-style:italic;'>{ht.escape(msg)}</p>"
        )
        return _wrap_analysis_html(body)

    def direction_arrow(f) -> str:
        d = getattr(f, "direction", None)
        if d == CausalDirection.FORWARD:
            return "→"
        if d == CausalDirection.REVERSE:
            return "←"
        if d == CausalDirection.BIDIRECTIONAL:
            return "↔"
        return "→"

    td_s = "padding:5px 10px;border-bottom:1px solid #eee;"
    th_s = "padding:6px 10px;border-bottom:2px solid #ddd;font-weight:600;text-align:left;white-space:nowrap;"

    # Build header columns per analyzer
    extra_headers = {
        "granger": ["Direction", "Strength", "Lag", "p-value"],
        "ccf": ["Strength", "Lag", "p-value", "95% CI"],
        "pcmci": ["Direction", "Strength", "p-value"],
        "te": ["Direction", "Strength", "TE↑ (nats)", "p-value"],
        "hybrid": ["Direction", "Score"],
    }
    cols = extra_headers.get(analyzer_name.lower(), ["Strength", "p-value"])

    header = f"<th style='{th_s}'>#</th><th style='{th_s}'>Factor</th>"
    for c in cols:
        header += f"<th style='{th_s}'>{ht.escape(c)}</th>"

    rows_html = ""
    for i, f in enumerate(factors[:20]):
        meta = f.metadata or {}
        arrow = direction_arrow(f)
        strength = f"{f.strength:.3f}" if f.strength is not None else "-"
        p_val = f.p_value
        if p_val is not None:
            p_str = "< 0.001" if p_val < 0.001 else f"{p_val:.3f}"
            if p_val < 0.01:
                p_color = "#2e7d32"
            elif p_val < 0.05:
                p_color = "#f57c00"
            else:
                p_color = "#757575"
            p_cell = f"<td style='{td_s}color:{p_color};'>{p_str}</td>"
        else:
            p_cell = f"<td style='{td_s}color:#bbb;'>-</td>"

        lag = ""
        if getattr(f, "lag", None) is not None:
            lag = f"{f.lag:.2f}s"
        elif getattr(f, "lag_rows", None) is not None:
            lag = f"{f.lag_rows} rows"
        lag_cell = f"<td style='{td_s}'>{ht.escape(lag)}</td>"

        ci = ""
        if getattr(f, "confidence_interval", None) is not None:
            lo, hi = f.confidence_interval
            ci = f"[{lo:.3f}, {hi:.3f}]"
        ci_cell = f"<td style='{td_s}'>{ht.escape(ci)}</td>"

        te_fwd = meta.get("te_forward_nats")
        te_cell = f"<td style='{td_s}'>{f'{te_fwd:.3f}' if te_fwd is not None else '-'}</td>"

        if analyzer_name.lower() == "granger":
            extra = f"<td style='{td_s}'>{arrow}</td><td style='{td_s}'>{strength}</td>{lag_cell}{p_cell}"
        elif analyzer_name.lower() == "ccf":
            extra = f"<td style='{td_s}'>{strength}</td>{lag_cell}{p_cell}{ci_cell}"
        elif analyzer_name.lower() == "pcmci":
            extra = f"<td style='{td_s}'>{arrow}</td><td style='{td_s}'>{strength}</td>{p_cell}"
        elif analyzer_name.lower() == "te":
            extra = f"<td style='{td_s}'>{arrow}</td><td style='{td_s}'>{strength}</td>{te_cell}{p_cell}"
        else:
            extra = f"<td style='{td_s}'>{arrow}</td><td style='{td_s}'>{strength}</td>"

        rows_html += (
            f"<tr>"
            f"<td style='{td_s}color:#999;'>{i+1}</td>"
            f"<td style='{td_s}font-weight:500;'>{ht.escape(f.name)}</td>"
            f"{extra}"
            f"</tr>"
        )

    body = (
        f"<p style='font-weight:600;margin:0 0 4px;'>{ht.escape(title)}</p>"
        f"<p style='color:#666;font-size:0.9em;margin:0 0 10px;'>{subtitle}</p>"
        "<div style='overflow:auto;max-height:calc(100vh - 80px);'>"
        f"<table style='border-collapse:collapse;font-size:13px;width:100%;'>"
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table></div>"
    )
    return _wrap_analysis_html(body)


def render_analysis_plot_png(
    csv_path: str,
    metric: str,
    lower_is_better: bool = True,
    num_groups: int = 2,
    auto_detect: bool = True,
    analyzer_name: str = "tree",
    filter_metric: str | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
    filter_values: list[str] | None = None,
    cutoff_values: list[float] | None = None,
    excluded_predictors: list[str] | None = None,
) -> bytes:
    """Render the analysis/tree visualizer plot as PNG bytes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    result = _compute_profile_analysis_cached(
        csv_path=csv_path,
        metric=metric,
        lower_is_better=lower_is_better,
        num_groups=num_groups,
        auto_detect=auto_detect,
        analyzer_name=analyzer_name,
        filter_metric=filter_metric,
        filter_min=filter_min,
        filter_max=filter_max,
        filter_values=filter_values,
        excluded_predictors=excluded_predictors,
        cutoff_values=cutoff_values,
    )

    fig = None
    if not result.get("error") and result.get("factors"):
        try:
            from src.gui.utils.profile.tree import render_tree_plot
            from src.gui.utils.profile.distribution import get_class_colors
            labeler = result["labeler"]
            registry = result.get("_registry")
            if registry:
                analyzer_obj = registry.get_analyzer(analyzer_name)
                if analyzer_obj and hasattr(analyzer_obj, "trained_model"):
                    trained_model = analyzer_obj.trained_model
                    if trained_model is not None:
                        sklearn_tree = trained_model.model
                        if not getattr(sklearn_tree, "feature_names_", None):
                            sklearn_tree.feature_names_ = trained_model.feature_names
                        class_names = labeler.get_class_names() if labeler else []
                        if class_names:
                            sklearn_tree.class_names_ = class_names
                        class_colors = get_class_colors(class_names)
                        fig = render_tree_plot(sklearn_tree, class_colors)
        except Exception:
            pass

        # Non-tree analyzers: render factor list as a text-based figure
        if fig is None and result.get("factors"):
            fig = _render_factor_list_figure(result, analyzer_name)

    if fig is None:
        fig, ax = plt.subplots(figsize=(10, 6))
        msg = result.get("error") or "No analysis results"
        ax.text(0.5, 0.5, msg, ha="center", va="center", transform=ax.transAxes,
                fontsize=10, wrap=True)
        ax.set_axis_off()

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    finally:
        plt.close(fig)
    return buf.getvalue()


def _render_factor_list_figure(result: dict, analyzer_name: str):
    """Render a matplotlib figure showing ranked factors for non-tree analyzers."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from src.core.profile.base import CausalDirection

    factors = result.get("factors", [])
    if not factors:
        return None

    # Analyzer display titles
    titles = {
        "granger": "Granger Causality",
        "ccf": "Cross-Correlation (CCF)",
        "pcmci": "Causal Graph (PCMCI)",
        "te": "Transfer Entropy",
        "hybrid": "Hybrid Ensemble",
        "consensus": "Consensus",
    }
    title = titles.get(analyzer_name.lower(), f"{analyzer_name} Analysis")

    top_factors = factors[:12]
    n = len(top_factors)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_axis_off()

    # Title
    ax.text(0.02, 0.95, title, fontsize=12, fontweight="bold",
            va="top", ha="left", transform=ax.transAxes)

    # Render each factor as a row
    y_start = 0.87
    line_height = 0.065
    for i, f in enumerate(top_factors):
        y = y_start - i * line_height
        if y < 0.02:
            break

        # Direction arrow
        arrow = "→"
        if hasattr(f, "direction") and f.direction is not None:
            if f.direction == CausalDirection.FORWARD:
                arrow = "→"
            elif f.direction == CausalDirection.REVERSE:
                arrow = "←"
            elif f.direction == CausalDirection.BIDIRECTIONAL:
                arrow = "↔"

        # Build label
        rank_str = f"{i+1}."
        strength_str = f"r = {f.strength:.3f}" if f.strength is not None else ""
        p_str = ""
        if f.p_value is not None:
            p_str = "(p < 0.001)" if f.p_value < 0.001 else f"(p = {f.p_value:.3f})"
        lag_str = ""
        if hasattr(f, "lag") and f.lag is not None:
            lag_str = f"lag {f.lag:.2f}s"
        elif hasattr(f, "lag_rows") and f.lag_rows is not None:
            lag_str = f"lag {f.lag_rows} rows"

        parts = [rank_str, f.name, arrow, strength_str]
        if lag_str:
            parts.append(lag_str)
        if p_str:
            parts.append(p_str)
        label = "  ".join(p for p in parts if p)

        # Color by significance
        color = "#333"
        if f.p_value is not None:
            if f.p_value < 0.01:
                color = "#2e7d32"
            elif f.p_value < 0.05:
                color = "#f57c00"
            else:
                color = "#757575"

        ax.text(0.02, y, label, fontsize=9, va="top", ha="left",
                transform=ax.transAxes, color=color, family="monospace")

    if n > 12:
        ax.text(0.02, 0.02, f"... and {len(factors) - 12} more factors",
                fontsize=8, va="bottom", ha="left", transform=ax.transAxes,
                color="#999", style="italic")

    fig.tight_layout(pad=0.5)
    return fig


def render_factor_scatter_png(
    csv_path: str,
    metric: str,
    factor_name: str,
    lower_is_better: bool = True,
    num_groups: int = 2,
    auto_detect: bool = True,
    filter_metric: str | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
    filter_values: list[str] | None = None,
) -> bytes:
    """Render a factor vs performance scatter plot as PNG bytes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from src.gui.utils.profile.factors import render_factor_scatter_plot

    df = _load_filtered_dataframe(
        csv_path,
        filter_metric or "",
        None,
        filter_values=filter_values or [],
        filter_min=filter_min,
        filter_max=filter_max,
    )

    metric_values = df[metric].drop_nulls().to_numpy() if metric in df.columns else np.array([])
    labeler_values = metric_values
    if auto_detect and len(labeler_values) > 50_000:
        step = max(1, len(labeler_values) // 50_000)
        labeler_values = labeler_values[::step]
    labeler = build_labeler(num_groups, auto_detect, labeler_values, lower_is_better)

    fig = None
    if factor_name in df.columns and metric in df.columns:
        try:
            fig = render_factor_scatter_plot(df, factor_name, metric, labeler)
        except Exception:
            pass

    if fig is None:
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    finally:
        plt.close(fig)
    return buf.getvalue()


def compute_factor_comparison_rows(
    csv_path: str,
    metric: str,
    factor_name: str,
    lower_is_better: bool = True,
    num_groups: int = 2,
    auto_detect: bool = True,
    filter_metric: str | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
    filter_values: list[str] | None = None,
) -> list[dict[str, str]]:
    """Compute factor statistics grouped by performance class."""
    df = _load_filtered_dataframe(
        csv_path,
        filter_metric or "",
        None,
        filter_values=filter_values or [],
        filter_min=filter_min,
        filter_max=filter_max,
    )

    if factor_name not in df.columns or metric not in df.columns:
        return []

    metric_values = df[metric].drop_nulls().to_numpy()
    if len(metric_values) == 0:
        return []

    labeler_values = metric_values
    if auto_detect and len(labeler_values) > 50_000:
        step = max(1, len(labeler_values) // 50_000)
        labeler_values = labeler_values[::step]
    labeler = build_labeler(num_groups, auto_detect, labeler_values, lower_is_better)

    if labeler is None:
        return []

    labels = labeler.label(metric_values)
    class_names = labeler.get_class_names()

    from src.gui.utils.profile.distribution import get_class_colors
    class_colors = get_class_colors(class_names)
    # Map class name → 25% alpha hex background (append '40' for ~25% opacity)
    color_map = {
        name: color + "40"
        for name, color in zip(class_names, class_colors)
    }

    df_labeled = df.with_columns(pl.Series("_class_", labels))
    rows = []
    for cls in class_names:
        group = df_labeled.filter(pl.col("_class_") == cls)
        if group.height == 0:
            continue
        col = group[factor_name].drop_nulls()
        rows.append({
            "group": cls,
            "color": color_map.get(cls, ""),
            "count": str(col.len()),
            "mean": f"{col.mean():.4g}" if col.len() > 0 else "",
            "std": f"{col.std():.4g}" if col.len() > 1 else "",
            "median": f"{col.median():.4g}" if col.len() > 0 else "",
        })
    return rows


def get_factor_narrative_html(analysis: dict[str, Any], factor_name: str) -> str:
    """Generate analysis narrative HTML for a selected factor."""
    from src.gui.utils.profile.visualizers import (
        get_visualizer_for,
        build_analysis_narrative_html,
    )

    if not factor_name or analysis.get("error"):
        return "<p style='color:#999;'>No analysis available.</p>"

    factors = analysis.get("factors", [])
    labeler = analysis.get("labeler")
    analyzer_name = analysis.get("analyzer_name", "tree")

    selected = next((f for f in factors if f.name == factor_name), None)
    if selected is None:
        return "<p style='color:#999;'>Factor not found in analysis results.</p>"

    class_names = labeler.get_class_names() if labeler else []
    visualizer = get_visualizer_for(
        analyzer_name=analyzer_name,
        tree=None,
        metric_col="",
        labeler=labeler,
    )
    narrative_map = visualizer.generate_narrative(
        factors=[selected],
        class_names=class_names,
    )
    return build_analysis_narrative_html(
        narrative_map=narrative_map,
        selected_factor=selected.name,
    )