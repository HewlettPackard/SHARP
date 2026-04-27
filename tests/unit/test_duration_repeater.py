"""
Unit tests for DurationRepeater.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import time
import pytest
from src.core.repeaters.duration import DurationRepeater
from src.core.rundata import RunData

class MockRunData:
    """Mock RunData for testing."""
    def __init__(self):
        self.perf = {"outer_time": [0.1]}

def test_duration_repeater():
    """Test that DurationRepeater stops after specified duration."""
    options = {
        "repeats": "DurationRepeater",
        "repeater_options": {
            "duration": "1s"
        }
    }

    # Initialize repeater
    # This sets the start time
    repeater = DurationRepeater(options)
    pdata = MockRunData()

    # Should continue initially (elapsed time ~0)
    assert repeater(pdata) is True, "Should continue immediately after start"

    # Sleep for slightly more than 1 second to exceed duration
    time.sleep(1.1)

    # Should stop now
    assert repeater(pdata) is False, "Should stop after duration exceeded"
