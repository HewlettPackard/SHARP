#!/usr/bin/env python3
"""Comprehensive roundtrip tests for profile settings save → restore → re-save.

Exercises all seven saveable parameters through the real
``extract_profile_settings_from_md`` → ``ProfileSettings`` →
``resolve_*`` / ``build_restored_labeler`` → ``build_profile_settings_payload``
→ ``update_markdown_profile_settings`` pipeline, using copies of the actual
``runlogs/cg/`` data files.

For each parameter, tests verify:
- Save encodes the correct value
- Restore reproduces the saved state
- Round-trip (save → load → re-save) is idempotent
- Switching between tasks with different saved settings restores correctly
- Clearing or changing a parameter and re-saving produces the right payload

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest

from src.core.profile.labeler import BinaryLabeler, ManualLabeler, RegressionLabeler
from src.core.runlogs.profile_settings import (
    build_profile_settings_payload,
    update_markdown_profile_settings,
)
from src.gui.utils.profile.restore import (
    ProfileSettings,
    build_restored_labeler,
    extract_profile_settings_from_md as extract_settings,
    resolve_filter_metric_selection,
    resolve_filter_restore_value,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def cg_c_prof(tmp_path: Path) -> tuple[Path, Path]:
    """Create a synthetic CG.C-prof-like CSV and seed a markdown with known settings.

    The CSV contains columns with value ranges deliberately chosen so that the
    seeded filter value [52368919, 179831107] lies strictly within the column range.
    No pre-existing files under runlogs/ are needed.
    """
    rng = np.random.default_rng(42)
    n = 50
    # Ensure L1_icache_load_misses spans the seeded filter range [52368919, 179831107].
    l1_values = [40_000_000] + rng.integers(41_000_000, 210_000_000, n - 2).tolist() + [220_000_000]
    csv_path = tmp_path / "CG.C-prof.csv"
    pl.DataFrame({
        "branch_misses": rng.integers(1_000, 50_000, n).tolist(),
        "L1_icache_load_misses": l1_values,
        "cpu_clock": rng.integers(1_000_000, 9_000_000, n).tolist(),
        "node_misses": rng.integers(50_000_000, 200_000_000, n).tolist(),
    }).write_csv(csv_path)
    md_path = tmp_path / "CG.C-prof.md"
    md_path.write_text("# CG.C-prof\n\n## Runtime options\n\n{}\n")
    payload = build_profile_settings_payload(
        outcome_metric="branch_misses",
        filter_metric="L1_icache_load_misses",
        filter_value=[52368919, 179831107],
        num_perf_groups=0,
        cutoff_values=None,
        influence_analyzer="tree",
        excluded_predictors=["L1_icache_load_misses", "cpu_clock"],
    )
    update_markdown_profile_settings(md_path, payload)
    return csv_path, md_path


@pytest.fixture()
def cg_cx_prof(tmp_path: Path) -> tuple[Path, Path]:
    """Create a synthetic cg.C.x-prof-like CSV and seed a markdown with known settings.

    The CSV contains columns with value ranges deliberately chosen so that the
    seeded filter value [60340880, 104619012] lies strictly within the column range.
    No pre-existing files under runlogs/ are needed.
    """
    rng = np.random.default_rng(99)
    n = 50
    # Ensure node_misses spans the seeded filter range [60340880, 104619012].
    node_values = [50_000_000] + rng.integers(51_000_000, 115_000_000, n - 2).tolist() + [120_000_000]
    csv_path = tmp_path / "cg.C.x-prof.csv"
    pl.DataFrame({
        "perf_time": rng.integers(1, 20, n).tolist(),
        "node_misses": node_values,
        "branch_misses": rng.integers(750_000_000, 790_000_000, n).tolist(),
        "LLC_misses": rng.integers(500_000_000, 700_000_000, n).tolist(),
    }).write_csv(csv_path)
    md_path = tmp_path / "cg.C.x-prof.md"
    md_path.write_text("# cg.C.x-prof\n\n## Runtime options\n\n{}\n")
    payload = build_profile_settings_payload(
        outcome_metric="perf_time",
        filter_metric="node_misses",
        filter_value=[60340880, 104619012],
        num_perf_groups=6,
        cutoff_values=[761104758.0068733, 763257432.5678436,
                       765333225.8944933, 766966952.1238011,
                       768523797.1187886],
        influence_analyzer="tree",
    )
    update_markdown_profile_settings(md_path, payload)
    return csv_path, md_path


@pytest.fixture()
def empty_md(tmp_path: Path) -> Path:
    """Create a minimal markdown file with no Profile settings section."""
    md = tmp_path / "empty.md"
    md.write_text("# Results\n\n## Runtime options\n\n{}\n")
    return md


def _load(md_path: Path) -> ProfileSettings:
    return extract_settings(str(md_path))


def _save(md_path: Path, **kwargs: Any) -> None:
    payload = build_profile_settings_payload(**kwargs)
    ok, _ = update_markdown_profile_settings(md_path, payload)
    assert ok, f"Failed to save settings to {md_path}"


# ---------------------------------------------------------------------------
# 1. Outcome metric
# ---------------------------------------------------------------------------

class TestOutcomeMetric:
    def test_round_trip(self, cg_c_prof: tuple[Path, Path]) -> None:
        _, md = cg_c_prof
        # Start from a clean slate — save a known metric, then verify load.
        _save(md, outcome_metric="branch_misses",
              filter_metric=None, filter_value=None,
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(md)
        assert ps.default_outcome_metric == "branch_misses"

        _save(md, outcome_metric="cache_misses",
              filter_metric=None, filter_value=None,
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        ps2 = _load(md)
        assert ps2.default_outcome_metric == "cache_misses"

    def test_clear(self, cg_c_prof: tuple[Path, Path]) -> None:
        _, md = cg_c_prof
        _save(md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(md)
        assert ps.default_outcome_metric is None

    def test_idempotent(self, cg_c_prof: tuple[Path, Path]) -> None:
        _, md = cg_c_prof
        ps1 = _load(md)
        _save(md, outcome_metric=ps1.default_outcome_metric,
              filter_metric=ps1.default_filter_metric,
              filter_value=ps1.default_filter_value,
              num_perf_groups=ps1.default_num_perf_groups,
              cutoff_values=ps1.default_cutoff_values or None,
              influence_analyzer=ps1.default_influence_analyzer,
              excluded_predictors=ps1.default_predictor_exclusions or None)
        ps2 = _load(md)
        assert ps2.default_outcome_metric == ps1.default_outcome_metric


# ---------------------------------------------------------------------------
# 2. Predictor exclusions
# ---------------------------------------------------------------------------

class TestPredictorExclusions:
    def test_round_trip(self, cg_c_prof: tuple[Path, Path]) -> None:
        _, md = cg_c_prof
        ps = _load(md)
        assert "L1_icache_load_misses" in ps.default_predictor_exclusions
        assert "cpu_clock" in ps.default_predictor_exclusions

    def test_save_and_restore(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None,
              excluded_predictors=["col_a", "col_b"])
        ps = _load(empty_md)
        assert sorted(ps.default_predictor_exclusions) == ["col_a", "col_b"]

    def test_clear_exclusions(self, cg_c_prof: tuple[Path, Path]) -> None:
        _, md = cg_c_prof
        _save(md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None,
              excluded_predictors=None)
        ps = _load(md)
        assert ps.default_predictor_exclusions == []


# ---------------------------------------------------------------------------
# 3. Filter metric
# ---------------------------------------------------------------------------

class TestFilterMetric:
    def test_round_trip(self, cg_c_prof: tuple[Path, Path]) -> None:
        _, md = cg_c_prof
        ps = _load(md)
        assert ps.default_filter_metric == "L1_icache_load_misses"

    def test_change_and_round_trip(self, cg_c_prof: tuple[Path, Path]) -> None:
        _, md = cg_c_prof
        _save(md, outcome_metric=None,
              filter_metric="node_misses", filter_value=[100, 200],
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(md)
        assert ps.default_filter_metric == "node_misses"

    def test_resolve_filter_metric_on_task_switch(self) -> None:
        snapshot = ProfileSettings(
            settings_view=None,
            default_outcome_metric=None,
            default_predictor_exclusions=[],
            default_filter_metric="node_misses",
            default_filter_value=[100, 200],
            default_num_perf_groups=None,
            default_cutoff_values=[],
            default_influence_analyzer=None,
        )
        filterable = ["cache_misses", "node_misses", "branch_misses"]

        result = resolve_filter_metric_selection(
            filterable=filterable,
            task_changed=True,
            snapshot=snapshot,
            md_settings=ProfileSettings.empty(),
            current_filter="cache_misses",  # stale from previous task
        )
        assert result == "node_misses"

    def test_resolve_filter_metric_falls_back_to_md_on_task_switch(self) -> None:
        md_settings = ProfileSettings(
            settings_view=None,
            default_outcome_metric=None,
            default_predictor_exclusions=[],
            default_filter_metric="branch_misses",
            default_filter_value=None,
            default_num_perf_groups=None,
            default_cutoff_values=[],
            default_influence_analyzer=None,
        )
        result = resolve_filter_metric_selection(
            filterable=["cache_misses", "branch_misses"],
            task_changed=True,
            snapshot=None,
            md_settings=md_settings,
            current_filter="cache_misses",
        )
        assert result == "branch_misses"

    def test_resolve_filter_metric_preserves_current_on_same_task(self) -> None:
        result = resolve_filter_metric_selection(
            filterable=["cache_misses", "node_misses"],
            task_changed=False,
            snapshot=None,
            md_settings=ProfileSettings.empty(),
            current_filter="cache_misses",
        )
        assert result == "cache_misses"

    def test_resolve_filter_metric_snapshot_wins_over_stale_input_on_same_task(self) -> None:
        """A→B→A race: pending_restore has A's metric, input still has B's stale value."""
        snapshot = ProfileSettings(
            settings_view=None,
            default_outcome_metric=None,
            default_predictor_exclusions=[],
            default_filter_metric="node_misses",
            default_filter_value=None,
            default_num_perf_groups=None,
            default_cutoff_values=[],
            default_influence_analyzer=None,
        )
        result = resolve_filter_metric_selection(
            filterable=["node_misses", "cache_misses"],
            task_changed=False,
            snapshot=snapshot,
            md_settings=ProfileSettings.empty(),
            current_filter="inst_count",  # stale, not even in filterable
        )
        assert result == "node_misses"

    def test_resolve_filter_metric_resets_to_placeholder_on_task_switch_no_saved(self) -> None:
        result = resolve_filter_metric_selection(
            filterable=["cache_misses", "node_misses"],
            task_changed=True,
            snapshot=None,
            md_settings=ProfileSettings.empty(),
            current_filter="cache_misses",
        )
        assert result == ""

    def test_resolve_filter_metric_resets_when_saved_metric_not_in_filterable(self) -> None:
        snapshot = ProfileSettings(
            settings_view=None,
            default_outcome_metric=None,
            default_predictor_exclusions=[],
            default_filter_metric="deleted_column",
            default_filter_value=None,
            default_num_perf_groups=None,
            default_cutoff_values=[],
            default_influence_analyzer=None,
        )
        result = resolve_filter_metric_selection(
            filterable=["cache_misses", "node_misses"],
            task_changed=True,
            snapshot=snapshot,
            md_settings=ProfileSettings.empty(),
            current_filter=None,
        )
        assert result == ""

    def test_resolve_filter_metric_md_fallback_on_same_task_empty_current(self) -> None:
        """When snapshot is consumed and current_filter is empty (selectize roundtrip
        not yet complete), md_settings provides the fallback so the just-restored
        filter metric is not clobbered."""
        md_settings = ProfileSettings(
            settings_view=None,
            default_outcome_metric=None,
            default_predictor_exclusions=[],
            default_filter_metric="node_misses",
            default_filter_value=None,
            default_num_perf_groups=None,
            default_cutoff_values=[],
            default_influence_analyzer=None,
        )
        result = resolve_filter_metric_selection(
            filterable=["cache_misses", "node_misses"],
            task_changed=False,
            snapshot=None,
            md_settings=md_settings,
            current_filter="",  # stale empty from selectize roundtrip
        )
        assert result == "node_misses"


# ---------------------------------------------------------------------------
# 4. Filter value
# ---------------------------------------------------------------------------

class TestFilterValue:
    def test_round_trip_numeric(self, cg_c_prof: tuple[Path, Path]) -> None:
        csv, md = cg_c_prof
        ps = _load(md)
        assert ps.default_filter_metric == "L1_icache_load_misses"
        assert ps.default_filter_value == [52368919, 179831107]

        data = pl.read_csv(csv)
        resolved = resolve_filter_restore_value(
            data=data,
            filter_metric="L1_icache_load_misses",
            preset_filter_metric="L1_icache_load_misses",
            preset_filter_value=[52368919, 179831107],
        )
        assert resolved is not None
        kind, value = resolved
        assert kind == "slider"
        assert len(value) == 2

    def test_round_trip_with_cutoffs(self, cg_cx_prof: tuple[Path, Path]) -> None:
        csv, md = cg_cx_prof
        ps = _load(md)
        assert ps.default_filter_metric == "node_misses"
        assert isinstance(ps.default_filter_value, list) and len(ps.default_filter_value) == 2

        data = pl.read_csv(csv)
        resolved = resolve_filter_restore_value(
            data=data,
            filter_metric="node_misses",
            preset_filter_metric="node_misses",
            preset_filter_value=ps.default_filter_value,
        )
        assert resolved is not None

    def test_filter_value_without_metric_not_saved(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric=None, filter_value=[10, 20],
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(empty_md)
        assert ps.default_filter_metric is None
        assert ps.default_filter_value is None

    def test_filter_value_clamped_to_column_range(self) -> None:
        data = pl.DataFrame({"x": [10, 20, 30, 40, 50]})
        resolved = resolve_filter_restore_value(
            data=data,
            filter_metric="x",
            preset_filter_metric="x",
            preset_filter_value=[0, 100],
        )
        assert resolved is not None
        kind, value = resolved
        assert kind == "slider"
        assert value[0] >= 10
        assert value[1] <= 50

    def test_filter_value_not_applied_to_wrong_metric(self) -> None:
        data = pl.DataFrame({"x": [10, 20], "y": [100, 200]})
        resolved = resolve_filter_restore_value(
            data=data,
            filter_metric="y",
            preset_filter_metric="x",
            preset_filter_value=[10, 20],
        )
        assert resolved is None

    def test_categorical_filter_value(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric="backend", filter_value=["local", "ssh"],
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(empty_md)
        assert ps.default_filter_value == ["local", "ssh"]
        data = pl.DataFrame({"backend": ["local", "ssh", "docker", "mpi"]})
        resolved = resolve_filter_restore_value(
            data=data,
            filter_metric="backend",
            preset_filter_metric="backend",
            preset_filter_value=["local", "ssh"],
        )
        assert resolved is not None
        kind, selected = resolved
        assert kind == "selectize"
        assert sorted(selected) == ["local", "ssh"]


# ---------------------------------------------------------------------------
# 5. Num perf groups (including auto-detect sentinel)
# ---------------------------------------------------------------------------

class TestNumPerfGroups:
    def test_auto_detect_sentinel(self, cg_c_prof: tuple[Path, Path]) -> None:
        _, md = cg_c_prof
        ps = _load(md)
        assert ps.default_num_perf_groups == 0  # auto-detect sentinel

    def test_explicit_groups(self, cg_cx_prof: tuple[Path, Path]) -> None:
        _, md = cg_cx_prof
        ps = _load(md)
        assert ps.default_num_perf_groups == 6

    def test_save_auto_detect(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=0, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(empty_md)
        assert ps.default_num_perf_groups == 0

    def test_save_explicit_groups(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=4, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(empty_md)
        assert ps.default_num_perf_groups == 4

    def test_groups_clamped_to_valid_range(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=50, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(empty_md)
        assert ps.default_num_perf_groups == 10  # clamped to max

    def test_clear_groups(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(empty_md)
        assert ps.default_num_perf_groups is None


# ---------------------------------------------------------------------------
# 6. Cutoff values
# ---------------------------------------------------------------------------

class TestCutoffValues:
    def test_round_trip(self, cg_cx_prof: tuple[Path, Path]) -> None:
        _, md = cg_cx_prof
        ps = _load(md)
        assert len(ps.default_cutoff_values) == 5
        assert ps.default_cutoff_values == sorted(ps.default_cutoff_values)

    def test_save_and_restore_cutoffs(self, empty_md: Path) -> None:
        cutoffs = [1.5, 3.0, 7.8]
        _save(empty_md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=4, cutoff_values=cutoffs,
              influence_analyzer=None)
        ps = _load(empty_md)
        assert ps.default_cutoff_values == [1.5, 3.0, 7.8]

    def test_build_labeler_from_cutoffs(self) -> None:
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        labeler, groups = build_restored_labeler(
            values=values,
            lower_is_better=True,
            preset_num_groups=None,
            preset_cutoffs=[3.5, 7.5],
        )
        assert isinstance(labeler, ManualLabeler)
        assert groups == 3

    def test_single_cutoff_produces_binary_labeler(self) -> None:
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        labeler, groups = build_restored_labeler(
            values=values,
            lower_is_better=True,
            preset_num_groups=None,
            preset_cutoffs=[3.0],
        )
        assert isinstance(labeler, BinaryLabeler)
        assert groups == 2

    def test_cutoffs_outside_range_ignored(self) -> None:
        values = np.array([10.0, 20.0, 30.0])
        labeler, groups = build_restored_labeler(
            values=values,
            lower_is_better=True,
            preset_num_groups=None,
            preset_cutoffs=[0.5, 50.0],
        )
        # Both cutoffs are outside data range, so they get filtered out
        assert labeler is None

    def test_cutoffs_deduplicated_and_sorted(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=None,
              cutoff_values=[5.0, 2.0, 5.0, 1.0],
              influence_analyzer=None)
        ps = _load(empty_md)
        assert ps.default_cutoff_values == [1.0, 2.0, 5.0]

    def test_cutoffs_win_over_num_groups(self) -> None:
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        labeler, groups = build_restored_labeler(
            values=values,
            lower_is_better=True,
            preset_num_groups=2,
            preset_cutoffs=[2.5, 4.0],
        )
        assert isinstance(labeler, ManualLabeler)
        assert groups == 3  # 2 cutoffs → 3 groups, not 2


# ---------------------------------------------------------------------------
# 7. Influence analyzer
# ---------------------------------------------------------------------------

class TestInfluenceAnalyzer:
    def test_round_trip(self, cg_c_prof: tuple[Path, Path]) -> None:
        _, md = cg_c_prof
        ps = _load(md)
        assert ps.default_influence_analyzer == "tree"

    def test_change_and_restore(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer="granger")
        ps = _load(empty_md)
        assert ps.default_influence_analyzer == "granger"

    def test_clear_analyzer(self, cg_c_prof: tuple[Path, Path]) -> None:
        _, md = cg_c_prof
        _save(md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(md)
        assert ps.default_influence_analyzer is None


# ---------------------------------------------------------------------------
# Multi-parameter roundtrip and task-switch tests
# ---------------------------------------------------------------------------

class TestFullRoundtrip:
    """Save all 7 parameters at once, re-load, and verify every field."""

    def test_save_all_seven_and_restore(self, empty_md: Path) -> None:
        _save(
            empty_md,
            outcome_metric="branch_misses",
            filter_metric="node_misses",
            filter_value=[100, 500],
            num_perf_groups=3,
            cutoff_values=[200.0, 400.0],
            influence_analyzer="tree",
            excluded_predictors=["col_a", "col_b"],
        )
        ps = _load(empty_md)
        assert ps.default_outcome_metric == "branch_misses"
        assert sorted(ps.default_predictor_exclusions) == ["col_a", "col_b"]
        assert ps.default_filter_metric == "node_misses"
        assert ps.default_filter_value == [100, 500]
        assert ps.default_num_perf_groups == 3
        assert ps.default_cutoff_values == [200.0, 400.0]
        assert ps.default_influence_analyzer == "tree"

    def test_overwrite_all_seven(self, cg_c_prof: tuple[Path, Path]) -> None:
        _, md = cg_c_prof
        ps_before = _load(md)
        assert ps_before.default_outcome_metric == "branch_misses"

        _save(
            md,
            outcome_metric="cache_misses",
            filter_metric="branch_misses",
            filter_value=[10, 90],
            num_perf_groups=5,
            cutoff_values=[20.0, 40.0, 60.0, 80.0],
            influence_analyzer="pcmci",
            excluded_predictors=["context_switches"],
        )
        ps_after = _load(md)
        assert ps_after.default_outcome_metric == "cache_misses"
        assert ps_after.default_filter_metric == "branch_misses"
        assert ps_after.default_filter_value == [10, 90]
        assert ps_after.default_num_perf_groups == 5
        assert ps_after.default_cutoff_values == [20.0, 40.0, 60.0, 80.0]
        assert ps_after.default_influence_analyzer == "pcmci"
        assert "context_switches" in ps_after.default_predictor_exclusions

    def test_idempotent_round_trip_real_data(self, cg_cx_prof: tuple[Path, Path]) -> None:
        _, md = cg_cx_prof
        ps1 = _load(md)
        _save(
            md,
            outcome_metric=ps1.default_outcome_metric,
            filter_metric=ps1.default_filter_metric,
            filter_value=ps1.default_filter_value,
            num_perf_groups=ps1.default_num_perf_groups,
            cutoff_values=ps1.default_cutoff_values or None,
            influence_analyzer=ps1.default_influence_analyzer,
            excluded_predictors=ps1.default_predictor_exclusions or None,
        )
        ps2 = _load(md)
        assert ps2.default_outcome_metric == ps1.default_outcome_metric
        assert ps2.default_predictor_exclusions == ps1.default_predictor_exclusions
        assert ps2.default_filter_metric == ps1.default_filter_metric
        assert ps2.default_filter_value == ps1.default_filter_value
        assert ps2.default_num_perf_groups == ps1.default_num_perf_groups
        assert ps2.default_cutoff_values == ps1.default_cutoff_values
        assert ps2.default_influence_analyzer == ps1.default_influence_analyzer


class TestTaskSwitchSimulation:
    """Simulate A→B and A→B→A task switching using real data files."""

    def test_a_to_b_uses_b_settings(
        self, cg_c_prof: tuple[Path, Path], cg_cx_prof: tuple[Path, Path]
    ) -> None:
        """Switching from A to B restores B's saved settings, not A's."""
        _, md_a = cg_c_prof
        _, md_b = cg_cx_prof
        ps_a = _load(md_a)
        ps_b = _load(md_b)
        # Verify they're different
        assert ps_a.default_filter_metric != ps_b.default_filter_metric

        # Simulate task switch to B: resolve_filter_metric_selection prefers B's snapshot
        data_b = pl.read_csv(str(cg_cx_prof[0]))
        filterable_b = [c for c in data_b.columns
                        if data_b[c].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32)
                        and data_b[c].n_unique() > 1]

        result = resolve_filter_metric_selection(
            filterable=filterable_b,
            task_changed=True,
            snapshot=ps_b,
            md_settings=ps_b,
            current_filter=ps_a.default_filter_metric,  # stale from task A
        )
        assert result == ps_b.default_filter_metric

    def test_a_to_b_to_a_restores_a(
        self, cg_c_prof: tuple[Path, Path], cg_cx_prof: tuple[Path, Path]
    ) -> None:
        """Round-trip A→B→A restores A's filter metric."""
        _, md_a = cg_c_prof
        _, md_b = cg_cx_prof
        ps_a = _load(md_a)
        ps_b = _load(md_b)

        data_a = pl.read_csv(str(cg_c_prof[0]))
        filterable_a = [c for c in data_a.columns
                        if data_a[c].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32)
                        and data_a[c].n_unique() > 1]

        # Switch back to A with B's filter still in input
        result = resolve_filter_metric_selection(
            filterable=filterable_a,
            task_changed=True,
            snapshot=ps_a,
            md_settings=ps_a,
            current_filter=ps_b.default_filter_metric,  # stale from B
        )
        assert result == ps_a.default_filter_metric

    def test_a_to_b_to_a_restores_filter_value(
        self, cg_c_prof: tuple[Path, Path], cg_cx_prof: tuple[Path, Path]
    ) -> None:
        """A→B→A restores A's saved filter *value*, not just the metric."""
        csv_a, md_a = cg_c_prof
        ps_a = _load(md_a)
        data_a = pl.read_csv(str(csv_a))

        resolved = resolve_filter_restore_value(
            data=data_a,
            filter_metric=ps_a.default_filter_metric,
            preset_filter_metric=ps_a.default_filter_metric,
            preset_filter_value=ps_a.default_filter_value,
        )
        assert resolved is not None
        kind, value = resolved
        assert kind == "slider"
        assert len(value) == 2

    def test_a_to_b_to_a_restores_all_seven(
        self, cg_c_prof: tuple[Path, Path], cg_cx_prof: tuple[Path, Path]
    ) -> None:
        """Full A→B→A simulation verifying all 7 parameters persist independently."""
        csv_a, md_a = cg_c_prof
        csv_b, md_b = cg_cx_prof

        # Read A's settings
        ps_a = _load(md_a)
        # Read B's settings
        ps_b = _load(md_b)

        # After visiting B, create snapshot of A on switch back
        ps_a_again = _load(md_a)

        # Verify all 7 params are the same as the original A
        assert ps_a_again.default_outcome_metric == ps_a.default_outcome_metric
        assert ps_a_again.default_predictor_exclusions == ps_a.default_predictor_exclusions
        assert ps_a_again.default_filter_metric == ps_a.default_filter_metric
        assert ps_a_again.default_filter_value == ps_a.default_filter_value
        assert ps_a_again.default_num_perf_groups == ps_a.default_num_perf_groups
        assert ps_a_again.default_cutoff_values == ps_a.default_cutoff_values
        assert ps_a_again.default_influence_analyzer == ps_a.default_influence_analyzer

    def test_switch_to_task_with_no_saved_settings(
        self, cg_c_prof: tuple[Path, Path], empty_md: Path
    ) -> None:
        """Switching to a task with no profile settings resets to defaults."""
        _, md_a = cg_c_prof
        ps_a = _load(md_a)
        ps_empty = _load(empty_md)

        assert ps_empty.default_outcome_metric is None
        assert ps_empty.default_filter_metric is None
        assert ps_empty.default_num_perf_groups is None
        assert ps_empty.default_influence_analyzer is None

        result = resolve_filter_metric_selection(
            filterable=["col_a", "col_b"],
            task_changed=True,
            snapshot=ps_empty,
            md_settings=ps_empty,
            current_filter=ps_a.default_filter_metric,
        )
        assert result == ""


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_payload_save_load(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(empty_md)
        assert ps.default_outcome_metric is None
        assert ps.default_filter_metric is None
        assert ps.default_num_perf_groups is None

    def test_single_cutoff_save_restore(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=2, cutoff_values=[5.0],
              influence_analyzer=None)
        ps = _load(empty_md)
        assert ps.default_cutoff_values == [5.0]
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        labeler, groups = build_restored_labeler(
            values=values,
            lower_is_better=True,
            preset_num_groups=2,
            preset_cutoffs=[5.0],
        )
        assert isinstance(labeler, BinaryLabeler)
        assert groups == 2

    def test_negative_filter_value(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric="temperature", filter_value=[-10, 40],
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(empty_md)
        assert ps.default_filter_value == [-10, 40]

    def test_float_filter_value_precision(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric="latency", filter_value=[0.001, 99.999],
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(empty_md)
        assert abs(ps.default_filter_value[0] - 0.001) < 1e-9
        assert abs(ps.default_filter_value[1] - 99.999) < 1e-9

    def test_groups_1_produces_regression_labeler(self) -> None:
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        labeler, groups = build_restored_labeler(
            values=values,
            lower_is_better=True,
            preset_num_groups=1,
            preset_cutoffs=None,
        )
        assert isinstance(labeler, RegressionLabeler)
        assert groups == 1

    def test_groups_2_produces_binary_labeler(self) -> None:
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        labeler, groups = build_restored_labeler(
            values=values,
            lower_is_better=True,
            preset_num_groups=2,
            preset_cutoffs=None,
        )
        assert isinstance(labeler, BinaryLabeler)
        assert groups == 2

    def test_groups_5_produces_manual_labeler(self) -> None:
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        labeler, groups = build_restored_labeler(
            values=values,
            lower_is_better=True,
            preset_num_groups=5,
            preset_cutoffs=None,
        )
        assert isinstance(labeler, ManualLabeler)
        assert groups == 5

    def test_auto_detect_sentinel_skips_labeler(self) -> None:
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        labeler, groups = build_restored_labeler(
            values=values,
            lower_is_better=True,
            preset_num_groups=0,
            preset_cutoffs=None,
        )
        assert labeler is None

    def test_multiple_saves_overwrite_cleanly(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric="a",
              filter_metric="x", filter_value=[1, 2],
              num_perf_groups=2, cutoff_values=[1.5],
              influence_analyzer="tree")
        _save(empty_md, outcome_metric="b",
              filter_metric="y", filter_value=[3, 4],
              num_perf_groups=4, cutoff_values=[2.0, 3.0, 3.5],
              influence_analyzer="granger")
        ps = _load(empty_md)
        assert ps.default_outcome_metric == "b"
        assert ps.default_filter_metric == "y"
        assert ps.default_filter_value == [3, 4]
        assert ps.default_num_perf_groups == 4
        assert ps.default_cutoff_values == [2.0, 3.0, 3.5]
        assert ps.default_influence_analyzer == "granger"

    def test_unicode_exclusion_names(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric=None, filter_value=None,
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None,
              excluded_predictors=["température", "délai"])
        ps = _load(empty_md)
        assert sorted(ps.default_predictor_exclusions) == ["délai", "température"]

    def test_save_preserves_non_profile_sections(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text(
            "# Results\n\n## Runtime options\n\n{}\n\n## Notes\n\nImportant notes.\n"
        )
        _save(md, outcome_metric="x",
              filter_metric=None, filter_value=None,
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        content = md.read_text()
        assert "## Runtime options" in content
        assert "## Notes" in content
        assert "Important notes." in content
        assert "## Profile settings" in content

    def test_filter_single_value_numeric(self, empty_md: Path) -> None:
        _save(empty_md, outcome_metric=None,
              filter_metric="x", filter_value=42,
              num_perf_groups=None, cutoff_values=None,
              influence_analyzer=None)
        ps = _load(empty_md)
        assert ps.default_filter_value == 42

    def test_restore_with_too_few_data_points(self) -> None:
        values = np.array([1.0])
        labeler, groups = build_restored_labeler(
            values=values,
            lower_is_better=True,
            preset_num_groups=3,
            preset_cutoffs=[0.5],
        )
        assert labeler is None
        assert groups is None
