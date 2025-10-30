"""
Block Bootstrap (BB) repeater strategy.

Stops when block bootstrap confidence intervals stabilize.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import copy
import random
from typing import Any, Dict, List, Optional

import numpy

from .base import RunData
from .count import CountRepeater


class BBRepeater(CountRepeater):
    """
    Stopping rule for autocorrelated series based on Block-boostrap

    BBRepeater stops repeating when the cl% confidence interval of the mean
    of samples obtained using the block boostrap methods remains stable.
    The goal of this method is to account for self-correlations in time series
    that can cause transient effects in performance by sampling using blocks.
    Based on the paper: "Performance Testing for Cloud Computing with Dependent
    Data Bootstrapping". https://doi.org/10.1109/ASE51524.2021.9678687
    """

    _DEFAULT_VALUES = {
        "epsilon": {
            "default": 0.01,
            "type": float,
            "help": "Autocorrelation threshold for negligible correlation",
        },
        "num_samples": {
            "default": 1000,
            "type": int,
            "help": "Number of bootstrap samples for mean estimation",
        },
        "cl_limit": {
            "default": 0.95,
            "type": float,
            "help": "Confidence level for bootstrap (0-1)",
        },
        "error_threshold": {
            "default": 0.03,
            "type": float,
            "help": "Acceptable error threshold for mean stability (0-1)",
        },
        "max": {
            "default": 200,
            "type": int,
            "help": "Maximum number of runs allowed",
        },
        "min": {
            "default": 20,
            "type": int,
            "help": "Minimum number of runs before checking",
        },
    }

    def __init__(self, options: Dict[str, Any]):
        """Initialize BB parameters from options."""
        super().__init__(options)
        self.__prev_means: List[float] = []

        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("BB", ropts)

        self.__epsilon: float = ropts.get("epsilon", self._DEFAULT_VALUES["epsilon"]["default"])
        self.__num_samples: int = ropts.get("num_samples", self._DEFAULT_VALUES["num_samples"]["default"])
        self.__cl_limit: float = ropts.get("cl_limit", self._DEFAULT_VALUES["cl_limit"]["default"])
        self.__thresh: float = ropts.get("error_threshold", self._DEFAULT_VALUES["error_threshold"]["default"])
        self.__max_repeats: int = ropts.get("max", self._DEFAULT_VALUES["max"]["default"])
        self.__min_repeats: int = ropts.get("min", self._DEFAULT_VALUES["min"]["default"])
        assert self.__min_repeats > 1, "Must have at least two samples to start with"

    def _autocor(self) -> Any:
        """
        Compute auto-correlations at all possible lags.

        Based on https://scicoding.com/4-ways-of-calculating-autocorrelation-in-python/
        """
        data = numpy.array(self._runtimes)
        mean = numpy.mean(data)
        var = numpy.var(data)
        ndata = data - mean
        acorr = numpy.correlate(ndata, ndata, "full")[len(ndata) - 1 :]
        return acorr / var / len(ndata)

    def _block_size(self, acf: List[float]) -> Optional[int]:
        """
        Return the block size (lag length) for which autocorrelation is negligible.

        This size corresponds to the index of first element in the autocorrelations
        that is less than self.epsilon.
        If no such value is found, returns None.
        """
        return next((i for i, v in enumerate(acf) if abs(v) < self.__epsilon), None)

    def _sample(self, bsize: int) -> List[float]:
        """
        Obtain a randomized sample of measurements from a current data set of runtimes while sampling entire units of size bsize at a time.

        The sample size will be no less than the current no. of measurements.
        """
        data: List[float] = self._runtimes
        samples: List[float] = []
        while len(samples) < len(data):
            idx = random.randint(0, len(data) - bsize)
            samples += data[idx : idx + bsize]

        return samples

    def _means_are_close_enough(self, bsize: int) -> bool:
        """
        Compare the means of the current data to the previous means.

        Returns true iff the means are close enough (within the error).
        """
        assert bsize is not None
        n = self.__num_samples
        means = [numpy.mean(self._sample(bsize)) for i in range(n)]
        prev = copy.copy(self.__prev_means)
        self.__prev_means = means   # type: ignore

        if not prev:
            return False  # Not enough samples to find a block with negligible correlations

        assert all(prev)  # No zeroes allowed, for division
        diffs = sorted([(means[i] - prev[i]) / prev[i] for i in range(n)])
        low = diffs[int(n * (1.0 - self.__cl_limit) / 2)]
        hi = diffs[int((1 + self.__cl_limit) * n / 2)]

        if self._verbose:
            print(
                f"BB at repeat {self.get_count()}\t bsize: {bsize}\tmeans: \
                    {means[0:10]}...\tdiffs: {diffs[0:10]}...\tlow: {low} high: {hi}"
            )
        return bool(low > -self.__thresh and hi < self.__thresh)

    def __call__(self, pdata: RunData) -> bool:
        """
        Stopping heuristic for BBRepeater.

        The block-bootstrap method (BB) intuitively works like this:
        - Find the "optimal" block size b, as described below
        - Sample randomly n/b blocks (where n is measurements) and collect the samples
        - Compute the mean of the samples and collect it in an array of length >= 1000
        - Compare the means to the previous means.
        - If it's less than e% error at a cl% level of confidence, stop.
        """
        super().__call__(pdata)
        N: int = len(self._runtimes)
        if N >= self.__max_repeats:
            return False
        elif N < self.__min_repeats:
            return True
        assert N >= 1

        acf = self._autocor()
        bsize = self._block_size(acf)
        if bsize is None:
            if self._verbose:
                print("Getting more samples until correlations are negligible")
            return True

        return not self._means_are_close_enough(bsize)
