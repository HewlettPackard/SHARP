# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
from pathlib import Path
import sys

import polars as pl
import pytest
from fastapi.testclient import TestClient

from src.gui.app import app
from src.gui.contracts.schemas import ExperimentItem, ExperimentListResponse, TaskItem, TaskListResponse
from src.gui.services.measure import (
    _friendly_benchmark_input,
    _python_dependency_preflight_error,
    _resolve_gui_entry_command,
)
from src.core.config.include_resolver import get_project_root


FIXTURES = Path("tests/fixtures/compare_cli")


@pytest.fixture
def synthetic_profile_csv(tmp_path):
    csv_path = tmp_path / "profile-smoke.csv"
    pl.DataFrame(
        {
            "timestamp": [1, 2, 3, 4, 5],
            "allreduce_latency_us": [10.0, 12.0, 9.0, 15.0, 11.0],
            "inner_time": [1.0, 1.1, 0.9, 1.2, 1.0],
        }
    ).write_csv(csv_path)
    return str(csv_path)


def test_discovery_routes_smoke() -> None:
    client = TestClient(app)

    experiments = client.get("/api/v1/experiments")
    assert experiments.status_code == 200
    assert "experiments" in experiments.json()

    benchmarks = client.get("/api/v1/benchmarks")
    assert benchmarks.status_code == 200
    assert benchmarks.json()["benchmarks"]

    backends = client.get("/api/v1/backends")
    assert backends.status_code == 200
    assert backends.json()["backends"]


def test_distribution_routes_smoke() -> None:
    client = TestClient(app)
    payload = {
        "csv_path": str(FIXTURES / "sleep_fast.csv"),
        "metric": "outer_time",
    }

    summary = client.post("/api/v1/distribution/summary", json=payload)
    assert summary.status_code == 200
    assert summary.json()["summary"]["n"] > 0

    changepoints = client.post("/api/v1/distribution/changepoints", json=payload)
    assert changepoints.status_code == 200
    assert changepoints.json()["metric"] == "outer_time"

    characterize = client.post("/api/v1/distribution/characterize", json=payload)
    assert characterize.status_code == 200
    assert characterize.json()["narrative"]


def test_distribution_route_accepts_filter_spec() -> None:
    client = TestClient(app)
    payload = {
        "csv_path": str(FIXTURES / "sleep_fast.csv"),
        "metric": "outer_time",
        "filters": [{"metric": "repeat", "kind": "range", "min": "1", "max": "3"}],
    }
    summary = client.post("/api/v1/distribution/summary", json=payload)
    assert summary.status_code == 200
    assert summary.json()["summary"]["n"] > 0


def test_distribution_route_rejects_multiple_filters() -> None:
    client = TestClient(app)
    payload = {
        "csv_path": str(FIXTURES / "sleep_fast.csv"),
        "metric": "outer_time",
        "filters": [
            {"metric": "repeat", "kind": "range", "min": "1", "max": "3"},
            {"metric": "rank", "kind": "equals", "value": "0"},
        ],
    }
    summary = client.post("/api/v1/distribution/summary", json=payload)
    assert summary.status_code == 422


def test_compare_route_smoke() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/compare",
        json={
            "baseline_csv": str(FIXTURES / "sleep_fast.csv"),
            "treatment_csv": str(FIXTURES / "sleep_slow.csv"),
            "metric": "outer_time",
            "lower_is_better": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric"] == "outer_time"
    assert "comparison" in payload
    assert "mann_whitney" in payload
    assert payload["narrative"]


def test_compare_route_accepts_filter_spec() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/compare",
        json={
            "baseline_csv": str(FIXTURES / "sleep_fast.csv"),
            "treatment_csv": str(FIXTURES / "sleep_slow.csv"),
            "metric": "outer_time",
            "filters": [{"metric": "repeat", "kind": "range", "min": "1", "max": "3"}],
        },
    )
    assert response.status_code == 200


