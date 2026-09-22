# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Comparison API routes for the SHARP GUI."""

from fastapi import APIRouter, HTTPException

from ..contracts.schemas import CompareRequest, CompareResponse
from ..services.compare import build_compare

router = APIRouter(prefix="/api/v1", tags=["api"])


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (KeyError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.post("/compare", response_model=CompareResponse)
def post_compare(request: CompareRequest) -> CompareResponse:
    """Return a comparison bundle for two runlogs."""
    try:
        return build_compare(request)
    except Exception as exc:  # pragma: no cover - translated in smoke tests
        raise _translate_error(exc) from exc
