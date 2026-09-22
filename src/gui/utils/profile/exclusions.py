"""
Metric selection and predictor statistics utilities.

Functions for selecting default metrics, computing predictor statistics
and correlations, and managing predictor exclusion for decision tree training.

This module provides GUI-specific UI components for predictor management.
Core computation is delegated to src.core.profile.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any
import re

from src.core.config.settings import Settings

# Re-export from core for backward compatibility
from .predictor_stats import (
    DEFAULT_EXCLUDED_PREDICTORS,
    compute_predictor_stats,
    get_auto_excluded_predictors as _collect_auto_excluded_predictors,
)

__all__ = [
    "DEFAULT_EXCLUDED_PREDICTORS",
    "compute_predictor_stats",
    "order_exclusions_with_defaults",
    "reset_exclusions",
    "apply_exclusions",
]


def _sanitize_for_html_id(name: str) -> str:
    """
    Sanitize column name to be a valid HTML element ID.

    Converts any column name to a valid C identifier by replacing
    non-alphanumeric characters with underscores.

    Args:
        name: Original column/predictor name

    Returns:
        Sanitized name safe for use as HTML element ID
    """
    # Replace any non-alphanumeric characters with underscore
    # This allows any CSV column name to be used as a valid HTML ID
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    # Ensure it doesn't start with a digit (HTML5 requirement)
    if sanitized and sanitized[0].isdigit():
        sanitized = '_' + sanitized
    return sanitized


def order_exclusions_with_defaults(excluded: list[str]) -> list[str]:
    """Return exclusions with defaults first, then remaining sorted.

    Ensures the default excluded predictors stay visible at the top of any
    ordered list (e.g., tooltips) even when many predictors are excluded.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for name in DEFAULT_EXCLUDED_PREDICTORS:
        if name in excluded and name not in seen:
            ordered.append(name)
            seen.add(name)
    for name in sorted(excluded):
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered


def _filter_modal_predictors(stats: list[dict[str, Any]], max_preds: int, search: str) -> list[dict[str, Any]]:
    """
    Filter and sort predictors for modal display.

    Filters by search term, sorts by absolute correlation (descending), and limits by max_preds.
    Does NOT filter by correlation threshold to allow users to find and uncheck any predictor.

    Args:
        stats: List of predictor statistics
        max_preds: Maximum number of predictors to display
        search: Search term to filter by predictor name

    Returns:
        Filtered and sorted list of predictor stats
    """
    result = stats
    if search:
        search_lower = search.lower()
        result = [s for s in result if search_lower in s["name"].lower()]

    # Sort by absolute correlation (descending)
    result = sorted(result, key=lambda s: abs(s.get("correlation", 0)), reverse=True)

    # Apply limit, but ensure default excluded predictors are always included
    # (unless filtered out by search criteria)
    limited = result[:max_preds]
    limited_names = {s["name"] for s in limited}

    # Find active default exclusions that would be hidden by the limit
    defaults_to_add = []
    for s in result[max_preds:]:
        if s["name"] in DEFAULT_EXCLUDED_PREDICTORS:
            defaults_to_add.append(s)

    if defaults_to_add:
        limited.extend(defaults_to_add)
        # Re-sort to ensure added items are placed correctly by correlation
        limited = sorted(limited, key=lambda s: abs(s.get("correlation", 0)), reverse=True)

    return limited


def _collect_manually_excluded_predictors(input: Any, filtered_stats: list[dict[str, Any]]) -> set[str]:
    """
    Collect predictors that are manually checked for exclusion.

    Args:
        input: Inputs object
        filtered_stats: List of predictor stats shown in the modal

    Returns:
        Set of predictor names that are checked
    """
    manually_excluded = set()
    for stat in filtered_stats:
        pred_name = stat["name"]
        checkbox_id = f"exclude_{_sanitize_for_html_id(pred_name)}"
        try:
            if getattr(input, checkbox_id, lambda: False)():
                manually_excluded.add(pred_name)
        except Exception:
            pass
    return manually_excluded


