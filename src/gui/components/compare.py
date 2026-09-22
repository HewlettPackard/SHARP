# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""dominate components for the Compare page."""

from typing import Any

from dominate.util import raw
from dominate.tags import (
    div,
    form,
    h2,
    h3,
    h5,
    img,
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


def compare_page(data: dict[str, Any]) -> str:
    """Render the full Compare page HTML."""
    from .layout import render_shell_with_content

    content = div(cls="compare-root")
    with content:
        if data.get("notice"):
            div(str(data["notice"]), cls="notice-banner")
        if data.get("error"):
            div(str(data["error"]), cls="error-banner")

        with section(cls="compare-controls"):
            h2("Compare", cls="section-title")
            with form(action="/ui/compare", method="get", cls="compare-form", id="compare-form"):
                # ── 3-column stacked controls ──────────────────────────────
                with div(cls="compare-cols"):
                    # Column 1: Baseline
                    with div(cls="compare-col"):
                        h5("Baseline run", cls="compare-col-title")
                        with div(cls="compare-cell"):
                            label("Experiment", _for="baseline_experiment", cls="field-label")
                            with select(id="baseline_experiment", name="baseline_experiment", cls="field-input"):
                                option("(select experiment)", value="")
                                selected_baseline_exp = str(data.get("baseline_experiment") or "")
                                for experiment in data.get("experiments", []):
                                    option(experiment, value=experiment, selected=experiment == selected_baseline_exp)
                        with div(cls="compare-cell"):
                            label("Task", _for="baseline_csv", cls="field-label")
                            with select(id="baseline_csv", name="baseline_csv", cls="field-input tomselect-single"):
                                option("(select task)", value="")
                                selected_baseline_csv = str(data.get("baseline_csv") or "")
                                for task in data.get("baseline_tasks", []):
                                    option(task["label"], value=task["csv_path"], selected=task["csv_path"] == selected_baseline_csv)
                        baseline_rows = data.get("baseline_rows")
                        if baseline_rows is not None:
                            p(f"✓ Loaded {baseline_rows} rows", cls="compare-status")

                    # Column 2: Treatment
                    with div(cls="compare-col"):
                        h5("Treatment run", cls="compare-col-title")
                        with div(cls="compare-cell"):
                            label("Experiment", _for="treatment_experiment", cls="field-label")
                            with select(id="treatment_experiment", name="treatment_experiment", cls="field-input"):
                                option("(select experiment)", value="")
                                selected_treatment_exp = str(data.get("treatment_experiment") or "")
                                for experiment in data.get("experiments", []):
                                    option(experiment, value=experiment, selected=experiment == selected_treatment_exp)
                        with div(cls="compare-cell"):
                            label("Task", _for="treatment_csv", cls="field-label")
                            with select(id="treatment_csv", name="treatment_csv", cls="field-input tomselect-single"):
                                option("(select task)", value="")
                                selected_treatment_csv = str(data.get("treatment_csv") or "")
                                for task in data.get("treatment_tasks", []):
                                    option(task["label"], value=task["csv_path"], selected=task["csv_path"] == selected_treatment_csv)
                        treatment_rows = data.get("treatment_rows")
                        if treatment_rows is not None:
                            p(f"✓ Loaded {treatment_rows} rows", cls="compare-status")

                    # Column 3: Metric + filter
                    with div(cls="compare-col"):
                        with div(cls="compare-cell"):
                            label("Metric to visualize", _for="metric", cls="field-label")
                            with select(
                                id="metric",
                                name="metric",
                                cls="field-input tomselect-single",
                                data_search_url="/ui/explore/metrics",
                                data_csv_path=str(data.get("baseline_csv") or ""),
                            ):
                                selected_metric = str(data.get("metric") or "")
                                if selected_metric and selected_metric not in data.get("metrics", []):
                                    option(selected_metric, value=selected_metric, selected=True)
                                if data.get("metrics"):
                                    for metric_name in data.get("metrics", []):
                                        option(metric_name, value=metric_name, selected=metric_name == selected_metric)
                                else:
                                    option("(select tasks first)", value="")

                        with div(cls="compare-cell compare-cell-filter-row"):
                            with div(cls="compare-filter-metric-wrap"):
                                label("Metric to Filter", _for="filter_metric", cls="field-label")
                                with select(
                                    id="filter_metric",
                                    name="filter_metric",
                                    cls="field-input tomselect-single",
                                    data_search_url="/ui/profile/filter-metrics",
                                    data_csv_path=str(data.get("baseline_csv") or ""),
                                ):
                                    option("(none)", value="")
                                    selected_filter_metric = str(data.get("filter_metric") or "")
                                    if selected_filter_metric and selected_filter_metric not in data.get("filter_metrics", []):
                                        option(selected_filter_metric, value=selected_filter_metric, selected=True)
                                    for m in data.get("filter_metrics", []):
                                        option(m, value=m, selected=m == selected_filter_metric)

                            with div(cls="compare-cell-filter-value"):
                                label("Filter value", cls="field-label")
                                filter_kind = str(data.get("filter_kind") or "none")
                                if filter_kind == "categorical":
                                    selected_values = set(str(v) for v in data.get("filter_values", []))
                                    with select(
                                        id="filter_values_select",
                                        name="filter_values",
                                        multiple=True,
                                        cls="field-input tomselect-multi",
                                        placeholder="Select values...",
                                    ):
                                        for value in data.get("filter_options", []):
                                            option(value, value=value, selected=(value in selected_values))
                                elif filter_kind in {"numeric", "time"}:
                                    min_bound_num = data.get("filter_min_bound_num")
                                    max_bound_num = data.get("filter_max_bound_num")
                                    min_val_num = data.get("filter_min_value_num")
                                    max_val_num = data.get("filter_max_value_num")
                                    is_integer = bool(data.get("filter_is_integer"))
                                    if min_bound_num is not None and max_bound_num is not None:
                                        cur_min = float(min_val_num) if min_val_num is not None else float(min_bound_num)
                                        cur_max = float(max_val_num) if max_val_num is not None else float(max_bound_num)
                                        div(
                                            id="filter-noui-slider",
                                            cls="noui-slider-target",
                                            data_min=str(min_bound_num),
                                            data_max=str(max_bound_num),
                                            data_start_min=str(cur_min),
                                            data_start_max=str(cur_max),
                                            data_kind=filter_kind,
                                            data_is_integer="1" if is_integer else "0",
                                            data_is_timestamp="1" if data.get("filter_is_timestamp_like") else "0",
                                        )
                                        with div(cls="noui-labels"):
                                            span("", id="filter_min_display")
                                            span("", id="filter_max_display")
                                        input_(type="hidden", id="filter_min", name="filter_min", value=str(data.get("filter_min") or ""))
                                        input_(type="hidden", id="filter_max", name="filter_max", value=str(data.get("filter_max") or ""))
                                    else:
                                        p("Choose a filter metric to configure filtering.", cls="muted")
                                else:
                                    p("Choose a filter metric to configure filtering.", cls="muted")

        # ── Results ────────────────────────────────────────────────────────
        with div(cls="compare-grid"):
            # Left: plots + narrative
            with div(cls="compare-main-col"):
                density_url = data.get("density_url")
                ecdf_url = data.get("ecdf_url")
                if density_url or ecdf_url:
                    with div(cls="compare-plots-row"):
                        if density_url:
                            with div(cls="result-card"):
                                h3("Density", cls="result-title")
                                img(src=str(density_url), cls="compare-plot-img", alt="Density comparison")
                        if ecdf_url:
                            with div(cls="result-card"):
                                h3("ECDF", cls="result-title")
                                img(src=str(ecdf_url), cls="compare-plot-img", alt="ECDF comparison")
                else:
                    with div(cls="result-card"):
                        p("Select baseline and treatment tasks, then select a metric.", cls="muted")

                with div(cls="result-card"):
                    h3("Narrative", cls="result-title")
                    narrative = data.get("narrative")
                    if narrative:
                        with div(cls="compare-narrative"):
                            raw(narrative)
                    else:
                        p("No narrative yet.", cls="muted")

            # Right: 5-column comparison table
            with div(cls="compare-side-col"):
                with div(cls="result-card"):
                    h3("Comparison summary", cls="result-title")
                    rows = list(data.get("summary_rows") or [])
                    if rows:
                        with div(cls="compare-table-wrap"):
                            with table(cls="compare-table"):
                                with thead():
                                    with tr():
                                        th("Statistic")
                                        th("Baseline")
                                        th("Treatment")
                                        th("% Change")
                                        th("P-value")
                                with tbody():
                                    for row in rows:
                                        with tr():
                                            td(str(row["stat"]))
                                            td(str(row["baseline"]))
                                            td(str(row["treatment"]))
                                            td(str(row["pct_change"]))
                                            td(str(row["p_value"]))
                    else:
                        p("Select baseline and treatment tasks, then select a metric.", cls="muted")

        with div(cls="result-card compare-metadata-card"):
            h3("Metadata comparison", cls="result-title")
            pre(str(data.get("metadata_diff") or "No metadata diff available for current selection."), cls="result-pre")

    return render_shell_with_content("compare", str(content))
