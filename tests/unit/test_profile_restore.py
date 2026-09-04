#!/usr/bin/env python3
"""Unit tests for profile preset restoration helpers.

Covers filter and labeler restore edge cases used by the Profile tab.
"""

import numpy as np
import polars as pl

from src.core.profile.labeler import AutoLabeler, BinaryLabeler, ManualLabeler, RegressionLabeler
from src.gui.utils.profile.restore import (
    build_restored_labeler,
    resolve_filter_restore_value,
)
from src.gui.utils.profile.labeler_ui import _should_preserve_existing_labeler


def test_restore_filter_value_without_filter_metric_uses_active_metric():
    """default_filter_value without default_filter_metric applies to active filter metric."""
    data = pl.DataFrame({"latency": [1.0, 2.0, 3.0, 4.0]})

    restored = resolve_filter_restore_value(
        data=data,
        filter_metric="latency",
        preset_filter_metric=None,
        preset_filter_value=[1.5, 3.5],
    )

    assert restored is not None
    restore_kind, restore_value = restored
    assert restore_kind == "slider"
    assert restore_value == [1.5, 3.5]


def test_restore_filter_value_ignored_when_metric_mismatch():
    """Preset filter value does not apply when explicit metric does not match active metric."""
    data = pl.DataFrame({"latency": [1.0, 2.0, 3.0, 4.0]})

    restored = resolve_filter_restore_value(
        data=data,
        filter_metric="latency",
        preset_filter_metric="throughput",
        preset_filter_value=[1.5, 3.5],
    )

    assert restored is None


def test_build_restored_labeler_cutoffs_take_precedence_over_num_groups():
    """Explicit cutoffs win even when they imply a different number of groups."""
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

    labeler, groups = build_restored_labeler(
        values=values,
        lower_is_better=True,
        preset_num_groups=2,
        preset_cutoffs=[2.2, 3.8],
    )

    assert isinstance(labeler, ManualLabeler)
    assert groups == 3
    assert labeler.get_cutoffs() == [2.2, 3.8]


def test_build_restored_labeler_returns_correct_groups_for_cutoffs():
    """Restoring 3 cutoffs returns (labeler, 4) — groups == len(cutoffs) + 1."""
    values = np.array([1.0, 3.0, 5.0, 7.0, 9.0])
    cutoffs = [2.5, 4.5, 6.5]

    labeler, groups = build_restored_labeler(
        values=values,
        lower_is_better=True,
        preset_num_groups=None,
        preset_cutoffs=cutoffs,
    )

    assert isinstance(labeler, ManualLabeler)
    assert groups == 4
    assert labeler.get_cutoffs() == cutoffs


# --- Regression tests: simulating the reactive execution order ---
# These tests reproduce the exact bug scenario where restored cutoffs
# get overwritten by delayed browser round-trips.

