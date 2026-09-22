# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""dominate components for the Explore page."""

from typing import Any

from dominate.tags import (
    div,
    form,
    h2,
    h3,
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


def explore_page(data: dict[str, Any]) -> str:
    """Render the full Explore page HTML."""
    from .layout import render_shell_with_content

    content = div(cls="explore-root")
    with content:
        if data.get("notice"):
            div(str(data["notice"]), cls="notice-banner")
        if data.get("error"):
            div(str(data["error"]), cls="error-banner")

        with section(cls="explore-controls"):
            h2("Explore", cls="section-title")
            with form(action="/ui/explore", method="get", cls="explore-form", id="explore-form"):
                with div(cls="explore-row"):
                    with div(cls="explore-cell"):
                        label("Experiment", _for="experiment", cls="field-label")
                        with select(id="experiment", name="experiment", cls="field-input"):
                            option("(select experiment)", value="")
                            selected_exp = str(data.get("experiment") or "")
                            for experiment in data.get("experiments", []):
                                option(experiment, value=experiment, selected=experiment == selected_exp)

                    with div(cls="explore-cell explore-cell-task"):
                        label("Task", _for="csv_path", cls="field-label")
                        with select(id="csv_path", name="csv_path", cls="field-input"):
                            option("(select task)", value="")
                            selected_csv = str(data.get("csv_path") or "")
                            for task in data.get("tasks", []):
                                option(task["label"], value=task["value"], selected=task["value"] == selected_csv)

                    with div(cls="explore-cell"):
                        label("Metric to visualize", _for="metric", cls="field-label")
                        with select(
                            id="metric",
                            name="metric",
                            cls="field-input tomselect-single",
                            data_search_url="/ui/explore/metrics",
                            data_csv_path=str(data.get("csv_path") or ""),
                        ):
                            selected_metric = str(data.get("metric") or "")
                            if selected_metric and selected_metric not in data.get("metrics", []):
                                option(selected_metric, value=selected_metric, selected=True)
                            for metric in data.get("metrics", []):
                                option(metric, value=metric, selected=metric == selected_metric)

                    with div(cls="explore-cell"):
                        label("Metric to Filter", _for="filter_metric", cls="field-label")
                        with select(
                            id="filter_metric",
                            name="filter_metric",
                            cls="field-input tomselect-single",
                            data_search_url="/ui/profile/filter-metrics",
                            data_csv_path=str(data.get("csv_path") or ""),
                        ):
                            option("(none)", value="")
                            selected_filter_metric = str(data.get("filter_metric") or "")
                            if selected_filter_metric and selected_filter_metric not in data.get("filter_metrics", []):
                                option(selected_filter_metric, value=selected_filter_metric, selected=True)
                            for metric in data.get("filter_metrics", []):
                                option(metric, value=metric, selected=metric == selected_filter_metric)

                    with div(cls="explore-cell explore-cell-filter-value"):
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

                                # noUiSlider target div with data attributes
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

                    with div(cls="explore-cell"):
                        label("Metrics to compare", cls="field-label")
                        selected_compare = set(str(v) for v in data.get("selected_compare_metrics", []))
                        with select(
                            id="compare_metrics",
                            name="compare_metrics",
                            multiple=True,
                            cls="field-input tomselect-multi",
                            placeholder="Type to search metrics...",
                        ):
                            for m in data.get("compare_metrics", []):
                                option(m, value=m, selected=(m in selected_compare))

        with div(cls="explore-grid"):
            with div(cls="explore-main-col"):
                with div(cls="result-card"):
                    h3("Distribution plot", cls="result-title")
                    plot_url = str(data.get("plot_url") or "")
                    if plot_url:
                        with div(cls="explore-plot-wrap"):
                            img(src=plot_url, alt="Distribution plot", cls="explore-plot-image")
                    else:
                        p("Select experiment/task/metric to see the distribution plot.", cls="muted")

                with div(cls="result-card"):
                    h3("Distribution characteristics", cls="result-title")
                    pre(str(data.get("narrative") or "No characterization yet."), cls="result-pre explore-narrative")

            with div(cls="explore-side-col"):
                with div(cls="result-card"):
                    h3("Summary statistics", cls="result-title")
                    rows = list(data.get("summary_rows") or [])
                    if rows:
                        with div(cls="explore-summary-wrap"):
                            with table(cls="explore-summary-table"):
                                with thead():
                                    with tr():
                                        th("Statistic")
                                        th("Value")
                                with tbody():
                                    for row in rows:
                                        with tr():
                                            td(str(row["stat"]))
                                            td(str(row["value"]))
                    else:
                        p("Select experiment/task/metric to see summary stats.", cls="muted")

        with div(cls="result-card explore-pairwise-card"):
            h3("Pairwise comparisons", cls="result-title")
            pair_url = str(data.get("pair_plot_url") or "")
            if pair_url:
                with div(cls="explore-plot-wrap"):
                    n_metrics = int(data.get("n_compare_metrics") or 2)
                    img(
                        src=pair_url,
                        alt="Pairwise comparisons",
                        cls="explore-plot-image explore-pairwise-image",
                        data_n_metrics=str(n_metrics),
                    )
            else:
                p("Select one or more metrics in 'Metrics to compare' to see pairwise distributions/correlations.", cls="muted")

    return render_shell_with_content("explore", str(content))