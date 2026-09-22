# © Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""Outcome mode helpers for profile analysis.

Provides a single place to derive classification vs regression mode from
GUI labeling state.
"""

from __future__ import annotations

from src.core.profile.labeler import PerformanceLabeler, RegressionLabeler


def resolve_outcome_mode(labeler: PerformanceLabeler | None) -> str:
    """Resolve analyzer outcome mode from labeler type.

    Returns:
        "regression" when RegressionLabeler is selected, else "classification".
    """
    if isinstance(labeler, RegressionLabeler):
        return "regression"
    return "classification"


def is_regression_mode(labeler: PerformanceLabeler | None) -> bool:
    """Return True when the current labeler implies regression mode."""
    return resolve_outcome_mode(labeler) == "regression"


__all__ = ["resolve_outcome_mode", "is_regression_mode"]
