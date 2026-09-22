# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""FastAPI application factory for the SHARP GUI."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .routes.api_compare import router as api_compare_router
from .routes.api_distribution import router as api_distribution_router
from .routes.api_experiments import router as api_experiments_router
from .routes.api_mitigate import router as api_mitigate_router
from .routes.api_profile import router as api_profile_router
from .routes.ui_compare import router as ui_compare_router
from .routes.ui_explore import router as ui_explore_router
from .routes.ui_measure import router as ui_measure_router
from .routes.ui_profile import router as ui_profile_router
from .routes.ui_settings import router as ui_settings_router
from .routes.ui_shell import router as ui_shell_router
from .routes.ui_summary import router as ui_summary_router


def create_app() -> FastAPI:
    """Create the SHARP FastAPI app with static assets and routes."""
    app = FastAPI(
        title="SHARP UI",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    static_dir = Path(__file__).parent / "static"
    legacy_www_dir = Path(__file__).resolve().parent.parent / "gui" / "www"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(ui_summary_router)
    app.include_router(ui_measure_router)
    app.include_router(ui_explore_router)
    app.include_router(ui_compare_router)
    app.include_router(ui_profile_router)
    app.include_router(ui_settings_router)
    app.include_router(ui_shell_router)
    app.include_router(api_experiments_router)
    app.include_router(api_distribution_router)
    app.include_router(api_compare_router)
    app.include_router(api_profile_router)
    app.include_router(api_mitigate_router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/ui/summary", status_code=307)

    @app.get("/health", response_class=HTMLResponse, include_in_schema=False)
    def health() -> str:
        return "ok"

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(
            legacy_www_dir / "sharp.png",
            media_type="image/png",
        )

    return app


app = create_app()