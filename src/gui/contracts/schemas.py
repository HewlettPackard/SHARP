# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Pydantic request/response contracts for the SHARP GUI API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExperimentItem(BaseModel):
    """Summary metadata for one experiment."""

    name: str
    run_count: int
    latest_timestamp: datetime | None = None


class ExperimentListResponse(BaseModel):
    """Collection of discovered experiments."""

    experiments: list[ExperimentItem]


class TaskItem(BaseModel):
    """Summary metadata for one task within an experiment."""

    experiment: str
    task: str
    csv_path: str
    md_path: str
    timestamp: datetime | None = None
    benchmark: str | None = None
    backends: list[str] = Field(default_factory=list)
    duration: float | None = None
    rows: int | None = None
    description: str | None = None


class TaskListResponse(BaseModel):
    """Collection of tasks for a selected experiment."""

    experiment: str
    tasks: list[TaskItem]


class BenchmarkItem(BaseModel):
    """Discovered benchmark metadata."""

    name: str
    path: str


class BenchmarkListResponse(BaseModel):
    """Collection of available benchmarks."""

    benchmarks: list[BenchmarkItem]


class BackendItem(BaseModel):
    """Discovered backend metadata."""

    name: str
    path: str
    profiling: bool
    composable: bool
    description: str | None = None


class BackendListResponse(BaseModel):
    """Collection of available backends."""

    backends: list[BackendItem]


class FilterSpec(BaseModel):
    """One public API row filter."""

    metric: str
    kind: Literal["equals", "in", "range"] = "in"
    value: str | None = None
    values: list[str] | None = None
    min: str | None = None
    max: str | None = None


class DistributionSummaryRequest(BaseModel):
    """Request payload for summary statistics over a metric column."""

    csv_path: str
    metric: str
    digits: int = 5
    filters: list[FilterSpec] = Field(default_factory=list)


class DistributionSummaryResponse(BaseModel):
    """Summary statistics for a metric column."""

    csv_path: str
    metric: str
    summary: dict[str, int | float | None]


class DistributionChangepointsRequest(BaseModel):
    """Request payload for changepoint analysis."""

    csv_path: str
    metric: str
    model: str = "auto"
    pen: float | None = None
    min_size: int | None = None
    filters: list[FilterSpec] = Field(default_factory=list)


class DistributionChangepointsResponse(BaseModel):
    """Changepoint analysis result for a metric column."""

    csv_path: str
    metric: str
    result: dict[str, Any]


class DistributionCharacterizeRequest(BaseModel):
    """Request payload for narrative distribution characterization."""

    csv_path: str
    metric: str
    model: str = "auto"
    pen: float | None = None
    min_size: int | None = None
    filters: list[FilterSpec] = Field(default_factory=list)


class DistributionCharacterizeResponse(BaseModel):
    """Narrative distribution characterization."""

    csv_path: str
    metric: str
    narrative: str


class CompareRequest(BaseModel):
    """Request payload for baseline versus treatment comparison."""

    baseline_csv: str
    treatment_csv: str
    metric: str
    lower_is_better: bool | None = True
    baseline_md: str | None = None
    treatment_md: str | None = None
    filters: list[FilterSpec] = Field(default_factory=list)


class CompareResponse(BaseModel):
    """Comparison result bundle for two datasets."""

    metric: str
    comparison: dict[str, Any]
    mann_whitney: dict[str, Any]
    ecdf: dict[str, Any] | None = None
    density: dict[str, Any] | None = None
    narrative: str
    metadata_diff: str | None = None
    summary_rows: list[Any] | None = None


class StubResponse(BaseModel):
    """Placeholder response for planned but unimplemented routes."""

    operation: str
    status: Literal["not_implemented"] = "not_implemented"
    message: str


# ============================================================================
# Profile API Schemas
# ============================================================================


class ProfileAnalyzeRequest(BaseModel):
    """Request payload for full profile analysis."""

    csv_path: str
    metric: str
    lower_is_better: bool = True
    num_groups: int = 2
    auto_detect: bool = True
    analyzer_name: str = "tree"
    filters: list[FilterSpec] = Field(default_factory=list)
    excluded_predictors: list[str] | None = None
    cutoff_values: list[float] | None = None


class ProfileFactorItem(BaseModel):
    """Stable, JSON-safe summary of one ranked influence factor."""

    name: str
    strength: float | None = None
    rank: int | None = None
    method: str | None = None
    direction: str | None = None
    p_value: float | None = None
    lag: int | None = None
    lag_rows: int | None = None
    confidence_interval: list[float] | None = None
    falsification_plan: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class ProfileAnalyzeResponse(BaseModel):
    """Response from full profile analysis pipeline."""

    error: str | None = None
    factors: list[ProfileFactorItem] = Field(default_factory=list)
    labels: list[Any] | None = None
    quality: dict[str, Any] | None = None
    analysis_data: dict[str, Any] | None = None
    reduced_columns: list[str] | None = None
    cleaned_columns: list[str] | None = None
    correlations: dict[str, Any] | None = None
    predictor_stats: dict[str, Any] | list[dict[str, Any]] | None = None
    analyzer_name: str | None = None


class ProfileFactorsRequest(BaseModel):
    """Request payload for ranked factors analysis."""

    csv_path: str
    metric: str
    lower_is_better: bool = True
    num_groups: int = 2
    auto_detect: bool = True
    analyzer_name: str = "tree"
    filters: list[FilterSpec] = Field(default_factory=list)
    excluded_predictors: list[str] | None = None
    cutoff_values: list[float] | None = None


class ProfileFactorsResponse(BaseModel):
    """Response with ranked factors from profile analysis."""

    error: str | None = None
    factors: list[ProfileFactorItem] = Field(default_factory=list)


class SuggestCutoffRequest(BaseModel):
    """Request payload for cutoff suggestion."""

    csv_path: str
    metric: str
    strategy: str = "binary"  # "binary" | "manual"
    num_groups: int | None = None
    filters: list[FilterSpec] = Field(default_factory=list)


class SuggestCutoffResponse(BaseModel):
    """Response with suggested cutoff values."""

    error: str | None = None
    cutoffs: list[float] | None = None
    strategy: str | None = None


# ============================================================================
# Mitigation API Schemas
# ============================================================================


class MitigationListResponse(BaseModel):
    """Response with all available mitigation names."""

    mitigations: list[str]


class MitigationInfoResponse(BaseModel):
    """Response with metadata for a specific mitigation."""

    name: str
    description: str | None = None
    references: dict[str, str] | None = None
    is_automated: bool = False
    backend_options: dict[str, Any] | None = None


class MitigationApplyRequest(BaseModel):
    """Request payload for automated mitigation run."""

    md_path: str
    mitigation_name: str


class MitigationApplyResponse(BaseModel):
    """Response returned immediately after queueing mitigation execution."""

    job_id: str
    status: str
    message: str


class MitigationApplyStatusResponse(BaseModel):
    """Current status/result for an asynchronous mitigation apply job."""

    job_id: str
    status: str
    success: bool | None = None
    error: str | None = None
    mitigation_csv: str | None = None
    notice: str | None = None
