"""
Relative Standard Error (RSE) based repeater strategy.

Stops when relative standard error (normalized standard error) drops below threshold.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import math
import warnings
from typing import Any, Dict

import numpy
import scipy.stats as st

from .base import RunData
from .count import CountRepeater


class RSERepeater(CountRepeater):
    """Stop repeating when the relative standard error of runtime measurements drops below a threshold"""

    _DEFAULT_VALUES = {
        "rse_threshold": {
            "default": 0.1,
            "type": float,
            "help": "Relative standard error threshold (0-1) for stopping",
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
        """Initialize RSE parameters from options."""
        super().__init__(options)
        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("RSE", ropts)
        # Support both parameter naming conventions
        self.__thresh: float = ropts.get("rse_threshold", ropts.get("error_threshold", self._DEFAULT_VALUES["rse_threshold"]["default"]))
        self.__min_repeats: int = ropts.get("starting_sample", ropts.get("min", self._DEFAULT_VALUES["starting_sample"]["default"]))
        self.__max_repeats: int = ropts.get("max", self._DEFAULT_VALUES["max"]["default"])
        assert self.__max_repeats >= self.__min_repeats

    def __call__(self, pdata: RunData) -> bool:
        """
        Stopping heuristic for RSERepeater.

        Algorithm to determine whether enough repeats have run:
        1. If maximum repeats were reached or exceeded, return False
        2. Otherwise, add reported run times to record of all runtimes.
        3. If the relative standard error falls below the threshold and a minimum
           number of repeats was performed, return False.
        The relative standard error is computed as: (SE / mean) where SE is the
        standard error of the mean (σ / √N).
        For definitions, see: https://www.abs.gov.au/statistics/understanding-statistics/statistical-terms-and-concepts/measures-error
        """
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        super().__call__(pdata)
        if self.get_count() >= self.__max_repeats:
            return False

        if self.get_count() > 1:
            N: int = len(self._runtimes)
            assert N > 0
            se: float = st.tstd(self._runtimes) / math.sqrt(N)
            mean = numpy.mean(self._runtimes)
            rse: float = se if mean == 0 else se / numpy.mean(self._runtimes)
            if self._verbose:
                print(
                    f"At repeat #{self.get_count()}, SE={se}, RSE={rse}, mean={mean}"
                )
                print(f"Previous runtimes={self._runtimes}")
                print(
                    f"Continue? {self.get_count() <= self.__min_repeats or rse > self.__thresh}"
                )

        return self.get_count() <= self.__min_repeats or rse > self.__thresh
