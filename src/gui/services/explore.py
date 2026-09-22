# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Explore-page service helpers."""

from __future__ import annotations

import io
from typing import Any

import matplotlib.pyplot as plt
import polars as pl

from src.core.config.settings import Settings
from src.core.runlogs.reader import load_table
from src.core.stats.distribution import characterize_distribution
from src.core.stats.distribution import compute_summary
from src.core.stats.distribution import create_distribution_plot

from .experiments import list_experiments
from .experiments import list_tasks
from .shared import (
    _filter_config_for_metric,
    _filter_kind,
    _is_time_series,
    _load_filtered_dataframe,
    _order_metric_candidates,
)


def render_distribution_plot_png(
    csv_path: str,
    metric: str,
    filter_metric: str | None = None,
    filter_value: str | None = None,
    filter_values: list[str] | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
) -> bytes:
    """Render filtered distribution plot PNG for Explore."""
    df = _load_filtered_dataframe(
        csv_path,
        filter_metric,
        filter_value,
        filter_values=filter_values,
        filter_min=filter_min,
        filter_max=filter_max,
    )
    if metric not in df.columns or df.height == 0:
        raise ValueError("No data available for selected metric.")

    values = df[metric].cast(float, strict=False).to_numpy()
    if len(values) == 0:
        raise ValueError("No numeric values available for selected metric.")

    settings = Settings()
    max_scatter = settings.get("gui.explore.max_scatter_points", 2000)
    figure = create_distribution_plot(values, metric, max_scatter_points=max_scatter)

    try:
        with io.BytesIO() as buffer:
            figure.savefig(buffer, format="png", dpi=120, bbox_inches="tight")
            return buffer.getvalue()
    finally:
        plt.close(figure)


def render_pairwise_plot_png(
    csv_path: str,
    metrics: list[str],
    filter_metric: str | None = None,
    filter_value: str | None = None,
    filter_values: list[str] | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
) -> bytes:
    """Render pairwise comparison/correlation plot PNG for selected metrics."""
    df = _load_filtered_dataframe(
        csv_path,
        filter_metric,
        filter_value,
        filter_values=filter_values,
        filter_min=filter_min,
        filter_max=filter_max,
    )

    selected = [metric for metric in metrics if metric in df.columns]
    if not selected:
        raise ValueError("No valid metrics selected for pairwise plot.")

    subset = df.select(selected).drop_nulls()
    if subset.height == 0:
        raise ValueError("No data available for selected metrics.")

    arrays = {col: subset[col].cast(float, strict=False).to_numpy() for col in selected}
    n = len(selected)

    # Wide non-square figure: each subplot column is 5in wide, each row is 3in tall.
    # At DPI=100 this gives 500×300 px per cell. JS/CSS enforce the display height.
    fig, axes = plt.subplots(n, n, figsize=(5 * n, 3 * n))
    if n == 1:
        ax = axes if hasattr(axes, "hist") else axes[0, 0]
        ax.hist(arrays[selected[0]], bins=30, color="steelblue", alpha=0.75, edgecolor="black")
        ax.set_xlabel(selected[0])
        ax.set_ylabel("Frequency")
    else:
        for i, ycol in enumerate(selected):
            for j, xcol in enumerate(selected):
                ax = axes[i, j]
                xvals = arrays[xcol]
                yvals = arrays[ycol]
                if i == j:
                    ax.hist(xvals, bins=30, color="steelblue", alpha=0.75, edgecolor="black")
                else:
                    ax.scatter(xvals, yvals, s=20, alpha=0.55, color="black", rasterized=True)
                    if len(xvals) > 2 and len(yvals) > 2:
                        try:
                            corr = float(np.corrcoef(xvals, yvals)[0, 1])
                            ax.text(
                                0.05,
                                0.9,
                                f"r={corr:.2f}",
                                transform=ax.transAxes,
                                fontsize=10,
                                bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.7},
                            )
                        except Exception:
                            pass

                if i == n - 1:
                    ax.set_xlabel(xcol, fontsize=10)
                else:
                    ax.set_xticklabels([])
                if j == 0:
                    ax.set_ylabel(ycol, fontsize=10)
                else:
                    ax.set_yticklabels([])

    plt.subplots_adjust(bottom=0.15, left=0.1, top=0.95, right=0.95, hspace=0.3, wspace=0.3)
    try:
        with io.BytesIO() as buffer:
            fig.savefig(buffer, format="png", dpi=100, bbox_inches="tight", pad_inches=0.12)
            return buffer.getvalue()
    finally:
        plt.close(fig)


def load_explore_form_data() -> dict[str, Any]:
    """Load experiments for Explore selectors."""
    experiments = [exp.name for exp in list_experiments().experiments]
    return {
        "experiments": experiments,
    }


