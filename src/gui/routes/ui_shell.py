# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Fallback shell route for the SHARP GUI."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..components.layout import TAB_LABELS, render_shell

router = APIRouter(tags=["ui"])


@router.get("/ui/{tab_name}", response_class=HTMLResponse)
def ui_tab(tab_name: str) -> str:
    """Render the shell for an unimplemented top-level tab."""
    normalized = tab_name.lower()
    if normalized not in TAB_LABELS:
        normalized = "summary"
    return render_shell(normalized)