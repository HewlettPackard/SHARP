"""
Simple count-based repeater strategy.

Stops after a predetermined number of runs.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any, Dict, List

from .base import Repeater, RunData


class CountRepeater(Repeater):
    """
    Simple Repeater that stops after predetermined number of runs

    The simplest (default) condition is simply to count repetitions to a limit.
    It contains a lower bound as well to be used by subclasses, since this
    Repeater is essentially the superclass of all others.
    """

    _DEFAULT_VALUES = {
        "max": {
            "default": 1,
            "type": int,
            "help": "Maximum number of runs before stopping",
        },
        "metric": {
            "default": "outer_time",
            "type": str,
            "help": "Performance metric to track (e.g., outer_time, inner_time)",
        },
    }

    def __init__(self, options: Dict[str, Any]):
        """Initialize count repeater from options."""
        super().__init__(options)
        repeater_opts: Dict[str, Any] = options.get("repeater_options", {})

        # metric is a shared parameter (inherited by all repeaters), so look for it
        # at the top level of repeater_options, not in a specific repeater's sub-dict
        metric_default = CountRepeater._DEFAULT_VALUES["metric"]["default"]
        self._metric: str = repeater_opts.get("metric", metric_default)

        # Now get repeater-specific options (max, etc.) from the CR sub-dict
        ropts = repeater_opts.get("CR", repeater_opts)
        max_default = self._DEFAULT_VALUES["max"]["default"]
        self._limit: int = int(ropts.get("max", max_default))

        self._runtimes: List[float] = []

    def __call__(self, pdata: RunData) -> bool:
        """Stopping heuristic based on reaching maximum run count."""
        super().__call__(pdata)
        self._runtimes += pdata.get_metric(self._metric)
        return self._count < self._limit
