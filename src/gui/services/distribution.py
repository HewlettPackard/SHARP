# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Distribution analysis services for the SHARP GUI API."""

from math import isnan

import numpy as np

from src.core.stats.distribution import characterize_distribution, compute_summary, detect_change_points

from ..contracts.schemas import (
    DistributionCharacterizeRequest,
    DistributionCharacterizeResponse,
    DistributionChangepointsRequest,
    DistributionChangepointsResponse,
    DistributionSummaryRequest,
    DistributionSummaryResponse,
    FilterSpec,
)
from .shared import _load_filtered_dataframe, filter_kwargs_from_specs


def _load_metric_values(csv_path: str, metric: str, filters: list[FilterSpec]) -> np.ndarray:
    """Load one metric column from a runlog as a NumPy array."""
    kwargs = filter_kwargs_from_specs(filters)
    df = _load_filtered_dataframe(csv_path, **kwargs)
    if metric not in df.columns:
        raise KeyError(f"Metric '{metric}' not found in {csv_path}")
    return df[metric].cast(float, strict=False).to_numpy()


def _normalize_summary(summary: dict[str, int | float]) -> dict[str, int | float | None]:
    """Convert NaN values to None for JSON compatibility."""
    normalized: dict[str, int | float | None] = {}
    for key, value in summary.items():
        if isinstance(value, float) and isnan(value):
            normalized[key] = None
        else:
            normalized[key] = value
    return normalized


def build_summary(request: DistributionSummaryRequest) -> DistributionSummaryResponse:
    """Compute summary statistics for a runlog metric."""
    values = _load_metric_values(request.csv_path, request.metric, request.filters)
    summary = compute_summary(values, digits=request.digits)
    return DistributionSummaryResponse(
        csv_path=request.csv_path,
        metric=request.metric,
        summary=_normalize_summary(summary),
    )


def build_changepoints(request: DistributionChangepointsRequest) -> DistributionChangepointsResponse:
    """Detect changepoints in a runlog metric."""
    values = _load_metric_values(request.csv_path, request.metric, request.filters)
    result = detect_change_points(
        values,
        model=request.model,
        pen=request.pen,
        min_size=request.min_size,
    )
    return DistributionChangepointsResponse(
        csv_path=request.csv_path,
        metric=request.metric,
        result=result,
    )


def build_characterization(
    request: DistributionCharacterizeRequest,
) -> DistributionCharacterizeResponse:
    """Generate a narrative characterization for a runlog metric."""
    values = _load_metric_values(request.csv_path, request.metric, request.filters)
    narrative = characterize_distribution(
        values,
        model=request.model,
        pen=request.pen,
        min_size=request.min_size,
    )
    return DistributionCharacterizeResponse(
        csv_path=request.csv_path,
        metric=request.metric,
        narrative=narrative,
    )
