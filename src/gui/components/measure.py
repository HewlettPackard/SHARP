# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""dominate components for the Measure page."""

from typing import Any
from urllib.parse import quote_plus

from dominate.tags import (
    a,
    button,
    datalist,
    div,
    form,
    h2,
    h3,
    input_,
    label,
    option,
    p,
    pre,
    section,
    select,
    span,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
)


def measure_page(data: dict[str, Any]) -> str:
    """Render the full Measure page HTML."""
    from .layout import render_shell_with_content

    content = div(cls="measure-root")
    with content:
        if data.get("notice"):
            div(str(data["notice"]), cls="notice-banner")
        if data.get("error"):
            error_text = str(data["error"])
            div(error_text, cls="error-banner")
            show_error_modal = "exited with code" in error_text and "Captured stderr/stdout" in error_text
            if show_error_modal:
                with div(
                    id="measure-error-modal",
                    cls="modal-shell is-hidden",
                    role="dialog",
                    aria_modal="true",
                    aria_labelledby="measure-error-title",
                ):
                    with div(cls="modal-card"):
                        h3("Benchmark Execution Failed", id="measure-error-title", cls="modal-title")
                        p(
                            "The benchmark exited with a nonzero status. Captured stderr/stdout is shown below.",
                            cls="modal-copy",
                        )
                        pre(error_text, cls="result-pre measure-error-pre")
                        with div(cls="modal-actions"):
                            button("Close", type="button", id="measure_error_close", cls="btn btn-secondary")

        with div(cls="measure-grid"):
            with section(cls="measure-config"):
                h2("Experiment Configuration", cls="section-title")

                with form(action="/ui/measure/run", method="post", cls="measure-form", id="measure-run-form"):
                    label("Experiment name", _for="experiment", cls="field-label")
                    input_(
                        id="experiment",
                        name="experiment",
                        value=str(data.get("experiment") or data.get("default_experiment") or "misc"),
                        required=True,
                        cls="field-input",
                    )

                    with div(cls="field-row"):
                        with div(cls="field-cell"):
                            label("Benchmark", _for="bench", cls="field-label")
                            input_(
                                id="bench",
                                name="bench",
                                value=str(data.get("bench") or ""),
                                placeholder="e.g. sleep 0.1",
                                list="benchmark-list",
                                required=True,
                                cls="field-input",
                            )
                            with datalist(id="benchmark-list"):
                                for benchmark in data.get("benchmarks", []):
                                    option(value=benchmark)
                        with div(cls="field-cell"):
                            label("Task (optional)", _for="task", cls="field-label")
                            input_(
                                id="task",
                                name="task",
                                value=str(data.get("task") or ""),
                                cls="field-input",
                            )

                    with div(cls="field-row"):
                        with div(cls="field-cell"):
                            label("When to stop?", _for="stopping", cls="field-label")
                            with select(id="stopping", name="stopping", cls="field-input"):
                                for repeater in data.get("repeaters", []):
                                    selected = repeater["key"] == str(data.get("stopping") or "COUNT")
                                    option(
                                        repeater["label"],
                                        value=repeater["key"],
                                        selected=selected,
                                        title=repeater["description"],
                                    )
                        with div(cls="field-cell"):
                            label("Max runs", _for="n", cls="field-label")
                            input_(
                                id="n",
                                name="n",
                                type="number",
                                min="1",
                                value=str(data.get("n") or "1"),
                                cls="field-input",
                            )

                    label("Backends", _for="backend", cls="field-label")
                    selected_backends = set(data.get("backend_selected") or [])
                    with select(id="backend", name="backend", cls="field-input", multiple=True, size="5"):
                        for backend in data.get("backends", []):
                            option(backend, value=backend, selected=backend in selected_backends)

                    with div(cls="field-row field-row-3"):
                        with div(cls="field-cell"):
                            label("Copies", _for="mpl", cls="field-label")
                            input_(
                                id="mpl",
                                name="mpl",
                                type="number",
                                min="1",
                                value=str(data.get("mpl") or "1"),
                                cls="field-input",
                            )
                        with div(cls="field-cell"):
                            label("Start", _for="start", cls="field-label")
                            with select(id="start", name="start", cls="field-input"):
                                start_selected = str(data.get("start") or "as-is")
                                option("as-is", value="as-is", selected=start_selected == "as-is")
                                option("cold", value="cold", selected=start_selected == "cold")
                                option("warm", value="warm", selected=start_selected == "warm")
                        with div(cls="field-cell"):
                            label("Timeout", _for="timeout", cls="field-label")
                            input_(
                                id="timeout",
                                name="timeout",
                                type="number",
                                min="1",
                                value=str(data.get("timeout") or "60"),
                                cls="field-input",
                            )

                    label("Any other arguments to pass along to SHARP?", _for="moreopts", cls="field-label")
                    input_(
                        id="moreopts",
                        name="moreopts",
                        value=str(data.get("moreopts") or ""),
                        cls="field-input",
                    )

                    with div(cls="measure-actions"):
                        with button(type="submit", cls="btn btn-success", id="run_button"):
                            span(cls="bi bi-play-circle")
                            span("Run")

            with section(cls="measure-output"):
                with div(cls="status-strip", id="measure-status-strip"):
                    p("Execution status", cls="status-title")
                    status_copy = str(data.get("notice") or "No run started yet.")
                    p(status_copy, cls="status-copy", id="measure-status-copy")
                    with div(cls="status-progress", id="measure-status-progress", data_mode="indeterminate"):
                        div(cls="status-progress-fill", id="measure-status-progress-fill")

                    if data.get("csv_path"):
                        experiment = str(data.get("experiment") or "")
                        task = str(data.get("task") or "")
                        csv_path = str(data.get("csv_path") or "")
                        with a(
                            "Explore results",
                            href=(
                                f"/ui/explore?experiment={quote_plus(experiment)}"
                                f"&task={quote_plus(task)}"
                                f"&csv_path={quote_plus(csv_path)}"
                            ),
                            cls="status-explore-link",
                        ):
                            span(cls="bi bi-bar-chart-line")

                with div(cls="result-card"):
                    h3("Run Results", cls="result-title")
                    columns = list(data.get("results_columns") or [])
                    rows = list(data.get("results_rows") or [])
                    if columns and rows:
                        with div(cls="measure-results-controls"):
                            input_(
                                id="measure-results-filter",
                                cls="field-input measure-results-filter",
                                type="search",
                                placeholder="Filter rows...",
                            )
                        with div(cls="measure-results-wrap"):
                            with table(cls="measure-results-table", id="measure-results-table"):
                                with thead():
                                    with tr():
                                        for column in columns:
                                            th(str(column), data_sortable="true")
                                with tbody():
                                    for row in rows:
                                        with tr():
                                            for value in row:
                                                td(str(value))
                    else:
                        pre("No results yet. Click Run to start an experiment.", cls="result-pre")

                with div(cls="result-card"):
                    h3("Metadata", cls="result-title")
                    pre(str(data.get("metadata_text") or "Metadata will be displayed here after a completed run."), cls="result-pre")

    return render_shell_with_content("measure", str(content))