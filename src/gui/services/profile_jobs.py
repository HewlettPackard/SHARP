# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Background run tracking for the SHARP GUI Profile reprofiling with callback updates."""

from __future__ import annotations

from copy import deepcopy
from threading import Condition, Lock, Thread
from typing import Any
from uuid import uuid4

from src.gui.utils.profile.files import extract_repeater_max_from_md

from .profile import run_profile_workflow


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
                "message": f"Profiling iteration {max(0, int(current))}/{int(total) if isinstance(total, int) else '?'}",
            },
        )

    return _progress_callback


def _run_profile_job(job_id: str, form: dict[str, Any]) -> None:
    """Run profile workflow in a background thread and finalize state."""
    _update_job(job_id, {"status": "running", "message": "Starting profiling run..."})

    workflow = run_profile_workflow(
        str(form.get("original_md") or ""),
        [str(v) for v in list(form.get("profiling_backends") or [])],
        str(form.get("profile_task_name") or "").strip(),
        progress_callback=_progress_callback_factory(job_id),
    )

    if workflow.get("success"):
        with _jobs_lock:
            final_current = int(_jobs.get(job_id, {}).get("current") or 0)
            total = _jobs.get(job_id, {}).get("total")
        _update_job(
            job_id,
            {
                "status": "completed",
                "workflow": workflow,
                "message": str(workflow.get("notice") or "Profiling completed."),
                "current": final_current,
                "total": int(total) if isinstance(total, int) else total,
            },
        )
        return

    _update_job(
        job_id,
        {
            "status": "failed",
            "error": str(workflow.get("error") or "Profiling failed"),
            "message": "Profiling failed",
        },
    )


def start_profile_job(form: dict[str, Any]) -> str:
    """Start a background profile run and return its job identifier."""
    job_id = str(uuid4())

    original_md = str(form.get("original_md") or "")
    total = extract_repeater_max_from_md(original_md) if original_md else None

    with _jobs_updated:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "current": 0,
            "total": int(total) if isinstance(total, int) else None,
            "message": "Queued",
            "form": deepcopy(form),
            "workflow": None,
            "error": "",
            "version": 0,
        }

    worker = Thread(target=_run_profile_job, args=(job_id, deepcopy(form)), daemon=True)
    worker.start()
    return job_id


def get_profile_job(job_id: str) -> dict[str, Any] | None:
    """Get current immutable snapshot of job data."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        return deepcopy(job) if job else None


def wait_for_profile_job_update(job_id: str, last_version: int, timeout: float = 15.0) -> dict[str, Any] | None:
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
