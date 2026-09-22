"""
Settings modal UI utilities for SHARP GUI.

Provides render_settings_modal() which returns a self-contained <dialog>
fragment.  It is served by GET /ui/settings/modal (HTMX) and submitted
via POST /ui/settings/save.

© Copyright 2025--2026 Hewlett Packard Enterprise Development LP
"""

import dominate.tags as t
from dominate.dom_tag import dom_tag
from dominate.util import raw

from src.core.config.settings import Settings

# <dialog> is not in dominate.tags — define it locally (same pattern as profile.py)
class _dialog(dom_tag):  # noqa: N801
    tagname = "dialog"


# Ordered list of (value, label, accent_hex) for the theme picker
_THEMES: list[tuple[str, str, str]] = [
    ("default",       "Default (Warm Parchment)", "#0f766e"),
    ("dark",          "Dark",                     "#34d399"),
    ("cool",          "Cool (Blue)",               "#3b82f6"),
    ("navy",          "Navy / Gold",               "#f5a623"),
    ("high-contrast", "High Contrast",             "#0050e6"),
]


def render_settings_modal() -> str:
    """Return a <dialog> fragment containing the settings form.

    The dialog uses the existing profile-modal CSS classes and is opened
    programmatically via showModal() after being swapped into
    #settings-modal-root by HTMX.
    """
    settings = Settings()

    dialog = _dialog(
        id="settings-modal",
        cls="profile-modal settings-modal",
    )

    with dialog:
        # ── Header ──────────────────────────────────────────────────────────
        with t.div(cls="profile-modal-header"):
            t.h3("Settings", cls="profile-modal-title")
            t.button(
                raw("&times;"),
                type="button",
                cls="profile-modal-close",
                **{"data-close-modal": "settings-modal"},
            )

        # ── Body / form ──────────────────────────────────────────────────────
        with t.div(cls="profile-modal-body"):
            with t.form(
                id="settings-form",
                action="/ui/settings/save",
                method="post",
                cls="settings-form",
            ):
                # ── Theme ────────────────────────────────────────────────────
                t.label("Theme", _for="settings_theme", cls="field-label")
                with t.div(cls="settings-theme-grid"):
                    current_theme = settings.get("gui.theme", "default")
                    for val, label, accent in _THEMES:
                        checked = (val == current_theme)
                        radio_id = f"theme-{val}"
                        with t.label(
                            _for=radio_id,
                            cls="settings-theme-card" + (" is-selected" if checked else ""),
                        ):
                            t.input_(
                                type="radio",
                                id=radio_id,
                                name="settings_theme",
                                value=val,
                                checked=checked or None,
                                cls="settings-theme-radio",
                            )
                            t.span(cls="settings-theme-swatch", style=f"background:{accent}")
                            t.span(label, cls="settings-theme-label")

                # ── Overview ─────────────────────────────────────────────────
                t.h5("Overview", cls="settings-section-heading")
                with t.div(cls="field-row"):
                    with t.div():
                        t.label("Recent Experiments", _for="settings_recent_count", cls="field-label")
                        t.input_(
                            type="number",
                            id="settings_recent_count",
                            name="settings_recent_count",
                            value=str(settings.get("gui.overview.recent_runs_count", 25)),
                            min="1", max="100",
                            cls="field-input",
                        )

                # ── Distribution plot colours ─────────────────────────────────
                t.h5("Distribution Plot Colours", cls="settings-section-heading")
                with t.div(cls="field-row field-row-3"):
                    for field_id, label_text, key, default in [
                        ("settings_divider_color", "Cutoff Line", "gui.distribution.divider_color", "#1f77b4"),
                        ("settings_fast_color",    "Fast/Better", "gui.distribution.fast_color",    "#a1e736"),
                        ("settings_slow_color",    "Slow/Worse",  "gui.distribution.slow_color",    "#dd560e"),
                    ]:
                        with t.div():
                            t.label(label_text, _for=field_id, cls="field-label")
                            t.input_(
                                type="color",
                                id=field_id,
                                name=field_id,
                                value=settings.get(key, default),
                                cls="field-input settings-color-input",
                            )

                t.label("Colour Palette (multi-group)", _for="settings_palette", cls="field-label")
                with t.select(
                    id="settings_palette",
                    name="settings_palette",
                    cls="field-input",
                ):
                    current_palette = settings.get("gui.distribution.palette", "bright")
                    for val, label_text in [
                        ("bright",     "Bright"),
                        ("tab10",      "Tab10"),
                        ("deep",       "Deep"),
                        ("muted",      "Muted"),
                        ("pastel",     "Pastel"),
                        ("dark",       "Dark"),
                        ("colorblind", "Colorblind"),
                        ("viridis",    "Viridis"),
                        ("Set2",       "Set2"),
                        ("Set3",       "Set3"),
                    ]:
                        t.option(
                            label_text,
                            value=val,
                            selected=(val == current_palette) or None,
                        )

                # ── Visualisation ─────────────────────────────────────────────
                t.h5("Visualisation", cls="settings-section-heading")
                with t.div(cls="field-row"):
                    with t.div():
                        t.label("Scatter Transparency (0–1)", _for="settings_alpha", cls="field-label")
                        t.input_(
                            type="number",
                            id="settings_alpha",
                            name="settings_alpha",
                            value=str(settings.get("gui.distribution.alpha", 0.4)),
                            min="0", max="1", step="0.05",
                            cls="field-input",
                        )
                    with t.div():
                        t.label("Max Scatter Points", _for="settings_max_scatter", cls="field-label")
                        t.input_(
                            type="number",
                            id="settings_max_scatter",
                            name="settings_max_scatter",
                            value=str(settings.get("gui.explore.max_scatter_points", 2000)),
                            min="100", max="50000", step="100",
                            cls="field-input",
                        )

                # ── Profiling ─────────────────────────────────────────────────
                t.h5("Profiling", cls="settings-section-heading")
                with t.div(cls="field-row field-row-3"):
                    for field_id, label_text, key, default, step in [
                        ("settings_max_predictors",  "Max Predictors",     "profiling.max_predictors",  200,  "1"),
                        ("settings_max_correlation", "Max Correlation",    "profiling.max_correlation", 0.99, "0.01"),
                        ("settings_max_search",      "Max Search Iters",   "profiling.max_search",      100,  "1"),
                    ]:
                        with t.div():
                            t.label(label_text, _for=field_id, cls="field-label")
                            t.input_(
                                type="number",
                                id=field_id,
                                name=field_id,
                                value=str(settings.get(key, default)),
                                step=step,
                                cls="field-input",
                            )

        # ── Footer ───────────────────────────────────────────────────────────
        with t.div(cls="profile-modal-footer settings-modal-footer"):
            t.button(
                "Cancel",
                type="button",
                cls="btn btn-secondary",
                **{"data-close-modal": "settings-modal"},
            )
            t.button(
                "Save & Reload",
                type="submit",
                form="settings-form",
                cls="btn btn-primary",
            )

    return str(dialog)

