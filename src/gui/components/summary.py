# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""dominate components for the Summary page."""

from typing import Any
from urllib.parse import quote_plus

from dominate.svg import svg
from dominate.tags import (
    a, button, caption, datalist, div, form, h2, h3, input_, label, option, p, section,
    span, table, tbody, td, th, thead, tr,
)
from dominate.util import raw


# ── helpers ─────────────────────────────────────────────────────────────────


def _icon(path_d: str, viewbox: str = "0 0 16 16") -> svg:
    """Inline SVG icon."""
    el = svg(
        xmlns="http://www.w3.org/2000/svg",
        width="1.3em",
        height="1.3em",
        viewBox=viewbox,
        fill="currentColor",
        aria_hidden="true",
    )
    el.add(raw(f'<path d="{path_d}"/>'))
    return el


def _chevron_right() -> svg:
    return _icon("M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z")


def _rocket() -> svg:
    return _icon(
        "M9.752 6.193c.599.6 1.73.437 2.528-.362.798-.799.96-1.932.362-2.531-.599-.6-1.73-.438-2.528.361-.798.8-.96 1.933-.362 2.532z"
        "M15.811 3.312c-.363 1.534-1.334 3.626-3.64 6.218l-.24 2.408a2.56 2.56 0 0 1-.732 1.526L8.817 15.85a.51.51 0 0 1-.867-.434l.746-3.WITH"
        "M6.444 11.316c-1.38 2.686-3.357 3.33-4.163 3.504C1.8 14.97 1 15.03.96 15.03c-.07 0-.11-.03-.14-.085a.27.27 0 0 1-.037-.183l.001-.005"
    )


# ── KPI card ────────────────────────────────────────────────────────────────


def kpi_card(label: str, value: str, icon_path: str, accent: str = "var(--accent)") -> div:
    """A single KPI metric tile."""
    card = div(cls="kpi-card")
    with card:
        with div(cls="kpi-icon", style=f"color:{accent}"):
            _icon(icon_path)
        with div(cls="kpi-body"):
            p(label, cls="kpi-label")
            h3(value, cls="kpi-value")
    return card


# ── Activity bar chart (pure CSS / SVG, server-rendered) ────────────────────


def activity_chart(activity: list[dict[str, Any]]) -> div:
    """Render a 30-day bar chart as inline SVG."""
    max_count = max((item["count"] for item in activity), default=1) or 1
    bar_w = 9
    gap = 3
    h = 80
    total_w = len(activity) * (bar_w + gap) - gap + 24  # + left margin

    el = div(cls="activity-chart-wrap")
    with el:
        p("Activity – last 30 days", cls="chart-title")
        s = svg(
            xmlns="http://www.w3.org/2000/svg",
            width="100%",
            viewBox=f"0 0 {total_w} {h + 24}",
            preserveAspectRatio="none",
            cls="activity-svg",
        )
        with s:
            for i, item in enumerate(activity):
                x = 12 + i * (bar_w + gap)
                bar_h = max(2, int(item["count"] / max_count * h))
                y = h - bar_h
                color = "var(--accent)" if item["count"] else "var(--line)"
                raw(
                    f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}"'
                    f' rx="2" fill="{color}" opacity="0.85">'
                    f'<title>{item["label"]}: {item["count"]} runs</title></rect>'
                )
            # x-axis labels every 5 bars
            for i, item in enumerate(activity):
                if i % 5 == 0:
                    x = 12 + i * (bar_w + gap) + bar_w // 2
                    raw(
                        f'<text x="{x}" y="{h + 18}" text-anchor="middle"'
                        f' font-size="8" fill="var(--muted)">{item["label"]}</text>'
                    )
    return el


# ── Recent runs table ────────────────────────────────────────────────────────


def recent_runs_table(runs: list[dict[str, Any]]) -> div:
    """Render the recent-runs table with Rerun and Explore links."""
    wrap = div(cls="runs-table-wrap")
    if not runs:
        with wrap:
            p("No recent experiments found.", cls="muted")
        return wrap

    with wrap:
        t = table(cls="runs-table")
        with t:
            caption("Recent experiment runs", cls="sr-only")
            with thead():
                with tr():
                    for col in ("Experiment", "Task", "Benchmark", "Backend", "Timestamp", "Rows", "", ""):
                        th(col, cls="runs-th")
            with tbody():
                for i, run in enumerate(runs):
                    exp = str(run.get("experiment", ""))
                    task = str(run.get("task", ""))
                    bench = str(run.get("benchmark") or "—")
                    backends_val = run.get("backends")
                    backend_str = ", ".join(backends_val) if backends_val else "local"
                    ts = run["timestamp"].strftime("%Y-%m-%d %H:%M") if run.get("timestamp") else "—"
                    rows_val = str(run["rows"]) if run.get("rows") is not None else "—"
                    desc = str(run.get("description") or "")

                    with tr(cls="runs-row", title=desc):
                        td(exp, cls="runs-td")
                        td(task, cls="runs-td font-mono")
                        td(bench, cls="runs-td")
                        td(backend_str, cls="runs-td")
                        td(ts, cls="runs-td ts")
                        td(rows_val, cls="runs-td num")
                        with td(cls="runs-td icon-cell"):
                            csv_path = str(run.get("csv_path") or "")
                            rerun_href = (
                                f"/ui/measure?rerun_experiment={quote_plus(exp)}"
                                f"&rerun_task={quote_plus(task)}"
                                f"&rerun_csv_path={quote_plus(csv_path)}"
                            )
                            a("↻", href=rerun_href, cls="action-link rerun-link", title="Rerun")
                        with td(cls="runs-td icon-cell"):
                            explore_href = f"/ui/explore?experiment={exp}&task={task}"
                            with a(href=explore_href, cls="action-link explore-link", title="Explore"):
                                raw(
                                    '<svg width="1.3em" height="1.3em" viewBox="0 0 16 16"'
                                    ' fill="currentColor" aria-hidden="true">'
                                    '<rect x="2" y="10" width="2" height="4"/>'
                                    '<rect x="5" y="6" width="2" height="8"/>'
                                    '<rect x="8" y="4" width="2" height="10"/>'
                                    '<rect x="11" y="7" width="2" height="7"/>'
                                    '</svg>'
                                )

    return wrap


