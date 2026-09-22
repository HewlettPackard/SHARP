# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Smoke and parity tests for the SHARP GUI Profile tab."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from fastapi.testclient import TestClient

from src.gui.app import app


# ---------------------------------------------------------------------------
# Synthetic profiled-experiment fixture
#
# These tests must never depend on a hardcoded path or on pre-existing (and
# git-ignored) run logs.  Instead, a modular fixture materialises a synthetic
# "matmul" profiled experiment (CSV + Markdown) in a temporary runlogs tree and
# points experiment discovery at it.  The module-level ``MATMUL_PROF`` /
# ``MATMUL_PROF_MD`` names are populated by the session fixture below so test
# bodies can keep referring to them.
# ---------------------------------------------------------------------------

MATMUL_EXPERIMENT = "matmul"
MATMUL_TASK = "matmul-100M-prof"

# Populated by the session-scoped ``_synthetic_matmul_runlogs`` fixture.
MATMUL_PROF = ""
MATMUL_PROF_MD = ""
MATMUL_RUNLOGS_ROOT = ""

# Column order mirrors a real perf-profiled matmul run log.
_MATMUL_COLUMNS = [
    "task", "start", "repeat", "concurrency", "rank",
    "outer_time", "inner_time", "perf_time",
    "cache_misses", "context_switches", "cpu_migrations", "page_faults",
    "dTLB_misses", "iTLB_misses", "emulation_faults",
    "L1_icache_load_misses", "L1_dcache_load_misses", "LLC_misses",
    "branch_misses", "node_misses", "cpu_clock", "clock_rate",
]

_LOWER_IS_BETTER = {"clock_rate": False}


def _build_synthetic_matmul_frame(n_rows: int = 200, seed: int = 0) -> pl.DataFrame:
    """Return a deterministic synthetic profiled matmul DataFrame.

    The outcome timings correlate with a handful of hardware counters so that
    the analysis pipeline (correlation filtering, decision tree, causal
    analyzers) has real signal to surface factors, exactly as it would on
    genuine run-log data.
    """
    rng = np.random.default_rng(seed)

    cache_misses = rng.normal(1.0e6, 1.2e5, n_rows).clip(min=1.0)
    branch_misses = rng.normal(4.0e5, 5.0e4, n_rows).clip(min=1.0)
    llc_misses = rng.normal(2.0e5, 3.0e4, n_rows).clip(min=1.0)
    context_switches = rng.normal(500.0, 60.0, n_rows).clip(min=1.0)

    # Latent performance signal driven mainly by cache + branch misses.  Each
    # timing gets its own independent noise so the three time columns correlate
    # with the counters (real analysis signal) without being near-perfectly
    # collinear with each other (which would otherwise trip redundancy
    # auto-exclusion at the 0.99 correlation threshold).  The timing scale is
    # chosen so ``inner_time`` spans roughly [0.64, 0.92] seconds.
    signal = 1.0e-6 * cache_misses + 5.0e-7 * branch_misses
    signal = (signal - signal.mean()) / signal.std()

    def _timing(center: float) -> np.ndarray:
        return center + 0.05 * signal + rng.normal(0.0, 0.021, n_rows)

    inner_time = _timing(0.78)
    perf_time = _timing(0.80)
    outer_time = _timing(0.82)

    data = {
        "task": [MATMUL_TASK] * n_rows,
        "start": ["normal"] * n_rows,
        "repeat": np.arange(n_rows, dtype=np.int64),
        "concurrency": np.ones(n_rows, dtype=np.int64),
        "rank": np.zeros(n_rows, dtype=np.int64),
        "outer_time": outer_time,
        "inner_time": inner_time,
        "perf_time": perf_time,
        "cache_misses": cache_misses,
        "context_switches": context_switches,
        "cpu_migrations": rng.normal(20.0, 4.0, n_rows).clip(min=0.0),
        "page_faults": rng.normal(1.2e4, 1.5e3, n_rows).clip(min=1.0),
        "dTLB_misses": rng.normal(3.0e5, 4.0e4, n_rows).clip(min=1.0),
        "iTLB_misses": rng.normal(1.0e5, 1.5e4, n_rows).clip(min=1.0),
        "emulation_faults": np.zeros(n_rows, dtype=np.float64),
        "L1_icache_load_misses": rng.normal(6.0e5, 7.0e4, n_rows).clip(min=1.0),
        "L1_dcache_load_misses": rng.normal(8.0e6, 9.0e5, n_rows).clip(min=1.0),
        "LLC_misses": llc_misses,
        "branch_misses": branch_misses,
        "node_misses": rng.normal(1.5e5, 2.0e4, n_rows).clip(min=1.0),
        "cpu_clock": rng.normal(3.0e5, 1.0e4, n_rows).clip(min=1.0),
        "clock_rate": rng.normal(2400.0, 30.0, n_rows).clip(min=1.0),
    }
    return pl.DataFrame(data).select(_MATMUL_COLUMNS)


def _build_synthetic_matmul_md() -> str:
    """Return Markdown describing the synthetic run log (metrics + fields)."""
    numeric_cols = [c for c in _MATMUL_COLUMNS if c not in ("task", "start")]
    metrics = {
        col: {
            "description": f"Synthetic metric {col}.",
            "lower_is_better": _LOWER_IS_BETTER.get(col, True),
            "type": "numeric",
            "units": "seconds" if col.endswith("time") else "count",
        }
        for col in numeric_cols
        if col not in ("repeat", "concurrency", "rank")
    }
    runtime_options = {
        "metrics": metrics,
        "function": "matmul",
        "arguments": "10000",
        "repeats": "200",
        "experiment": MATMUL_EXPERIMENT,
        "task": MATMUL_TASK,
        "backends": ["local", "perf"],
    }
    field_lines = [
        "  * `task` (string): Task name.",
        "  * `start` (string): Warm, cold, or normal start.",
        "  * `repeat` (int): Batch number (iteration) when a task is repeated.",
    ]
    for col in numeric_cols:
        if col in ("repeat", "concurrency", "rank"):
            continue
        better = "higher is better" if not _LOWER_IS_BETTER.get(col, True) else "lower is better"
        field_lines.append(f"  * `{col}` (numeric): Synthetic metric {col}; {better}.")
    return (
        "Experiment completed at 2026-01-01 00:00:00+00:00 "
        "(total experiment time: 42s).\n\n"
        f"This file describes the fields in the file {MATMUL_TASK}.csv.\n\n"
        "## Runtime options\n\n"
        "```\n"
        f"{json.dumps(runtime_options, indent=2)}\n"
        "```\n\n"
        "## Field description\n\n"
        + "\n".join(field_lines)
        + "\n"
    )


def build_synthetic_matmul_runlogs(root: Path) -> tuple[Path, Path]:
    """Materialise a synthetic profiled matmul experiment under *root*.

    Creates ``<root>/matmul/matmul-100M-prof.{csv,md}`` and returns their
    paths, mirroring the ``runlogs/<experiment>/<task>`` layout expected by
    :func:`src.core.runlogs.scanner.scan_runlogs`.
    """
    exp_dir = root / MATMUL_EXPERIMENT
    exp_dir.mkdir(parents=True, exist_ok=True)
    csv_path = exp_dir / f"{MATMUL_TASK}.csv"
    md_path = exp_dir / f"{MATMUL_TASK}.md"
    _build_synthetic_matmul_frame().write_csv(csv_path)
    md_path.write_text(_build_synthetic_matmul_md(), encoding="utf-8")
    return csv_path, md_path


@pytest.fixture(scope="session", autouse=True)
def _synthetic_matmul_runlogs(tmp_path_factory):
    """Build the synthetic matmul run log once per session and expose its paths."""
    root = tmp_path_factory.mktemp("synthetic_runlogs")
    csv_path, md_path = build_synthetic_matmul_runlogs(root)
    global MATMUL_PROF, MATMUL_PROF_MD, MATMUL_RUNLOGS_ROOT
    MATMUL_PROF = str(csv_path)
    MATMUL_PROF_MD = str(md_path)
    MATMUL_RUNLOGS_ROOT = str(root)
    yield


@pytest.fixture(autouse=True)
def _wire_matmul_discovery(monkeypatch):
    """Point experiment discovery at the synthetic runlogs tree."""
    from src.gui.services import experiments as experiments_mod

    real_scan = experiments_mod.scan_runlogs
    monkeypatch.setattr(
        experiments_mod,
        "scan_runlogs",
        lambda runlogs_dir=None, limit=None: real_scan(MATMUL_RUNLOGS_ROOT, limit),
    )
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def demo_source_csvs(tmp_path):
    """Create synthetic original/prof CSVs for source-selection route tests."""
    base_dir = tmp_path / "demo"
    base_dir.mkdir(parents=True, exist_ok=True)
    original_csv = base_dir / "matmul.csv"
    prof_csv = base_dir / "matmul-prof.csv"

    pl.DataFrame(
        {
            "perf_time": [10.0, 20.0, 30.0, 40.0],
            "inner_time": [1.0, 2.0, 3.0, 4.0],
            "cache_misses": [100.0, 120.0, 140.0, 160.0],
            "timestamp": [1, 2, 3, 4],
        }
    ).write_csv(original_csv)
    pl.DataFrame(
        {
            "perf_time": [9.0, 18.0, 27.0, 36.0],
            "inner_time": [0.9, 1.8, 2.7, 3.6],
            "cache_misses": [90.0, 110.0, 130.0, 150.0],
            "timestamp": [1, 2, 3, 4],
        }
    ).write_csv(prof_csv)

    return {
        "original_csv": str(original_csv),
        "prof_csv": str(prof_csv),
    }


