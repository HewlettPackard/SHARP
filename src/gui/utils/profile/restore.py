"""Profile settings retrieval and preset restoration helpers.

Handles parsing profile settings from markdown and providing pure helper
functions for translating those settings into concrete UI/state updates.
Keeping this logic out of ``profile.py`` makes behavior easier to test and
keeps the module focused on wiring.

Save path: when the user clicks "save settings" in the Profile tab,
``profile.py`` collects the current UI state (metric, filter metric/value,
grouping mode, cutoffs, analyzer, and extra predictor exclusions), builds a
payload, and writes it under ``## Profile settings`` in the task markdown.
This module defines the schema-level normalization used on that payload after
reload: alias handling, type coercion, cutoff sanitization, and support for
special sentinel values such as ``default_num_perf_groups = 0`` for
auto-detect mode.

Restore path: on task switch, ``profile.py`` reads markdown once, snapshots
the resulting ``ProfileSettings``, and applies those presets one time to the
static controls (metric/filter/labeler/analyzer). The helpers here stay pure
so they can be called safely from route handlers and render functions without
adding extra reactive dependencies. In practice, request timing still matters:
input updates involve browser round-trips, so restore code uses snapshot-based
reads and resolved/clamped values (for example, filter sliders and manual
cutoffs) to avoid stale-input races and preserve the saved state across
intermediate invalidations.

See also: ``src.core.runlogs.profile_settings`` for the
save-path helpers.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np
import polars as pl

from src.core.runlogs import (
    extract_profile_settings_from_md as _parse_profile_settings,
)
from src.core.config.settings import SettingsView
from src.core.profile.labeler import (
    PerformanceLabeler,
    BinaryLabeler,
    ManualLabeler,
    RegressionLabeler,
)
from src.gui.utils.filters import is_time_column


@dataclass
class ProfileSettings:
    """
    Parsed per-experiment profile settings from the '## Profile settings'
    markdown section.

    ``settings_view`` is a :class:`SettingsView` that can replace bare
    ``Settings()`` calls to honour dot-key overrides defined in the section.
    The two remaining fields carry per-experiment directives that are not
    ``settings.yaml``-style keys.
    """

    settings_view: SettingsView
    """Overlay that checks per-experiment overrides before Settings()."""

    default_outcome_metric: str | None
    """Metric column to pre-select when the experiment is loaded."""

    default_predictor_exclusions: List[str]
    """Extra predictors to add to the initial exclusion list."""

    default_filter_metric: str | None
    """Filter metric column to pre-select when loading the experiment."""

    default_filter_value: Any | None
    """Filter value to apply for the selected filter metric (type depends on column)."""

    default_num_perf_groups: int | None
    """Default number of performance groups (1-10)."""

    default_cutoff_values: List[float]
    """Explicit cutoff positions to restore for manual/binary labeling."""

    default_influence_analyzer: str | None
    """Influence analyzer to pre-select in the Profile controls."""

    default_max_correlation: float | None = None
    """Max-correlation threshold used in the exclude-predictors modal slider."""

    @classmethod
    def empty(cls) -> 'ProfileSettings':
        """Return a no-op ProfileSettings (absent or unparseable section)."""
        return cls(
            settings_view=SettingsView({}),
            default_outcome_metric=None,
            default_predictor_exclusions=[],
            default_filter_metric=None,
            default_filter_value=None,
            default_num_perf_groups=None,
            default_cutoff_values=[],
            default_max_correlation=None,
            default_influence_analyzer=None,
        )


def _first_present(raw: Dict[str, Any], *keys: str) -> Any:
    """Return the first value found in ``raw`` for the provided key aliases."""
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def _normalize_optional_non_empty_str(value: Any) -> str | None:
    """Normalize a config value to a non-empty string or None."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value else None


def _normalize_optional_int(value: Any, min_value: int, max_value: int) -> int | None:
    """Normalize and clamp integer config values.

    A value of 0 is preserved as-is because it is used as the auto-detect
    sentinel for ``default_num_perf_groups``; the caller is responsible for
    treating 0 specially.
    """
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed == 0:
        return 0
    return max(min_value, min(max_value, parsed))


def _normalize_cutoffs(raw_cutoffs: Any) -> List[float]:
    """Normalize cutoff values from config into sorted unique finite floats."""
    if not isinstance(raw_cutoffs, list):
        return []

    parsed: List[float] = []
    for item in raw_cutoffs:
        try:
            value = float(item)
            if not (value == value):  # NaN check
                continue
            if value in (float("inf"), float("-inf")):
                continue
            parsed.append(value)
        except (TypeError, ValueError):
            continue

    return sorted(set(parsed))


