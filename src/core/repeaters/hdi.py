"""
Highest Density Interval (HDI) based repeater strategy.

Stops when HDI width drops below threshold.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any, Dict

import arviz
import numpy

from .base import RunData
from .count import CountRepeater


class HDIRepeater(CountRepeater):
    """
    Repeater based on high-density interval

    HDIRepeater stops repeating when the 95% highest-density interval
    of all runtime measurements is smaller than a threshold proportion of mean.
    Note: if the inherent noise of the task exceeds the error threshold, this
    method will never converge and will only stop when it reaches max_repeats.
    """

    _DEFAULT_VALUES = {
        "hdi_limit": {
            "default": 0.89,
            "type": float,
            "help": "Highest-density interval probability (0-1)",
        },
        "hdi_threshold": {
            "default": 0.1,
            "type": float,
            "help": "HDI width threshold as proportion of mean (0-1)",
        },
        "starting_sample": {
            "default": 15,
            "type": int,
            "help": "Minimum number of runs before checking threshold",
        },
        "max": {
            "default": 200,
            "type": int,
            "help": "Maximum number of runs allowed",
        },
    }

    def __init__(self, options: Dict[str, Any]):
        """Initialize HDI parameters from options."""
        super().__init__(options)
        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("HDI", ropts)

        self.__hdi_limit: float = ropts.get("hdi_limit", self._DEFAULT_VALUES["hdi_limit"]["default"])
        # Support both parameter naming conventions
        self.__thresh: float = ropts.get("hdi_threshold", ropts.get("error_threshold", self._DEFAULT_VALUES["hdi_threshold"]["default"]))
        self.__min_repeats: int = ropts.get("starting_sample", ropts.get("min", self._DEFAULT_VALUES["starting_sample"]["default"]))
        self.__max_repeats: int = ropts.get("max", self._DEFAULT_VALUES["max"]["default"])
        assert self.__max_repeats >= self.__min_repeats

    def __call__(self, pdata: RunData) -> bool:
        """
        Stopping heuristic for HDIRepeater.

        Algorithm to determine whether enough repeats have run:
        1. If maximum repeats were reached or exceeded, return True
        2. Otherwise, add reported run times to record of all runtimes.
        3. Compute length of HDI using the arviz library.
        4. If the HDI length falls below the threshold and a minimum number
        of repeats was performed, return True.
        For definitions and computations of HDI, see:
         https://www.sciencedirect.com/topics/mathematics/highest-density-interval
        For a discussion of the merits of the CI criteraion, see:
          https://www.sciencedirect.com/topics/mathematics/highest-density-interval
        See also:
          - Doing Bayesian Data Analysis: A Tutorial with R, JAGS, and Stan
          - Bayesian Analysis with Python: Introduction to statistical modeling and probabilistic programming using PyMC3 and ArviZ
        """
        super().__call__(pdata)
        if self.get_count() >= self.__max_repeats:
            return False

        if self.get_count() > 1:
            N: int = len(self._runtimes)
            hdi = arviz.hdi(numpy.asarray(self._runtimes), hdi_prob=self.__hdi_limit)  # type: ignore
            mean = numpy.mean(self._runtimes)
            rel_hdi: float = 0 if mean == 0 else (hdi[1] - hdi[0]) / mean
            if self._verbose:
                print(
                    f"At repeat #{self.get_count()}, HDI={hdi}, rel_HDI={rel_hdi}, mean={mean}"
                )
                print(
                    f"Previous runtimes={self._runtimes}\nContinue?:",
                    f"{self.get_count() <= self.__min_repeats or rel_hdi > self.__thresh}",
                )

        return self.get_count() <= self.__min_repeats or rel_hdi > self.__thresh