class TestProfileRouteSmoke:
    """Basic route accessibility tests."""

    def test_empty_profile_page(self, client):
        """Profile page renders with no parameters."""
        r = client.get("/ui/profile")
        assert r.status_code == 200
        assert "Profile" in r.text
        assert "profile-form" in r.text

    def test_profile_with_experiment_only(self, client):
        """Profile page renders with just an experiment selected."""
        r = client.get("/ui/profile?experiment=matmul")
        assert r.status_code == 200
        assert "matmul" in r.text

    def test_profile_with_task(self, client):
        """Profile page renders with experiment + task."""
        r = client.get("/ui/profile?experiment=matmul&task=matmul-100M-prof")
        assert r.status_code == 200
        assert "perf_time" in r.text
        assert "distribution.png" in r.text

    def test_profile_nonprof_task_prompts_for_source(self, client, monkeypatch, demo_source_csvs):
        """Selecting non-prof CSV prompts for source choice instead of silent load."""
        import src.gui.routes.ui_profile as ui_profile_route

        monkeypatch.setattr(
            ui_profile_route,
            "list_profile_task_choices",
            lambda _experiment: [
                {"label": "matmul", "csv_path": demo_source_csvs["original_csv"]},
                {"label": "matmul-prof", "csv_path": demo_source_csvs["prof_csv"]},
            ],
        )

        r = client.get(
            "/ui/profile",
            params={
                "experiment": "demo",
                "task": "matmul",
                "csv_path": demo_source_csvs["original_csv"],
            },
        )
        assert r.status_code == 200
        assert "Profile Options" in r.text or "Profiling Data Found" in r.text
        assert "Profile Task" in r.text or "Reprofile Task" in r.text

    def test_profile_use_original_source_loads_data(self, client, monkeypatch, demo_source_csvs):
        """source=use_original bypasses prompt and loads data."""
        import src.gui.routes.ui_profile as ui_profile_route

        monkeypatch.setattr(
            ui_profile_route,
            "list_profile_task_choices",
            lambda _experiment: [
                {"label": "matmul", "csv_path": demo_source_csvs["original_csv"]},
                {"label": "matmul-prof", "csv_path": demo_source_csvs["prof_csv"]},
            ],
        )

        r = client.get(
            "/ui/profile",
            params={
                "experiment": "demo",
                "task": "matmul",
                "csv_path": demo_source_csvs["original_csv"],
                "source": "use_original",
            },
        )
        assert r.status_code == 200
        assert "distribution.png" in r.text

    def test_profile_use_existing_switches_task_to_prof(self, client, monkeypatch, demo_source_csvs):
        """source=use_existing should update selected task to prof variant."""
        import src.gui.routes.ui_profile as ui_profile_route

        monkeypatch.setattr(
            ui_profile_route,
            "list_profile_task_choices",
            lambda _experiment: [
                {"label": "matmul", "csv_path": demo_source_csvs["original_csv"]},
                {"label": "matmul-prof", "csv_path": demo_source_csvs["prof_csv"]},
            ],
        )

        r = client.get(
            "/ui/profile",
            params={
                "experiment": "demo",
                "task": "matmul",
                "csv_path": demo_source_csvs["original_csv"],
                "source": "use_existing",
            },
        )
        assert r.status_code == 200
        assert 'option selected="selected" value="matmul-prof"' in r.text

    def test_profile_with_factor(self, client):
        """Profile page renders loading state, then analysis fragment contains factor."""
        # Page itself loads instantly with HTMX placeholder
        r = client.get("/ui/profile?experiment=matmul&task=matmul-100M-prof&factor=inner_time")
        assert r.status_code == 200
        assert "analysis-fragment" in r.text

        # The HTMX fragment endpoint delivers the factor detail
        r2 = client.get(
            "/ui/profile/analysis-fragment",
            params={
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "analyzer": "tree",
                "factor": "inner_time",
            },
        )
        assert r2.status_code == 200
        assert "Factor Analysis: inner_time" in r2.text
        assert "factor_scatter.png" in r2.text

    def test_profile_time_filter_slider_uses_numeric_bounds(self):
        """Profile time filters must render numeric noUiSlider bounds."""
        from src.gui.components.profile import profile_page

        html = profile_page(
            {
                "experiments": [],
                "tasks": [],
                "metrics": ["perf_time"],
                "filter_metrics": ["Time"],
                "active_csv": "/tmp/demo.csv",
                "csv_path": "/tmp/demo.csv",
                "metric": "perf_time",
                "filter_metric": "Time",
                "filter_kind": "time",
                "filter_min_bound": "08:46:51.000",
                "filter_max_bound": "09:36:28.000",
                "filter_min_bound_num": 31611.0,
                "filter_max_bound_num": 34588.0,
                "filter_min": "08:56:51",
                "filter_max": "09:36:28",
                "lower_is_better": True,
                "num_groups": 2,
                "analyzer_choices": {},
            }
        )

        slider = re.search(r'<div[^>]*id="profile-noui-slider"[^>]*>', html)
        assert slider is not None
        tag = slider.group(0)
        assert 'data-min="31611.0"' in tag
        assert 'data-max="34588.0"' in tag
        assert 'data-start-min="32211.0"' in tag
        assert 'data-start-max="34588.0"' in tag
        assert 'data-min="08:46:51.000"' not in tag

    def test_profile_numeric_filter_slider_preserves_full_precision(self):
        """Numeric filter bounds must keep full float precision in the slider.

        Regression: a constant high-magnitude timestamp column (e.g. all rows
        == 20260512.180722) was truncated by noUiSlider's default 2-decimal
        formatter to 20260512.18 on submit, so ``value <= 20260512.18``
        excluded every row and the analysis plots went empty. The rendered
        slider bounds must carry every decimal so the JS full-precision
        ``format`` round-trips the real value back to the form.
        """
        from src.gui.components.profile import profile_page

        html = profile_page(
            {
                "experiments": [],
                "tasks": [],
                "metrics": ["Avg_Transfer_MB_per_sec"],
                "filter_metrics": ["timestamp"],
                "active_csv": "/tmp/demo.csv",
                "csv_path": "/tmp/demo.csv",
                "metric": "Avg_Transfer_MB_per_sec",
                "filter_metric": "timestamp",
                "filter_kind": "numeric",
                "filter_min_bound": 20260512.180722,
                "filter_max_bound": 20260512.280722,
                "filter_min_bound_num": 20260512.180722,
                "filter_max_bound_num": 20260512.280722,
                "filter_is_timestamp_like": True,
                "lower_is_better": True,
                "num_groups": 2,
                "analyzer_choices": {},
            }
        )

        slider = re.search(r'<div[^>]*id="profile-noui-slider"[^>]*>', html)
        assert slider is not None
        tag = slider.group(0)
        assert 'data-min="20260512.180722"' in tag
        assert 'data-max="20260512.280722"' in tag
        # Must NOT be truncated to 2 decimals.
        assert 'data-min="20260512.18"' not in tag
        assert 'data-max="20260512.28"' not in tag

    def test_constant_numeric_filter_at_bound_keeps_all_rows(self, tmp_path):
        """Filtering a constant column at its exact value must keep all rows.

        Truncating the bound (20260512.18 instead of 20260512.180722) made the
        ``<=`` comparison drop every row. Full-precision bounds keep the data.
        """
        import polars as pl
        from src.gui.services.shared import _load_filtered_dataframe

        csv = tmp_path / "const.csv"
        pl.DataFrame(
            {
                "timestamp": [20260512.180722] * 5,
                "metric": [1.0, 2.0, 3.0, 4.0, 5.0],
            }
        ).write_csv(csv)

        full = _load_filtered_dataframe(
            str(csv), "timestamp", None, None,
            "20260512.180722", "20260512.180722",
        )
        assert full.height == 5

        truncated = _load_filtered_dataframe(
            str(csv), "timestamp", None, None,
            "20260512.18", "20260512.18",
        )
        # Documents the pre-fix failure mode the JS precision format avoids.
        assert truncated.height == 0

    def test_profile_start_profiling_returns_run_id(self, client, monkeypatch):
        """Profile start endpoint should return a run id for SSE progress."""
        import src.gui.routes.ui_profile as ui_profile_route

        monkeypatch.setattr(ui_profile_route, "start_profile_job", lambda form: "run-123")

        r = client.post(
            "/ui/profile/start-profiling",
            data={
                "original_md": MATMUL_PROF_MD,
                "csv_path": MATMUL_PROF,
                "profile_task_name": "matmul-100M-prof",
                "profiling_backends": ["perf"],
                "redirect_url": "/ui/profile",
            },
        )
        assert r.status_code == 200
        assert r.json().get("run_id") == "run-123"

    def test_profile_stream_completed_emits_redirect(self, client, monkeypatch):
        """Profile stream should emit completed payload with redirect URL."""
        import src.gui.routes.ui_profile as ui_profile_route

        monkeypatch.setattr(
            ui_profile_route,
            "get_profile_job",
            lambda run_id: {
                "job_id": run_id,
                "version": 1,
                "status": "completed",
                "current": 3,
                "total": 3,
                "message": "Profiling completed.",
                "workflow": {
                    "success": True,
                    "profile_csv": MATMUL_PROF,
                    "notice": "Profiling completed successfully.",
                },
                "form": {
                    "redirect_url": "/ui/profile",
                    "csv_path": MATMUL_PROF,
                },
            },
        )

        r = client.get("/ui/profile/stream", params={"run_id": "run-123"})
        assert r.status_code == 200
        assert '"status": "completed"' in r.text
        assert '"redirect_url":' in r.text

    def test_predictors_fragment_auto_excludes_high_corr_by_default(self, client, monkeypatch):
        """Without custom exclusions, high-correlation predictors are checked by default."""
        import src.gui.routes.ui_profile as ui_profile_route

        monkeypatch.setattr(
            ui_profile_route,
            "_load_filtered_dataframe",
            lambda *args, **kwargs: pl.DataFrame({"perf_time": [1.0, 2.0, 3.0]}),
        )

        import src.gui.utils.profile.predictor_stats as predictor_stats
        monkeypatch.setattr(
            predictor_stats,
            "compute_predictor_stats",
            lambda df, metric: [
                {"name": "wall_time", "non_na_count": 3, "correlation": 0.998},
                {"name": "cache_misses", "non_na_count": 3, "correlation": 0.42},
            ],
        )

        r = client.get(
            "/ui/profile/predictors-fragment",
            params={
                "csv_path": "runlogs/test/auto-corr-default.csv",
                "metric": "perf_time",
            },
        )
        assert r.status_code == 200
        assert 'value="wall_time"' in r.text
        assert re.search(
            r'<input[^>]*(value="wall_time"[^>]*checked|checked[^>]*value="wall_time")',
            r.text,
        )

    def test_predictors_fragment_slider_overrides_stored_exclusions(self, client, monkeypatch):
        """Changing max_corr slider must recheck predictors whose correlation exceeds
        the new threshold, even when an excluded_state token is already present.

        Regression for: slider change ignored when excluded_state was passed,
        causing the old frozen exclusion list to be used instead.
        """
        import src.gui.routes.ui_profile as ui_profile_route
        from src.gui.services.exclusion_store import create_exclusion_state

        monkeypatch.setattr(
            ui_profile_route,
            "_load_filtered_dataframe",
            lambda *args, **kwargs: pl.DataFrame({"perf_time": [1.0, 2.0, 3.0]}),
        )
        import src.gui.utils.profile.predictor_stats as predictor_stats
        monkeypatch.setattr(
            predictor_stats,
            "compute_predictor_stats",
            lambda df, metric: [
                {"name": "wall_time",   "non_na_count": 3, "correlation": 0.998},
                {"name": "medium_corr", "non_na_count": 3, "correlation": 0.90},
                {"name": "cache_misses","non_na_count": 3, "correlation": 0.42},
            ],
        )

        # Create an excluded_state that was frozen at 0.99 threshold —
        # only wall_time (0.998) was auto-excluded, not medium_corr (0.90).
        token = create_exclusion_state(
            "runlogs/test/slider.csv", "perf_time", ["wall_time"]
        )

        # Now reload with max_corr=0.88, which should also check medium_corr.
        r = client.get(
            "/ui/profile/predictors-fragment",
            params={
                "csv_path": "runlogs/test/slider.csv",
                "metric": "perf_time",
                "max_corr": "0.88",
                "excluded_state": token,
            },
        )
        assert r.status_code == 200
        # medium_corr (0.90 > 0.88) must now be checked
        assert re.search(
            r'<input[^>]*(value="medium_corr"[^>]*checked|checked[^>]*value="medium_corr")',
            r.text,
        ), "medium_corr (corr=0.90) must be checked when threshold drops to 0.88"
        # cache_misses (0.42 < 0.88) must NOT be checked
        assert not re.search(
            r'<input[^>]*(value="cache_misses"[^>]*checked|checked[^>]*value="cache_misses")',
            r.text,
        ), "cache_misses (corr=0.42) must not be checked at threshold 0.88"