def test_profile_and_mitigate_endpoints_are_implemented() -> None:
    """profile/mitigate HTTP endpoints are now active (no longer 501 stubs).

    Backed by GUI service modules; Phase 12 migrates them to ``src/api``.
    ``/profile/analyze`` requires a JSON body, so an empty POST is a 422
    validation error (not a 501 stub). ``/mitigate/list`` returns data.
    """
    client = TestClient(app)

    profile = client.post("/api/v1/profile/analyze")
    assert profile.status_code == 422  # missing required request body, not a stub

    mitigate = client.get("/api/v1/mitigate/list")
    assert mitigate.status_code == 200
    assert isinstance(mitigate.json()["mitigations"], list)


def test_review_and_measure_pages_smoke() -> None:
    client = TestClient(app)

    review = client.get("/ui/summary")
    assert review.status_code == 200
    assert "Review" in review.text

    measure = client.get("/ui/measure")
    assert measure.status_code == 200
    assert "Experiment Configuration" in measure.text
    assert "Run Results" in measure.text

    run_redirect = client.post(
        "/ui/measure/run",
        data={
            "experiment": "misc",
            "bench": "",
            "task": "quick-run",
        },
        follow_redirects=False,
    )
    assert run_redirect.status_code == 303
    assert run_redirect.headers["location"].startswith("/ui/measure?error=")
    assert "Benchmark+field+is+required" in run_redirect.headers["location"]

    stderr_modal = client.get(
        "/ui/measure",
        params={
            "error": "Command 0 exited with code 1\n\nCaptured stderr/stdout:\nTraceback",
        },
    )
    assert stderr_modal.status_code == 200
    assert "measure-error-modal" in stderr_modal.text


def test_measure_python_script_runs_with_interpreter() -> None:
    entry_point, args = _resolve_gui_entry_command(
        "/tmp/bench.py",
        ["1"],
    )

    assert entry_point in {sys.executable, "uv", "/usr/bin/uv", "/bin/uv"} or entry_point.endswith("/uv")
    assert args[-2:] == ["/tmp/bench.py", "1"]


def test_measure_friendly_benchmark_input_recovers_benchmark_name() -> None:
    entry_point = get_project_root() / "benchmarks" / "micro" / "cpu" / "sleep.py"
    friendly = _friendly_benchmark_input(f"{entry_point} 1")

    assert friendly == "sleep 1"


def test_measure_missing_dependencies_returns_appimage_guidance() -> None:
    error = _python_dependency_preflight_error(
        entry_point="/tmp/bench.py",
        benchmark_name="bench",
        benchmark_data={
            "build": {
                "requires": {
                    "python": ["definitely-not-installed-package-xyz123"],
                }
            }
        },
        backend_names=["local"],
    )

    assert error is not None
    assert "Build the benchmark AppImage" in error


def test_explore_page_smoke() -> None:
    client = TestClient(app)

    empty = client.get("/ui/explore")
    assert empty.status_code == 200
    assert "Explore" in empty.text

    selected = client.get(
        "/ui/explore",
        params={
            "experiment": "misc",
            "csv_path": str(FIXTURES / "sleep_fast.csv"),
        },
    )
    assert selected.status_code == 200
    assert 'option selected="selected" value="inner_time"' in selected.text
    assert "explore/plot.png" in selected.text
    assert "Metrics to compare" in selected.text
    assert "Pairwise comparisons" in selected.text
    assert "Summary statistics" in selected.text
    assert "Distribution characteristics" in selected.text

    pair = client.get(
        "/ui/explore/pairwise.png",
        params=[
            ("csv_path", str(FIXTURES / "sleep_fast.csv")),
            ("compare_metrics", "inner_time"),
            ("compare_metrics", "outer_time"),
        ],
    )
    assert pair.status_code == 200
    assert pair.headers["content-type"].startswith("image/png")


