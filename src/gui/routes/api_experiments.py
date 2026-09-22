# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Discovery API routes for the SHARP GUI."""

from fastapi import APIRouter

from ..contracts.schemas import BackendListResponse, BenchmarkListResponse, ExperimentListResponse, TaskListResponse
from ..services.experiments import list_backends, list_benchmarks, list_experiments, list_tasks

router = APIRouter(prefix="/api/v1", tags=["api"])


@router.get("/experiments", response_model=ExperimentListResponse)
def get_experiments() -> ExperimentListResponse:
    """Return discovered experiments."""
    return list_experiments()


@router.get("/experiments/{experiment}/tasks", response_model=TaskListResponse)
def get_tasks(experiment: str) -> TaskListResponse:
    """Return tasks for one experiment."""
    return list_tasks(experiment)


@router.get("/benchmarks", response_model=BenchmarkListResponse)
def get_benchmarks() -> BenchmarkListResponse:
    """Return available benchmarks."""
    return list_benchmarks()


@router.get("/backends", response_model=BackendListResponse)
def get_backends() -> BackendListResponse:
    """Return available backends."""
    return list_backends()
