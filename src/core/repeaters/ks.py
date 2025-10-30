"""
Kolmogorov-Smirnov (KS) test repeater strategy.

Stops when KS test indicates two halves of data come from same distribution.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any, Dict

from scipy.stats import ks_2samp

from .base import RunData
from .count import CountRepeater


class KSRepeater(CountRepeater):
    """
    Stop when the Kolmogorov-Smirnov statistic between the first half and second half drops below a threshold

    The KSRepeater applies the Kolmogorov-Smirnov (KS) test to compare first
    half of the data to the second half. It stops the process if the KS statistic
    is below a specified threshold, indicating that the two halves come from the
    same distribution.

    This repeater uses the ks_2samp test from SciPy:
    https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ks_2samp.html

    The KS test is non-parametric and does not assume a specific distribution
    for the data, in contrast to the Gaussian Mixture Model.

    Args:
        threshold:    KS statistic value that triggers stopping (default: 2)
        max_repeats:  Maximum number of repetitions allowed (default: 1000)
    """

    _DEFAULT_VALUES = {
        "ks_threshold": {
            "default": 0.1,
            "type": float,
            "help": "KS statistic threshold for stopping (0-1)",
        },
        "starting_sample": {
            "default": 5,
            "type": int,
            "help": "Minimum number of runs before checking threshold",
        },
        "max": {
            "default": 1000,
            "type": int,
            "help": "Maximum number of runs allowed",
        },
    }

    def __init__(self, options: Dict[str, Any]):
        """Initialize KSRepeater from options."""
        super().__init__(options)

        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("KS", ropts)

        # Accept both "starting_sample" (consistent) and "min" (legacy)
        self.__min_repeats: int = ropts.get("starting_sample", ropts.get("min", self._DEFAULT_VALUES["starting_sample"]["default"]))
        self.__max_repeats: int = int(ropts.get("max", self._DEFAULT_VALUES["max"]["default"]))
        # Accept both "ks_threshold" (consistent) and "threshold" (legacy)
        self.__threshold: float = float(ropts.get("ks_threshold", ropts.get("threshold", self._DEFAULT_VALUES["ks_threshold"]["default"])))

    def __call__(self, pdata: RunData) -> bool:
        """Stopping heuristic using KS test."""
        super().__call__(pdata)

        if self.get_count() < self.__min_repeats:
            return True
        if self.get_count() >= self.__max_repeats:
            return False

        # Extract metric column from pdata
        self._runtimes += pdata.get_metric(self._metric)
        ks_statistic, ks_p_value = ks_2samp(
            self._runtimes[: int(self.get_count() / 2)],
            self._runtimes[int(self.get_count() / 2) :],
        )

        if self._verbose:
            print(f"KS distance for repeater: {ks_statistic}")

        return bool(ks_statistic > self.__threshold)