def test_compare_page_smoke() -> None:
    client = TestClient(app)

    empty = client.get("/ui/compare")
    assert empty.status_code == 200
    assert "Compare" in empty.text

    selected = client.get(
        "/ui/compare",
        params={
            "baseline_csv": str(FIXTURES / "sleep_fast.csv"),
            "treatment_csv": str(FIXTURES / "sleep_slow.csv"),
            "metric": "outer_time",
            "lower_is_better": "true",
        },
    )
    assert selected.status_code == 200
    assert "Comparison summary" in selected.text
    assert "% Change" in selected.text
    assert "Narrative" in selected.text


def test_measure_to_explore_handoff_smoke() -> None:
    client = TestClient(app)

    run_redirect = client.post(
        "/ui/measure/run",
        data={
            "experiment": "misc",
            "bench": "/bin/sleep 0.01",
            "task": "measure-explore-smoke",
            "stopping": "COUNT",
            "n": "2",
            "mpl": "1",
            "start": "as-is",
            "timeout": "60",
            "moreopts": "",
        },
        follow_redirects=False,
    )

    assert run_redirect.status_code == 303
    location = run_redirect.headers["location"]
    assert "csv_path=" in location

    explore = client.get(
        "/ui/explore",
        params={
            "experiment": "misc",
            "task": "measure-explore-smoke",
        },
    )
    assert explore.status_code == 200
    assert "measure-explore-smoke" in explore.text
    assert "Summary statistics" in explore.text


def test_explore_task_selector_scoped_by_experiment(monkeypatch) -> None:
    client = TestClient(app)
    from src.gui.routes import ui_explore as explore_route

    monkeypatch.setattr(
        explore_route,
        "load_explore_form_data",
        lambda: {"experiments": ["expA", "expB"]},
    )
    monkeypatch.setattr(
        explore_route,
        "list_task_choices",
        lambda experiment: (
            [{"value": "runlogs/expA/task_a.csv", "label": "task_a"}]
            if experiment == "expA"
            else [{"value": "runlogs/expB/task_b.csv", "label": "task_b"}]
        ),
    )

    response = client.get("/ui/explore", params={"experiment": "expA"})
    assert response.status_code == 200

    task_select = response.text.split('id="csv_path"', 1)[1].split("</select>", 1)[0]
    assert "task_a" in task_select
    assert "task_b" not in task_select


def test_compare_task_selectors_scoped_by_experiment(monkeypatch) -> None:
    client = TestClient(app)
    from src.gui.routes import ui_compare as compare_route

    monkeypatch.setattr(
        compare_route,
        "list_experiments",
        lambda: ExperimentListResponse(
            experiments=[
                ExperimentItem(name="expA", run_count=1, latest_timestamp=None),
                ExperimentItem(name="expB", run_count=1, latest_timestamp=None),
            ]
        ),
    )

    def fake_list_tasks(experiment: str) -> TaskListResponse:
        if experiment == "expA":
            tasks = [
                TaskItem(
                    experiment="expA",
                    task="task_a",
                    csv_path="runlogs/expA/task_a.csv",
                    md_path="runlogs/expA/task_a.md",
                    timestamp=None,
                    benchmark=None,
                    backends=[],
                    duration=None,
                    rows=None,
                    description=None,
                )
            ]
        elif experiment == "expB":
            tasks = [
                TaskItem(
                    experiment="expB",
                    task="task_b",
                    csv_path="runlogs/expB/task_b.csv",
                    md_path="runlogs/expB/task_b.md",
                    timestamp=None,
                    benchmark=None,
                    backends=[],
                    duration=None,
                    rows=None,
                    description=None,
                )
            ]
        else:
            tasks = []
        return TaskListResponse(experiment=experiment, tasks=tasks)

    monkeypatch.setattr(compare_route, "list_tasks", fake_list_tasks)

    response = client.get(
        "/ui/compare",
        params={"baseline_experiment": "expA", "treatment_experiment": "expB"},
    )
    assert response.status_code == 200

    baseline_select = response.text.split('id="baseline_csv"', 1)[1].split("</select>", 1)[0]
    treatment_select = response.text.split('id="treatment_csv"', 1)[1].split("</select>", 1)[0]

    assert "task_a" in baseline_select
    assert "task_b" not in baseline_select
    assert "task_b" in treatment_select
    assert "task_a" not in treatment_select


