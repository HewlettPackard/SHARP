# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Background run tracking for the SHARP GUI Measure with callback updates."""

from __future__ import annotations

from copy import deepcopy
from threading import Condition, Lock, Thread
from typing import Any
from uuid import uuid4

from .measure import run_measure_workflow


_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = Lock()
_jobs_updated = Condition(_jobs_lock)


def _update_job(job_id: str, updates: dict[str, Any]) -> None:
    """Apply partial updates, bump version, and notify waiting stream consumers."""
    with _jobs_updated:
        job = _jobs.get(job_id)
        if not job:
            return
        job.update(updates)
        job["version"] = int(job.get("version", 0)) + 1
        _jobs_updated.notify_all()


def _progress_callback_factory(job_id: str):
    """Create a progress callback that updates shared run state."""

    def _progress_callback(current: int, total: int | None) -> None:
        _update_job(
            job_id,
            {
                "status": "running",
                "current": max(0, int(current)),
                "total": int(total) if isinstance(total, int) else None,
            },
        )

    return _progress_callback


def _run_measure_job(job_id: str, form: dict[str, Any]) -> None:
    """Run measure workflow in a background thread and finalize state."""
    _update_job(job_id, {"status": "running", "message": "Starting benchmark run..."})

    workflow = run_measure_workflow(form, progress_callback=_progress_callback_factory(job_id))

    if workflow.get("success"):
        with _jobs_lock:
            final_current = int(_jobs.get(job_id, {}).get("current") or 0)
        _update_job(
            job_id,
            {
                "status": "completed",
                "workflow": workflow,
                "message": str(workflow.get("notice") or "Run completed."),
                "current": final_current,
            },
        )
        return

    _update_job(
        job_id,
        {
            "status": "failed",
            "error": str(workflow.get("error") or "Run failed"),
            "message": "Run failed",
        },
    )


def start_measure_job(form: dict[str, Any]) -> str:
    """Start a background run and return its job identifier."""
    job_id = str(uuid4())
    total = int(form.get("n") or 1) if str(form.get("stopping") or "").upper() == "COUNT" else None

    with _jobs_updated:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "current": 0,
            "total": total,
            "message": "Queued",
            "form": deepcopy(form),
            "workflow": None,
            "error": "",
            "version": 0,
        }

    worker = Thread(target=_run_measure_job, args=(job_id, deepcopy(form)), daemon=True)
    worker.start()
    return job_id


def get_measure_job(job_id: str) -> dict[str, Any] | None:
    """Get current immutable snapshot of job data."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        return deepcopy(job) if job else None


def wait_for_measure_job_update(job_id: str, last_version: int, timeout: float = 15.0) -> dict[str, Any] | None:
    """Block until job updates or timeout and return latest snapshot."""
    with _jobs_updated:
        _jobs_updated.wait_for(
            lambda: (
                job_id not in _jobs
                or int(_jobs[job_id].get("version", 0)) > int(last_version)
                or str(_jobs[job_id].get("status") or "") in {"completed", "failed"}
            ),
            timeout=timeout,
        )
        job = _jobs.get(job_id)
        return deepcopy(job) if job else None