class TestRestoreNotOverwrittenByDelayedUpdates:
    """Simulate the Shiny reactive execution order during task switches.

    Reproduces the bug where:
    1. _check_prof_file sends ui.update_numeric("num_perf_groups", 2)
    2. _restore_labeler_from_markdown restores a 4-group labeler with saved cutoffs
    3. The browser round-trip for step 1 arrives AFTER the restore
    4. _handle_num_groups_change fires with num_groups=2, overwriting the restored labeler
    5. Then the restore's ui.update_numeric(4) arrives, creating a FRESH 4-group
       labeler with default quantile cutoffs instead of the saved ones
    """

    SAVED_CUTOFFS = [3.1301680639108107, 5.015784390624589, 7.990506699147185]

    @staticmethod
    def _make_values():
        """Generate data in [2.31, 9.98] range matching real CG.C data."""
        rng = np.random.default_rng(42)
        return rng.uniform(2.31, 9.98, 500)

    def test_restore_produces_exact_saved_cutoffs(self):
        """build_restored_labeler must produce a ManualLabeler with the exact saved cutoffs."""
        values = self._make_values()
        labeler, groups = build_restored_labeler(
            values=values,
            lower_is_better=True,
            preset_num_groups=4,
            preset_cutoffs=self.SAVED_CUTOFFS,
        )
        assert isinstance(labeler, ManualLabeler)
        assert groups == 4
        assert labeler.get_cutoffs() == self.SAVED_CUTOFFS

    def test_initialize_preserves_restored_labeler_despite_stale_num_groups(self):
        """_should_preserve_existing_labeler must preserve restored labeler.

        After _restore_labeler_from_markdown sets a 4-group ManualLabeler,
        filter restore changes active_data(), which re-triggers
        _initialize_labeler.  At that point input.num_perf_groups() is still
        2 (browser hasn't processed ui.update_numeric(4) yet).

        The preservation function must NOT check group count — doing so
        would reject the restored labeler and create a fresh default one
        with wrong cutoff positions.
        """
        values = self._make_values()
        restored_labeler, _ = build_restored_labeler(
            values=values, lower_is_better=True,
            preset_num_groups=4, preset_cutoffs=self.SAVED_CUTOFFS,
        )

        # _initialize_labeler fires after filter restore, with stale num_groups
        # The preserved flag must be True regardless of what num_groups says
        should_preserve = _should_preserve_existing_labeler(
            restored_labeler, is_auto=False, lower_is_better=True,
        )

        assert should_preserve, (
            "_should_preserve_existing_labeler must preserve the restored labeler; "
            "checking stale num_groups would cause _initialize_labeler to overwrite "
            "it with a default quantile-based labeler"
        )

    def test_preservation_rejects_lower_is_better_mismatch(self):
        """Changing lower_is_better must rebuild even when labeler exists."""
        values = self._make_values()
        restored_labeler, _ = build_restored_labeler(
            values=values, lower_is_better=True,
            preset_num_groups=4, preset_cutoffs=self.SAVED_CUTOFFS,
        )

        should_preserve = _should_preserve_existing_labeler(
            restored_labeler, is_auto=False, lower_is_better=False,
        )
        assert not should_preserve

    def test_fresh_manual_labeler_has_different_cutoffs_than_saved(self):
        """A fresh ManualLabeler(values, lower_is_better, 3) uses quantile-based cutoffs.

        These differ from the saved cutoffs — confirming that if _handle_num_groups_change
        creates a fresh ManualLabeler after the restore, the saved positions are lost.
        """
        values = self._make_values()
        fresh = ManualLabeler(values, True, 3)
        assert fresh.get_cutoffs() != self.SAVED_CUTOFFS, (
            "Fresh quantile cutoffs should differ from saved cutoffs — "
            "if they're the same, this test is not meaningful"
        )

    def test_simulated_full_flow_restore_then_stale_num_groups(self):
        """Full simulation of the bug: restore succeeds, then stale num_groups=2 arrives.

        This simulates the exact reactive ordering:
        1. _check_prof_file: current_labeler=None, sends update_numeric(2)
        2. _restore_labeler_from_markdown: sets current_labeler to 4-group with saved cutoffs
        3. Browser round-trip: num_perf_groups=2 arrives
        4. _handle_num_groups_change: reads num_groups=2, current_labeler is 4-group ManualLabeler

        In _handle_num_groups_change, the code does:
          if isinstance(labeler, ManualLabeler):
              if len(labeler.get_cutoffs()) == num_cutoffs:
                  return  # Already correct
              if num_cutoffs == 1:
                  current_labeler.set(BinaryLabeler(values, lower_is_better))
                  return

        So with num_groups=2 → num_cutoffs=1, and existing is ManualLabeler(3 cutoffs),
        it creates a BinaryLabeler — destroying the restored labeler!
        """
        values = self._make_values()

        # Step 2: Restore succeeds
        restored_labeler, restored_groups = build_restored_labeler(
            values=values, lower_is_better=True,
            preset_num_groups=4, preset_cutoffs=self.SAVED_CUTOFFS,
        )
        assert restored_groups == 4
        current_labeler = restored_labeler  # This is what current_labeler holds

        # Step 3: Browser round-trip for ui.update_numeric("num_perf_groups", 2) arrives
        stale_num_groups = 2
        num_cutoffs = stale_num_groups - 1  # = 1

        # Step 4: _handle_num_groups_change logic (from labeler_ui.py lines 340-375)
        # Without fix, this would overwrite:
        if isinstance(current_labeler, ManualLabeler):
            if len(current_labeler.get_cutoffs()) != num_cutoffs:
                # This branch FIRES — it creates a BinaryLabeler, destroying saved cutoffs
                overwritten = True
            else:
                overwritten = False
        else:
            overwritten = False

        assert overwritten, (
            "Without a guard, the stale num_groups=2 round-trip WILL overwrite "
            "the restored 4-group labeler — this test confirms the bug mechanism"
        )


class TestShouldPreserveExistingLabeler:
    """Unit tests for _should_preserve_existing_labeler edge cases."""

    @staticmethod
    def _values():
        return np.array([1.0, 2.0, 3.0, 4.0, 5.0])

    def test_preserve_binary_labeler(self):
        existing = BinaryLabeler(self._values(), True)
        assert _should_preserve_existing_labeler(
            existing, is_auto=False, lower_is_better=True,
        )

    def test_preserve_regression_labeler(self):
        existing = RegressionLabeler(self._values(), True)
        assert _should_preserve_existing_labeler(
            existing, is_auto=False, lower_is_better=True,
        )

    def test_preserve_auto_only_in_auto_mode(self):
        existing = AutoLabeler(self._values(), True)
        assert _should_preserve_existing_labeler(
            existing, is_auto=True, lower_is_better=True,
        )
        assert not _should_preserve_existing_labeler(
            existing, is_auto=False, lower_is_better=True,
        )

    def test_do_not_preserve_none(self):
        assert not _should_preserve_existing_labeler(
            None, is_auto=False, lower_is_better=True,
        )

    def test_do_not_preserve_when_cutoffs_outside_data_range(self):
        """Labeler from a different metric (cutoff outside new data range)."""
        old_values = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        existing = BinaryLabeler(old_values, True)
        # New metric has a completely different range
        new_values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert not _should_preserve_existing_labeler(
            existing, is_auto=False, lower_is_better=True, values=new_values,
        )

    def test_preserve_when_cutoffs_within_data_range(self):
        """Labeler with cutoffs within the current data range should be preserved."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        existing = BinaryLabeler(values, True)
        assert _should_preserve_existing_labeler(
            existing, is_auto=False, lower_is_better=True, values=values,
        )

    def test_regression_labeler_preserved_even_with_different_values(self):
        """RegressionLabeler has no cutoffs, so it's always preserved."""
        existing = RegressionLabeler(self._values(), True)
        new_values = np.array([100.0, 200.0, 300.0])
        assert _should_preserve_existing_labeler(
            existing, is_auto=False, lower_is_better=True, values=new_values,
        )