def extract_profile_settings_from_md(md_path: str) -> ProfileSettings:
    """
    Parse the optional '## Profile settings' section from a runlog markdown file.

    Args:
        md_path: Path to the markdown file

    Returns:
        :class:`ProfileSettings` with overrides and per-experiment directives.
        All fields are empty/None if the section is absent or unparseable.
    """
    raw: Dict[str, Any] = _parse_profile_settings(md_path)
    if not raw:
        return ProfileSettings.empty()

    # Extract per-experiment directives (not dot-key settings overrides)
    default_outcome_metric = _normalize_optional_non_empty_str(
        _first_present(
            raw,
            "profiling.default_outcome_metric",
            "default_outcome_metric",
        )
    )

    raw_exclusions = _first_present(
        raw,
        "profiling.default_predictor_exclusions",
        "default_predictor_exclusions",
    )
    if raw_exclusions is None:
        raw_exclusions = []
    if not isinstance(raw_exclusions, list):
        raw_exclusions = []
    default_predictor_exclusions = [str(x) for x in raw_exclusions if x]

    default_filter_metric = _normalize_optional_non_empty_str(
        _first_present(
            raw,
            "profiling.default_filter_metric",
            "default_filter_metric",
        )
    )
    default_filter_value = _first_present(
        raw,
        "profiling.default_filter_value",
        "default_filter_value",
    )

    default_num_perf_groups = _normalize_optional_int(
        _first_present(
            raw,
            "profiling.default_num_perf_groups",
            "default_num_perf_groups",
        ),
        min_value=1,
        max_value=10,
    )

    default_cutoff_values = _normalize_cutoffs(
        _first_present(
            raw,
            "profiling.default_cutoff_values",
            "default_cutoff_values",
            "profiling.default_cutoffs",
            "default_cutoffs",
        )
    )

    default_influence_analyzer = _normalize_optional_non_empty_str(
        _first_present(
            raw,
            "profiling.default_influence_analyzer",
            "default_influence_analyzer",
        )
    )

    _raw_max_corr = _first_present(
        raw,
        "profiling.default_max_correlation",
        "default_max_correlation",
    )
    try:
        default_max_correlation: float | None = float(_raw_max_corr) if _raw_max_corr is not None else None
        if default_max_correlation is not None:
            default_max_correlation = max(0.0, min(1.0, default_max_correlation))
    except (TypeError, ValueError):
        default_max_correlation = None

    # All remaining keys become dot-key settings overrides
    _SPECIAL_KEYS = {
        "default_outcome_metric",
        "default_predictor_exclusions",
        "default_filter_metric",
        "default_filter_value",
        "default_num_perf_groups",
        "default_cutoff_values",
        "default_cutoffs",
        "default_influence_analyzer",
        "profiling.default_outcome_metric",
        "profiling.default_predictor_exclusions",
        "profiling.default_filter_metric",
        "profiling.default_filter_value",
        "profiling.default_num_perf_groups",
        "profiling.default_cutoff_values",
        "profiling.default_cutoffs",
        "profiling.default_influence_analyzer",
        "profiling.default_max_correlation",
        "default_max_correlation",
    }
    overrides = {k: v for k, v in raw.items() if k not in _SPECIAL_KEYS}

    return ProfileSettings(
        settings_view=SettingsView(overrides),
        default_outcome_metric=default_outcome_metric,
        default_predictor_exclusions=default_predictor_exclusions,
        default_filter_metric=default_filter_metric,
        default_filter_value=default_filter_value,
        default_num_perf_groups=default_num_perf_groups,
        default_cutoff_values=default_cutoff_values,
        default_influence_analyzer=default_influence_analyzer,
        default_max_correlation=default_max_correlation,
    )


def _to_seconds(value: Any) -> float:
    """Convert HH:MM:SS(.sss) values to seconds; invalid inputs return 0."""
    try:
        parts = str(value).strip().split(":")
        if len(parts) != 3:
            return 0.0
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except (TypeError, ValueError):
        return 0.0


def resolve_filter_restore_value(
    data: pl.DataFrame,
    filter_metric: str,
    preset_filter_metric: str | None,
    preset_filter_value: Any,
) -> tuple[str, Any] | None:
    """Resolve the preset filter value for the active column.

    Returns:
        ``("slider", value)`` for numeric/time slider updates,
        ``("selectize", list[str])`` for categorical multi-select,
        or ``None`` when no valid preset can be applied.
    """
    if not filter_metric or filter_metric not in data.columns:
        return None
    if preset_filter_value is None:
        return None
    if preset_filter_metric and filter_metric != preset_filter_metric:
        return None

    col = data[filter_metric]

    # Time columns use numeric-second range slider values.
    if is_time_column(col):
        if not (isinstance(preset_filter_value, (list, tuple)) and len(preset_filter_value) == 2):
            return None
        values = col.drop_nulls().to_list()
        if not values:
            return None

        seconds_values = [_to_seconds(t) for t in values]
        col_min = float(min(seconds_values))
        col_max = float(max(seconds_values))
        start = max(col_min, min(col_max, float(preset_filter_value[0])))
        end = max(col_min, min(col_max, float(preset_filter_value[1])))
        if start > end:
            start, end = end, start
        return "slider", [start, end]

    if col.dtype == pl.Categorical or col.dtype == pl.Utf8:
        available = {str(v) for v in col.unique().to_list() if v is not None}
        if isinstance(preset_filter_value, (list, tuple)):
            selected_values = [str(v) for v in preset_filter_value if str(v) in available]
        else:
            candidate = str(preset_filter_value)
            selected_values = [candidate] if candidate in available else []

        if not selected_values:
            return None
        return "selectize", selected_values

    if col.dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
        values = col.drop_nulls().to_numpy()
        if len(values) == 0:
            return None
        col_min = float(values.min())
        col_max = float(values.max())
        if isinstance(preset_filter_value, (list, tuple)) and len(preset_filter_value) == 2:
            start = max(col_min, min(col_max, float(preset_filter_value[0])))
            end = max(col_min, min(col_max, float(preset_filter_value[1])))
            if start > end:
                start, end = end, start
            return "slider", [start, end]
        if isinstance(preset_filter_value, (int, float)):
            value = max(col_min, min(col_max, float(preset_filter_value)))
            return "slider", value

    return None


