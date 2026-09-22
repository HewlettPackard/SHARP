# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Route handlers for the Compare tab."""

from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.responses import Response

from src.core.runlogs.reader import load_table
from src.gui.components.compare import compare_page
from src.gui.contracts.schemas import CompareRequest
from src.gui.services.compare import build_compare
from src.gui.services.compare import render_density_comparison_png
from src.gui.services.compare import render_ecdf_comparison_png
from src.gui.services.compare import _metric_values
from src.gui.services.experiments import list_experiments
from src.gui.services.experiments import list_tasks
from src.gui.services.explore import _filter_config_for_metric
from src.gui.services.explore import _load_filtered_dataframe
from src.gui.services.shared import METRIC_PREFERENCES, _filter_kind

router = APIRouter(prefix="/ui")


def _task_choices(experiment: str) -> list[dict[str, str]]:
    """Return task choice list for Compare selectors."""
    if not experiment:
        return []

    choices: list[dict[str, str]] = []
    for task in list_tasks(experiment).tasks:
        choices.append({"csv_path": task.csv_path, "md_path": task.md_path, "label": task.task})
    return choices


def _numeric_metric_columns(csv_path: str) -> list[str]:
    """Return numeric columns from a runlog."""
    if not csv_path:
        return []

    df = load_table(csv_path)
    out: list[str] = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        if any(token in dtype for token in ["Int", "Float", "Decimal"]):
            out.append(col)
    return out


def _filterable_metric_columns(csv_path: str) -> list[str]:
    """Return columns that can be used as filter metrics (numeric + time strings)."""
    if not csv_path:
        return []

    df = load_table(csv_path)
    out: list[str] = []
    for col in df.columns:
        kind = _filter_kind(df[col])
        if kind != "unsupported":
            out.append(col)
    return out


def _shared_metrics(baseline_csv: str, treatment_csv: str) -> list[str]:
    """Return numeric metric intersection ordered by old-gui preferences."""
    if not baseline_csv or not treatment_csv:
        return []

    baseline_metrics = set(_numeric_metric_columns(baseline_csv))
    treatment_metrics = set(_numeric_metric_columns(treatment_csv))
    shared = baseline_metrics.intersection(treatment_metrics)

    preferred = [metric for metric in METRIC_PREFERENCES if metric in shared]
    remaining = sorted(metric for metric in shared if metric not in METRIC_PREFERENCES)
    return preferred + remaining


def _loaded_rows(csv_path: str) -> int | None:
    """Return loaded row count for the selected CSV."""
    if not csv_path:
        return None
    try:
        return len(load_table(csv_path))
    except Exception:
        return None



