"""
Confidence Interval (CI) based repeater strategy.

Stops when 95% confidence interval relative width drops below threshold.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import math
import warnings
from typing import Any, Dict

import numpy
import scipy.stats as st  # type: ignore

from .base import RunData
from .count import CountRepeater


class CIRepeater(CountRepeater):
    """Stop repeating when the 95% right-tailed confidence interval of all runtime measurements is smaller than a threshold proportion of mean"""

    _DEFAULT_VALUES = {
        "ci_limit": {
            "default": 0.95,
            "type": float,
            "help": "Confidence level for interval (0-1)",
        },
        "ci_threshold": {
            "default": 0.05,
            "type": float,
            "help": "Confidence interval threshold as proportion of mean (0-1)",
        },
        "starting_sample": {
            "default": 15,
            "type": int,
            "help": "Minimum number of runs before checking threshold",
        },
        "max": {
            "default": 100,
            "type": int,
            "help": "Maximum number of runs allowed",
        },
    }

    def __init__(self, options: Dict[str, Any]):
        """Initialize CI parameters from options."""
        super().__init__(options)
        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("CI", ropts)

        self.__ci_limit: float = ropts.get("ci_limit", self._DEFAULT_VALUES["ci_limit"]["default"])
        # Support both parameter naming conventions
        self.__thresh: float = ropts.get("ci_threshold", ropts.get("error_threshold", self._DEFAULT_VALUES["ci_threshold"]["default"]))
        self.__min_repeats: int = int(ropts.get("starting_sample", ropts.get("min", self._DEFAULT_VALUES["starting_sample"]["default"])))
        self.__max_repeats: int = int(ropts.get("max", self._DEFAULT_VALUES["max"]["default"]))
        assert self.__max_repeats >= self.__min_repeats

    def __call__(self, pdata: RunData) -> bool:
        """
        Stopping heuristic for CIRepeater.

        Algorithm to determine whether enough repeats have run:
        1. If maximum repeats were reached or exceeded, return True
        2. Otherwise, add reported run times to record of all runtimes.
        3. Compute length of right-tailed CI based on t-distribution.
        4. If the CI length (relative standard error) falls below the
           threshold and a minimum number of repeats was performed, return True.
        For definitions and computations of CI, see:
          https://sphweb.bumc.bu.edu/otlt/mph-modules/bs/bs704_confidence_intervals/bs704_confidence_intervals_print.html
        For a discussion of the merits of the CI criteraion, see:
          https://janhove.github.io/design/2017/09/19/peeking-confidence-intervals
        """
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        super().__call__(pdata)
        if self.get_count() >= self.__max_repeats:
            return False

        if self.get_count() > 1:
            N: int = len(self._runtimes)
            t: float = st.t.ppf(q=self.__ci_limit, df=N - 1)
            ci: float = t * st.tstd(self._runtimes) / math.sqrt(N)
            rel_ci: float = ci / numpy.mean(self._runtimes)
            if self._verbose:
                print(
                    f"At repeat #{self.get_count()}, CI={ci}, rel_CI={rel_ci}, mean={numpy.mean(self._runtimes)}"
                )
                print(f"Previous runtimes={self._runtimes}")
                print(
                    f"Continue?: {self.get_count() <= self.__min_repeats or rel_ci > self.__thresh}"
                )

        return self.get_count() <= self.__min_repeats or rel_ci > self.__thresh