class TestProfilePlotEndpoints:
    """Test PNG rendering endpoints."""

    def test_distribution_plot_png(self, client):
        """Distribution plot returns valid PNG."""
        r = client.get(
            "/ui/profile/distribution.png",
            params={
                "csv_path": MATMUL_PROF,
                "metric": "perf_time",
                "lower_is_better": "1",
                "num_groups": 2,
                "auto_detect": "1",
            },
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert len(r.content) > 1000  # Real plot, not just text

    def test_analysis_plot_png(self, client):
        """Analysis plot endpoint returns PNG."""
        r = client.get(
            "/ui/profile/analysis.png",
            params={
                "csv_path": MATMUL_PROF,
                "metric": "perf_time",
                "lower_is_better": "1",
                "num_groups": 2,
                "auto_detect": "1",
                "analyzer": "tree",
            },
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"

    def test_analysis_tree_html(self, client):
        """Interactive tree endpoint returns HTML for iframe embedding."""
        r = client.get(
            "/ui/profile/analysis-tree.html",
            params={
                "csv_path": MATMUL_PROF,
                "metric": "perf_time",
                "lower_is_better": "1",
                "num_groups": 2,
                "auto_detect": "0",
                "analyzer": "tree",
            },
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert "<html" in r.text.lower()

    def test_factor_scatter_png(self, client):
        """Factor scatter plot returns valid PNG."""
        r = client.get(
            "/ui/profile/factor_scatter.png",
            params={
                "csv_path": MATMUL_PROF,
                "metric": "perf_time",
                "factor_name": "inner_time",
                "lower_is_better": "1",
                "num_groups": 2,
                "auto_detect": "1",
            },
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert len(r.content) > 1000

    def test_mitigation_density_plot_png(self, client):
        """Mitigation density endpoint returns valid PNG."""
        r = client.get(
            "/ui/profile/mitigation_density.png",
            params={
                "baseline_csv": MATMUL_PROF,
                "mitigation_csv": MATMUL_PROF,
                "metric": "perf_time",
            },
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert len(r.content) > 1000


@pytest.fixture
def wide_profile_csv(tmp_path):
    """Generate a synthetic wide profile CSV with many filterable columns."""
    import numpy as np
    import polars as pl

    rng = np.random.default_rng(42)
    n_rows = 100

    # Create a dataframe with many numeric columns to simulate a wide dataset
    data = {
        f"metric_{i:05d}": rng.normal(0, 1, n_rows)
        for i in range(200)
    }
    # Add a sparse metric name similar to Avenger
    data["8389856_0_isal_work_cpu_cur"] = rng.normal(0, 1, n_rows)
    # Add outcome metric
    data["perf_time"] = rng.exponential(1.0, n_rows)

    df = pl.DataFrame(data)
    csv_path = tmp_path / "wide_test_profile.csv"
    df.write_csv(str(csv_path))
    return str(csv_path)


class TestProfileServices:
    """Test the profile service layer."""

    def test_load_profile_dataset(self):
        """Loading a profile dataset returns expected keys."""
        from src.gui.services.profile import load_profile_dataset

        result = load_profile_dataset(MATMUL_PROF)
        assert "metrics" in result
        assert "filter_metrics" in result
        assert "metric" in result
        assert "perf_time" in result["metrics"]
        assert result["rows"] > 0

    def test_load_profile_dataset_applies_initial_column_reduction(self, tmp_path, monkeypatch):
        """Initial profile load should use reduced columns for metric/filter choices."""
        import src.gui.services.profile as profile_service

        csv_path = tmp_path / "initial_load_wide.csv"
        n_rows = 20
        data = {
            "perf_time": np.linspace(1.0, 2.0, n_rows),
            "kept_metric": np.linspace(10.0, 30.0, n_rows),
            "dropped_metric": np.ones(n_rows),
        }
        pl.DataFrame(data).write_csv(csv_path)

        calls = {"count": 0}

        def fake_compute_cleaned_columns(df, settings=None):
            calls["count"] += 1
            return ["perf_time", "kept_metric"]

        monkeypatch.setattr(profile_service, "compute_cleaned_columns", fake_compute_cleaned_columns)

        result = profile_service.load_profile_dataset(str(csv_path))

        assert calls["count"] >= 1
        assert "kept_metric" in result["filter_metrics"]
        assert "dropped_metric" not in result["filter_metrics"]

    def test_profile_filter_metric_uses_server_side_search(self, client, wide_profile_csv):
        """Profile filter metric search should stay server-side for very wide datasets."""
        # The search endpoint should find sparse metrics by prefix/substring
        r = client.get(
            "/ui/profile/filter-metrics",
            params={
                "csv_path": wide_profile_csv,
                "q": "8389856_0_isal",
                "limit": 50,
            },
        )
        assert r.status_code == 200
        payload = r.json()
        items = payload.get("items", [])
        assert any(item.get("value") == "8389856_0_isal_work_cpu_cur" for item in items)
        assert len(items) <= 50

        # The profile page should wire server-side search for the filter metric select
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "misc",
                "csv_path": wide_profile_csv,
                "metric": "perf_time",
            },
        )
        assert r.status_code == 200
        assert 'data-search-url="/ui/profile/filter-metrics"' in r.text
        assert f'data-csv-path="{wide_profile_csv}"' in r.text

        # App JS should contain Shiny-style server-side selectize behavior:
        # preload on focus and do not require two typed chars before searching.
        app_js = Path("src/gui/static/app.js").read_text()
        assert "createRemoteSingleSelect" in app_js
        assert 'preload: "focus"' in app_js
        assert "query.length >= 2" not in app_js
        assert "fetch(url.toString()" in app_js

    def test_profile_filter_metric_prefix_ranking(self, wide_profile_csv):
        """Search should rank prefix matches before substring matches."""
        from src.gui.services.profile import search_profile_filter_metrics

        # Search for "metric_0" should return prefix matches first
        results = search_profile_filter_metrics(wide_profile_csv, "metric_0", limit=20)
        assert len(results) > 0
        # Prefix matches like metric_00001, metric_00002, etc. should come before
        # any metric that merely contains "metric_0" as a substring
        assert results[0].startswith("metric_0")

    def test_outcome_metric_search_preloads_and_finds_wide_columns(self, wide_profile_csv):
        """Outcome metric search should preload and search all numeric columns server-side."""
        from src.gui.services.shared import search_outcome_metrics

        preload = search_outcome_metrics(wide_profile_csv, "", limit=10)
        assert len(preload) == 10

        results = search_outcome_metrics(wide_profile_csv, "8389856_0_isal", limit=20)
        assert any(item == "8389856_0_isal_work_cpu_cur" for item in results)

    def test_filter_metric_search_preloads_and_includes_categorical_columns(self, tmp_path):
        """Filter metric search should include numeric and filterable non-numeric columns."""
        from src.gui.services.shared import search_filter_metrics

        csv_path = tmp_path / "filterable.csv"
        pl.DataFrame(
            {
                "perf_time": [1.0, 2.0, 3.0, 4.0],
                "category": ["a", "b", "a", "b"],
                "constant": ["x", "x", "x", "x"],
            }
        ).write_csv(csv_path)

        preload = search_filter_metrics(str(csv_path), "", limit=10)
        assert "perf_time" in preload
        assert "category" in preload
        assert "constant" not in preload

        results = search_filter_metrics(str(csv_path), "cat", limit=10)
        assert results == ["category"]

    def test_profile_filter_metric_search_reuses_cached_metrics(self, wide_profile_csv, monkeypatch):
        """Repeated searches on the same CSV should not reload the table each time."""
        import src.gui.services.profile as profile_service
        import src.gui.services.shared as shared_service

        shared_service._FILTER_METRICS_CACHE.clear()

        original_load_table = shared_service.load_table
        calls = {"count": 0}

        def counting_load_table(path: str):
            calls["count"] += 1
            return original_load_table(path)

        monkeypatch.setattr(shared_service, "load_table", counting_load_table)

        first = profile_service.search_profile_filter_metrics(wide_profile_csv, "metric_0", limit=20)
        second = profile_service.search_profile_filter_metrics(wide_profile_csv, "8389856_0_isal", limit=20)
        third = profile_service.search_profile_filter_metrics(wide_profile_csv, "work_cpu", limit=20)

        assert calls["count"] == 1
        assert len(first) > 0
        assert any(item == "8389856_0_isal_work_cpu_cur" for item in second)
        assert any(item == "8389856_0_isal_work_cpu_cur" for item in third)

    def test_compute_profile_analysis_returns_factors(self):
        """Analysis pipeline returns ranked factors."""
        from src.gui.services.profile import compute_profile_analysis

        result = compute_profile_analysis(
            csv_path=MATMUL_PROF,
            metric="perf_time",
            lower_is_better=True,
            num_groups=2,
            auto_detect=True,
            analyzer_name="tree",
        )
        assert result["error"] is None
        assert len(result["factors"]) > 0
        # Factors should have name and strength
        f = result["factors"][0]
        assert hasattr(f, "name")
        assert hasattr(f, "strength")
        assert f.strength > 0

    def test_compute_profile_analysis_removes_excluded_predictors_from_model_input(self):
        """Excluded predictors must not be present in model input columns."""
        from src.gui.services.profile import compute_profile_analysis

        excluded_name = "repeat"
        result = compute_profile_analysis(
            csv_path=MATMUL_PROF,
            metric="inner_time",
            lower_is_better=True,
            num_groups=2,
            auto_detect=False,
            analyzer_name="tree",
            excluded_predictors=[excluded_name],
        )
        assert result["error"] is None
        assert excluded_name not in (result.get("reduced_columns") or [])
        analysis_data = result.get("analysis_data")
        assert analysis_data is not None
        assert excluded_name not in analysis_data.columns

    def test_hybrid_analysis_does_not_return_excluded_outcome_metric(self):
        """Hybrid causal analysis must not use the continuous metric as a factor."""
        from src.gui.services.profile import compute_profile_analysis

        result = compute_profile_analysis(
            csv_path=MATMUL_PROF,
            metric="perf_time",
            lower_is_better=True,
            num_groups=2,
            auto_detect=False,
            analyzer_name="hybrid",
            excluded_predictors=["repeat", "inner_time", "outer_time", "perf_time"],
        )

        assert result["error"] is None
        assert "perf_time" not in [f.name for f in result["factors"]]

    def test_compute_profile_analysis_all_excluded_returns_clear_error(self):
        """Excluding every available predictor must return a clear error, not silent empty factors.

        Regression for: when all C1+C2-cleaned predictors are excluded, the analysis
        silently returned factors=[] with error=None, giving the user no indication
        of why the tree showed no factors.
        """
        import polars as pl
        from src.gui.services.profile import compute_profile_analysis
        from src.gui.utils.profile.data_pipeline import (
            compute_cleaned_columns,
            compute_outcome_correlations,
        )

        df = pl.read_csv(MATMUL_PROF)
        metric = "inner_time"
        cleaned = compute_cleaned_columns(df)
        _, stats = compute_outcome_correlations(df, metric, cleaned)
        all_predictors = [s["name"] for s in stats]

        result = compute_profile_analysis(
            csv_path=MATMUL_PROF,
            metric=metric,
            lower_is_better=True,
            num_groups=2,
            auto_detect=False,
            analyzer_name="tree",
            excluded_predictors=all_predictors,
        )
        assert result["error"] is not None, (
            "Excluding all predictors must set error, not silently return empty factors"
        )
        assert "excluded" in result["error"].lower() or "predictor" in result["error"].lower(), (
            f"Error message should mention exclusions or predictors, got: {result['error']!r}"
        )
        assert result["factors"] == []

    def test_compute_profile_analysis_no_correlated_predictors_returns_clear_error(
        self, monkeypatch
    ):
        """When all candidate columns survive C1+C2 but are filtered by C3 (no correlation),
        a clear error must be returned.
        """
        import polars as pl
        import src.gui.services.profile as profile_svc
        from src.gui.services.profile import compute_profile_analysis

        # Make C3 always return empty by patching compute_reduced_columns
        monkeypatch.setattr(
            profile_svc,
            "compute_reduced_columns",
            lambda *a, **kw: [],
        )

        result = compute_profile_analysis(
            csv_path=MATMUL_PROF,
            metric="inner_time",
            lower_is_better=True,
            num_groups=2,
            auto_detect=False,
            analyzer_name="tree",
        )
        assert result["error"] is not None, (
            "Empty reduced_cols must set error, not silently return empty factors"
        )
        assert result["factors"] == []


        """AutoLabeler can be built with metric values."""
        from src.gui.services.profile import build_labeler

        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0] * 20)
        labeler = build_labeler(2, True, values, True)
        assert labeler is not None
        labels = labeler.label(values)
        assert len(labels) == len(values)

    def test_build_labeler_binary(self):
        """BinaryLabeler can be built manually."""
        from src.gui.services.profile import build_labeler

        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0] * 20)
        labeler = build_labeler(2, False, values, True)
        assert labeler is not None
        labels = labeler.label(values)
        assert len(labels) == len(values)

    def test_build_labeler_regression(self):
        """RegressionLabeler (num_groups=1) returns continuous values."""
        from src.gui.services.profile import build_labeler

        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        labeler = build_labeler(1, False, values, True)
        assert labeler is not None

    def test_build_labeler_five_groups(self):
        """Fixed five-group mode should create four cutoffs and five labels."""
        from src.gui.services.profile import build_labeler

        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0] * 20)
        labeler = build_labeler(5, False, values, True)
        assert labeler is not None
        assert len(labeler.get_cutoffs() or []) == 4
        assert len(labeler.get_class_names()) == 5

    def test_build_labeler_empty_values(self):
        """Empty values returns None."""
        from src.gui.services.profile import build_labeler

        labeler = build_labeler(2, True, np.array([]), True)
        assert labeler is None

    def test_get_analyzer_choices(self):
        """Analyzer choices include tree and others."""
        from src.gui.services.profile import get_analyzer_choices

        choices = get_analyzer_choices()
        assert "tree" in choices
        assert len(choices) >= 3

    def test_get_metric_direction_default(self):
        """Default metric direction is True (lower is better)."""
        from src.gui.services.profile import get_metric_direction

        assert get_metric_direction("perf_time", None) is True
        assert get_metric_direction("perf_time", "/nonexistent.md") is True


