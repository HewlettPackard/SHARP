# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Layout helpers for the SHARP FastAPI GUI."""

from pathlib import Path

from dominate import document
from dominate.tags import a, body, div, h1, head, header, link, main, meta, p, script, span, title

TAB_LABELS = {
    "summary": "Review",
    "measure": "Measure",
    "explore": "Explore",
    "compare": "Compare",
    "profile": "Profile",
}


_APP_JS_PATH = Path(__file__).resolve().parents[1] / "static" / "app.js"


def _app_js_url() -> str:
    # Read mtime per request so editing app.js busts the browser cache without
    # requiring a server restart.
    try:
        version = str(int(_APP_JS_PATH.stat().st_mtime))
    except OSError:
        version = "0"
    return f"/static/app.js?v={version}"


def render_shell(active_tab: str) -> str:
    """Render the page shell with working tab navigation."""
    label = TAB_LABELS[active_tab]
    doc = document(title=f"SHARP UI | {label}")

    with doc.head:
        meta(charset="utf-8")
        meta(name="viewport", content="width=device-width, initial-scale=1")
        title(f"SHARP UI | {label}")
        link(rel="icon", href="/favicon.ico", type="image/png")
        link(rel="stylesheet", href="/static/app.css")
        script(src="https://unpkg.com/htmx.org@1.9.12")
        script(src=_app_js_url())

    with doc:
        with body():
            with header(cls="shell-header"):
                with div(cls="shell-brand"):
                    a("SHARP", href="/ui/summary", cls="brand-link")
                with div(cls="shell-tabs", role="tablist", aria_label="Primary"):
                    for tab_name, tab_label in TAB_LABELS.items():
                        classes = "shell-tab"
                        if tab_name == active_tab:
                            classes += " is-active"
                        a(tab_label, href=f"/ui/{tab_name}", cls=classes)

            with main(cls="shell-main"):
                with div(cls="shell-panel"):
                    h1(label)

    return str(doc)


def render_shell_with_content(active_tab: str, content_html: str) -> str:
    """Render the page shell with caller-supplied HTML as the main body."""
    from src.core.config.settings import Settings
    theme = Settings().get("gui.theme", "default")
    # Fall back to default for unknown theme names
    _VALID_THEMES = {"default", "dark", "cool", "high-contrast", "navy"}
    if theme not in _VALID_THEMES:
        theme = "default"

    label = TAB_LABELS.get(active_tab, active_tab.title())
    doc = document(title=f"SHARP UI | {label}")

    with doc.head:
        meta(charset="utf-8")
        meta(name="viewport", content="width=device-width, initial-scale=1")
        title(f"SHARP UI | {label}")
        link(rel="icon", href="/favicon.ico", type="image/png")
        link(rel="stylesheet", href="/static/app.css")
        link(rel="stylesheet", href=f"/static/themes/{theme}.css")
        link(
            rel="stylesheet",
            href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css",
        )
        link(
            rel="stylesheet",
            href="https://cdn.jsdelivr.net/npm/tom-select@2.4.3/dist/css/tom-select.css",
        )
        link(
            rel="stylesheet",
            href="https://cdn.jsdelivr.net/npm/nouislider@15.8.1/dist/nouislider.min.css",
        )
        script(src="https://unpkg.com/htmx.org@1.9.12")
        script(src="https://cdn.jsdelivr.net/npm/tom-select@2.4.3/dist/js/tom-select.complete.min.js")
        script(src="https://cdn.jsdelivr.net/npm/nouislider@15.8.1/dist/nouislider.min.js")
        script(src=_app_js_url(), defer=True)

    with doc:
        with body():
            with header(cls="shell-header"):
                with div(cls="shell-brand"):
                    with a(href="/ui/summary", cls="brand-link", title="SHARP"):
                        from dominate.tags import img
                        img(src="/static/sharp.png", height="30", width="90", alt="SHARP")
                with div(cls="shell-tabs", role="tablist", aria_label="Primary"):
                    for tab_name, tab_label in TAB_LABELS.items():
                        classes = "shell-tab"
                        if tab_name == active_tab:
                            classes += " is-active"
                        a(tab_label, href=f"/ui/{tab_name}", cls=classes)
                with div(cls="shell-nav-end"):
                    a(
                        span(cls="bi bi-gear"),
                        href="#",
                        cls="settings-btn",
                        title="Settings",
                        id="settings_btn",
                        **{
                            "hx-get": "/ui/settings/modal",
                            "hx-target": "#settings-modal-root",
                            "hx-swap": "innerHTML",
                        },
                    )

            # Settings modal is fetched into this root element by the gear button
            div(id="settings-modal-root")

            with main(cls="shell-main") as _main:
                _main += raw_html(content_html)

    return str(doc)


def raw_html(html: str):  # noqa: ANN001
    """Wrap a pre-rendered HTML string for dominate insertion."""
    from dominate.util import raw
    return raw(html)