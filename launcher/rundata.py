"""
Data structure to store performance data, and algorithms to process and compute statistics on it.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import re
import time
from typing import *


class RunData:
    """
    The RunData class Holds data for a single task run (possibly with multiple copies).

    Currently holds a list of outer (total) runtimes for the task (sec),
    and a list of arbitrary metrics reported by each rank (sec).
    Automatically starts a clock for outer time upon construction, and ends when
    the last rank has been added.
    """

    def __init__(self, ncopies: int = 1):
        """
        Initialize RunData data structure.

        Initially only stores an "outer_time" metric, the only performance metric
        that is required (and in fact, computed by this class).
        Also stores the number of expected copies of this run.
        Starts a clock at construction that will be matched when a run is added.
        """
        self.perf: Dict[str, List[Any]] = {"outer_time": []}
        self.start_time: float = time.perf_counter()
        self.ncopies: int = ncopies

    ######################
    def __str__(self) -> str:
        """String representation of RunData, for debugging."""
        return (
            f"Recorded {len(self.perf['outer_time'])} runs out of {self.ncopies}, "
            + f"with these metrics: {self.perf}"
        )

    ######################
    def user_metrics(self) -> List[str]:
        """Return a list of the names of user-added metrics (not "outer_time")."""
        metrics = list(self.perf.keys())
        metrics.remove("outer_time")
        return metrics

    ######################
    def add_run(self, metrics: Dict[str, Any]) -> None:
        """Add all metrics for a measurement, convert to float if possible."""
        nruns: int = len(self.perf["outer_time"])
        self.perf["outer_time"].append(time.perf_counter() - self.start_time)

        for metric in metrics.keys():
            if metric not in self.perf:
                self.perf[metric] = []
            value = metrics[metric]
            if re.match(r"^-?\d+(?:\.\d+)$", value) is not None:
                value = float(value)
            self.perf[metric].append(value)

    ######################
    def get_outer(self) -> List[float]:
        """Get values for outer_time."""
        assert (
            len(self.perf["outer_time"]) >= self.ncopies
        ), f"Attempted to access task's runtime before {self.ncopies} copies have been completed"
        return self.perf["outer_time"]

    ######################
    def get_metric(self, metric: str) -> List[Any]:
        """Get values for a specific metric."""
        assert (
            len(self.perf["outer_time"]) >= self.ncopies
        ), f"Attempted to access task's runtime before {self.ncopies} copies have been completed"
        return self.perf[metric]