# ── Top-level summary page ───────────────────────────────────────────────────


def summary_page(data: dict[str, Any]) -> str:
    """Render the full Summary page HTML."""
    from .layout import render_shell_with_content

    content = div(cls="summary-root")
    with content:
        if data.get("notice"):
            div(str(data["notice"]), cls="notice-banner")
        if data.get("error"):
            div(str(data["error"]), cls="error-banner")

        # KPI row
        with div(cls="kpi-row"):
            kpi_card(
                "Total Runs",
                str(data["total"]),
                "M9.293 1.5l.707.707L5.707 6H13v1H5.707l4.293 4.293-.707.707L4 7l5.293-5.5z",
                accent="var(--accent)",
            )
            kpi_card(
                "Avg. Execution Time",
                data["avg_time"],
                "M8 3.5a.5.5 0 0 0-1 0V9a.5.5 0 0 0 .252.434l3.5 2a.5.5 0 0 0 .496-.868L8 8.71V3.5z"
                "M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16zm7-8A7 7 0 1 1 1 8a7 7 0 0 1 14 0z",
                accent="#0ea5e9",
            )
            activity_chart(data["activity"])

        with section(cls="runs-section"):
            with div(cls="section-header"):
                h2("Recent Experiment Runs", cls="section-title")
                with div(cls="section-actions"):
                    with a(href="/ui/measure", cls="btn btn-primary", id="quick_launch"):
                        span(cls="bi bi-rocket-takeoff")
                        span("Launch New Experiment")
                    with a(
                        href="#",
                        cls="btn btn-secondary",
                        id="upload_experiment_btn",
                    ):
                        span(cls="bi bi-cloud-upload")
                        span("Upload Experiment")

            recent_runs_table(data["recent"])

        with div(id="upload-experiment-modal", cls="modal-shell is-hidden", role="dialog", aria_modal="true"):
            with div(cls="modal-card"):
                h3("Upload Experiment Files", cls="modal-title")
                p("Select or enter an experiment name and upload CSV/MD files.", cls="modal-copy")

                with form(action="/ui/summary/upload", method="post", enctype="multipart/form-data"):
                    label("Experiment Name", _for="upload_experiment_name", cls="modal-label")
                    input_(
                        id="upload_experiment_name",
                        name="upload_experiment_name",
                        list="experiment-options",
                        placeholder="Type experiment name or select existing...",
                        required=True,
                        cls="modal-input",
                    )
                    with datalist(id="experiment-options"):
                        for experiment in data.get("experiments", []):
                            option(value=experiment)

                    label("Upload Files", _for="upload_files", cls="modal-label")
                    input_(
                        id="upload_files",
                        name="upload_files",
                        type="file",
                        multiple=True,
                        accept=".csv,.md",
                        required=True,
                        cls="modal-input",
                    )

                    with div(cls="modal-actions"):
                        with button(type="button", cls="btn btn-success", id="new_experiment_btn"):
                            span("New experiment")
                        with button(type="button", cls="btn btn-secondary", id="upload_cancel"):
                            span("Cancel")
                        with button(type="submit", cls="btn btn-primary", id="upload_confirm"):
                            span("Upload")

        with div(id="new-experiment-modal", cls="modal-shell is-hidden", role="dialog", aria_modal="true"):
            with div(cls="modal-card"):
                h3("Create New Experiment", cls="modal-title")
                p("Enter a name for the new experiment directory.", cls="modal-copy")

                with form(action="/ui/summary/new-experiment", method="post"):
                    label("Experiment Name", _for="new_experiment_name", cls="modal-label")
                    input_(
                        id="new_experiment_name",
                        name="new_experiment_name",
                        placeholder="Enter experiment name...",
                        required=True,
                        cls="modal-input",
                    )
                    with div(cls="modal-actions"):
                        with button(type="button", cls="btn btn-secondary", id="new_experiment_cancel"):
                            span("Cancel")
                        with button(type="submit", cls="btn btn-primary", id="new_experiment_apply"):
                            span("Apply")

    return render_shell_with_content("summary", str(content))
