"""
Labeler state management for profile tab.

Handles initialization, updates, and interactions with performance labelers.

© Copyright 2025--2026 Hewlett Packard Enterprise Development LP
"""
from typing import Any

import numpy as np

from src.gui.utils import ui_kit as ui
from src.core.profile.labeler import (
    PerformanceLabeler,
    BinaryLabeler,
    CutoffBasedLabeler,
    TertileLabeler,
    QuartileLabeler,
    AutoLabeler,
    ManualLabeler,
    RegressionLabeler,
)


def _should_preserve_existing_labeler(
    existing_labeler: PerformanceLabeler | None,
    *,
    is_auto: bool,
    lower_is_better: bool,
    values: np.ndarray | None = None,
) -> bool:
    """Return True when _initialize_labeler should keep the existing labeler.

    Checks mode and lower_is_better only — NOT group count, because the
    browser value of num_perf_groups may be stale during a restore.

    If *values* is provided and the labeler carries cutoff points, those
    cutoffs are validated against [values.min(), values.max()].  A labeler
    whose cutoffs fall outside the current data range is not preserved.
    """
    if existing_labeler is None:
        return False
    if getattr(existing_labeler, "lower_is_better", None) != lower_is_better:
        return False
    if is_auto:
        return isinstance(existing_labeler, AutoLabeler)
    if not isinstance(existing_labeler, (BinaryLabeler, ManualLabeler, RegressionLabeler)):
        return False
    # Range check: if the current data was provided, ensure all cutoffs are
    # within its range.  RegressionLabeler has no cutoffs, so it always passes.
    if values is not None and isinstance(existing_labeler, CutoffBasedLabeler):
        lo, hi = float(values.min()), float(values.max())
        if any(c < lo or c > hi for c in existing_labeler.cutoffs):
            return False
    return True


def get_cutoff_display_info(labeler: PerformanceLabeler | None) -> tuple[str, bool]:
    """
    Get cutoff display string and control visibility from labeler.

    Args:
        labeler: Current performance labeler

    Returns:
        Tuple of (cutoff_display_string, show_cutoff_controls)
    """
    if labeler is not None:
        cutoffs = labeler.get_cutoffs()
        cutoff_display = ", ".join(f"{c:.4g}" for c in cutoffs) if cutoffs else "N/A (quantile-based)"
        show_cutoff_controls = hasattr(labeler, 'is_mutable') and labeler.is_mutable
        return cutoff_display, show_cutoff_controls
    else:
        return "Initializing...", False


def render_cutoff_actions(
    labeler: PerformanceLabeler | None,
    excluded_names: list[str] | None = None,
) -> list[ui.TagChild]:
    """
    Render labeler-derived action buttons and sync disabled state for group controls.

    The perf_auto_detect checkbox and num_perf_groups stepper live in a stable
    parent render and are NOT recreated here.  This function returns only the
    search/predictors action buttons plus a JS snippet that synchronises the
    stepper's disabled and opacity state with the current labeler.

    Args:
        labeler: Current performance labeler (None if not yet initialized)
        excluded_names: Excluded predictor names for the tooltip badge

    Returns:
        List of UI elements for the action panel
    """
    is_auto = isinstance(labeler, AutoLabeler)
    is_regression = isinstance(labeler, RegressionLabeler)
    is_mutable = (
        not is_auto
        and not is_regression
        and labeler is not None
        and isinstance(labeler, CutoffBasedLabeler)
        and labeler.is_mutable
    )
    search_disabled = is_auto or is_regression or labeler is None

    if is_auto:
        search_title = "Search is not available in Auto mode."
    elif is_regression:
        search_title = "Search is not available in regression mode (1 group)."
    elif is_mutable:
        search_title = (
            "Search finds the optimal cutoff positions that minimize tree entropy. "
            "Clicking on the distribution plot moves the nearest cutoff manually."
        )
    else:
        search_title = ""

    btn_class = "btn-secondary btn-sm" + (" disabled" if search_disabled else "")

    # Sync the disabled / opacity state of num_perf_groups which lives in the
    # stable parent render and is never recreated here.
    disabled_js = "true" if is_auto else "false"
    opacity_js = "0.4" if is_auto else "1"
    sync_script = ui.tags.script(
        "(function(){"
        "var el=document.getElementById('num_perf_groups');"
        f"if(el){{el.disabled={disabled_js};"
        f"el.style.opacity='{opacity_js}';}}"
        "})()"
    )

    return [
        sync_script,
        # Search button (always visible; grayed for Auto/regression)
        ui.div(
            ui.input_action_button(
                "search_cutoff_btn",
                "Search for optimal tree",
                class_=btn_class,
                icon=ui.tags.i(class_="bi bi-search"),
            ),
            title=search_title,
            style="display: flex; align-items: center; margin-top: 2px;",
        ),
        # Predictors button + exclusion count badge
        ui.div(
            ui.input_action_button(
                "exclude_predictors_btn",
                "Predictors",
                class_="btn-secondary btn-sm",
                icon=ui.tags.i(class_="bi bi-table"),
            ),
            ui.tags.span(
                f"({len(excluded_names) if excluded_names else 0} excluded)",
                title=(
                    "Excluded predictors:\n" + "\n".join(excluded_names)
                    if excluded_names and len(excluded_names) > 0
                    else "No predictors excluded"
                ),
                style=(
                    "cursor: help; border-bottom: 1px dotted #999; "
                    "font-size: 0.8em; color: #666; margin-left: 6px;"
                ),
            ),
            title="Click here to determine which predictors are included or excluded from the factor analysis",
            style="display: flex; align-items: center; gap: 0; margin-top: 5px;",
        ),
    ]
