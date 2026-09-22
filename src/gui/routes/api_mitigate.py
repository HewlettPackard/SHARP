# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Mitigation HTTP JSON endpoints (``/api/v1/mitigate/...``) for the SHARP GUI.

These endpoints are backed by GUI service modules. Phase 12 will migrate
implementation behind ``src/api``. See ``docs/api.md``.
"""

from __future__ import annotations

from copy import deepcopy
from threading import Lock, Thread
from typing import Any, NoReturn
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Path, status

from ..contracts.schemas import (
    MitigationApplyRequest,
    MitigationApplyResponse,
    MitigationApplyStatusResponse,
    MitigationInfoResponse,
    MitigationListResponse,
    StubResponse,
)
from ..services.mitigate import not_implemented_message
from ..services.profile import load_mitigation_info, run_mitigation_workflow
from src.core.metrics.factors import get_mitigation_backend
from src.core.metrics.factors import list_mitigations as get_all_mitigations

router = APIRouter(prefix="/api/v1/mitigate", tags=["api"])

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = Lock()


def _stub(operation: str) -> NoReturn:
    raise HTTPException(
        status_code=501,
        detail=StubResponse(
            operation=operation,
            message=not_implemented_message(operation),
        ).model_dump(),
    )


def _set_job(job_id: str, updates: dict[str, Any]) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(updates)


def _run_apply_job(job_id: str, req: MitigationApplyRequest) -> None:
    _set_job(job_id, {"status": "running", "message": "Applying mitigation..."})
    result = run_mitigation_workflow(req.md_path, req.mitigation_name)
    if result.get("success"):
        _set_job(
            job_id,
            {
                "status": "completed",
                "success": True,
                "mitigation_csv": result.get("mitigation_csv"),
                "notice": result.get("notice"),
                "message": result.get("notice") or "Mitigation completed.",
            },
        )
        return
    _set_job(
        job_id,
        {
            "status": "failed",
            "success": False,
            "error": result.get("error") or "Mitigation failed",
            "message": result.get("error") or "Mitigation failed",
        },
    )


@router.get("/list", response_model=MitigationListResponse)
def list_mitigations() -> MitigationListResponse:
    """Return all available mitigation names."""
    return MitigationListResponse(mitigations=get_all_mitigations())


@router.get("/info/{mitigation}", response_model=MitigationInfoResponse)
def mitigation_info(mitigation: str = Path(...)) -> MitigationInfoResponse:
    """Return metadata and execution capability for a specific mitigation."""
    info = load_mitigation_info(mitigation)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Mitigation '{mitigation}' not found")
    return MitigationInfoResponse(
        name=mitigation,
        description=info.get("description"),
        references=info.get("references"),
        is_automated=info.get("is_automated", False),
        backend_options=get_mitigation_backend(mitigation),
    )


@router.post("/apply", response_model=MitigationApplyResponse, status_code=status.HTTP_202_ACCEPTED)
def apply_mitigation(req: MitigationApplyRequest) -> MitigationApplyResponse:
    """Queue an automated mitigation run and return a job id immediately."""
    job_id = str(uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "success": None,
            "error": None,
            "mitigation_csv": None,
            "notice": None,
            "message": "Queued",
        }
    Thread(target=_run_apply_job, args=(job_id, req), daemon=True).start()
    return MitigationApplyResponse(job_id=job_id, status="queued", message="Queued")


@router.get("/apply/{job_id}", response_model=MitigationApplyStatusResponse)
def apply_status(job_id: str = Path(...)) -> MitigationApplyStatusResponse:
    """Return the status/result of a queued mitigation apply job."""
    with _jobs_lock:
        job = deepcopy(_jobs.get(job_id))
    if job is None:
        raise HTTPException(status_code=404, detail=f"Mitigation job '{job_id}' not found")
    return MitigationApplyStatusResponse(**job)


@router.post("/revert", response_model=StubResponse)
def revert_mitigation() -> StubResponse:
    """Reserved route; safe revert semantics are not implemented on this branch."""
    _stub("mitigate.revert")