def reset_exclusions(
    excluded_predictors: Any,
    predictor_stats_full: Any,
    predictor_modal_filters: Any,
    settings: Any | None = None,
) -> None:
    """
    Reset exclusions and threshold to defaults (same as reload).

    Resets to: DEFAULT_EXCLUDED_PREDICTORS + auto-exclusions at default threshold.

    Args:
        excluded_predictors: Reactive value storing list of excluded predictor names
        predictor_stats_full: Reactive value storing full predictor statistics
        predictor_modal_filters: Reactive value storing filter state
    """
    if settings is None:
        settings = Settings()
    default_max_corr = settings.get("profiling.max_correlation", 0.99)
    default_max_preds = settings.get("profiling.max_predictors", 100)

    # Compute default exclusions: always include the 4 defaults + auto-excluded
    stats = predictor_stats_full.get()
    new_exclusions = set(DEFAULT_EXCLUDED_PREDICTORS)
    if stats:
        new_exclusions.update(_collect_auto_excluded_predictors(stats, default_max_corr))
    new_exclusions_list = sorted(new_exclusions)

    # Reset modal state and clear user_has_applied flag
    # checkbox_state=new_exclusions_list so render shows correct checkboxes
    predictor_modal_filters.set({
        "max_corr": default_max_corr,
        "max_predictors": default_max_preds,
        "search_term": "",
        "checkbox_state": new_exclusions_list,
        "user_has_applied": False,
    })

    excluded_predictors.set(new_exclusions_list)


def apply_exclusions(
    input: Any,
    excluded_predictors: Any,
    predictor_stats_full: Any,
    predictor_modal_filters: Any
) -> None:
    """
    Apply predictor exclusions when Apply button is clicked.

    Reads checkbox states from the modal and saves to excluded_predictors.

    Args:
        input: Inputs object
        excluded_predictors: Reactive value storing list of excluded predictor names
        predictor_stats_full: Reactive value storing full predictor statistics
        predictor_modal_filters: Reactive value storing filter state
    """
    all_stats = predictor_stats_full.get()
    if not all_stats:
        return

    # Get current filter values
    max_corr = input.predictor_max_corr()
    max_preds = input.predictor_max_preds()
    search = input.predictor_search() if hasattr(input, 'predictor_search') else ""

    # Get visible predictors and read their checkbox states
    filtered_stats = _filter_modal_predictors(all_stats, max_preds, search)
    visible_names = {stat["name"] for stat in filtered_stats}
    visible_checked = _collect_manually_excluded_predictors(input, filtered_stats)

    # Preserve exclusions for predictors not shown in the current view.
    # Only change exclusions for predictors that are visible in the modal.
    # If the threshold slider changed, use fresh auto-exclusions as the base.
    saved_filters = predictor_modal_filters.get()
    saved_threshold = saved_filters.get("max_corr") if saved_filters else None

    if saved_threshold is not None and abs(float(max_corr) - float(saved_threshold)) < 1e-9:
        base_exclusions = set(excluded_predictors.get())
    else:
        base_exclusions = set(_collect_auto_excluded_predictors(all_stats, max_corr))

    # Apply visible checkbox changes: checked => excluded, unchecked => included
    visible_current = base_exclusions & visible_names
    new_exclusions = base_exclusions | visible_checked
    new_exclusions -= (visible_current - visible_checked)

    # Final result
    new_exclusions_list = sorted(new_exclusions)

    # Save filter state and mark that user has applied (prevents auto-overwrite)
    predictor_modal_filters.set({
        "max_corr": max_corr,
        "max_predictors": max_preds,
        "search_term": search,
        "checkbox_state": None,  # Will be set from excluded_predictors on next modal open
        "user_has_applied": True,
    })

    excluded_predictors.set(new_exclusions_list)

