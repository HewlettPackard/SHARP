# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Distribution API routes for the SHARP GUI."""

from fastapi import APIRouter, HTTPException

from ..contracts.schemas import (
    DistributionCharacterizeRequest,
    DistributionCharacterizeResponse,
    DistributionChangepointsRequest,
    DistributionChangepointsResponse,
    DistributionSummaryRequest,
    DistributionSummaryResponse,
)
from ..services.distribution import build_characterization, build_changepoints, build_summary

router = APIRouter(prefix="/api/v1/distribution", tags=["api"])


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (KeyError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.post("/summary", response_model=DistributionSummaryResponse)
def post_summary(request: DistributionSummaryRequest) -> DistributionSummaryResponse:
    """Return summary statistics for a runlog metric."""
    try:
        return build_summary(request)
    except Exception as exc:  # pragma: no cover - translated in smoke tests
        raise _translate_error(exc) from exc


@router.post("/changepoints", response_model=DistributionChangepointsResponse)
def post_changepoints(
    request: DistributionChangepointsRequest,
) -> DistributionChangepointsResponse:
    """Return changepoint analysis for a runlog metric."""
    try:
        return build_changepoints(request)
    except Exception as exc:  # pragma: no cover - translated in smoke tests
        raise _translate_error(exc) from exc


@router.post("/characterize", response_model=DistributionCharacterizeResponse)
def post_characterize(
    request: DistributionCharacterizeRequest,
) -> DistributionCharacterizeResponse:
    """Return narrative characterization for a runlog metric."""
    try:
        return build_characterization(request)
    except Exception as exc:  # pragma: no cover - translated in smoke tests
        raise _translate_error(exc) from exc
