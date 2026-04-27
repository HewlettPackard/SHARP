"""
Unit tests for labeler interaction logic.

Tests the helper function that updates labelers based on user clicks.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
from src.gui.utils.profile.distribution import update_labeler_from_click
from src.core.profile.labeler import BinaryLabeler, CutoffBasedLabeler


def test_create_labeler_from_click_when_none():
    """Test creating a new labeler when none exists."""
    new_labeler = update_labeler_from_click(
        click_x=2.5,
        labeler=None,
        lower_is_better=True
    )

    assert isinstance(new_labeler, BinaryLabeler)
    cutoffs = new_labeler.get_cutoffs()
    assert len(cutoffs) == 1
    assert cutoffs[0] == 2.5


def test_move_single_cutoff():
    """Test moving the cutoff in a binary labeler."""
    initial_labeler = BinaryLabeler.with_cutoff(2.0, lower_is_better=True)

    # Click at 3.5 - should move cutoff there
    updated_labeler = update_labeler_from_click(
        click_x=3.5,
        labeler=initial_labeler,
        lower_is_better=True
    )

    cutoffs = updated_labeler.get_cutoffs()
    assert len(cutoffs) == 1
    assert cutoffs[0] == 3.5


def test_move_nearest_cutoff_in_multi_cutoff():
    """Test that clicking moves the nearest cutoff in multi-cutoff labeler."""
    # Create multi-cutoff labeler with cutoffs at [1.0, 3.0, 5.0]
    multi_labeler = CutoffBasedLabeler(
        cutoffs=[1.0, 3.0, 5.0],
        class_names=["Class0", "Class1", "Class2", "Class3"],
        lower_is_better=True
    )

    # Click at 2.8 - nearest cutoff is 3.0, should move it
    updated_labeler = update_labeler_from_click(
        click_x=2.8,
        labeler=multi_labeler,
        lower_is_better=True
    )

    cutoffs = updated_labeler.get_cutoffs()
    assert len(cutoffs) == 3
    assert 1.0 in cutoffs
    assert 2.8 in cutoffs  # Moved from 3.0
    assert 5.0 in cutoffs


def test_cutoffs_stay_sorted():
    """Test that cutoffs remain sorted after update."""
    multi_labeler = CutoffBasedLabeler(
        cutoffs=[1.0, 3.0, 5.0],
        class_names=["Class0", "Class1", "Class2", "Class3"],
        lower_is_better=True
    )

    # Click at 4.0 - nearest is 3.0, move it to 4.0
    updated_labeler = update_labeler_from_click(
        click_x=4.0,
        labeler=multi_labeler,
        lower_is_better=True
    )

    cutoffs = updated_labeler.get_cutoffs()
    assert cutoffs == [1.0, 4.0, 5.0]  # Still sorted


def test_preserves_lower_is_better_setting():
    """Test that lower_is_better setting is preserved."""
    initial_labeler = BinaryLabeler.with_cutoff(2.0, lower_is_better=False)

    updated_labeler = update_labeler_from_click(
        click_x=3.0,
        labeler=initial_labeler,
        lower_is_better=False
    )

    # Verify by checking classification behavior
    # With lower_is_better=False, values > cutoff should be better (FAST)
    test_values = np.array([2.5, 3.5])
    labels = updated_labeler.label(test_values)

    # 2.5 < 3.0 should be SLOW (worse)
    # 3.5 > 3.0 should be FAST (better)
    assert labels[0] == "SLOW"
    assert labels[1] == "FAST"


def test_flipping_lower_is_better_swaps_labels():
    """Test that flipping lower_is_better swaps FAST/SLOW labels."""
    cutoff = 5.0
    test_values = np.array([3.0, 7.0])  # One below, one above cutoff

    # With lower_is_better=True: 3.0 is FAST, 7.0 is SLOW
    labeler_lower = BinaryLabeler.with_cutoff(cutoff, lower_is_better=True)
    labels_lower = labeler_lower.label(test_values)
    assert labels_lower[0] == "FAST"
    assert labels_lower[1] == "SLOW"

    # With lower_is_better=False: 3.0 is SLOW, 7.0 is FAST
    labeler_higher = BinaryLabeler.with_cutoff(cutoff, lower_is_better=False)
    labels_higher = labeler_higher.label(test_values)
    assert labels_higher[0] == "SLOW"
    assert labels_higher[1] == "FAST"

    # Verify class names are swapped
    assert labeler_lower.get_class_names() == ["FAST", "SLOW"]
    assert labeler_higher.get_class_names() == ["SLOW", "FAST"]
