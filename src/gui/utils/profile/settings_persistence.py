"""Save helpers for profile settings persistence.

Collects the current UI state into a normalized payload and writes it
to the ``## Profile settings`` section of the task's markdown file.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

from typing import Any

from shiny import reactive, Inputs, ui
from shiny.types import SilentException

from src.core.runlogs.profile_settings import (
    build_profile_settings_payload,
    update_markdown_profile_settings,
)
from src.gui.utils.filters import get_active_filter_value
from src.gui.utils.profile.exclusions import DEFAULT_EXCLUDED_PREDICTORS


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------

def collect_save_state(
    input: Inputs,
    current_labeler: Any,
    excluded_predictors: reactive.Value,
) -> dict[str, Any]:
    """Collect current UI state into a raw settings dict for markdown.

    Returns the dict produced by ``build_profile_settings_payload``.
    """
    filter_metric = input.profile_filter_metric()
    filter_metric = filter_metric.strip() if filter_metric else None

    filter_value = get_active_filter_value(input, "profile_filter_value")

    is_auto = bool(input.perf_auto_detect())
    if is_auto:
        num_perf_groups = 0
    else:
        try:
            num_perf_groups = int(input.num_perf_groups() or 2)
        except (TypeError, ValueError):
            num_perf_groups = None

    labeler = current_labeler.get()
    cutoff_values: list[float] = []
    if not is_auto and labeler and hasattr(labeler, "get_cutoffs"):
        cutoffs = labeler.get_cutoffs()
        if cutoffs:
            cutoff_values = list(cutoffs)

    try:
        analyzer = input.profile_influence_analyzer()
    except SilentException:
        analyzer = None

    try:
        outcome_metric = str(input.profile_metric()) or None
    except SilentException:
        outcome_metric = None

    current_excluded = excluded_predictors.get()
    excluded_extra = sorted(
        set(current_excluded) - set(DEFAULT_EXCLUDED_PREDICTORS)
    ) if current_excluded else []

    return build_profile_settings_payload(
        filter_metric=filter_metric,
        filter_value=filter_value,
        num_perf_groups=num_perf_groups,
        cutoff_values=cutoff_values,
        influence_analyzer=analyzer,
        outcome_metric=outcome_metric,
        excluded_predictors=excluded_extra or None,
    )


def save_settings_to_markdown(
    md_path: str,
    input: Inputs,
    current_labeler: Any,
    excluded_predictors: reactive.Value,
) -> tuple[bool, str]:
    """Collect UI state and persist to the markdown file.

    Returns ``(success, message)`` suitable for ``ui.notification_show``.
    """
    settings_dict = collect_save_state(input, current_labeler, excluded_predictors)
    if not settings_dict:
        return False, "No profile settings to save (all controls at defaults)"
    return update_markdown_profile_settings(md_path, settings_dict)


__all__ = [
    "collect_save_state",
    "save_settings_to_markdown",
]
