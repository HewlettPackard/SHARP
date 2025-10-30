"""
Data structure to store performance data.

Adapted from launcher/rundata.py for the new core architecture.
In this version, RunData is constructed from already-extracted metrics
rather than tracking outer_time with a clock.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import re
from typing import Any, Dict, List


class RunData:
    """
    Holds performance metrics for a single iteration.

    Stores arbitrary metrics extracted from benchmark output.
    outer_time is mandatory and used by repeaters to determine convergence.
    """

    def __init__(self, metrics: Dict[str, List[str]]) -> None:
        """
        Initialize RunData with extracted metrics.

        Args:
            metrics: Dict mapping metric name to list of string values
                    Must include 'outer_time' key

        Raises:
            ValueError: If 'outer_time' not present or empty
        """
        if "outer_time" not in metrics or not metrics["outer_time"]:
            raise ValueError("RunData requires 'outer_time' metric")

        self.perf: Dict[str, List[Any]] = {}

        # Convert string values to float where possible
        for metric_name, values in metrics.items():
            converted_values: list[Any] = []
            for value in values:
                # Skip NA values
                if value == "NA":
                    continue
                # Try to convert to float if it looks numeric
                if re.match(r"^-?\d+(?:\.\d+)?$", value) is not None:
                    converted_values.append(float(value))
                else:
                    converted_values.append(value)
            self.perf[metric_name] = converted_values

    def __str__(self) -> str:
        """String representation of RunData, for debugging."""
        return f"RunData with metrics: {list(self.perf.keys())}"

    def get_metric(self, metric: str) -> List[Any]:
        """
        Get values for a specific metric.

        Args:
            metric: Name of metric to retrieve

        Returns:
            List of values (floats or strings depending on conversion)
        """
        return self.perf.get(metric, [])

    def get_outer_time(self) -> float:
        """
        Get the most recent outer_time measurement.

        Returns:
            Most recent outer_time value as float

        Raises:
            ValueError: If outer_time not available
        """
        times = self.perf.get("outer_time", [])
        if not times:
            raise ValueError("No outer_time available")
        return float(times[-1])

    def user_metrics(self) -> List[str]:
        """
        Return list of user-defined metric names.

        Excludes system metrics like outer_time.

        Returns:
            List of user metric names
        """
        return [m for m in self.perf.keys() if m != "outer_time"]