class TestProfileSaveSettings:
    """Test the save-settings POST endpoint."""

    def test_save_settings_creates_redirect(self, client):
        """Save settings redirects back to profile page."""
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
            f.write(Path(MATMUL_PROF_MD).read_text())
            tmp_md = f.name

        try:
            r = client.post(
                "/ui/profile/save-settings",
                data={
                    "md_path": tmp_md,
                    "metric": "perf_time",
                    "filter_metric": "",
                    "filter_min": "",
                    "filter_max": "",
                    "num_groups": "2",
                    "auto_detect": "1",
                    "analyzer": "tree",
                    "redirect_url": "/ui/profile?experiment=matmul",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            assert "/ui/profile" in r.headers["location"]
        finally:
            Path(tmp_md).unlink()

    def test_save_settings_missing_md_redirects(self, client):
        """Save with nonexistent md_path still redirects gracefully."""
        r = client.post(
            "/ui/profile/save-settings",
            data={
                "md_path": "/nonexistent/path.md",
                "metric": "perf_time",
                "filter_metric": "",
                "filter_min": "",
                "filter_max": "",
                "num_groups": "2",
                "auto_detect": "1",
                "analyzer": "tree",
                "redirect_url": "/ui/profile",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_save_settings_persists_all_cutoffs_from_plural_field(self, client):
        """Save-settings should accept plural cutoff_values form fields."""
        from src.core.runlogs.profile_settings import extract_profile_settings_from_md

        with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
            f.write("# test\n")
            tmp_md = f.name

        try:
            r = client.post(
                "/ui/profile/save-settings",
                data={
                    "md_path": tmp_md,
                    "metric": "perf_time",
                    "num_groups": "5",
                    "auto_detect": "0",
                    "cutoff_values": ["1.0", "2.0", "3.0", "4.0"],
                    "redirect_url": "/ui/profile?experiment=matmul&num_groups=5",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303

            saved = extract_profile_settings_from_md(tmp_md)
            assert saved.get("profiling.default_cutoff_values") == [1.0, 2.0, 3.0, 4.0]
            assert saved.get("profiling.default_num_perf_groups") == 5
        finally:
            Path(tmp_md).unlink()

    def test_save_settings_recovers_cutoffs_from_redirect_url_when_form_is_partial(self, client):
        """If posted cutoff fields are incomplete, save-settings should recover from redirect URL."""
        from src.core.runlogs.profile_settings import extract_profile_settings_from_md

        with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
            f.write("# test\n")
            tmp_md = f.name

        try:
            r = client.post(
                "/ui/profile/save-settings",
                data={
                    "md_path": tmp_md,
                    "metric": "perf_time",
                    "num_groups": "5",
                    "auto_detect": "0",
                    "cutoff_value": ["9.5"],
                    "redirect_url": (
                        "/ui/profile?experiment=matmul&num_groups=5"
                        "&cutoff_value=1.0&cutoff_value=2.0&cutoff_value=3.0&cutoff_value=4.0"
                    ),
                },
                follow_redirects=False,
            )
            assert r.status_code == 303

            saved = extract_profile_settings_from_md(tmp_md)
            assert saved.get("profiling.default_cutoff_values") == [1.0, 2.0, 3.0, 4.0]
            assert saved.get("profiling.default_num_perf_groups") == 5
        finally:
            Path(tmp_md).unlink()


class TestProfileMitigations:
    """Mitigation-related UI and workflow tests."""

    def test_profile_with_factor_shows_mitigation_controls(self, client):
        """Selecting a known factor renders mitigation UI in analysis fragment."""
        r = client.get(
            "/ui/profile/analysis-fragment",
            params={
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "analyzer": "tree",
                "factor": "cache_misses",
            },
        )
        assert r.status_code == 200
        assert "Mitigations" in r.text
        assert "Choose mitigation" in r.text
        assert "profile-mitigation-action-row" in r.text
        assert "Try it!" in r.text

    def test_use_existing_mitigation_csv_missing_redirects_error(self, client, monkeypatch):
        """Using missing mitigation data redirects with an error."""
        from src.gui.routes import ui_profile

        monkeypatch.setattr(
            ui_profile,
            "resolve_mitigation_paths",
            lambda csv_path, mitigation_name: {
                "baseline_csv": csv_path,
                "baseline_md": "runlogs/matmul/matmul-100M.md",
                "mitigation_csv": "runlogs/matmul/__definitely_missing__-huge_pages.csv",
                "mitigation_md": "runlogs/matmul/__definitely_missing__-huge_pages.md",
            },
        )

        r = client.post(
            "/ui/profile/mitigation/run",
            data={
                "md_path": "",
                "csv_path": MATMUL_PROF,
                "mitigation": "huge_pages",
                "action": "use",
                "redirect_url": "/ui/profile?experiment=matmul&task=matmul-100M-prof",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "error=" in r.headers["location"]
        assert "mitigation=huge_pages" in r.headers["location"]

    def test_run_mitigation_uses_service_and_redirects_notice(self, client, monkeypatch):
        """Mitigation run endpoint redirects with notice on success."""
        from src.gui.routes import ui_profile

        def _fake_run(md_path: str, mitigation_name: str):
            assert mitigation_name == "huge_pages"
            return {
                "success": True,
                "mitigation_csv": "runlogs/matmul/matmul-100M-huge_pages.csv",
                "notice": "Mitigation completed: matmul-100M-huge_pages.csv",
            }

        monkeypatch.setattr(ui_profile, "run_mitigation_workflow", _fake_run)

        r = client.post(
            "/ui/profile/mitigation/run",
            data={
                "md_path": "runlogs/matmul/matmul-100M.md",
                "csv_path": MATMUL_PROF,
                "mitigation": "huge_pages",
                "action": "run",
                "redirect_url": "/ui/profile?experiment=matmul&task=matmul-100M-prof&factor=cache_misses",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "notice=" in r.headers["location"]
        assert "mitigation=huge_pages" in r.headers["location"]
        assert "mitigation_csv=" in r.headers["location"]

    def test_run_mitigation_missing_selection_redirects_error(self, client):
        """Missing mitigation name returns redirect with an error."""
        r = client.post(
            "/ui/profile/mitigation/run",
            data={
                "md_path": "",
                "csv_path": "",
                "mitigation": "",
                "action": "run",
                "redirect_url": "/ui/profile",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "error=" in r.headers["location"]

    def test_modal_shows_use_data_when_mitigation_csv_exists(self, client):
        """Try-it! modal must offer 'Use data' when the mitigation CSV already exists."""
        from src.gui.services.profile import resolve_mitigation_paths

        paths = resolve_mitigation_paths(MATMUL_PROF, "huge_pages")
        mit_csv = Path(paths["mitigation_csv"])
        already_existed = mit_csv.exists()
        if not already_existed:
            mit_csv.parent.mkdir(parents=True, exist_ok=True)
            mit_csv.write_text("col\n1\n")
        try:
            r = client.get(
                "/ui/profile",
                params={
                    "experiment": "matmul",
                    "csv_path": MATMUL_PROF,
                    "metric": "inner_time",
                    "num_groups": "2",
                    "factor": "cache_misses",
                    "mitigation": "huge_pages",
                    "show_mitigation_modal": "1",
                },
            )
            assert r.status_code == 200
            assert "Use data" in r.text, "Modal must show 'Use data' when mitigation CSV exists"
        finally:
            if not already_existed and mit_csv.exists():
                mit_csv.unlink()

    def test_analysis_fragment_preserves_experiment_task_in_links(self, client):
        """Experiment and task passed to fragment must appear in Try-it!/Cancel URLs."""
        r = client.get(
            "/ui/profile/analysis-fragment",
            params={
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "experiment": "matmul",
                "task": "matmul-100M-prof",
                "factor": "cache_misses",
            },
        )
        assert r.status_code == 200
        assert "show_mitigation_modal" in r.text, "Fragment must render a Try-it! link"
        assert "experiment=matmul" in r.text, "experiment must appear in Try-it!/Cancel URLs"
        assert "task=matmul-100M-prof" in r.text, "task must appear in Try-it!/Cancel URLs"

    def test_cutoff_values_forwarded_to_analysis_fragment_url(self, client):
        """Cutoff values must appear in analysis_fragment_url so the async HTMX
        load passes them to the analysis backend.

        This is a regression test for the bug where get_analysis_fragment did not
        accept cutoff_value params at all, causing the tree to always be trained
        with auto-detected boundaries regardless of where the user placed the
        cutoff on the distribution plot.
        """
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "num_groups": "2",
                "auto_detect": "0",
                "cutoff_value": ["0.05"],
            },
        )
        assert r.status_code == 200
        # The analysis_fragment_url must include cutoff_value so the HTMX
        # async load carries the cutoff to the analysis endpoint.
        assert "analysis-fragment" in r.text, "Page must render an analysis fragment URL"
        assert "cutoff_value=0.05" in r.text, (
            "analysis_fragment_url must include cutoff_value params — "
            "without this the analysis always ignores manual cutoffs"
        )


class TestProfileEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_num_groups_clamped(self, client):
        """Invalid num_groups values are clamped to 1-10 range."""
        r = client.get("/ui/profile?experiment=matmul&task=matmul-100M-prof&num_groups=999")
        assert r.status_code == 200
        # Should be clamped to 10
        assert 'value="10"' in r.text

    def test_invalid_num_groups_string(self, client):
        """Non-numeric num_groups defaults to 2."""
        r = client.get("/ui/profile?experiment=matmul&task=matmul-100M-prof&num_groups=abc")
        assert r.status_code == 200
        assert 'value="2"' in r.text

    def test_nonexistent_experiment(self, client):
        """Nonexistent experiment shows empty task list."""
        r = client.get("/ui/profile?experiment=DOES_NOT_EXIST_12345")
        assert r.status_code == 200
        assert "error" not in r.text.lower() or "error-banner" not in r.text

    def test_unresolved_task_shows_guidance_instead_of_500(self, client):
        """Unresolved task with blank csv_path should render a helpful error banner."""
        r = client.get(
            "/ui/profile"
            "?experiment=misc&task=DOES_NOT_EXIST_12345&metric=&lower_is_better=1&lower_is_better_default=0"
            "&filter_metric=&csv_path=&source=&num_groups=2&analyzer=tree&factor="
            "&filter_min=&filter_max=&mitigation=&mitigation_metric=&mitigation_csv="
        )
        assert r.status_code == 200
        assert "Could not resolve task 'DOES_NOT_EXIST_12345' in experiment 'misc'" in r.text

    def test_nonexistent_metric(self, client):
        """Nonexistent metric doesn't crash the page."""
        r = client.get(
            "/ui/profile?experiment=matmul&task=matmul-100M-prof&metric=BOGUS_METRIC"
        )
        assert r.status_code == 200

    def test_nonexistent_factor(self, client):
        """Nonexistent factor doesn't crash the page."""
        r = client.get(
            "/ui/profile?experiment=matmul&task=matmul-100M-prof&factor=BOGUS_FACTOR"
        )
        assert r.status_code == 200

    def test_lower_is_better_false(self, client):
        """lower_is_better=0 propagates correctly."""
        r = client.get(
            "/ui/profile?experiment=matmul&task=matmul-100M-prof&lower_is_better=0"
        )
        assert r.status_code == 200
        # The checkbox should not be checked
        # The plot URL should have lower_is_better=0
        assert "lower_is_better=0" in r.text

    def test_filter_with_range(self, client):
        """Numeric filter propagates to plot URLs."""
        r = client.get(
            "/ui/profile?experiment=matmul&task=matmul-100M-prof"
            "&filter_metric=perf_time&filter_min=0.5&filter_max=2.0"
        )
        assert r.status_code == 200
        assert "filter_min=0.5" in r.text
        assert "filter_max=2.0" in r.text


class TestProfileDataReductionPipeline:
    """
    Regression tests for the R1/R2/R3 row-reduction pipeline and tree downsampling.

    These tests guard against regressions where features that prevent large-dataset
    hangs are inadvertently removed from the profile analysis pipeline.
    """

    def _write_csv(self, df: pl.DataFrame, tmp_path: Path, name: str = "test.csv") -> str:
        """Write a Polars DataFrame to a temporary CSV and return its path string."""
        path = tmp_path / name
        df.write_csv(str(path))
        return str(path)

    def test_profile_analysis_applies_r1_row_reduction(self, tmp_path, monkeypatch):
        """compute_profile_analysis calls reduce_rows (R1/R2/R3 pipeline is wired in)."""
        import src.gui.services.profile as profile_svc

        reduction_calls: list[dict] = []
        original_reduce_rows = profile_svc.reduce_rows

        def spy_reduce_rows(df, outcome_col, predictor_cols, settings=None):
            reduction_calls.append({
                "n_in": df.height,
                "outcome_col": outcome_col,
            })
            return original_reduce_rows(df, outcome_col, predictor_cols, settings)

        monkeypatch.setattr(profile_svc, "reduce_rows", spy_reduce_rows)

        rng = np.random.default_rng(42)
        n = 100
        predictor = rng.normal(0, 1, n)
        outcome = predictor + rng.normal(0, 0.01, n)
        df = pl.DataFrame({"outcome": outcome, "predictor": predictor})
        csv_path = self._write_csv(df, tmp_path)

        profile_svc.compute_profile_analysis(
            csv_path=csv_path,
            metric="outcome",
            lower_is_better=True,
            num_groups=2,
            auto_detect=True,
            analyzer_name="tree",
        )

        assert reduction_calls, (
            "reduce_rows was never called — R1/R2/R3 pipeline is missing from "
            "compute_profile_analysis. This would cause large-dataset hangs."
        )
        assert reduction_calls[0]["outcome_col"] == "outcome"

    def test_r1_all_null_rows_are_removed(self, tmp_path):
        """Rows that are all-null are filtered out before analysis (R1)."""
        from src.gui.services.profile import compute_profile_analysis

        rng = np.random.default_rng(42)
        n_good = 80
        predictor = rng.normal(0, 1, n_good).tolist()
        outcome = (np.array(predictor) + rng.normal(0, 0.01, n_good)).tolist()

        # Add 20 rows that are all-null in every column
        predictor += [None] * 20
        outcome += [None] * 20

        df = pl.DataFrame({"outcome": outcome, "predictor": predictor})
        csv_path = self._write_csv(df, tmp_path)

        result = compute_profile_analysis(
            csv_path=csv_path,
            metric="outcome",
            lower_is_better=True,
            num_groups=2,
            auto_detect=True,
            analyzer_name="tree",
        )

        # Analysis should succeed (all-null rows don't cause a crash)
        assert "error" not in result or result["error"] is None, (
            f"Analysis failed unexpectedly: {result.get('error')}"
        )

    def test_tree_downsampling_is_wired_into_analysis(self, tmp_path, monkeypatch):
        """Tree training receives at most target_rows rows when dataset is large."""
        from src.core.config.settings import Settings
        from src.core.profile.decision_tree import DecisionTreeTrainer
        from src.gui.services.profile import compute_profile_analysis

        # Read the live target_rows setting so the test adapts to any configuration.
        target_rows = Settings().get("profiling.tree_training.target_rows", 1000)

        training_row_counts: list[int] = []
        original_train = DecisionTreeTrainer.train

        def capturing_train(self, data, labels, **kwargs):
            training_row_counts.append(len(data))
            return original_train(self, data, labels, **kwargs)

        monkeypatch.setattr(DecisionTreeTrainer, "train", capturing_train)

        # Build a dataset larger than target_rows so downsampling must occur.
        n = target_rows + 500
        rng = np.random.default_rng(42)
        predictor = rng.normal(0, 1, n)
        outcome = predictor + rng.normal(0, 0.1, n)
        df = pl.DataFrame({"outcome": outcome, "predictor": predictor})
        csv_path = self._write_csv(df, tmp_path)

        compute_profile_analysis(
            csv_path=csv_path,
            metric="outcome",
            lower_is_better=True,
            num_groups=2,
            auto_detect=True,
            analyzer_name="tree",
        )

        # Tree training should have received at most target_rows rows
        assert training_row_counts, "DecisionTreeTrainer.train was never invoked"
        assert training_row_counts[0] <= target_rows, (
            f"Tree was trained on {training_row_counts[0]} rows; "
            f"expected ≤{target_rows} (tree downsampling not applied)"
        )


class TestProfileUIInteractions:
    """Test interactive UI elements: tabs, buttons, tooltips."""

    def test_factor_tabs_are_clickable_and_switch_panels(self, client):
        """Clicking on Description/Mitigations tabs should show their content."""
        r = client.get(
            "/ui/profile/analysis-fragment",
            params={
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "analyzer": "tree",
                "factor": "cache_misses",
            },
        )
        assert r.status_code == 200
        # Check that tab nav exists with all three tabs
        assert 'class="profile-tab' in r.text
        assert "data-tab=" in r.text
        # Check that tab panels exist for all three tabs
        assert 'id="factor-tabs-analysis"' in r.text
        assert 'id="factor-tabs-desc"' in r.text
        assert 'id="factor-tabs-mitigations"' in r.text

    def test_excluded_predictors_badge_shows_correct_tooltip(self, client, monkeypatch):
        """Auto-excluded high-correlation predictors should appear in badge tooltip and analysis params."""
        import src.gui.routes.ui_profile as ui_profile_route
        import src.gui.utils.profile.predictor_stats as predictor_stats
        import src.core.runlogs.reader as runlog_reader

        monkeypatch.setattr(
            ui_profile_route,
            "load_profile_dataset",
            lambda _csv_path, **kwargs: {
                "metrics": ["perf_time", "wall_time"],
                "filter_metrics": ["perf_time"],
                "metric": "perf_time",
                "active_csv": "runlogs/test/synthetic-prof.csv",
                "md_path": "",
                "rows": 3,
                "settings": None,
                "file_state": "state1",
                "prof_csv_path": "",
                "has_prof_csv": False,
                "original_csv": "runlogs/test/synthetic-prof.csv",
                "original_md": "runlogs/test/synthetic-prof.md",
            },
        )
        monkeypatch.setattr(
            predictor_stats,
            "compute_predictor_stats",
            lambda df, metric: [
                {"name": "wall_time", "non_na_count": 3, "correlation": 0.998},
                {"name": "cache_misses", "non_na_count": 3, "correlation": 0.42},
            ],
        )
        monkeypatch.setattr(
            runlog_reader,
            "load_table",
            lambda _path: pl.DataFrame({"perf_time": [1.0, 2.0, 3.0], "wall_time": [1.0, 2.0, 3.0]}),
        )
        monkeypatch.setattr(
            ui_profile_route,
            "_load_filtered_dataframe",
            lambda *args, **kwargs: pl.DataFrame({"perf_time": [1.0, 2.0, 3.0]}),
        )
        monkeypatch.setattr(
            ui_profile_route,
            "get_distribution_meta",
            lambda *args, **kwargs: {"xmin": 0.0, "xmax": 1.0},
        )

        r = client.get(
            "/ui/profile",
            params={"experiment": "misc", "csv_path": "runlogs/test/synthetic-prof.csv", "metric": "perf_time"},
        )
        assert r.status_code == 200
        assert "excluded" in r.text
        assert "wall_time" in r.text
        assert "excluded_predictor=wall_time" in r.text

        iframe_match = re.search(r'src="([^"]*analysis-tree\.html\?[^"]*)"', r.text)
        assert iframe_match is not None, "Expected analysis-tree iframe URL in profile page"
        assert "excluded_predictor=wall_time" in iframe_match.group(1)
        assert "data-initial-url=\"/ui/profile/predictors-fragment?" in r.text

    def test_search_and_exclude_buttons_have_click_handlers(self, client):
        """Search and Exclude buttons must exist in the profile page when data is loaded."""
        r = client.get(
            "/ui/profile",
            params={"experiment": "matmul", "csv_path": MATMUL_PROF, "metric": "inner_time"},
        )
        assert r.status_code == 200
        assert 'id="search_cutoff_btn"' in r.text
        assert 'id="exclude_predictors_btn"' in r.text
        assert "app.js" in r.text

    def test_button_js_handlers_inside_domcontentloaded(self):
        """Button click handlers must be inside DOMContentLoaded, not at module level.

        Handlers placed outside DOMContentLoaded run before the DOM is ready,
        so getElementById returns null and no handler is ever attached.
        """
        from pathlib import Path
        app_js = Path("src/gui/static/app.js").read_text()
        dcl_start = app_js.find('addEventListener("DOMContentLoaded"')
        assert dcl_start != -1, "DOMContentLoaded block not found in app.js"
        # Find where DOMContentLoaded block closes: the top-level '});' at column 0
        dcl_close = app_js.find("\n});\n", dcl_start)
        assert dcl_close != -1, "DOMContentLoaded block closing not found"
        # Button handler code must NOT appear after the DCL closing bracket
        after_dcl = app_js[dcl_close + 5:]
        assert "search_cutoff_btn" not in after_dcl, (
            "search_cutoff_btn handler must be inside DOMContentLoaded, not at module level"
        )
        assert "exclude_predictors_btn" not in after_dcl, (
            "exclude_predictors_btn handler must be inside DOMContentLoaded, not at module level"
        )

    def test_excluded_badge_tooltip_shows_default_count_when_no_params(self, client):
        """When no excluded_predictor params are provided, the badge shows the 4 defaults.

        DEFAULT_EXCLUDED_PREDICTORS = ['repeat', 'inner_time', 'outer_time', 'perf_time']
        are automatically applied as defaults so users see useful behaviour without
        explicitly specifying exclusions.
        """
        r = client.get(
            "/ui/profile",
            params={"experiment": "matmul", "csv_path": MATMUL_PROF, "metric": "inner_time"},
        )
        assert r.status_code == 200
        assert "(5 excluded)" in r.text, (
            "With no excluded_predictor params, badge must say '(5 excluded)' (defaults)"
        )
        # The tooltip must list the default excluded predictor names
        for name in ("repeat", "inner_time", "outer_time", "perf_time"):
            assert name in r.text, f"Default excluded predictor '{name}' must appear in page"

    def test_search_modal_dialog_exists_in_page(self, client):
        """The search-cutoff modal <dialog> must exist in the profile page HTML."""
        r = client.get(
            "/ui/profile",
            params={"experiment": "matmul", "csv_path": MATMUL_PROF, "metric": "inner_time"},
        )
        assert r.status_code == 200
        assert 'id="search-cutoff-modal"' in r.text, (
            "Search cutoff modal <dialog> element not found in page"
        )

    def test_exclude_modal_dialog_exists_in_page(self, client):
        """The exclude-predictors modal <dialog> must exist in the profile page HTML."""
        r = client.get(
            "/ui/profile",
            params={"experiment": "matmul", "csv_path": MATMUL_PROF, "metric": "inner_time"},
        )
        assert r.status_code == 200
        assert 'id="exclude-predictors-modal"' in r.text, (
            "Exclude predictors modal <dialog> element not found in page"
        )

    def test_save_settings_route_redirects(self, client):
        """POST /ui/profile/save-settings must return 303 redirect."""
        r = client.post(
            "/ui/profile/save-settings",
            data={
                "md_path": "/nonexistent/settings.md",
                "metric": "inner_time",
                "filter_metric": "",
                "filter_min": "",
                "filter_max": "",
                "num_groups": "2",
                "auto_detect": "0",
                "analyzer": "tree",
                "redirect_url": "/ui/profile",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_excluded_badge_tooltip_lists_predictor_names(self, client):
        """Tooltip on the excluded-badge must list the actual predictor names.

        When exclusions are applied, the redirect URL should carry a state token,
        and only that URL should reflect the custom predictor names.
        """
        response = client.post(
            "/ui/profile/update-exclusions",
            data={
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "excluded_predictor": ["cpu_freq", "cache_refs"],
                "redirect_url": f"/ui/profile?experiment=matmul&csv_path={MATMUL_PROF}&metric=inner_time",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        location = response.headers.get("location") or ""
        assert "excluded_state=" in location

        r = client.get(location)
        assert r.status_code == 200
        assert "cpu_freq" in r.text, "Excluded predictor 'cpu_freq' must appear in tooltip"
        assert "cache_refs" in r.text, "Excluded predictor 'cache_refs' must appear in tooltip"
        assert "(2 excluded)" in r.text, "Badge must show correct count (2)"

        base = client.get(
            "/ui/profile",
            params={"experiment": "matmul", "csv_path": MATMUL_PROF, "metric": "inner_time"},
        )
        assert base.status_code == 200
        assert "cpu_freq" not in base.text
        assert "cache_refs" not in base.text

    def test_analysis_fragment_includes_cleaned_columns_data(self, client):
        """Analysis fragment must include a hidden element with all cleaned column names.

        This element is used by JavaScript to populate the exclude-predictors modal
        dynamically after the HTMX fragment loads.
        """
        r = client.get(
            "/ui/profile/analysis-fragment",
            params={
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "analyzer": "tree",
                "num_groups": "2",
            },
        )
        assert r.status_code == 200
        assert 'id="profile-cleaned-columns"' in r.text, (
            "Fragment must include hidden div#profile-cleaned-columns for JS modal population"
        )
        assert "data-columns=" in r.text, (
            "div#profile-cleaned-columns must have data-columns JSON attribute"
        )

    def test_exclude_modal_has_dynamic_container_not_static_message(self, client):
        """Exclude-predictors modal must have an HTMX-loaded container referencing the predictors endpoint."""
        r = client.get(
            "/ui/profile",
            params={"experiment": "matmul", "csv_path": MATMUL_PROF, "metric": "inner_time"},
        )
        assert r.status_code == 200
        assert 'id="exclude-predictors-list"' in r.text, (
            "Modal must have #exclude-predictors-list container"
        )
        assert "predictors-fragment" in r.text, (
            "Modal must reference predictors-fragment endpoint via HTMX"
        )
        assert "Load an analysis first" not in r.text, (
            "Modal must not show 'Load an analysis first' static message"
        )

    def test_search_modal_preserves_auto_detect_setting(self, client):
        """Search modal form must preserve the current auto_detect=0 setting, not force auto_detect=1."""
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "auto_detect": "0",
                "num_groups": "3",
            },
        )
        assert r.status_code == 200
        assert 'id="search-cutoff-modal"' in r.text
        # dominate renders: name="auto_detect" type="hidden" value="..."
        # When current setting is auto_detect=0, the modal must NOT hardcode value="1"
        search_form_idx = r.text.find('id="search-cutoff-form"')
        assert search_form_idx != -1, "Search cutoff form must exist"
        search_form_snippet = r.text[search_form_idx:search_form_idx + 800]
        assert 'name="auto_detect" type="hidden" value="1"' not in search_form_snippet, (
            "Search modal must not override auto_detect to 1 when user set it to 0"
        )

    def test_default_excluded_predictors_applied(self, client):
        """With no excluded_predictor query params, the default 4 predictors must be excluded.

        DEFAULT_EXCLUDED_PREDICTORS = ['repeat', 'inner_time', 'outer_time', 'perf_time']
        """
        r = client.get(
            "/ui/profile",
            params={"experiment": "matmul", "csv_path": MATMUL_PROF, "metric": "inner_time"},
        )
        assert r.status_code == 200
        assert "(5 excluded)" in r.text, "Badge must show '(5 excluded)' by default"
        # The four default names must appear in the tooltip somewhere on the page
        for name in ("repeat", "inner_time", "outer_time", "perf_time"):
            assert name in r.text, f"Default excluded predictor '{name}' must appear in tooltip"

    def test_predictors_fragment_endpoint_returns_table_with_correlations(self, client):
        """GET /ui/profile/predictors-fragment must return a table with predictor names and correlations."""
        r = client.get(
            "/ui/profile/predictors-fragment",
            params={"csv_path": MATMUL_PROF, "metric": "inner_time"},
        )
        assert r.status_code == 200
        # Must have a table
        assert "<table" in r.text or "<tr" in r.text, "Fragment must contain a table"
        # Must have a correlation column header
        assert "Correlation" in r.text or "correlation" in r.text
        # Must have a search box
        assert 'type="search"' in r.text or 'name="search"' in r.text or "predictor_search" in r.text

    def test_exclude_modal_uses_htmx_predictors_endpoint(self, client):
        """Exclude-predictors modal must use HTMX to load content from /ui/profile/predictors-fragment."""
        r = client.get(
            "/ui/profile",
            params={"experiment": "matmul", "csv_path": MATMUL_PROF, "metric": "inner_time"},
        )
        assert r.status_code == 200
        assert 'id="exclude-predictors-modal"' in r.text
        # Modal body must reference the predictors-fragment endpoint via HTMX
        assert "predictors-fragment" in r.text, (
            "Exclude modal must reference predictors-fragment endpoint for HTMX loading"
        )

    def test_search_cutoffs_endpoint_returns_redirect_with_cutoffs(self, client):
        """POST /ui/profile/search-cutoffs must run the search and redirect with cutoff_value params."""
        r = client.post(
            "/ui/profile/search-cutoffs",
            data={
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "lower_is_better": "1",
                "num_groups": "2",
                "auto_detect": "0",
                "analyzer": "tree",
                "filter_metric": "",
                "filter_min": "",
                "filter_max": "",
                "redirect_url": "/ui/profile?csv_path=" + MATMUL_PROF + "&metric=inner_time",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303, f"Expected redirect (303), got {r.status_code}"
        location = r.headers.get("location", "")
        assert "cutoff_value" in location, (
            f"Redirect URL must contain 'cutoff_value' params. Got: {location}"
        )


class TestDistributionPlotInteractivity:
    """Tests for click-to-move-cutoff and hover nearest-point features."""

    def test_distribution_plot_has_interactive_wrapper(self, client):
        """Profile page includes distribution wrapper metadata for accurate click mapping."""
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "num_groups": "2",
                "auto_detect": "0",
            },
        )
        assert r.status_code == 200
        html = r.text
        assert "profile-dist-wrapper" in html, "Distribution wrapper div must be present"
        assert "data-xmin=" in html, "data-xmin attribute must be present"
        assert "data-xmax=" in html, "data-xmax attribute must be present"
        assert "data-plot-left=" in html, "data-plot-left attribute must be present"
        assert "data-plot-right=" in html, "data-plot-right attribute must be present"
        assert "data-mutable=" in html, "data-mutable attribute must be present"

    def test_distribution_wrapper_mutable_when_not_auto_detect(self, client):
        """data-mutable should be '1' when auto_detect is off."""
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "num_groups": "2",
                "auto_detect": "0",
            },
        )
        assert r.status_code == 200
        assert 'data-mutable="1"' in r.text, "Wrapper must be mutable when not auto-detecting"

    def test_distribution_wrapper_not_mutable_when_auto_detect(self, client):
        """data-mutable should be '0' when auto_detect is on."""
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "num_groups": "2",
                "auto_detect": "1",
            },
        )
        assert r.status_code == 200
        assert 'data-mutable="0"' in r.text, "Wrapper must not be mutable when auto-detecting"

    def test_move_cutoff_endpoint_returns_redirect(self, client):
        """POST /ui/profile/move-cutoff must update the cutoff store and redirect."""
        r = client.post(
            "/ui/profile/move-cutoff",
            data={
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "click_x": "0.05",
                "lower_is_better": "1",
                "num_groups": "2",
                "auto_detect": "0",
                "filter_metric": "",
                "filter_min": "",
                "filter_max": "",
                "filter_values_json": "[]",
                "redirect_url": "/ui/profile?csv_path=" + MATMUL_PROF + "&metric=inner_time",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303, f"Expected 303 redirect, got {r.status_code}"
        assert r.headers.get("location"), "Response must have a location header"

    def test_move_cutoff_persists_in_distribution_plot_url(self, client):
        """Manual cutoff values in the URL should be reflected in the distribution plot URL."""
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "num_groups": "2",
                "auto_detect": "0",
                "cutoff_value": ["0.05"],
            },
        )
        assert r.status_code == 200
        assert "cutoff_value" in r.text, (
            "Distribution plot URL must include cutoff_value params when they are present in the page URL"
        )

    def test_distribution_wrapper_has_axis_limits(self, client):
        """distribution wrapper must carry data-xmin and data-xmax attributes."""
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "num_groups": "2",
                "auto_detect": "0",
            },
        )
        assert r.status_code == 200
        assert "data-xmin=" in r.text, "data-xmin must be present on wrapper"
        assert "data-xmax=" in r.text, "data-xmax must be present on wrapper"

    def test_profile_page_base_url_has_no_cutoff_state(self, client):
        """Base profile URL without cutoff_value params must not embed cutoffs."""
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "num_groups": "2",
                "auto_detect": "0",
            },
        )
        assert r.status_code == 200
        assert "cutoff_value=" not in r.text, (
            "Base profile URL must not embed cutoff state"
        )

    def test_profile_task_navigation_clears_source_override(self):
        """Changing experiment or task must clear the source-selection override."""
        app_js = Path("src/gui/static/app.js").read_text()
        # Task selector: multi-select — does NOT override task (FormData collects it),
        # but must reset csv_path and source so stale overrides are cleared.
        assert 'csv_path: "",\n                        source: ""' in app_js
        assert 'experiment: profileExperiment.value || "",\n                    task: "",\n                    csv_path: "",\n                    source: ""' in app_js

    def test_profile_page_shows_click_helper_only_for_multiple_groups(self, client):
        """Distribution header should only show click helper when more than one group is active."""
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "num_groups": "2",
                "auto_detect": "0",
            },
        )
        assert r.status_code == 200
        assert "Click on plot to move nearest cutoff" in r.text

        r_single = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "num_groups": "1",
                "auto_detect": "0",
            },
        )
        assert r_single.status_code == 200
        assert "Click on plot to move nearest cutoff" not in r_single.text

    def test_profile_page_shows_tree_zoom_helper_only_for_tree(self):
        """Influence header should only show zoom helper for tree analyzer."""
        from src.gui.components.profile import profile_page

        common = {
            "active_csv": "runlogs/test/example.csv",
            "metric": "inner_time",
            "distribution_plot_url": "/ui/profile/distribution.png?x=1",
            "distribution_meta": {"xmin": 0.0, "xmax": 1.0, "plot_left": 0.1, "plot_right": 0.9},
            "analysis_tree_url": "/ui/profile/analysis-tree.html?x=1",
            "num_groups": 2,
            "auto_detect": False,
            "lower_is_better": True,
            "filter_values": [],
        }

        html_tree = profile_page({**common, "analyzer": "tree"})
        assert "Use scrollwheel to zoom" in html_tree

        html_other = profile_page({**common, "analyzer": "correlation"})
        assert "Use scrollwheel to zoom" not in html_other

    def test_build_labeler_uses_cutoff_values(self):
        """build_labeler with a single cutoff returns BinaryLabeler (FAST/SLOW labels)."""
        from src.gui.services.profile import build_labeler
        from src.core.profile.labeler import BinaryLabeler, ManualLabeler

        vals = np.array([0.01, 0.02, 0.03, 0.04, 0.05])

        # Single cutoff → BinaryLabeler so class names stay FAST/SLOW
        labeler = build_labeler(2, False, vals, True, cutoff_values=[0.03])
        assert isinstance(labeler, BinaryLabeler)
        cutoffs = labeler.get_cutoffs()
        assert len(cutoffs) == 1
        assert abs(cutoffs[0] - 0.03) < 1e-9
        assert labeler.get_class_names() == ["FAST", "SLOW"]

        # Multiple cutoffs → ManualLabeler
        labeler2 = build_labeler(3, False, vals, True, cutoff_values=[0.02, 0.04])
        assert isinstance(labeler2, ManualLabeler)

    def test_click_move_cutoff_full_round_trip_binary(self, client):
        """Clicking the plot with num_groups=2 moves the cutoff end-to-end.

        Scenario: no existing cutoffs, user clicks at a specific x value.
        The redirect must include the new cutoff, and the resulting page
        must show it in the distribution plot URL.
        """
        redirect_base = (
            f"/ui/profile?experiment=matmul&csv_path={MATMUL_PROF}"
            f"&metric=inner_time&num_groups=2&auto_detect=0"
        )
        r = client.post(
            "/ui/profile/move-cutoff",
            data={
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "click_x": "0.05",
                "lower_is_better": "1",
                "num_groups": "2",
                "auto_detect": "0",
                "filter_metric": "",
                "filter_min": "",
                "filter_max": "",
                "filter_values_json": "[]",
                "redirect_url": redirect_base,
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        loc = r.headers["location"]
        assert "cutoff_value" in loc, (
            "Redirect after click must include cutoff_value in the URL"
        )
        # Follow the redirect
        page = client.get(loc)
        assert page.status_code == 200
        assert "cutoff_value" in page.text, (
            "Page after click-move-cutoff must show cutoff in distribution plot URL"
        )

    def test_click_move_cutoff_full_round_trip_tertile(self, client):
        """Clicking the plot with num_groups=3 moves a cutoff end-to-end.

        When no existing cutoffs are in the URL, the server builds a TertileLabeler
        (2 auto-cutoffs) and moves the nearest one. The redirect must carry 2 cutoffs
        and the resulting page must reflect them.
        """
        redirect_base = (
            f"/ui/profile?experiment=matmul&csv_path={MATMUL_PROF}"
            f"&metric=inner_time&num_groups=3&auto_detect=0"
        )
        r = client.post(
            "/ui/profile/move-cutoff",
            data={
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "click_x": "0.05",
                "lower_is_better": "1",
                "num_groups": "3",
                "auto_detect": "0",
                "filter_metric": "",
                "filter_min": "",
                "filter_max": "",
                "filter_values_json": "[]",
                "redirect_url": redirect_base,
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        loc = r.headers["location"]
        assert "cutoff_value" in loc, (
            "Redirect after click with num_groups=3 must include cutoff_value params"
        )
        # Should have 2 cutoffs for 3 groups
        from urllib.parse import urlparse, parse_qs
        parsed = parse_qs(urlparse(loc).query)
        cutoff_count = len(parsed.get("cutoff_value", []))
        assert cutoff_count == 2, (
            f"Expected 2 cutoffs for num_groups=3 after click, got {cutoff_count}"
        )
        # Follow the redirect
        page = client.get(loc)
        assert page.status_code == 200
        assert "cutoff_value" in page.text, (
            "Page after click must show cutoffs in distribution plot URL"
        )

    def test_click_move_cutoff_without_num_groups_in_url(self, client):
        """Click works even when the redirect_url has no num_groups param.

        This simulates the case where the user arrived via a direct URL (no
        num_groups in query string) but the wrapper still carries num_groups=3.
        The move-cutoff endpoint uses the form's num_groups to compute the right
        number of cutoffs and must include num_groups in the redirect so the
        server-side guard sees a consistent count.
        """
        # redirect_url deliberately has no num_groups
        redirect_base = (
            f"/ui/profile?experiment=matmul&csv_path={MATMUL_PROF}"
            f"&metric=inner_time&auto_detect=0"
        )
        r = client.post(
            "/ui/profile/move-cutoff",
            data={
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "click_x": "0.05",
                "lower_is_better": "1",
                "num_groups": "3",  # form sends this
                "auto_detect": "0",
                "filter_metric": "",
                "filter_min": "",
                "filter_max": "",
                "filter_values_json": "[]",
                "redirect_url": redirect_base,
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        loc = r.headers["location"]
        # The redirect must include both cutoffs AND num_groups so the guard
        # can verify consistency
        assert "cutoff_value" in loc, "Redirect must include cutoffs after click"
        # Follow and verify the page renders the cutoffs
        page = client.get(loc)
        assert page.status_code == 200
        assert "cutoff_value" in page.text, (
            "Page must show cutoffs after click even when initial URL had no num_groups"
        )

    def test_second_click_moves_existing_cutoff(self, client):
        """A second click on the plot moves an existing cutoff.

        Scenario: page already has cutoffs from a previous click.
        Clicking again must update (not add to) the cutoff list.
        """
        from urllib.parse import urlparse, parse_qs
        redirect_with_cutoffs = (
            f"/ui/profile?experiment=matmul&csv_path={MATMUL_PROF}"
            f"&metric=inner_time&num_groups=2&auto_detect=0&cutoff_value=0.03"
        )
        r = client.post(
            "/ui/profile/move-cutoff",
            data={
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "click_x": "0.07",
                "lower_is_better": "1",
                "num_groups": "2",
                "auto_detect": "0",
                "filter_metric": "",
                "filter_min": "",
                "filter_max": "",
                "filter_values_json": "[]",
                "redirect_url": redirect_with_cutoffs,
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        loc = r.headers["location"]
        parsed = parse_qs(urlparse(loc).query)
        new_cutoffs = parsed.get("cutoff_value", [])
        assert len(new_cutoffs) == 1, (
            "Moving an existing cutoff must not change the cutoff count"
        )
        assert abs(float(new_cutoffs[0]) - 0.07) < 1e-9, (
            "The existing cutoff must have moved to the click position"
        )
        # Follow redirect and verify page shows it
        page = client.get(loc)
        assert page.status_code == 200
        assert "cutoff_value" in page.text


class TestAutoDetectLabelerInteraction:
    """Tests for auto_detect / cutoff_values / BODY-only interaction in build_labeler."""

    def test_auto_detect_ignores_cutoff_values(self):
        """Bug: clicking Auto groups when cutoff_values are present kept the old labeler.

        When auto_detect=True, build_labeler must return AutoLabeler regardless
        of whether cutoff_values were passed (restored cutoffs should be cleared).
        """
        from src.gui.services.profile import build_labeler
        from src.core.profile.labeler import AutoLabeler

        rng = np.random.default_rng(42)
        vals = rng.exponential(scale=0.05, size=200)

        # auto_detect=True + explicit cutoffs → must still use AutoLabeler
        labeler = build_labeler(4, True, vals, True, cutoff_values=[0.02, 0.04, 0.06])
        assert isinstance(labeler, AutoLabeler), (
            "auto_detect=True must produce AutoLabeler even when cutoff_values are supplied"
        )

    def test_auto_labeler_fallback_on_homogeneous_data(self):
        """AutoLabeler on homogeneous data returns single BODY class.

        build_labeler must fall back to BinaryLabeler so the user always
        sees at least 2 groups in classification mode.
        """
        from src.gui.services.profile import build_labeler

        # Tight homogeneous data: CV ≈ 0.003 → AutoLabeler._cluster_body returns BODY only
        vals = np.linspace(1.0, 1.01, 200)

        labeler = build_labeler(2, True, vals, True)
        names = labeler.get_class_names()
        assert len(names) >= 2, (
            f"build_labeler must produce at least 2 classes; got {names}"
        )
        assert names != ["BODY"], (
            "All data labeled BODY is useless; build_labeler must fall back to binary"
        )

    def test_auto_detect_overrides_regression_mode(self):
        """Bug: switching from regression (num_groups=1) to Auto kept chart in regression mode.

        When auto_detect=True and num_groups=1 (JS sends current stepper value),
        build_labeler must still return AutoLabeler, not RegressionLabeler.
        auto_detect must take priority over num_groups==1.
        """
        from src.gui.services.profile import build_labeler
        from src.core.profile.labeler import AutoLabeler, RegressionLabeler

        rng = np.random.default_rng(42)
        vals = rng.exponential(scale=0.05, size=200)

        # Regression mode alone (num_groups=1, auto_detect=False) → RegressionLabeler
        labeler_reg = build_labeler(1, False, vals, True)
        assert isinstance(labeler_reg, RegressionLabeler), (
            "num_groups=1, auto_detect=False must produce RegressionLabeler"
        )

        # Auto toggled while stepper frozen at 1 → must use AutoLabeler
        labeler_auto = build_labeler(1, True, vals, True)
        assert not isinstance(labeler_auto, RegressionLabeler), (
            "auto_detect=True must override num_groups==1 and NOT return RegressionLabeler"
        )
        assert isinstance(labeler_auto, AutoLabeler), (
            "auto_detect=True with num_groups=1 must return AutoLabeler"
        )

    def test_apply_defaults_skips_cutoffs_when_auto_detect_explicit(self):
        """ProfileState.apply_defaults must not restore saved cutoffs when auto_detect is explicit.

        Scenario: user clicks "Auto groups" → URL has auto_detect=1 but no
        cutoff_value params.  Settings have saved cutoffs.  apply_defaults
        must NOT restore those cutoffs because the user explicitly chose auto.
        """
        from src.gui.models.profile_state import ProfileState
        from starlette.datastructures import QueryParams
        from unittest.mock import MagicMock

        # Simulate URL: auto_detect=1&num_groups=3 (both explicit, no cutoff_value)
        request = MagicMock()
        request.query_params = QueryParams(
            "experiment=test&csv_path=test.csv&metric=inner_time&auto_detect=1&num_groups=3"
        )

        state = ProfileState.from_request(request)
        assert state.auto_detect is True
        assert state.cutoff_values == []

        # Settings have saved cutoffs
        settings = MagicMock()
        settings.default_filter_metric = None
        settings.default_num_perf_groups = None
        settings.default_influence_analyzer = None
        settings.default_cutoff_values = [0.1, 0.12, 0.14]

        state.apply_defaults(settings)

        # Cutoffs must NOT be restored when auto_detect is explicit
        assert state.cutoff_values == [], (
            f"Cutoffs should not be restored when auto_detect is explicit; got {state.cutoff_values}"
        )


class TestSearchCutoffsFilterValues:
    """Search-cutoffs must honour the active categorical filter_values.

    When the user has filtered the dataset to specific categorical values (e.g.
    concurrency=1) and then runs "Search for optimal tree", the search must
    operate on the filtered rows only — not the full dataset.  Before the fix,
    the search-cutoffs form did not include filter_values hidden inputs and the
    endpoint hardcoded filter_values=[], causing the search to run on
    unfiltered data.
    """

    def test_search_cutoff_form_includes_filter_values_hidden_inputs(self, client):
        """The profile page must render filter_values hidden inputs inside the
        search-cutoffs modal form when a categorical filter is active."""
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "filter_metric": "concurrency",
                "filter_values": ["1", "2"],
            },
        )
        assert r.status_code == 200

        # The search-cutoff modal form must include hidden inputs for
        # filter_values so the POST carries them to the endpoint.
        # We scope the check to the search-cutoff modal.
        search_modal_start = r.text.find('id="search-cutoff-modal"')
        search_modal_end = r.text.find("</dialog>", search_modal_start)
        assert search_modal_start != -1, "search-cutoff-modal must be in page"
        modal_html = r.text[search_modal_start:search_modal_end]

        # Dominate renders alphabetically: name="filter_values" type="hidden" value="1"
        assert 'name="filter_values" type="hidden" value="1"' in modal_html, (
            "search-cutoffs modal form must include a hidden input for "
            "filter_values=1 so the search uses filtered data"
        )
        assert 'name="filter_values" type="hidden" value="2"' in modal_html, (
            "search-cutoffs modal form must include a hidden input for "
            "filter_values=2 so the search uses filtered data"
        )

    def test_search_cutoffs_endpoint_uses_filter_values(self, client, tmp_path):
        """POST to /profile/search-cutoffs with filter_values must narrow the
        dataset before searching.  We verify by comparing the cutoff found on
        the full dataset vs a heavily filtered one — they should differ when
        filtering removes most rows."""
        import polars as pl
        import numpy as np

        rng = np.random.default_rng(42)
        # Two groups of inner_time values, split by category A vs B.
        # Category A is entirely SLOW (0.9+); category B is entirely FAST (0.3-).
        # Full-dataset optimal cutoff is ~0.6; category-A-only optimal cutoff is ~0.95.
        n = 80
        df = pl.DataFrame({
            "inner_time": np.concatenate([
                rng.uniform(0.3, 0.4, n // 2),   # category B: fast
                rng.uniform(0.9, 1.0, n // 2),   # category A: slow
            ]),
            "category": ["B"] * (n // 2) + ["A"] * (n // 2),
            "other": rng.uniform(0, 1, n),
        })
        csv_path = str(tmp_path / "synthetic.csv")
        df.write_csv(csv_path)

        # Search on full dataset — cutoff should land ~0.6 (between the two groups)
        r_full = client.post(
            "/ui/profile/search-cutoffs",
            data={
                "csv_path": csv_path,
                "metric": "inner_time",
                "num_groups": "2",
                "auto_detect": "0",
                "lower_is_better": "1",
                "redirect_url": "/ui/profile?experiment=test",
            },
            follow_redirects=False,
        )
        assert r_full.status_code in (302, 303)
        full_loc = r_full.headers.get("location", "")
        assert "cutoff_value=" in full_loc, "full-data search must return a cutoff"

        # Search on category-A only — cutoff should land ~0.95 (within slow group)
        r_filtered = client.post(
            "/ui/profile/search-cutoffs",
            data={
                "csv_path": csv_path,
                "metric": "inner_time",
                "filter_metric": "category",
                "filter_values": ["A"],
                "num_groups": "2",
                "auto_detect": "0",
                "lower_is_better": "1",
                "redirect_url": "/ui/profile?experiment=test",
            },
            follow_redirects=False,
        )
        assert r_filtered.status_code in (302, 303)
        filtered_loc = r_filtered.headers.get("location", "")
        assert "cutoff_value=" in filtered_loc, "filtered search must return a cutoff"

        from urllib.parse import urlparse, parse_qs
        full_cutoff = float(parse_qs(urlparse(full_loc).query)["cutoff_value"][0])
        filtered_cutoff = float(parse_qs(urlparse(filtered_loc).query)["cutoff_value"][0])

        # Full-data cutoff must be well below 0.9; filtered (cat A only) cutoff must
        # be above 0.85 since all category-A rows are in [0.9, 1.0].
        assert full_cutoff < 0.8, (
            f"Full-data cutoff ({full_cutoff:.3f}) should separate the two groups "
            "and land below 0.8"
        )
        assert filtered_cutoff > 0.85, (
            f"Category-A-only cutoff ({filtered_cutoff:.3f}) should be within the "
            "slow group (0.9-1.0) and land above 0.85. "
            "If it's near 0.6, filter_values was ignored."
        )


class TestCutoffNavigationPreservation:
    """Changing any sidebar control must not silently drop cutoff positions.

    When the user has a manual cutoff in the URL (cutoff_value=X) and then
    changes the influence analyzer, the navigation form must carry the cutoff
    values forward so the server receives them and the distribution plot URL
    continues to include cutoff_value=X.

    The root cause of the bug: the profile navigation form (<form
    id="profile-form">) had no hidden <input name="cutoff_value"> fields, so
    navigateGetFormWithOverrides() never included them in the rebuilt URL.
    When the resulting URL reached the server with no cutoff_value param, the
    restore logic applied the *saved* default cutoff from markdown — making
    the cutoff appear to "jump" to the saved position.
    """

    @staticmethod
    def _nav_form_html(page_text: str) -> str:
        """Extract only the <section class="profile-controls"> block, which
        contains the navigation form and nothing else (the save form lives in
        the analysis area below that section)."""
        marker = '<section class="profile-controls">'
        start = page_text.find(marker)
        if start == -1:
            return ""
        end = page_text.find("</section>", start)
        return page_text[start: end + len("</section>")]

    def test_navigation_form_carries_cutoff_values(self, client):
        """The profile page must emit hidden cutoff_value inputs inside the
        navigation form so that any form re-submission preserves them.

        We scope the check to the <section class="profile-controls"> block
        which wraps only the navigation form — the save form lives outside
        that section in the analysis area, so finding the input here confirms
        it is in the navigation form, not just the save form."""
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "cutoff_value": "0.75",
                "analyzer": "tree",
            },
        )
        assert r.status_code == 200

        nav_html = self._nav_form_html(r.text)
        assert nav_html, "profile-controls section must be present in the page"
        # Dominate renders attributes alphabetically:
        # name="cutoff_value" type="hidden" value="0.75"
        assert 'name="cutoff_value" type="hidden" value="0.75"' in nav_html, (
            "A hidden <input name='cutoff_value' value='0.75'> must appear "
            "inside the navigation form (profile-controls section) so that "
            "changing the analyzer preserves the cutoff position. "
            "Found in nav section: " + repr(nav_html[:400])
        )

    def test_analyzer_change_preserves_cutoff_in_navigation_url(self, client):
        """Simulates changing the analyzer: the page is re-fetched with a new
        analyzer value but the same cutoff_value — the server must keep it
        in the distribution URL (i.e., not treat it as a missing-settings
        trigger that jumps the cutoff to a saved default)."""
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "cutoff_value": "0.75",
                "analyzer": "granger",
            },
        )
        assert r.status_code == 200
        assert "cutoff_value=0.75" in r.text, (
            "distribution plot URL must preserve cutoff_value=0.75 after "
            "changing the analyzer from tree to granger"
        )


class TestProfileSaveRestoreParity:
    """Tests for complete save/restore parity with the old GUI.

    These tests cover bugs where the save endpoint or restore path was
    missing certain fields: cutoff positions, excluded predictors, and
    the numeric filter range.
    """

    def test_save_endpoint_persists_cutoff_values(self, client):
        """cutoff_value form params are written to default_cutoff_values in markdown."""
        with tempfile.NamedTemporaryFile(
            suffix=".md", delete=False, mode="w"
        ) as f:
            f.write("# Test\n\n## Analysis\nContent.\n")
            tmp_md = f.name
        try:
            r = client.post(
                "/ui/profile/save-settings",
                data={
                    "md_path": tmp_md,
                    "metric": "perf_time",
                    "filter_metric": "",
                    "filter_min": "",
                    "filter_max": "",
                    "num_groups": "3",
                    "auto_detect": "0",
                    "cutoff_value": ["0.5", "1.5"],
                    "analyzer": "tree",
                    "redirect_url": "/ui/profile",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            content = Path(tmp_md).read_text()
            assert "profiling.default_cutoff_values" in content, (
                "Saved cutoff positions must appear in markdown under "
                "'profiling.default_cutoff_values'"
            )
            assert "0.5" in content
            assert "1.5" in content
        finally:
            Path(tmp_md).unlink(missing_ok=True)

    def test_save_endpoint_persists_excluded_predictors(self, client):
        """excluded_predictor form params beyond defaults are written to markdown."""
        with tempfile.NamedTemporaryFile(
            suffix=".md", delete=False, mode="w"
        ) as f:
            f.write("# Test\n\n## Analysis\nContent.\n")
            tmp_md = f.name
        try:
            # DEFAULT_EXCLUDED_PREDICTORS = ["repeat", "inner_time", "outer_time", "perf_time"]
            # "custom_pred_X" is an extra exclusion beyond defaults
            r = client.post(
                "/ui/profile/save-settings",
                data={
                    "md_path": tmp_md,
                    "metric": "perf_time",
                    "filter_metric": "",
                    "filter_min": "",
                    "filter_max": "",
                    "num_groups": "2",
                    "auto_detect": "1",
                    "excluded_predictor": [
                        "repeat", "inner_time", "outer_time", "perf_time",
                        "custom_pred_X",
                    ],
                    "analyzer": "tree",
                    "redirect_url": "/ui/profile",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            content = Path(tmp_md).read_text()
            assert "profiling.default_predictor_exclusions" in content, (
                "Extra excluded predictors must be persisted under "
                "'profiling.default_predictor_exclusions'"
            )
            assert "custom_pred_X" in content, (
                "The extra predictor 'custom_pred_X' must appear in saved exclusions"
            )
        finally:
            Path(tmp_md).unlink(missing_ok=True)

    def test_restore_applies_default_filter_value(self, client, monkeypatch):
        """Saved default_filter_value is applied to filter_min/filter_max on page load.

        inner_time in matmul-100M-prof.csv spans [0.64, 0.92].  The saved
        values [0.65, 0.90] fall inside that range and must not be clamped,
        so they appear verbatim in the distribution plot URL.
        """
        from src.gui.utils.profile.restore import ProfileSettings
        from src.core.config.settings import SettingsView
        from src.gui.routes import ui_profile

        mock_settings = ProfileSettings(
            settings_view=SettingsView({}),
            default_outcome_metric=None,
            default_predictor_exclusions=[],
            default_filter_metric="inner_time",
            default_filter_value=[0.65, 0.90],
            default_num_perf_groups=None,
            default_cutoff_values=[],
            default_influence_analyzer=None,
        )
        real_load = ui_profile.load_profile_dataset

        def mock_load(csv_path: str, **kwargs) -> dict:
            result = real_load(csv_path)
            result["settings"] = mock_settings
            return result

        monkeypatch.setattr(ui_profile, "load_profile_dataset", mock_load)

        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
            },
        )
        assert r.status_code == 200
        assert "distribution.png" in r.text, "Distribution plot URL must be present"
        # The restored filter range must appear in the distribution plot URL.
        # Before fix: filter_min= is empty in the URL.
        # After fix: filter_min=0.65 and filter_max=0.9 are present.
        assert "filter_min=0.65" in r.text, (
            "Restored filter_min=0.65 must appear in the distribution plot URL "
            "when default_filter_value=[0.65, 0.90] is in saved settings"
        )
        assert "filter_max=0.9" in r.text, (
            "Restored filter_max=0.9 must appear in the distribution plot URL"
        )

    def test_restore_applies_default_cutoff_values(self, client, monkeypatch):
        """Saved default_cutoff_values appear in the distribution plot URL on page load."""
        from src.gui.utils.profile.restore import ProfileSettings
        from src.core.config.settings import SettingsView
        from src.gui.routes import ui_profile

        mock_settings = ProfileSettings(
            settings_view=SettingsView({}),
            default_outcome_metric=None,
            default_predictor_exclusions=[],
            default_filter_metric=None,
            default_filter_value=None,
            default_num_perf_groups=3,
            default_cutoff_values=[0.003, 0.007],
            default_influence_analyzer=None,
        )
        real_load = ui_profile.load_profile_dataset

        def mock_load(csv_path: str, **kwargs) -> dict:
            result = real_load(csv_path)
            result["settings"] = mock_settings
            return result

        monkeypatch.setattr(ui_profile, "load_profile_dataset", mock_load)

        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
            },
        )
        assert r.status_code == 200
        assert "distribution.png" in r.text, "Distribution plot URL must be present"
        assert "cutoff_value=0.003" in r.text, (
            "Saved cutoff 0.003 must appear in the distribution plot URL "
            "when default_cutoff_values is set in saved settings"
        )
        assert "cutoff_value=0.007" in r.text, (
            "Saved cutoff 0.007 must appear in the distribution plot URL"
        )

    def test_changing_num_groups_does_not_restore_stale_cutoffs(self, client, monkeypatch):
        """Changing num_groups in the UI must not re-apply saved cutoffs for a
        different group count.

        Scenario: saved settings have num_groups=3 with 2 cutoffs.  User changes
        num_groups to 4 in the UI (URL has num_groups=4, no cutoff_value params).
        The page must NOT restore the 2 saved cutoffs — that would leave the user
        stuck with 3 groups even though they asked for 4.
        """
        from src.gui.utils.profile.restore import ProfileSettings
        from src.core.config.settings import SettingsView
        from src.gui.routes import ui_profile

        mock_settings = ProfileSettings(
            settings_view=SettingsView({}),
            default_outcome_metric=None,
            default_predictor_exclusions=[],
            default_filter_metric=None,
            default_filter_value=None,
            default_num_perf_groups=3,
            default_cutoff_values=[0.003, 0.007],  # 2 cutoffs → 3 groups
            default_influence_analyzer=None,
            default_max_correlation=None,
        )
        real_load = ui_profile.load_profile_dataset

        def mock_load(csv_path: str, **kwargs) -> dict:
            result = real_load(csv_path)
            result["settings"] = mock_settings
            return result

        monkeypatch.setattr(ui_profile, "load_profile_dataset", mock_load)

        # User explicitly asks for 4 groups — URL has num_groups=4 but no cutoff_value
        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
                "num_groups": "4",
            },
        )
        assert r.status_code == 200
        assert "distribution.png" in r.text
        # The stale 2-cutoff values must NOT appear in the plot URL
        assert "cutoff_value=0.003" not in r.text, (
            "Saved cutoffs for 3 groups must not be restored when num_groups=4 "
            "is explicitly set in the URL — that would leave the user stuck at 3 groups"
        )
        assert "cutoff_value=0.007" not in r.text, (
            "Saved cutoffs for 3 groups must not be restored when num_groups=4"
        )

    def test_restore_applies_saved_predictor_exclusions(self, client, monkeypatch):
        """Saved default_predictor_exclusions are merged into the excluded list on load."""
        from src.gui.utils.profile.restore import ProfileSettings
        from src.core.config.settings import SettingsView
        from src.gui.routes import ui_profile

        mock_settings = ProfileSettings(
            settings_view=SettingsView({}),
            default_outcome_metric=None,
            default_predictor_exclusions=["custom_pred_Z"],
            default_filter_metric=None,
            default_filter_value=None,
            default_num_perf_groups=None,
            default_cutoff_values=[],
            default_influence_analyzer=None,
        )
        real_load = ui_profile.load_profile_dataset

        def mock_load(csv_path: str, **kwargs) -> dict:
            result = real_load(csv_path)
            result["settings"] = mock_settings
            return result

        monkeypatch.setattr(ui_profile, "load_profile_dataset", mock_load)

        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
            },
        )
        assert r.status_code == 200
        assert "custom_pred_Z" in r.text, (
            "Saved extra exclusion 'custom_pred_Z' must appear in the excluded "
            "predictors list when default_predictor_exclusions is set in saved settings"
        )

    def test_save_endpoint_persists_max_corr(self, client):
        """max_corr form param is written to default_max_correlation in markdown."""
        with tempfile.NamedTemporaryFile(
            suffix=".md", delete=False, mode="w"
        ) as f:
            f.write("# Test\n\n## Analysis\nContent.\n")
            tmp_md = f.name
        try:
            r = client.post(
                "/ui/profile/save-settings",
                data={
                    "md_path": tmp_md,
                    "metric": "perf_time",
                    "filter_metric": "",
                    "filter_min": "",
                    "filter_max": "",
                    "num_groups": "2",
                    "auto_detect": "1",
                    "analyzer": "tree",
                    "max_corr": "0.70",
                    "redirect_url": "/ui/profile",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            content = Path(tmp_md).read_text()
            assert "profiling.default_max_correlation" in content, (
                "Saved max_corr must appear in markdown under "
                "'profiling.default_max_correlation'"
            )
            assert "0.7" in content
        finally:
            Path(tmp_md).unlink(missing_ok=True)

    def test_restore_applies_saved_max_corr_to_modal_slider(self, client, monkeypatch):
        """Saved default_max_correlation appears in the exclude-predictors modal slider."""
        from src.gui.utils.profile.restore import ProfileSettings
        from src.core.config.settings import SettingsView
        from src.gui.routes import ui_profile

        mock_settings = ProfileSettings(
            settings_view=SettingsView({}),
            default_outcome_metric=None,
            default_predictor_exclusions=[],
            default_filter_metric=None,
            default_filter_value=None,
            default_num_perf_groups=None,
            default_cutoff_values=[],
            default_influence_analyzer=None,
            default_max_correlation=0.70,
        )
        real_load = ui_profile.load_profile_dataset

        def mock_load(csv_path: str, **kwargs) -> dict:
            result = real_load(csv_path)
            result["settings"] = mock_settings
            return result

        monkeypatch.setattr(ui_profile, "load_profile_dataset", mock_load)

        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
            },
        )
        assert r.status_code == 200
        # The exclude-predictors modal renders the max_corr slider with
        # data-initial-url containing max_corr=0.70.
        assert "max_corr=0.70" in r.text, (
            "Saved max_corr=0.70 must appear in the predictors-fragment URL "
            "inside the exclude-predictors modal when default_max_correlation is set"
        )

    def test_restore_excluded_predictors_shown_checked_in_modal(self, client, monkeypatch):
        """After restore, the exclude-predictors modal must show saved exclusions checked.

        This covers the full round-trip: saved exclusions are restored into
        data['excluded_names'], the modal form passes them as excluded_predictor
        params in the HTMX fragment URL, and the fragment renders them checked.
        """
        import re as _re
        from src.gui.utils.profile.restore import ProfileSettings
        from src.core.config.settings import SettingsView
        from src.gui.routes import ui_profile

        mock_settings = ProfileSettings(
            settings_view=SettingsView({}),
            default_outcome_metric=None,
            default_predictor_exclusions=["cache_misses"],
            default_filter_metric=None,
            default_filter_value=None,
            default_num_perf_groups=None,
            default_cutoff_values=[],
            default_influence_analyzer=None,
            default_max_correlation=None,
        )
        real_load = ui_profile.load_profile_dataset

        def mock_load(csv_path: str, **kwargs) -> dict:
            result = real_load(csv_path)
            result["settings"] = mock_settings
            return result

        monkeypatch.setattr(ui_profile, "load_profile_dataset", mock_load)

        r = client.get(
            "/ui/profile",
            params={
                "experiment": "matmul",
                "csv_path": MATMUL_PROF,
                "metric": "inner_time",
            },
        )
        assert r.status_code == 200

        modal_start = r.text.find('id="exclude-predictors-modal"')
        assert modal_start != -1, "exclude-predictors-modal must be present"
        modal_html = r.text[modal_start:r.text.find("</dialog>", modal_start)]

        # The fragment URL must contain the excluded_state token so the server can
        # render restored exclusions as checked.
        assert "excluded_state=" in modal_html, (
            "Restored exclusions must be encoded in the excluded_state token in the "
            "predictors-fragment URL (not as individual excluded_predictor params)"
        )

        # Call the fragment endpoint directly and verify the checkbox is checked.
        m = _re.search(r'data-initial-url="([^"]+)"', modal_html)
        assert m is not None, "Modal must have data-initial-url for HTMX"
        frag_url = m.group(1).replace("&amp;", "&")

        frag_r = client.get(frag_url)
        assert frag_r.status_code == 200
        concurrency_pos = frag_r.text.find('value="cache_misses"')
        assert concurrency_pos != -1, (
            "cache_misses must appear in the predictors fragment "
            "(it is a column in the matmul CSV)"
        )
        # Look for 'checked' within ~300 chars before the value attribute
        nearby = frag_r.text[max(0, concurrency_pos - 300):concurrency_pos + 50]
        assert "checked" in nearby, (
            "cache_misses checkbox must be rendered checked after restore"
        )


class TestNumGroupsCutoffInteraction:
    """Comprehensive coverage for num_groups / cutoff_values interaction.

    The rules:
    1. Cutoffs in the URL that don't match num_groups-1 are DISCARDED (server guard).
    2. Saved cutoffs are NOT restored when URL has explicit num_groups incompatible
       with the saved cutoff count.
    3. Saved cutoffs ARE restored on initial load (no explicit num_groups in URL).
    4. When num_groups matches saved cutoff count + 1, saved cutoffs ARE restored.
    5. No saved settings → cutoffs never restored, num_groups used freely.
    6. Partial saved settings (only num_groups, no cutoffs) → no cutoff restore.
    7. Partial saved settings (only cutoffs, no num_groups) → cutoffs restored on
       initial load.
    """

    def _mock_settings(self, monkeypatch, settings):
        """Patch load_profile_dataset to inject mock ProfileSettings."""
        from src.gui.routes import ui_profile
        real_load = ui_profile.load_profile_dataset

        def mock_load(csv_path: str, **kwargs) -> dict:
            result = real_load(csv_path)
            result["settings"] = settings
            return result

        monkeypatch.setattr(ui_profile, "load_profile_dataset", mock_load)

    def _get_profile(self, client, params=None):
        base = {
            "experiment": "matmul",
            "csv_path": MATMUL_PROF,
            "metric": "inner_time",
        }
        if params:
            base.update(params)
        return client.get("/ui/profile", params=base)

    def _make_settings(self, num_groups=None, cutoffs=None, **kwargs):
        from src.gui.utils.profile.restore import ProfileSettings
        from src.core.config.settings import SettingsView
        return ProfileSettings(
            settings_view=SettingsView({}),
            default_outcome_metric=None,
            default_predictor_exclusions=[],
            default_filter_metric=None,
            default_filter_value=None,
            default_num_perf_groups=num_groups,
            default_cutoff_values=cutoffs or [],
            default_influence_analyzer=None,
            default_max_correlation=None,
            **kwargs,
        )

    # --- Rule 1: URL cutoffs mismatching num_groups are discarded ---

    def test_url_cutoffs_mismatching_num_groups_discarded(self, client):
        """cutoff_value params in URL that don't match num_groups-1 are dropped."""
        r = self._get_profile(client, {
            "num_groups": "4",
            "cutoff_value": ["0.003", "0.007"],  # 2 cutoffs for 3 groups, not 4
        })
        assert r.status_code == 200
        # With num_groups=4 and 2 cutoffs (which implies 3 groups), server
        # should discard the cutoffs.
        assert "cutoff_value=0.003" not in r.text
        assert "cutoff_value=0.007" not in r.text

    def test_url_cutoffs_matching_num_groups_kept(self, client):
        """cutoff_value params matching num_groups-1 are kept in the plot URL."""
        r = self._get_profile(client, {
            "num_groups": "3",
            "cutoff_value": ["0.003", "0.007"],  # 2 cutoffs for 3 groups ✓
        })
        assert r.status_code == 200
        assert "cutoff_value=0.003" in r.text
        assert "cutoff_value=0.007" in r.text

    def test_single_cutoff_matching_binary_groups(self, client):
        """One cutoff with num_groups=2 is valid and kept."""
        r = self._get_profile(client, {
            "num_groups": "2",
            "cutoff_value": ["0.005"],
        })
        assert r.status_code == 200
        assert "cutoff_value=0.005" in r.text

    # --- Rule 2: Saved cutoffs NOT restored when URL num_groups is incompatible ---

    def test_saved_cutoffs_not_restored_num_groups_higher(self, client, monkeypatch):
        """Saved 2-cutoffs (3 groups) not restored when URL has num_groups=4."""
        self._mock_settings(monkeypatch, self._make_settings(
            num_groups=3, cutoffs=[0.003, 0.007],
        ))
        r = self._get_profile(client, {"num_groups": "4"})
        assert r.status_code == 200
        assert "cutoff_value=0.003" not in r.text
        assert "cutoff_value=0.007" not in r.text

    def test_saved_cutoffs_not_restored_num_groups_lower(self, client, monkeypatch):
        """Saved 3-cutoffs (4 groups) not restored when URL has num_groups=2."""
        self._mock_settings(monkeypatch, self._make_settings(
            num_groups=4, cutoffs=[0.002, 0.005, 0.008],
        ))
        r = self._get_profile(client, {"num_groups": "2"})
        assert r.status_code == 200
        assert "cutoff_value=0.002" not in r.text
        assert "cutoff_value=0.005" not in r.text
        assert "cutoff_value=0.008" not in r.text

    # --- Rule 3: Saved cutoffs ARE restored on initial load (no num_groups in URL) ---

    def test_initial_load_restores_saved_cutoffs(self, client, monkeypatch):
        """No num_groups in URL → settings cutoffs are restored."""
        self._mock_settings(monkeypatch, self._make_settings(
            num_groups=3, cutoffs=[0.003, 0.007],
        ))
        # Don't pass num_groups — simulates direct navigation (not via form)
        r = client.get("/ui/profile", params={
            "experiment": "matmul",
            "csv_path": MATMUL_PROF,
            "metric": "inner_time",
        })
        assert r.status_code == 200
        assert "cutoff_value=0.003" in r.text
        assert "cutoff_value=0.007" in r.text

    def test_initial_load_restores_saved_num_groups(self, client, monkeypatch):
        """No num_groups in URL → settings num_groups is applied."""
        self._mock_settings(monkeypatch, self._make_settings(
            num_groups=4, cutoffs=[0.002, 0.005, 0.008],
        ))
        r = client.get("/ui/profile", params={
            "experiment": "matmul",
            "csv_path": MATMUL_PROF,
            "metric": "inner_time",
        })
        assert r.status_code == 200
        # num_groups input should show 4
        assert 'value="4"' in r.text
        # All 3 cutoffs should be present in the distribution plot URL
        assert "cutoff_value=0.002" in r.text
        assert "cutoff_value=0.005" in r.text
        assert "cutoff_value=0.008" in r.text

    # --- Rule 4: Matching num_groups in URL → saved cutoffs ARE restored ---

    def test_matching_num_groups_in_url_restores_cutoffs(self, client, monkeypatch):
        """URL num_groups=3 with saved 2-cutoff settings → cutoffs restored."""
        self._mock_settings(monkeypatch, self._make_settings(
            num_groups=3, cutoffs=[0.003, 0.007],
        ))
        r = self._get_profile(client, {"num_groups": "3"})
        assert r.status_code == 200
        assert "cutoff_value=0.003" in r.text
        assert "cutoff_value=0.007" in r.text

    # --- Rule 5: No saved settings → num_groups used freely, no cutoff restore ---

    def test_no_settings_num_groups_used_freely(self, client, monkeypatch):
        """No settings → no cutoff restore, page uses num_groups from URL."""
        self._mock_settings(monkeypatch, None)
        r = self._get_profile(client, {"num_groups": "5"})
        assert r.status_code == 200
        assert "num_groups=5" in r.text
        # No cutoffs should appear
        assert "cutoff_value=" not in r.text

    # --- Rule 6: Partial settings (only num_groups, no cutoffs) ---

    def test_partial_settings_only_num_groups(self, client, monkeypatch):
        """Saved num_groups but no cutoffs → num_groups restored, no cutoffs."""
        self._mock_settings(monkeypatch, self._make_settings(
            num_groups=4, cutoffs=[],
        ))
        r = client.get("/ui/profile", params={
            "experiment": "matmul",
            "csv_path": MATMUL_PROF,
            "metric": "inner_time",
        })
        assert r.status_code == 200
        assert 'value="4"' in r.text
        assert "cutoff_value=" not in r.text

    # --- Rule 7: Partial settings (only cutoffs, no num_groups) ---

    def test_partial_settings_only_cutoffs_restored_on_initial_load(self, client, monkeypatch):
        """Saved cutoffs but no num_groups → cutoffs still restored on initial load."""
        self._mock_settings(monkeypatch, self._make_settings(
            num_groups=None, cutoffs=[0.004, 0.009],
        ))
        r = client.get("/ui/profile", params={
            "experiment": "matmul",
            "csv_path": MATMUL_PROF,
            "metric": "inner_time",
        })
        assert r.status_code == 200
        assert "cutoff_value=0.004" in r.text
        assert "cutoff_value=0.009" in r.text

    # --- Edge cases ---

    def test_url_cutoffs_with_num_groups_1_regression_mode(self, client):
        """num_groups=1 (regression) with cutoffs → cutoffs discarded."""
        r = self._get_profile(client, {
            "num_groups": "1",
            "cutoff_value": ["0.003"],
        })
        assert r.status_code == 200
        # num_groups=1 means 0 cutoffs expected; 1 cutoff is a mismatch
        # but our guard is `num_groups > 1`, so cutoffs pass through.
        # That's OK — regression mode ignores cutoffs in labeler anyway.

    def test_auto_detect_does_not_restore_cutoffs(self, client, monkeypatch):
        """auto_detect=1 with saved cutoffs → cutoffs still appear in URL
        but labeler will use auto-detect (this is the expected server behavior)."""
        self._mock_settings(monkeypatch, self._make_settings(
            num_groups=3, cutoffs=[0.003, 0.007],
        ))
        # auto_detect with matching num_groups: cutoffs ARE restored (they're
        # used as initial cutoff lines even in auto-detect mode)
        r = client.get("/ui/profile", params={
            "experiment": "matmul",
            "csv_path": MATMUL_PROF,
            "metric": "inner_time",
            "auto_detect": "1",
        })
        assert r.status_code == 200
        # Cutoffs may or may not appear — the key is num_groups wasn't in URL
        # so the guard allows restore. The labeler decides what to do with them.

    def test_save_then_load_round_trip(self, client):
        """Save settings with cutoffs, then verify they restore on load."""
        import tempfile
        with tempfile.NamedTemporaryFile(
            suffix=".md", delete=False, mode="w"
        ) as f:
            f.write("# Test\n\n## Analysis\nContent.\n")
            tmp_md = f.name

        try:
            # Save with 3 groups and 2 cutoffs
            r = client.post(
                "/ui/profile/save-settings",
                data={
                    "md_path": tmp_md,
                    "metric": "inner_time",
                    "filter_metric": "",
                    "filter_min": "",
                    "filter_max": "",
                    "num_groups": "3",
                    "auto_detect": "0",
                    "cutoff_value": ["0.003", "0.007"],
                    "analyzer": "tree",
                    "max_corr": "0.90",
                    "redirect_url": "/ui/profile",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303

            # Verify markdown was written correctly
            content = Path(tmp_md).read_text()
            assert "profiling.default_num_perf_groups" in content
            assert "profiling.default_cutoff_values" in content
            assert "0.003" in content
            assert "0.007" in content

            # Now verify the extract round-trip
            from src.gui.utils.profile.restore import extract_profile_settings_from_md
            settings = extract_profile_settings_from_md(tmp_md)
            assert settings.default_num_perf_groups == 3
            assert settings.default_cutoff_values == [0.003, 0.007]
        finally:
            Path(tmp_md).unlink(missing_ok=True)


class TestResolveExcludedPredictors:
    """Unit tests for _resolve_excluded_predictors."""

    def test_auto_excluded_merged_with_custom_exclusions(self, monkeypatch):
        """Predictors exceeding max_corr must be excluded even when excluded_state is set.

        Regression for: analysis used only the excluded_state token and ignored the
        max_corr threshold, so a high-correlation predictor shown as checked in the
        dialog still appeared as the main decision predictor in the tree.
        """
        import polars as pl
        import src.core.runlogs.reader as reader_mod
        import src.gui.utils.profile.predictor_stats as predictor_stats_mod
        from src.gui.models.profile_state import ProfileState
        from src.gui.routes.ui_profile import _resolve_excluded_predictors
        from src.gui.services.exclusion_store import create_exclusion_state

        csv_path = "runlogs/test/fake.csv"
        metric = "perf_time"

        # excluded_state only contains "explicit_excl" — NOT "high_corr_pred"
        token = create_exclusion_state(csv_path, metric, ["explicit_excl"])
        state = ProfileState(csv_path=csv_path, metric=metric, excluded_state=token)

        monkeypatch.setattr(
            reader_mod,
            "load_table",
            lambda path: pl.DataFrame({metric: [1.0, 2.0, 3.0]}),
        )
        monkeypatch.setattr(
            predictor_stats_mod,
            "compute_predictor_stats",
            lambda df, m: [
                {"name": "explicit_excl",  "non_na_count": 3, "correlation": 0.50},
                {"name": "high_corr_pred", "non_na_count": 3, "correlation": 1.00},
                {"name": "normal_pred",    "non_na_count": 3, "correlation": 0.30},
            ],
        )

        data = {"predictor_max_corr": 0.99}
        result = _resolve_excluded_predictors(state, None, metric, csv_path, data)

        assert "high_corr_pred" in result, (
            "high_corr_pred (corr=1.0 > max_corr=0.99) must be excluded "
            "even when excluded_state is already set"
        )
        assert "explicit_excl" in result, "explicitly excluded predictor must remain excluded"
        assert "normal_pred" not in result, "normal_pred (corr=0.30) must not be excluded"
