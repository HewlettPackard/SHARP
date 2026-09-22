"""
Regression test: ensure exclude-predictors modal is rendered when conditions are met.

This test verifies that the modal is only rendered when both active_csv and metric
are present in the data dict. This catches the bug where missing these values would
prevent the modal from rendering, breaking the exclude-predictors functionality.
"""

import pytest
from src.gui.components.profile import profile_page


def test_exclude_predictors_modal_rendered_when_conditions_met():
    """Modal must be present when both active_csv and metric are in data."""
    # Minimal data required for modal to render
    data = {
        "active_csv": "test.csv",
        "metric": "inner_time",
        "excluded_state": "",
        "excluded_names": [],
        "excluded_count": 0,
        "csv_path": "test.csv",
        "source": "",
        "cutoff_values": [],
        # Empty lists to prevent rendering issues
        "experiments": [],
        "tasks": [],
        "metrics": [],
    }

    html = profile_page(data)

    # Modal must be rendered with the correct ID
    assert 'id="exclude-predictors-modal"' in html, (
        "Modal with id='exclude-predictors-modal' must be present "
        "when active_csv and metric are set"
    )
    # Modal must be a dialog element
    assert '<dialog class="profile-modal" id="exclude-predictors-modal"' in html, (
        "Modal must be a <dialog> element with proper ID"
    )


def test_exclude_predictors_modal_not_rendered_without_active_csv():
    """Modal must NOT be rendered if active_csv is missing."""
    data = {
        # Intentionally missing active_csv
        "metric": "inner_time",
        "excluded_state": "",
        "excluded_names": [],
        "excluded_count": 0,
        "csv_path": "test.csv",
        "source": "",
        "cutoff_values": [],
        "experiments": [],
        "tasks": [],
        "metrics": [],
    }

    html = profile_page(data)

    # Modal must NOT be rendered when active_csv is missing
    assert 'id="exclude-predictors-modal"' not in html, (
        "Modal must not be rendered when active_csv is missing"
    )


def test_exclude_predictors_modal_not_rendered_without_metric():
    """Modal must NOT be rendered if metric is missing."""
    data = {
        "active_csv": "test.csv",
        # Intentionally missing metric
        "excluded_state": "",
        "excluded_names": [],
        "excluded_count": 0,
        "csv_path": "test.csv",
        "source": "",
        "cutoff_values": [],
        "experiments": [],
        "tasks": [],
        "metrics": [],
    }

    html = profile_page(data)

    # Modal must NOT be rendered when metric is missing
    assert 'id="exclude-predictors-modal"' not in html, (
        "Modal must not be rendered when metric is missing"
    )
