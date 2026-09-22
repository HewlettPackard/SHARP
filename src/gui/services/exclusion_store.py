"""In-memory exclusion state store for the Profile page.

Stores excluded predictor sets server-side behind URL-scoped tokens so they
do not leak into the same base URL for a dataset.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

from uuid import uuid4

from src.gui.utils.profile.predictor_stats import DEFAULT_EXCLUDED_PREDICTORS


# Module-level state: token → (csv_path, metric, excluded predictor names).
_exclusion_state: dict[str, tuple[str, str, list[str]]] = {}


def create_exclusion_state(csv_path: str, metric: str, excluded: list[str]) -> str:
    """Store a custom exclusion list and return its URL-scoped token."""
    token = uuid4().hex
    _exclusion_state[token] = (csv_path, metric, list(excluded))
    return token


def get_excluded_predictors(state_token: str | None, csv_path: str, metric: str) -> list[str]:
    """Return the excluded predictor list for this URL-scoped state.

    Returns DEFAULT_EXCLUDED_PREDICTORS if no custom state has been set.
    """
    if not state_token:
        return list(DEFAULT_EXCLUDED_PREDICTORS)
    stored = _exclusion_state.get(state_token)
    if stored is None:
        return list(DEFAULT_EXCLUDED_PREDICTORS)
    stored_csv_path, stored_metric, stored_excluded = stored
    if stored_csv_path != csv_path or stored_metric != metric:
        return list(DEFAULT_EXCLUDED_PREDICTORS)
    return list(stored_excluded)


def reset_excluded_predictors(state_token: str) -> None:
    """Drop a stored exclusion state token."""
    _exclusion_state.pop(state_token, None)


def has_custom_exclusions(state_token: str | None, csv_path: str, metric: str) -> bool:
    """Check whether a valid URL-scoped custom exclusion state is present."""
    if not state_token:
        return False
    stored = _exclusion_state.get(state_token)
    if stored is None:
        return False
    stored_csv_path, stored_metric, _stored_excluded = stored
    return stored_csv_path == csv_path and stored_metric == metric
