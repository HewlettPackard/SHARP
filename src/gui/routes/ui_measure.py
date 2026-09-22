# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Route handlers for the Measure tab."""

import json
from urllib.parse import quote_plus

from fastapi import APIRouter
from fastapi import Form
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.responses import StreamingResponse

from src.gui.components.measure import measure_page
from src.gui.services.measure import load_measure_outputs
from src.gui.services.measure import load_measure_form_data
from src.gui.services.measure import load_rerun_prefill
from src.gui.services.measure import run_measure_workflow
from src.gui.services.measure_jobs import get_measure_job
from src.gui.services.measure_jobs import start_measure_job
from src.gui.services.measure_jobs import wait_for_measure_job_update

router = APIRouter(prefix="/ui")


def _build_error_redirect_url(error: str, bench: str) -> str:
    """Build redirect URL for a failed measure run."""
    return (
        f"/ui/measure?error={quote_plus(str(error or 'Run failed'))}"
        f"&bench={quote_plus(bench)}"
    )


def _build_success_redirect_url(workflow: dict[str, object], bench: str, experiment: str, task: str) -> str:
    """Build redirect URL for a completed measure run."""
    notice = quote_plus(str(workflow.get("notice") or "Run completed successfully."))
    query = [
        f"notice={notice}",
        f"bench={quote_plus(bench)}",
        f"rerun_experiment={quote_plus(str(workflow.get('experiment') or experiment))}",
        f"rerun_task={quote_plus(str(workflow.get('task') or task))}",
    ]

    csv_path = workflow.get("csv_path")
    md_path = workflow.get("md_path")
    if csv_path:
        query.append(f"csv_path={quote_plus(str(csv_path))}")
    if md_path:
        query.append(f"md_path={quote_plus(str(md_path))}")

    return f"/ui/measure?{'&'.join(query)}"


@router.get("/measure", response_class=HTMLResponse, include_in_schema=False)
def get_measure(request: Request) -> str:
    """Render the Measure page."""
    data = load_measure_form_data()
    data["notice"] = request.query_params.get("notice")
    data["error"] = request.query_params.get("error")
    data["bench"] = request.query_params.get("bench")
    data.update(
        load_rerun_prefill(
            request.query_params.get("rerun_csv_path"),
            request.query_params.get("rerun_experiment"),
            request.query_params.get("rerun_task"),
        )
    )

    csv_path = request.query_params.get("csv_path")
    md_path = request.query_params.get("md_path")
    data["csv_path"] = csv_path
    data["md_path"] = md_path
    if csv_path or md_path:
        data.update(load_measure_outputs(csv_path, md_path))
    return measure_page(data)


@router.post("/measure/run", include_in_schema=False)
def run_measure(
    experiment: str = Form(""),
    bench: str = Form(""),
    task: str = Form(""),
    stopping: str = Form("COUNT"),
    n: int = Form(1),
    backend: list[str] = Form(default=[]),
    mpl: int = Form(1),
    start: str = Form("as-is"),
    timeout: int = Form(60),
    moreopts: str = Form(""),
) -> RedirectResponse:
    """Run a benchmark from the Measure tab and redirect with results."""
    form_payload = {
        "experiment": experiment,
        "bench": bench,
        "task": task,
        "stopping": stopping,
        "n": n,
        "backend": backend,
        "mpl": mpl,
        "start": start,
        "timeout": timeout,
        "moreopts": moreopts,
    }

    workflow = run_measure_workflow(form_payload)

    if not workflow.get("success"):
        return RedirectResponse(
            url=_build_error_redirect_url(str(workflow.get("error") or "Run failed"), bench),
            status_code=303,
        )

    return RedirectResponse(
        url=_build_success_redirect_url(workflow, bench, experiment, task),
        status_code=303,
    )


@router.post("/measure/start", include_in_schema=False)
def start_measure(
    experiment: str = Form(""),
    bench: str = Form(""),
    task: str = Form(""),
    stopping: str = Form("COUNT"),
    n: int = Form(1),
    backend: list[str] = Form(default=[]),
    mpl: int = Form(1),
    start: str = Form("as-is"),
    timeout: int = Form(60),
    moreopts: str = Form(""),
) -> JSONResponse:
    """Start a benchmark from Measure and return run id for SSE progress stream."""
    form_payload = {
        "experiment": experiment,
        "bench": bench,
        "task": task,
        "stopping": stopping,
        "n": n,
        "backend": backend,
        "mpl": mpl,
        "start": start,
        "timeout": timeout,
        "moreopts": moreopts,
    }

    run_id = start_measure_job(form_payload)
    return JSONResponse(content={"run_id": run_id})


@router.get("/measure/stream", include_in_schema=False)
def stream_measure(run_id: str) -> StreamingResponse:
    """Stream Measure progress events via SSE until completion."""
    initial = get_measure_job(run_id)
    if not initial:
        return StreamingResponse(iter(["event: error\ndata: {\"error\": \"missing run\"}\n\n"]), media_type="text/event-stream")

    def _stream():
        current = initial
        version = int(current.get("version") or 0)

        while current is not None:
            payload: dict[str, object] = {
                "status": str(current.get("status") or ""),
                "current": int(current.get("current") or 0),
                "total": current.get("total"),
                "message": str(current.get("message") or ""),
            }

            status = str(current.get("status") or "")
            if status == "completed":
                workflow = current.get("workflow")
                form = current.get("form") or {}
                if isinstance(workflow, dict):
                    payload["redirect_url"] = _build_success_redirect_url(
                        workflow,
                        str(form.get("bench") or ""),
                        str(form.get("experiment") or ""),
                        str(form.get("task") or ""),
                    )
            elif status == "failed":
                form = current.get("form") or {}
                payload["error_url"] = _build_error_redirect_url(
                    str(current.get("error") or "Run failed"),
                    str(form.get("bench") or ""),
                )

            yield f"data: {json.dumps(payload)}\n\n"

            if status in {"completed", "failed"}:
                break

            updated = wait_for_measure_job_update(run_id, version, timeout=10.0)
            if updated is None:
                yield ": keepalive\n\n"
                current = get_measure_job(run_id)
                if current is None:
                    break
                version = int(current.get("version") or version)
                continue

            current = updated
            version = int(current.get("version") or version)

    _SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)
