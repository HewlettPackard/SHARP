# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Comparison services for the SHARP GUI API."""

import io
from pathlib import Path
from typing import Any

import numpy as np

from src.core.runlogs.metadata_compare import compare_metadata
from src.core.runlogs.reader import load_table
from src.core.stats.comparisons import comparison_table, density_comparison, ecdf_comparison, mann_whitney_test
from src.core.stats.narrative import generate_comparison_narrative
from src.gui.utils.comparisons import compute_comparison_summary

from ..contracts.schemas import CompareRequest, CompareResponse
from .shared import filter_kwargs_from_specs


def _metric_values(
    csv_path: str,
    metric: str,
    filter_metric: str | None = None,
    filter_value: str | None = None,
    filter_values: list[str] | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
) -> np.ndarray:
    """Load one metric column from a runlog, with optional filtering, as a NumPy array."""
    from src.gui.services.shared import _load_filtered_dataframe

    df = _load_filtered_dataframe(
        csv_path,
        filter_metric=filter_metric,
        filter_value=filter_value,
        filter_values=filter_values,
        filter_min=filter_min,
        filter_max=filter_max,
    )
    if metric not in df.columns:
        raise KeyError(f"Metric '{metric}' not found in {csv_path}")
    return df[metric].cast(float, strict=False).to_numpy()


def _resolve_md_path(csv_path: str, md_path: str | None) -> Path | None:
    """Resolve the markdown companion path when present."""
    if md_path:
        path = Path(md_path)
    else:
        path = Path(csv_path).with_suffix(".md")
    return path if path.exists() else None


def _jsonify(value: Any) -> Any:
    """Convert NumPy scalars and nested containers into JSON-safe builtins."""
    if isinstance(value, dict):
        return {str(key): _jsonify(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonify(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def render_density_comparison_png(
    baseline: np.ndarray, treatment: np.ndarray, metric: str
) -> bytes:
    """Render density comparison as a PNG byte string."""
    import matplotlib.pyplot as plt
    from src.gui.utils.comparisons import render_density_comparison_plot

    fig = render_density_comparison_plot(baseline, treatment, metric=metric)
    if fig is None:
        raise ValueError(f"Could not render density plot for metric '{metric}'")
    try:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        return buf.getvalue()
    finally:
        plt.close(fig)


def render_ecdf_comparison_png(
    baseline: np.ndarray, treatment: np.ndarray, metric: str
) -> bytes:
    """Render ECDF comparison as a PNG byte string."""
    import matplotlib.pyplot as plt
    from src.gui.utils.comparisons import render_ecdf_comparison_plot

    fig = render_ecdf_comparison_plot(baseline, treatment, metric=metric)
    if fig is None:
        raise ValueError(f"Could not render ECDF plot for metric '{metric}'")
    try:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        return buf.getvalue()
    finally:
        plt.close(fig)


def build_compare(request: CompareRequest) -> CompareResponse:
    """Build the comparison bundle for two runlogs."""
    _filter_kwargs = filter_kwargs_from_specs(request.filters)
    baseline = _metric_values(request.baseline_csv, request.metric, **_filter_kwargs)
    treatment = _metric_values(request.treatment_csv, request.metric, **_filter_kwargs)

    comparison = comparison_table(
        baseline,
        treatment,
        metric=request.metric,
        better="lower" if request.lower_is_better is not False else "higher",
    )
    mw = mann_whitney_test(baseline, treatment)
    ecdf = ecdf_comparison(baseline, treatment, request.metric)
    density = density_comparison(baseline, treatment, request.metric)
    narrative = generate_comparison_narrative(
        baseline,
        treatment,
        lower_is_better=request.lower_is_better,
    )

    baseline_md = _resolve_md_path(request.baseline_csv, request.baseline_md)
    treatment_md = _resolve_md_path(request.treatment_csv, request.treatment_md)
    metadata_diff = None
    if baseline_md is not None and treatment_md is not None:
        metadata_diff = compare_metadata(
            baseline_md=baseline_md,
            treatment_md=treatment_md,
            format="plaintext",
        )

    raw_summary = compute_comparison_summary(baseline, treatment)
    summary_rows = [
        {
            "stat": name,
            "baseline": b,
            "treatment": t,
            "pct_change": pct,
            "p_value": pv,
        }
        for name, b, t, pct, pv in zip(
            raw_summary["statistic_names"],
            raw_summary["baseline"],
            raw_summary["treatment"],
            raw_summary["pct_change"],
            raw_summary["p_value"],
        )
    ]

    return CompareResponse(
        metric=request.metric,
        comparison=_jsonify(comparison),
        mann_whitney=_jsonify(mw),
        ecdf=_jsonify(ecdf),
        density=_jsonify(density),
        narrative=narrative,
        metadata_diff=metadata_diff,
        summary_rows=summary_rows,
    )