def load_explore_dataset(experiment: str, csv_path: str) -> dict[str, Any]:
    """Load selected dataset and compute available metrics/filters."""
    df = load_table(csv_path)

    metric_candidates: list[str] = []
    filter_candidates: list[str] = []

    for col in df.columns:
        series = df[col]
        dtype = str(series.dtype)
        if any(token in dtype for token in ["Int", "Float", "Decimal"]):
            metric_candidates.append(col)

        if _is_time_series(series):
            filter_candidates.append(col)
            continue

        if any(token in dtype for token in ["Int", "Float", "Decimal"]):
            if series.n_unique() > 1:
                filter_candidates.append(col)
            continue

        if any(token in dtype for token in ["String", "Utf8", "Categorical"]):
            unique_count = series.n_unique()
            if unique_count > 1 and unique_count < df.height:
                filter_candidates.append(col)

    metric_candidates = _order_metric_candidates(metric_candidates)
    filter_candidates = sorted(filter_candidates)
    metric = metric_candidates[0] if metric_candidates else None
    summary_rows: list[dict[str, Any]] = []
    narrative = "No metric selected."
    if metric:
        values = df[metric].cast(float, strict=False).to_numpy()
        summary = compute_summary(values)
        summary_rows = [{"stat": key, "value": value} for key, value in summary.items()]
        narrative = characterize_distribution(values)

    return {
        "experiment": experiment,
        "csv_path": csv_path,
        "metric": metric,
        "metrics": metric_candidates,
        "filter_metrics": filter_candidates,
        "compare_metrics": metric_candidates,
        "selected_compare_metrics": [],
        "summary_rows": summary_rows,
        "narrative": narrative,
        "has_plot": bool(metric),
        "filter_kind": "none",
        "filter_options": [],
        "filter_min_bound": None,
        "filter_max_bound": None,
    }


def list_task_choices(experiment: str) -> list[dict[str, str]]:
    """Return task choices (csv_path + label) for selected experiment."""
    if not experiment:
        return []
    tasks = list_tasks(experiment).tasks
    return [
        {
            "value": task.csv_path,
            "label": task.task,
        }
        for task in tasks
    ]


def resolve_csv_path_for_task(experiment: str, task_name: str) -> str | None:
    """Resolve a task name to csv_path within an experiment."""
    if not experiment or not task_name:
        return None

    for task in list_tasks(experiment).tasks:
        if task.task == task_name:
            return task.csv_path
    return None


def apply_explore_filter(
    csv_path: str,
    metric: str,
    filter_metric: str | None,
    filter_value: str | None,
    filter_values: list[str] | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
) -> dict[str, Any]:
    """Apply optional equality filter and recompute summary/narrative."""
    raw_df = load_table(csv_path)
    config = _filter_config_for_metric(raw_df, filter_metric)

    min_bound_num = config.get("filter_min_bound_num")
    max_bound_num = config.get("filter_max_bound_num")

    min_value_num: float | None = None
    max_value_num: float | None = None

    if config.get("filter_kind") == "numeric" and min_bound_num is not None and max_bound_num is not None:
        try:
            min_value_num = float(filter_min) if filter_min not in (None, "") else float(min_bound_num)
        except Exception:
            min_value_num = float(min_bound_num)
        try:
            max_value_num = float(filter_max) if filter_max not in (None, "") else float(max_bound_num)
        except Exception:
            max_value_num = float(max_bound_num)

    if config.get("filter_kind") == "time" and min_bound_num is not None and max_bound_num is not None:
        try:
            min_value_num = _time_to_seconds(str(filter_min)) if filter_min not in (None, "") else float(min_bound_num)
        except Exception:
            min_value_num = float(min_bound_num)
        try:
            max_value_num = _time_to_seconds(str(filter_max)) if filter_max not in (None, "") else float(max_bound_num)
        except Exception:
            max_value_num = float(max_bound_num)

    df = _load_filtered_dataframe(
        csv_path,
        filter_metric,
        filter_value,
        filter_values=filter_values,
        filter_min=filter_min,
        filter_max=filter_max,
    )

    if metric not in df.columns or df.height == 0:
        return {
            "summary_rows": [],
            "narrative": "No data after filtering.",
            "has_plot": False,
            "filter_min_value_num": min_value_num,
            "filter_max_value_num": max_value_num,
            **config,
        }

    values = df[metric].cast(float, strict=False).to_numpy()
    summary = compute_summary(values)
    narrative = characterize_distribution(values)
    return {
        "summary_rows": [{"stat": key, "value": value} for key, value in summary.items()],
        "narrative": narrative,
        "has_plot": True,
        "filter_min_value_num": min_value_num,
        "filter_max_value_num": max_value_num,
        **config,
    }
