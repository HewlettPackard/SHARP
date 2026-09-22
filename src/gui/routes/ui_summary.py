# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Route handler for the Summary tab."""

from pathlib import Path
from urllib.parse import quote_plus

from fastapi import APIRouter
from fastapi import File
from fastapi import Form
from fastapi import Request
from fastapi import UploadFile
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse

from src.gui.components.summary import summary_page
from src.gui.services.summary import ensure_experiment_dir
from src.gui.services.summary import get_runlogs_dir
from src.gui.services.summary import load_summary_data
from src.gui.services.summary import normalize_experiment_name

router = APIRouter(prefix="/ui")


@router.get("/summary", response_class=HTMLResponse, include_in_schema=False)
def get_summary(request: Request) -> str:
    """Render the Summary page."""
    data = load_summary_data()
    data["notice"] = request.query_params.get("notice")
    data["error"] = request.query_params.get("error")
    return summary_page(data)


@router.post("/summary/new-experiment", include_in_schema=False)
def create_experiment(new_experiment_name: str = Form(...)) -> RedirectResponse:
    """Create a new experiment directory and return to Review."""
    try:
        experiment_name = normalize_experiment_name(new_experiment_name)
        runlogs_dir = get_runlogs_dir()
        existed_before = (runlogs_dir / experiment_name).exists()
        ensure_experiment_dir(experiment_name)
        if existed_before:
            message = f"Experiment '{experiment_name}' is ready."
            return RedirectResponse(
                url=f"/ui/summary?notice={quote_plus(message)}",
                status_code=303,
            )
    except ValueError as exc:
        return RedirectResponse(url=f"/ui/summary?error={quote_plus(str(exc))}", status_code=303)
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(url=f"/ui/summary?error={quote_plus(str(exc))}", status_code=303)

    message = f"Created experiment '{experiment_name}'."
    return RedirectResponse(url=f"/ui/summary?notice={quote_plus(message)}", status_code=303)


@router.post("/summary/upload", include_in_schema=False)
def upload_experiment_files(
    upload_experiment_name: str = Form(...),
    upload_files: list[UploadFile] = File(...),
) -> RedirectResponse:
    """Upload CSV/MD files into the selected experiment directory."""
    try:
        experiment_name = normalize_experiment_name(upload_experiment_name)
        experiment_dir = ensure_experiment_dir(experiment_name)

        uploaded_count = 0
        skipped_files: list[str] = []
        for upload in upload_files:
            filename = Path(upload.filename or "").name
            ext = Path(filename).suffix.lower()
            if ext not in {".csv", ".md"}:
                skipped_files.append(filename or "<unnamed>")
                continue

            target = experiment_dir / filename
            with target.open("wb") as out:
                out.write(upload.file.read())
            uploaded_count += 1

        if uploaded_count == 0:
            skipped = ", ".join(skipped_files) if skipped_files else "no files"
            return RedirectResponse(
                url=f"/ui/summary?error={quote_plus(f'No files uploaded. Skipped: {skipped}.')}",
                status_code=303,
            )

        message = f"Uploaded {uploaded_count} file(s) to '{experiment_name}'."
        if skipped_files:
            message += f" Skipped: {', '.join(skipped_files)}."
        return RedirectResponse(url=f"/ui/summary?notice={quote_plus(message)}", status_code=303)
    except ValueError as exc:
        return RedirectResponse(url=f"/ui/summary?error={quote_plus(str(exc))}", status_code=303)
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(url=f"/ui/summary?error={quote_plus(str(exc))}", status_code=303)
