# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Settings routes: modal fragment and save handler."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(prefix="/ui", tags=["settings"])


@router.get("/settings/modal", response_class=HTMLResponse, include_in_schema=False)
def get_settings_modal() -> HTMLResponse:
    """Return the settings <dialog> HTML fragment for HTMX to swap in.

    After the swap app.js opens the dialog via showModal().
    """
    from src.gui.utils.settings import render_settings_modal
    html = render_settings_modal()
    resp = HTMLResponse(html)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.post("/settings/save", include_in_schema=False)
def save_settings(
    request: Request,
    settings_theme: str = Form("default"),
    settings_recent_count: int = Form(25),
    settings_divider_color: str = Form("#1f77b4"),
    settings_fast_color: str = Form("#a1e736"),
    settings_slow_color: str = Form("#dd560e"),
    settings_palette: str = Form("bright"),
    settings_alpha: float = Form(0.4),
    settings_max_scatter: int = Form(2000),
    settings_max_predictors: int = Form(200),
    settings_max_correlation: float = Form(0.99),
    settings_max_search: int = Form(100),
) -> RedirectResponse:
    """Persist settings to settings.yaml and redirect back to the current page.

    Uses ruamel.yaml to preserve comments in the file.
    After saving, redirects to the Referer (or /ui/summary) so the fresh page
    load picks up the new theme stylesheet and setting values.
    """
    from pathlib import Path
    from ruamel.yaml import YAML

    from src.core.config.settings import Settings

    _VALID_THEMES = {"default", "dark", "cool", "high-contrast", "navy"}
    if settings_theme not in _VALID_THEMES:
        settings_theme = "default"

    settings = Settings()
    settings_path = settings.config_path

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False

    try:
        with open(settings_path, "r") as fh:
            config = yaml.load(fh) or {}

        # Ensure nested structure
        config.setdefault("gui", {})
        config["gui"].setdefault("overview", {})
        config["gui"].setdefault("distribution", {})
        config["gui"].setdefault("explore", {})
        config.setdefault("profiling", {})

        config["gui"]["theme"] = settings_theme
        config["gui"]["overview"]["recent_runs_count"] = settings_recent_count
        config["gui"]["distribution"]["divider_color"] = settings_divider_color
        config["gui"]["distribution"]["fast_color"] = settings_fast_color
        config["gui"]["distribution"]["slow_color"] = settings_slow_color
        config["gui"]["distribution"]["palette"] = settings_palette
        config["gui"]["distribution"]["alpha"] = round(float(settings_alpha), 3)
        config["gui"]["explore"]["max_scatter_points"] = settings_max_scatter
        config["profiling"]["max_predictors"] = settings_max_predictors
        config["profiling"]["max_correlation"] = round(float(settings_max_correlation), 4)
        config["profiling"]["max_search"] = settings_max_search

        with open(settings_path, "w") as fh:
            yaml.dump(config, fh)

        # Invalidate the settings singleton so the next request picks up changes
        Settings.reset()

    except Exception:  # noqa: BLE001
        pass

    # Redirect back so the new theme CSS is loaded
    referer = request.headers.get("referer", "/ui/summary")
    return RedirectResponse(url=referer, status_code=303)