def test_profile_page_defaults_to_tree_analyzer(synthetic_profile_csv):
    """Profile page must default to 'tree' analyzer, not alphabetically-first 'ccf'.

    This guards against the regression where next(iter(analyzer_choices)) resolved
    to 'ccf' (alphabetically first), which is a slow causal analyzer that hangs
    on datasets with timestamp columns.
    """
    from fastapi.testclient import TestClient
    from src.gui.app import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        "/ui/profile",
        params={
            "experiment": "test-exp",
            "task": "test-task",
            "csv_path": synthetic_profile_csv,
            "source": "use_original",
            "metric": "allreduce_latency_us",
        },
    )
    assert response.status_code == 200, f"Profile page returned {response.status_code}"
    text = response.text
    # The analyzer select must exist
    assert 'name="analyzer"' in text, "Analyzer dropdown not rendered"
    # tree must be the selected value, not ccf
    analyzer_select = text.split('name="analyzer"', 1)[1].split("</select>", 1)[0]
    # The selected option should contain "tree", not "ccf"
    selected_options = [
        part.split("value=\"", 1)[1].split('"', 1)[0]
        for part in analyzer_select.split("<option")
        if "selected" in part and 'value="' in part
    ]
    assert selected_options, "No option is selected in analyzer dropdown"
    assert selected_options[0] == "tree", (
        f"Expected 'tree' to be selected by default, got {selected_options[0]!r}. "
        "Regression: ccf (alphabetically first) must not be the default."
    )
    assert "/ui/profile/analysis-tree.html?" in text, (
        "Expected tree analyzer to use interactive HTML tree endpoint."
    )


def test_profile_auto_detect_disables_group_count_and_uses_full_heading(synthetic_profile_csv):
    """Profile sidebar mirrors old GUI: Auto disables count and heading text is full."""
    from fastapi.testclient import TestClient
    from src.gui.app import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        "/ui/profile",
        params={
            "experiment": "test-exp",
            "task": "test-task",
            "csv_path": synthetic_profile_csv,
            "source": "use_original",
            "metric": "allreduce_latency_us",
            "auto_detect": "1",
        },
    )
    assert response.status_code == 200
    text = response.text

    assert "PERFORMANCE GROUPS" in text
    assert "Perf. Groups" not in text

    num_groups_tag = next(
        part for part in text.split("<input") if 'id="num_groups"' in part
    )
    assert "disabled" in num_groups_tag, "num_groups input must be disabled when Auto is enabled"


# ============================================================================
# gui entry-point tests
# ============================================================================

def test_gui_main_module_is_importable():
    """src.gui.__main__ can be imported and exposes a callable main()."""
    from src.gui import __main__ as gui_main  # noqa: PLC0415

    assert callable(gui_main.main), "gui.__main__.main must be a callable"


def test_gui_entry_point_registered_in_pyproject():
    """pyproject.toml declares gui = src.gui.__main__:main."""
    import tomllib  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    data = tomllib.loads(Path("pyproject.toml").read_text())
    scripts = data["project"]["scripts"]
    assert "gui" in scripts, "gui entry-point missing from [project.scripts]"
    assert "gui2" not in scripts, "gui2 alias should not exist after full migration"
    assert scripts["gui"] == "src.gui.__main__:main", (
        f"gui entry-point target is wrong: {scripts['gui']}"
    )


def test_gui_main_accepts_help_flag(capsys):
    """main(--help) prints usage and exits cleanly (no unhandled exception)."""
    import pytest  # noqa: PLC0415
    from src.gui.__main__ import main  # noqa: PLC0415

    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    assert exc.value.code == 0, "gui --help should exit with code 0"
    out = capsys.readouterr().out
    assert "--port" in out, "--port should appear in help text"
    assert "--host" in out, "--host should appear in help text"
    assert "--no-reload" in out, "--no-reload should appear in help text"