@router.get("/compare", response_class=HTMLResponse, include_in_schema=False)
def get_compare(
    request: Request,
    filter_values: list[str] = Query(default=[]),
) -> str:
    """Render Compare page with optional completed comparison."""
    baseline_experiment = request.query_params.get("baseline_experiment", "")
    treatment_experiment = request.query_params.get("treatment_experiment", "")
    baseline_csv = request.query_params.get("baseline_csv", "")
    treatment_csv = request.query_params.get("treatment_csv", "")
    metric = request.query_params.get("metric", "")
    filter_metric = request.query_params.get("filter_metric", "")
    filter_min = request.query_params.get("filter_min", "")
    filter_max = request.query_params.get("filter_max", "")

    data: dict[str, Any] = {
        "notice": request.query_params.get("notice"),
        "error": request.query_params.get("error"),
        "experiments": [item.name for item in list_experiments().experiments],
        "baseline_experiment": baseline_experiment,
        "treatment_experiment": treatment_experiment,
        "baseline_csv": baseline_csv,
        "treatment_csv": treatment_csv,
        "baseline_rows": _loaded_rows(baseline_csv),
        "treatment_rows": _loaded_rows(treatment_csv),
        "metric": metric,
        "baseline_tasks": _task_choices(baseline_experiment),
        "treatment_tasks": _task_choices(treatment_experiment),
        "metrics": [],
        "filter_metric": filter_metric,
        "filter_metrics": [],
        "filter_kind": "none",
        "filter_options": [],
        "filter_values": filter_values,
        "filter_min": filter_min,
        "filter_max": filter_max,
        "filter_min_bound_num": None,
        "filter_max_bound_num": None,
        "filter_is_timestamp_like": False,
        "summary_rows": [],
        "density_url": None,
        "ecdf_url": None,
        "narrative": "",
        "metadata_diff": None,
    }

    if baseline_csv and treatment_csv:
        try:
            metrics = _shared_metrics(baseline_csv, treatment_csv)
            data["metrics"] = metrics

            # Pick metric: explicit > preferred default > first available
            # (shared_metrics already orders by METRIC_PREFERENCES)
            if not metric and metrics:
                metric = metrics[0]
            data["metric"] = metric

            # Common filterable columns (intersection of both datasets)
            b_filterable = set(_filterable_metric_columns(baseline_csv))
            t_filterable = set(_filterable_metric_columns(treatment_csv))
            data["filter_metrics"] = sorted(b_filterable & t_filterable)

            # Build filter widget config from baseline dataset
            if filter_metric:
                baseline_df = load_table(baseline_csv)
                filter_cfg = _filter_config_for_metric(baseline_df, filter_metric)
                data.update(filter_cfg)

                # Resolve numeric current values from URL params
                if filter_cfg.get("filter_kind") in {"numeric", "time"}:
                    try:
                        data["filter_min_value_num"] = float(filter_min) if filter_min else filter_cfg.get("filter_min_bound_num")
                        data["filter_max_value_num"] = float(filter_max) if filter_max else filter_cfg.get("filter_max_bound_num")
                    except (ValueError, TypeError):
                        data["filter_min_value_num"] = filter_cfg.get("filter_min_bound_num")
                        data["filter_max_value_num"] = filter_cfg.get("filter_max_bound_num")

            if metric:
                result = build_compare(
                    CompareRequest(
                        baseline_csv=baseline_csv,
                        treatment_csv=treatment_csv,
                        metric=metric,
                        lower_is_better=True,
                        filter_metric=filter_metric or None,
                        filter_values=filter_values if filter_values else None,
                        filter_min=filter_min or None,
                        filter_max=filter_max or None,
                    )
                )

                data["summary_rows"] = result.summary_rows or []
                data["narrative"] = result.narrative
                data["metadata_diff"] = result.metadata_diff

                # Build plot image URLs
                plot_params: list[tuple[str, str]] = [
                    ("baseline_csv", baseline_csv),
                    ("treatment_csv", treatment_csv),
                    ("metric", data["metric"]),
                ]
                if filter_metric:
                    plot_params.append(("filter_metric", filter_metric))
                if filter_min:
                    plot_params.append(("filter_min", filter_min))
                if filter_max:
                    plot_params.append(("filter_max", filter_max))
                for fv in filter_values:
                    plot_params.append(("filter_values", fv))
                plot_qs = urlencode(plot_params)
                data["density_url"] = f"/ui/compare/density.png?{plot_qs}"
                data["ecdf_url"] = f"/ui/compare/ecdf.png?{plot_qs}"
        except Exception as exc:  # noqa: BLE001
            data["error"] = str(exc)

    return compare_page(data)


@router.get("/compare/density.png", include_in_schema=False)
def get_compare_density_png(
    request: Request,
    filter_values: list[str] = Query(default=[]),
) -> Response:
    """Render a density comparison plot as PNG."""
    baseline_csv = request.query_params.get("baseline_csv", "")
    treatment_csv = request.query_params.get("treatment_csv", "")
    metric = request.query_params.get("metric", "")
    filter_metric = request.query_params.get("filter_metric", "") or None
    filter_min = request.query_params.get("filter_min", "") or None
    filter_max = request.query_params.get("filter_max", "") or None

    if not (baseline_csv and treatment_csv and metric):
        raise HTTPException(status_code=400, detail="Missing required parameters.")

    _filter_kwargs: dict[str, Any] = dict(
        filter_metric=filter_metric,
        filter_values=filter_values if filter_values else None,
        filter_min=filter_min,
        filter_max=filter_max,
    )
    baseline = _metric_values(baseline_csv, metric, **_filter_kwargs)
    treatment = _metric_values(treatment_csv, metric, **_filter_kwargs)
    png = render_density_comparison_png(baseline, treatment, metric)
    return Response(content=png, media_type="image/png")


@router.get("/compare/ecdf.png", include_in_schema=False)
def get_compare_ecdf_png(
    request: Request,
    filter_values: list[str] = Query(default=[]),
) -> Response:
    """Render an ECDF comparison plot as PNG."""
    baseline_csv = request.query_params.get("baseline_csv", "")
    treatment_csv = request.query_params.get("treatment_csv", "")
    metric = request.query_params.get("metric", "")
    filter_metric = request.query_params.get("filter_metric", "") or None
    filter_min = request.query_params.get("filter_min", "") or None
    filter_max = request.query_params.get("filter_max", "") or None

    if not (baseline_csv and treatment_csv and metric):
        raise HTTPException(status_code=400, detail="Missing required parameters.")

    _filter_kwargs: dict[str, Any] = dict(
        filter_metric=filter_metric,
        filter_values=filter_values if filter_values else None,
        filter_min=filter_min,
        filter_max=filter_max,
    )
    baseline = _metric_values(baseline_csv, metric, **_filter_kwargs)
    treatment = _metric_values(treatment_csv, metric, **_filter_kwargs)
    png = render_ecdf_comparison_png(baseline, treatment, metric)
    return Response(content=png, media_type="image/png")
