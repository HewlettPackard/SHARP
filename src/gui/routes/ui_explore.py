# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Route handlers for the Explore tab."""

from urllib.parse import urlencode

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.responses import Response

from src.gui.components.explore import explore_page
from src.gui.services.explore import (
    apply_explore_filter,
    list_task_choices,
    load_explore_dataset,
    load_explore_form_data,
    render_pairwise_plot_png,
    render_distribution_plot_png,
    resolve_csv_path_for_task,
)

router = APIRouter(prefix="/ui")


@router.get("/explore", response_class=HTMLResponse, include_in_schema=False)
def get_explore(request: Request) -> str:
    """Render Explore page with optional selected dataset and filter."""
    experiment = request.query_params.get("experiment", "")
    csv_path = request.query_params.get("csv_path", "")
    task = request.query_params.get("task", "")
    metric = request.query_params.get("metric", "")
    filter_metric = request.query_params.get("filter_metric", "")
    filter_value = request.query_params.get("filter_value", "")
    filter_min = request.query_params.get("filter_min", "")
    filter_max = request.query_params.get("filter_max", "")
    filter_values = [v for v in request.query_params.getlist("filter_values") if v]
    compare_metrics = [v for v in request.query_params.getlist("compare_metrics") if v]

    if experiment and task and not csv_path:
        csv_path = resolve_csv_path_for_task(experiment, task) or ""

    data = load_explore_form_data()
    data["experiment"] = experiment
    data["task"] = task
    data["csv_path"] = csv_path
    data["tasks"] = list_task_choices(experiment)

    if experiment and csv_path:
        try:
            dataset = load_explore_dataset(experiment, csv_path)
            data.update(dataset)

            active_metric = metric or dataset.get("metric") or ""
            data["metric"] = active_metric
            data["filter_metric"] = filter_metric
            data["filter_value"] = filter_value
            data["filter_min"] = filter_min
            data["filter_max"] = filter_max
            data["filter_values"] = filter_values
            data["selected_compare_metrics"] = compare_metrics

            if active_metric:
                data.update(
                    apply_explore_filter(
                        csv_path=csv_path,
                        metric=active_metric,
                        filter_metric=filter_metric or None,
                        filter_value=filter_value,
                        filter_values=filter_values,
                        filter_min=filter_min or None,
                        filter_max=filter_max or None,
                    )
                )
                plot_params = [
                    ("csv_path", csv_path),
                    ("metric", active_metric),
                    ("filter_metric", filter_metric),
                    ("filter_value", filter_value),
                    ("filter_min", filter_min),
                    ("filter_max", filter_max),
                ]
                plot_params.extend(("filter_values", v) for v in filter_values)
                data["plot_url"] = "/ui/explore/plot.png?" + urlencode(plot_params)

                if compare_metrics:
                    data["n_compare_metrics"] = len(compare_metrics)
                    pair_params = [
                        ("csv_path", csv_path),
                        ("filter_metric", filter_metric),
                        ("filter_value", filter_value),
                        ("filter_min", filter_min),
                        ("filter_max", filter_max),
                    ]
                    pair_params.extend(("filter_values", v) for v in filter_values)
                    pair_params.extend(("compare_metrics", v) for v in compare_metrics)
                    data["pair_plot_url"] = "/ui/explore/pairwise.png?" + urlencode(pair_params)
        except Exception as exc:  # noqa: BLE001
            data["error"] = str(exc)

    return explore_page(data)


@router.get("/explore/plot.png", include_in_schema=False)
def get_explore_plot(
    csv_path: str,
    metric: str,
    filter_metric: str = "",
    filter_value: str = "",
    filter_values: list[str] | None = None,
    filter_min: str = "",
    filter_max: str = "",
) -> Response:
    """Render Explore distribution plot image for current selection."""
    content = render_distribution_plot_png(
        csv_path=csv_path,
        metric=metric,
        filter_metric=filter_metric or None,
        filter_value=filter_value,
        filter_values=filter_values or [],
        filter_min=filter_min or None,
        filter_max=filter_max or None,
    )
    return Response(content=content, media_type="image/png")


@router.get("/explore/pairwise.png", include_in_schema=False)
def get_explore_pairwise_plot(
    csv_path: str,
    compare_metrics: list[str] = Query(default=[]),
    filter_metric: str = "",
    filter_value: str = "",
    filter_values: list[str] | None = None,
    filter_min: str = "",
    filter_max: str = "",
) -> Response:
    """Render Explore pairwise comparison/correlation plot image."""
    content = render_pairwise_plot_png(
        csv_path=csv_path,
        metrics=compare_metrics,
        filter_metric=filter_metric or None,
        filter_value=filter_value,
        filter_values=filter_values or [],
        filter_min=filter_min or None,
        filter_max=filter_max or None,
    )
    return Response(content=content, media_type="image/png")

@router.get("/explore/metrics", include_in_schema=False)
def get_explore_metrics(
    csv_path: str = Query(""),
    q: str = Query(""),
    limit: int = Query(150, ge=1, le=500),
) -> JSONResponse:
    """Search outcome (numeric) metrics for large explore datasets."""
    from src.gui.services.shared import search_outcome_metrics

    if not csv_path:
        return JSONResponse({"items": []})

    try:
        matches = search_outcome_metrics(csv_path, q, limit)
    except Exception:
        matches = []

    items = [{"value": m, "text": m, "label": m} for m in matches]
    return JSONResponse({"items": items})