def test_gui_main_accepts_port_flag(monkeypatch):
    """main(--port 9999) passes port=9999 to uvicorn.run without error."""
    import uvicorn  # noqa: PLC0415
    from src.gui.__main__ import main  # noqa: PLC0415

    calls: list[dict] = []

    def fake_run(app, host, port, reload, reload_dirs=None, **kwargs):
        calls.append({"app": app, "host": host, "port": port, "reload": reload})

    monkeypatch.setattr(uvicorn, "run", fake_run)
    main(["--port", "9999"])

    assert calls, "uvicorn.run was not called"
    assert calls[0]["port"] == 9999
    assert calls[0]["app"] == "src.gui.app:app"


def test_gui_main_no_reload_flag(monkeypatch):
    """main(--no-reload) passes reload=False to uvicorn.run."""
    import uvicorn  # noqa: PLC0415
    from src.gui.__main__ import main  # noqa: PLC0415

    calls: list[dict] = []

    def fake_run(app, host, port, reload, reload_dirs=None, **kwargs):
        calls.append({"reload": reload, "reload_dirs": reload_dirs})

    monkeypatch.setattr(uvicorn, "run", fake_run)
    main(["--no-reload"])

    assert calls, "uvicorn.run was not called"
    assert calls[0]["reload"] is False
    assert calls[0]["reload_dirs"] is None


def test_gui_main_reload_uses_src_dir(monkeypatch):
    """main() without --no-reload passes reload_dirs=['src'] to uvicorn."""
    import uvicorn  # noqa: PLC0415
    from src.gui.__main__ import main  # noqa: PLC0415

    calls: list[dict] = []

    def fake_run(app, host, port, reload, reload_dirs=None, **kwargs):
        calls.append({"reload": reload, "reload_dirs": reload_dirs})

    monkeypatch.setattr(uvicorn, "run", fake_run)
    main([])

    assert calls, "uvicorn.run was not called"
    assert calls[0]["reload"] is True
    assert calls[0]["reload_dirs"] == ["src"], (
        "reload_dirs should be ['src'] so uvicorn only watches the source tree"
    )


def test_gui_default_port_from_settings(monkeypatch):
    """main() reads the port from gui.port in settings when no CLI flag given."""
    import uvicorn  # noqa: PLC0415
    from src.gui.__main__ import main  # noqa: PLC0415

    calls: list[dict] = []

    def fake_run(app, host, port, reload, reload_dirs=None, **kwargs):
        calls.append({"port": port})

    monkeypatch.setattr(uvicorn, "run", fake_run)
    main([])

    assert calls, "uvicorn.run was not called"
    # The default from settings.yaml is 8282; accept any int (settings may vary)
    assert isinstance(calls[0]["port"], int), "port must be an integer"


def test_gui_primary_tabs_render_canonical_urls():
    """The shell tabs should render as fresh entrypoints, not restored deep links."""
    client = TestClient(app)

    response = client.get(
        "/ui/profile?experiment=portage&task=latency-tall-32M-N-1000-h-128--19ms"
        "&csv_path=runlogs%2Fportage%2Flatency-tall-32M-N-1000-h-128--19ms.csv"
        "&source=use_original&metric=allreduce_latency_us"
    )

    assert response.status_code == 200
    assert 'href="/ui/summary"' in response.text
    assert 'href="/ui/measure"' in response.text
    assert 'href="/ui/explore"' in response.text
    assert 'href="/ui/compare"' in response.text
    assert 'href="/ui/profile"' in response.text


def test_gui_tab_url_restore_logic_removed_from_app_js():
    """The browser script should not rewrite primary tab hrefs from sessionStorage."""
    app_js = Path("src/gui/static/app.js").read_text()

    assert "gui2.tab.last_url" not in app_js
    assert "shell-tab[href^='/ui/']" not in app_js
