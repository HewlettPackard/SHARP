"""
Duration-based repeater strategy.

Stops after a specified duration has elapsed.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import time
from typing import Any, Dict

from durations import Duration

from .base import Repeater, RunData


class DurationRepeater(Repeater):
    """
    Repeater that stops after a specified duration.
    """

    _DEFAULT_VALUES = {
        "duration": {
            "default": "1m",
            "type": str,
            "help": "Duration to run the experiment (e.g. 10s, 1m, 1h)",
        },
    }

    def __init__(self, options: Dict[str, Any]):
        """Initialize duration repeater from options."""
        super().__init__(options)
        repeater_opts = options.get("repeater_options", {})

        # Get duration from options
        duration_str = repeater_opts.get("duration", self._DEFAULT_VALUES["duration"]["default"])
        self._duration_seconds = Duration(duration_str).to_seconds()
        self._start_time = time.time()

    def __call__(self, pdata: RunData) -> bool:
        """Decide whether to repeat based on elapsed time."""
        super().__call__(pdata)
        elapsed = time.time() - self._start_time

        if self._verbose:
            print(f"DurationRepeater: elapsed={elapsed:.2f}s, limit={self._duration_seconds}s")

        return elapsed < self._duration_seconds