def build_restored_labeler(
    values: np.ndarray,
    lower_is_better: bool,
    preset_num_groups: int | None,
    preset_cutoffs: list[float] | None,
) -> tuple[PerformanceLabeler | None, int | None]:
    """Build a labeler from preset group/cutoff settings.

    Rules:
    - Valid explicit cutoffs take precedence over group count.
    - If provided cutoffs are invalid for this dataset, fall back to groups.
    - Returns ``(None, None)`` when nothing can/should be restored.
    """
    if len(values) < 2:
        return None, None

    vmin = float(np.min(values))
    vmax = float(np.max(values))

    normalized_cutoffs: list[float] = []
    if preset_cutoffs:
        normalized_cutoffs = sorted(set(c for c in preset_cutoffs if vmin < c < vmax))

    if normalized_cutoffs:
        if len(normalized_cutoffs) == 1:
            return BinaryLabeler.with_cutoff(normalized_cutoffs[0], lower_is_better), 2
        return ManualLabeler.with_cutoffs(normalized_cutoffs, lower_is_better), len(normalized_cutoffs) + 1

    if preset_num_groups is None:
        return None, None

    # Sentinel 0 means auto-detect; the caller (profile.py) handles this
    # before delegating here, but guard defensively.
    if preset_num_groups == 0:
        return None, None

    num_groups = max(1, min(10, int(preset_num_groups)))
    if num_groups <= 1:
        return RegressionLabeler(values, lower_is_better), 1
    if num_groups == 2:
        return BinaryLabeler(values, lower_is_better), 2
    return ManualLabeler(values, lower_is_better, num_groups - 1), num_groups


def resolve_filter_metric_selection(
    filterable: list[str],
    task_changed: bool,
    snapshot: "ProfileSettings | None",
    md_settings: "ProfileSettings",
    current_filter: str | None,
) -> str:
    """Determine which filter metric to pre-select after a task or metric change.

    Encodes two rules:

    **Task switch** (``task_changed=True``):
        Restore the saved filter from the pending-restore snapshot first.
        Fall back to re-parsing ``md_settings`` directly to handle the
        execution-order edge case where the snapshot has not been set yet.
        Reset to placeholder (no filter) when neither source has a saved metric.

    **Same-task metric change** (``task_changed=False``):
        Check the snapshot *before* falling back to ``current_filter``.
        After a task switch the browser emits ``profile_metric`` before
        ``profile_filter_metric`` arrives, so ``current_filter`` is still the
        previous task's stale column (absent from the new dataset).  The
        snapshot is still live at that moment, so it yields the correct metric.
        Only if the snapshot is empty does the current input value reflect a
        genuine same-task user choice.

    Args:
        filterable: Column names that can be filtered for the current dataset.
        task_changed: True when the active task differs from the previous call.
        snapshot: Pending-restore snapshot (``pending_restore.get()``), may be None.
        md_settings: Profile settings parsed from the current task markdown.
        current_filter: Isolated read of ``input.profile_filter_metric()``, may be None.

    Returns:
        Column name to pre-select, or ``""`` (PLACEHOLDER) for no filter.
    """
    PLACEHOLDER = ""

    if task_changed:
        if snapshot and snapshot.default_filter_metric and snapshot.default_filter_metric in filterable:
            return snapshot.default_filter_metric
        if md_settings.default_filter_metric and md_settings.default_filter_metric in filterable:
            return md_settings.default_filter_metric
        return PLACEHOLDER

    # Same-task metric change: snapshot may still be live mid-roundtrip.
    if snapshot and snapshot.default_filter_metric and snapshot.default_filter_metric in filterable:
        return snapshot.default_filter_metric
    if current_filter and current_filter in filterable:
        return current_filter
    # Fallback: the selectize update from a task-switch may still be in
    # flight (browser roundtrip not complete), leaving current_filter stale.
    # Re-read the saved setting so we don't clobber a just-restored value.
    if md_settings.default_filter_metric and md_settings.default_filter_metric in filterable:
        return md_settings.default_filter_metric
    return PLACEHOLDER


__all__ = [
    "ProfileSettings",
    "extract_profile_settings_from_md",
    "resolve_filter_restore_value",
    "resolve_filter_metric_selection",
    "build_restored_labeler",
]
