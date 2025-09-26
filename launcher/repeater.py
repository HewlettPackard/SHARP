"""
Repeater class repeats an experiment for as long as a certain condition holds.

Each Repeater subclass supports a different type of condition. Every time
the object is invoked with operator __call__(), it checks for the condition
and returns True iff another repeat is warranted.
A repeater should save and/or measure all the state it needs to decide
whether to repeat or not. No data is passed to it after initialization.

The basic CountRepeater simply stops at a given repeat count and is perfectly
suitable if you can run many times quickly or you have a reasonable assumption
of how many repetitions are sufficient to capture the performance.

The rest of the Repeater subclasses try to intelligently apply a stopping
rule based on statistics of the samples collected so far.
Look at specific classes for documentation and assumptions.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""


import arviz
import copy
import math
import numpy
import random
from rundata import RunData
import warnings

import scipy  # type: ignore
import scipy.stats as st  # type: ignore

from sklearn.mixture import GaussianMixture  # type: ignore
from sklearn.model_selection import GridSearchCV  # type: ignore
from scipy.stats import ks_2samp
from typing import *


###################
class Repeater:
    """Base class for all Repeaters."""

    #################
    def __init__(self, options: Dict[str, Any]):
        """Initialize Repeater from options dictionary."""
        self._count: int = 0
        self._verbose = options.get("repeater_options", {}).get("verbose", False)

    #################
    def __call__(self, pdata: RunData) -> bool:
        """
        Invoke (test) Repeater.

        Args:
            pdata (RunData): the performance metrics for the latest run

        Returns:
            bool: True iff another repetition of the experiment should happen
        """
        self._count += 1
        return False

    def get_count(self) -> int:
        """Return total number of runs to date."""
        return self._count


##########################################


class CountRepeater(Repeater):
    """
    Simple Repeater that stops after predetermined number of runs.

    The simplest (default) condition is simply to count repetitions to a limit.
    It contains a lower bound as well to be used by subclasses, since this
    Repeater is essentially the superclass of all others.
    """

    def __init__(self, options: Dict[str, Any]):
        """Initialize count repeater from options."""
        super().__init__(options)
        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("CR", ropts)

        self._limit: int = int(ropts.get("max", 1))
        self._metric: str = ropts.get("metric", "outer_time")
        self._runtimes: List[float] = []

    def __call__(self, pdata: RunData) -> bool:
        """Stopping heuristic based on reaching maximum run count."""
        super().__call__(pdata)
        self._runtimes += pdata.get_metric(self._metric)
        return self._count < self._limit


###########################################################################
class SERepeater(CountRepeater):
    """Stop repeating when the normalized standard error of the previous runtime drops down below a threshold."""

    ##########################
    def __init__(self, options: Dict[str, Any]):
        """Initialize SE parameters from options."""
        super().__init__(options)
        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("SE", ropts)
        self.__thresh: float = ropts.get("error_threshold", 0.05)
        self.__min_repeats: int = ropts.get("min", 5)
        self.__max_repeats: int = ropts.get("max", 100)
        assert self.__max_repeats >= self.__min_repeats

    ##########################
    def __call__(self, pdata: RunData) -> bool:
        """
        Stopping heuristic for SERepater.

        Algorithm to determine whether enough repeats have run:
        1. If maximum repeats were reached or exceeded, return True
        2. Otherwise, add reported run times to record of all runtimes.
        3. If the fractional uncertainty (relative standard error) falls below the
           threshold and a minimum number of repeats was performed, return True.
        For definitions, see: https://www.webassign.net/question_assets/unccolphysmechl1/measurements/manual.html
        """
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        super().__call__(pdata)
        if self.get_count() >= self.__max_repeats:
            return False

        if self.get_count() > 1:
            N: int = len(self._runtimes)
            assert N > 0
            se: float = st.tstd(self._runtimes) / math.sqrt(N)
            mean = scipy.mean(self._runtimes)
            rel_se: float = se if mean == 0 else se / scipy.mean(self._runtimes)
            if self._verbose:
                print(
                    f"At repeat #{self.get_count()}, SE={se}, RSE={rel_se}, mean={mean}"
                )
                print(f"Previous runtimes={self._runtimes}")
                print(
                    f"Continue? {self.get_count() <= self.__min_repeats or rel_se > self.__thresh}"
                )

        return self.get_count() <= self.__min_repeats or rel_se > self.__thresh


###########################################################################
class CIRepeater(CountRepeater):
    """Stop repeating when the 95% right-tailed confidence interval of all runtime measurements is smaller than a threshold proportion of mean."""

    ##########################
    def __init__(self, options: Dict[str, Any]):
        """Initialize CI parameters from options."""
        super().__init__(options)
        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("CI", ropts)

        self.__ci_limit: float = ropts.get("ci_limit", 0.95)
        self.__thresh: float = ropts.get("error_threshold", 0.05)
        self.__min_repeats: int = int(ropts.get("min", 5))
        self.__max_repeats: int = int(ropts.get("max", 100))
        assert self.__max_repeats >= self.__min_repeats

    ##########################
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
            rel_ci: float = ci / scipy.mean(self._runtimes)
            if self._verbose:
                print(
                    f"At repeat #{self.get_count()}, CI={ci}, rel_CI={rel_ci}, mean={scipy.mean(self._runtimes)}"
                )
                print(f"Previous runtimes={self._runtimes}")
                print(
                    f"Continue?: {self.get_count() <= self.__min_repeats or rel_ci > self.__thresh}"
                )

        return self.get_count() < self.__min_repeats or rel_ci > self.__thresh


###########################################################################
class HDIRepeater(CountRepeater):
    """
    Repeater based on high-density interval.

    HDIRepeater stops repeating when the 95% highest-density interval
    of all runtime measurements is smaller than a threshold proportion of mean.
    Note: if the inherent noise of the task exceeds the error threshold, this
    method will never converge and will only stop when it reaches max_repeats.
    """

    ##########################
    def __init__(self, options: Dict[str, Any]):
        """Initialize HDI parameters from options."""
        super().__init__(options)
        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("HDI", ropts)

        self.__hdi_limit: float = ropts.get("hdi_limit", 0.89)
        self.__thresh: float = ropts.get("error_threshold", 0.1)
        self.__min_repeats: int = ropts.get("min", 5)
        self.__max_repeats: int = ropts.get("max", 200)
        assert self.__max_repeats >= self.__min_repeats

    ##########################
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
        #        warnings.filterwarnings("ignore", category=RuntimeWarning)
        super().__call__(pdata)
        if self.get_count() >= self.__max_repeats:
            return False

        if self.get_count() > 1:
            N: int = len(self._runtimes)
            hdi = arviz.hdi(numpy.asarray(self._runtimes), hdi_prob=self.__hdi_limit) # type: ignore
            mean = scipy.mean(self._runtimes)
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


###########################################################################
class BBRepeater(CountRepeater):
    """
    Block-bootstrapping stopping rule.

    BBRepeater stops repeating when the cl% confidence interval of the mean
    of samples obtained using the block boostrap methods remains stable.
    The goal of this method is to account for self-correlations in time series
    that can cause transient effects in performance by sampling using blocks.
    Based on the paper: "Performance Testing for Cloud Computing with Dependent
    Data Bootstrapping". https://doi.org/10.1109/ASE51524.2021.9678687
    """

    ##########################
    def __init__(self, options: Dict[str, Any]):
        """Initialize BB parameters from options."""
        super().__init__(options)
        self.__prev_means: List[float] = []

        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("BB", ropts)

        self.__epsilon: float = ropts.get("epsilon", 0.01)
        self.__num_samples: int = ropts.get("num_samples", 1000)
        self.__cl_limit: float = ropts.get("cl_limit", 0.95)
        self.__thresh: float = ropts.get("error_threshold", 0.03)
        self.__max_repeats: int = ropts.get("max", 200)
        self.__min_repeats: int = ropts.get("min", 10)
        assert self.__min_repeats > 1, "Must have at least two samples to start with"

    ##########################
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

    ##########################
    def _block_size(self, acf: List[float]) -> Optional[int]:
        """
        Return the block size (lag length) for which autocorrelation is negligible.

        This size corresponds to the index of first element in the autocorrelations
        that is less than self.epsilon.
        If no such value is found, returns None.
        """
        return next((i for i, v in enumerate(acf) if abs(v) < self.__epsilon), None)

    ##########################
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

    ##########################
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

    ##########################
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


###########################################################################
class GaussianMixtureRepeater(CountRepeater):
    """
    Gaussian Mixture stopping rule.

    The GaussianMixtureRepeater fits a Gaussian Mixture model to
    current measurements, and stops if the goodness of fit of the
    model above a threshold.

    The best fit is found by optimizing the BIC score:
    https://en.wikipedia.org/wiki/Bayesian_information_criterion

    This repeater uses the GaussianMixture model from sklearn:
    https://scikit-learn.org/stable/modules/generated/sklearn.mixture.GaussianMixture.html

    Args:
        goodness_threshold:       Likelihood value that triggers stopping (default: 2)
        max_gaussian_components:  Maximum gaussian components used in the model (default: 8)
        gaussian_covariances:     List of strings with covariance modes to be tested (default: ["spherical", "tied", "diag", "full"])
    """

    def __init__(self, options: Dict[str, Any]):
        """Initialize GMM from options."""
        super().__init__(options)

        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("GMM", ropts)

        self.__max_repeats: int = int(ropts.get("max", 100))
        self.__goodness_threshold: float = float(ropts.get("goodness_threshold", 2))
        self.__max_gaussian_components: int = int(
            ropts.get("max_gaussian_components", 8)
        )
        self.__gaussian_covariances: List[str] = ropts.get(
            "gaussian_covariances", ["spherical", "tied", "diag", "full"]
        )

    ##########################
    def __call__(self, pdata: RunData) -> bool:
        """Stopping heuristic using Gaussian Mixture model."""
        super().__call__(pdata)

        def gmm_bic_score(estimator: GaussianMixture, X_data: numpy.ndarray) -> Any: # type: ignore
            """
            Callable passed to GridSearchCV using the BIC score.

            It's negative because GridSearchCV maximizes by default.
            """
            return -estimator.bic(X_data)

        if self.get_count() <= min(
            self.__max_repeats - 1,
            self.__max_gaussian_components * len(self.__gaussian_covariances),
        ):
            return True

        else:
            param_grid = {
                "n_components": range(1, self.__max_gaussian_components),
                "covariance_type": self.__gaussian_covariances,
            }

            grid_search = GridSearchCV(
                GaussianMixture(), param_grid=param_grid, scoring=gmm_bic_score
            )

            model = grid_search.fit(numpy.array(self._runtimes).reshape(-1, 1))

            if self.get_count() >= self.__max_repeats:
                if self._verbose:
                    print(f"GMM exhausted experimental budget, stop.")
                return False

            return bool(
                numpy.abs(
                    model.best_estimator_.score(
                        numpy.array(self._runtimes).reshape(-1, 1)
                    )
                )
                <= self.__goodness_threshold
            )


###########################################################################
class KSRepeater(CountRepeater):
    """
    KS stopping rule.

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

    def __init__(self, options: Dict[str, Any]):
        """Initialize KSRepeater from options."""
        super().__init__(options)

        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("KS", ropts)

        self.__min_repeats: int = ropts.get("min", 5)
        self.__max_repeats: int = int(ropts.get("max", 1000))
        self.__threshold: float = float(ropts.get("threshold", 0.1))

    ##########################
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


class DecisionRepeater(CountRepeater):
    """
    Meta-heuristic stopping rule.

    The DecisionRepeater uses other repeaters in this file to determine when to
    stop.  It employs a series of statistical tests, described in this classes'
    functions, to determine which repeater will be consulted to decide if it's
    time to stop.

    Because of the number of distinct tests performed, this repeater has a large
    number of parameters. Additionally, each sub-repeater used in this repeater
    accepts its own parameters. The parameters of this class control the
    strictness of each statistical test, and the sub-repeaters' parameters
    control the strictness of the stopping rule encapsulated in each repeater.

    Args:
        decision_verbose:         Print information about succeeding tests (default: False)
        p_threshold:              P-value threshold for various tests (default: 0.1)
        lognormal_threshold:      P-value threshold for lognormal test (default: 0.1)
        gaussian_threshold:       Threshold for the gaussian test (default: 0.2)
        uniform_threshold:        Threshold for the uniform test (default: 0.2)
        mean_threshold:           Threshold for the mean test (default: 0.1)
        autocor_threshold:        Threshold for the autocorrelation test (default: 0.8)

    Args for the multimodal detection test:
        goodness_threshold:       Likelihood value that triggers stopping (default: 2)
        max_gaussian_components:  Maximum gaussian components used in the model (default: 8)
        gaussian_covariances:     List of strings with covariance modes to be tested (default: ["spherical", "tied", "diag", "full"])

    Args selecting sub-repeaters:
        repeaters: This should be a dictionary where the keys are repeater names, such
                   as "SERepeater", and the corresponding values are dictionaries with
                   instances of the repeater and a boolean for the last decision made
                   by the repeater. For example, a valid repeaters dictionary is:
                   { "SERepeater": { "repeater": SERepeater(options), "last_decision": True } }.
                   (default (looks for sub-repeater options in the same dictionary):
                       {"SERepeater": {"repeater": SERepeater(options),
                                   "last_decision": True},
                        "CIRepeater": {"repeater": CIRepeater(options),
                                   "last_decision": True},
                        "HDIRepeater": {"repeater": HDIRepeater(options),
                                    "last_decision": True},
                        "BBRepeater": {"repeater": BBRepeater(options),
                                   "last_decision": True},
                        "GaussianMixtureRepeater": {"repeater": GaussianMixtureRepeater(options),
                                                "last_decision": True}}
               )
    """

    def __init__(self, options: Dict[str, Any]):
        """Initialize meta-parameters from options."""
        super().__init__(options)
        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("DC", ropts)

        self.__max_repeats: int = ropts.get("max", 400)

        self.__starting_sample: int = min(
            ropts.get("starting_sample", 20), self.__max_repeats
        )
        self.__test_after: int = ropts.get("test_after", 10)

        assert self.__test_after != 0, "test_after must be positive"

        self.__p_threshold: float = ropts.get("p_threshold", 0.1)
        self.__lognormal_threshold: float = ropts.get("lognormal_threshold", 0.2)
        self.__gaussian_threshold: float = ropts.get("gaussian_threshold", 0.2)
        self.__uniform_threshold: float = ropts.get("uniform_threshold", 0.2)
        self.__mean_threshold: float = ropts.get("mean_threshold", 0.1)

        self.__autocor_threshold: float = ropts.get("autocor_threshold", 0.8)

        self.__goodness_threshold: float = ropts.get("goodness_threshold", 2)
        self.__max_gaussian_components: int = ropts.get("max_gaussian_components", 6)
        self.__gaussian_covariances: int = ropts.get(
            "gaussian_covariances", ["spherical", "tied", "diag", "full"]
        )

        self.__decision_verbose: bool = ropts.get("decision_verbose", False)

        self.__default_repeaters: Dict[str, Any] = {
            "SERepeater": {"repeater": SERepeater(options), "last_decision": True},
            "CIRepeater": {"repeater": CIRepeater(options), "last_decision": True},
            "HDIRepeater": {"repeater": HDIRepeater(options), "last_decision": True},
            "BBRepeater": {"repeater": BBRepeater(options), "last_decision": True},
            "GaussianMixtureRepeater": {
                "repeater": GaussianMixtureRepeater(options),
                "last_decision": True,
            },
        }

        self.__repeaters = ropts.get("repeaters", self.__default_repeaters)

    #########################
    def __call__(self, pdata: RunData) -> bool:
        """Stopping meta-heuristic."""
        super().__call__(pdata)

        for repeater_info in self.__repeaters.values():
            repeater_info["last_decision"] = repeater_info["repeater"](pdata)

        info_string: str = f"runs: {len(self._runtimes)}, decisions: {[(k, v['last_decision']) for k, v in self.__repeaters.items()]}"

        if (
            self.get_count() < self.__starting_sample
            or (self.get_count() - self.__starting_sample) % self.__test_after != 0
        ):
            # We're below initial sample size, or don't have enough samples to reassess, continue.
            return True

        elif self._is_constant(self._runtimes):
            # Sample is constant so far, stop execution.
            if self.__decision_verbose:
                print(info_string + f" | Runtimes passed constant test")

            return False

        elif self._is_monotonic(self._runtimes):
            # Something is wrong if the sample is monotonic, stop execution.
            if self.__decision_verbose:
                print(info_string + f"| Runtimes passed monotonic test")

            return False

        elif self._is_autocorrelated(self._runtimes):
            if self.__decision_verbose:
                print(info_string + f"| Runtimes passed autocorrelated test")

            return self.__repeaters["BBRepeater"]["last_decision"] # type: ignore

        elif self._is_gaussian(self._runtimes):
            # Sample is gaussian so far, use Gaussian stopping criteria.
            if self.__decision_verbose:
                print(info_string + f"| Runtimes passed gaussian test")

            return self.__repeaters["CIRepeater"]["last_decision"] # type: ignore

        elif self._is_lognormal(self._runtimes):
            if self.__decision_verbose:
                print(info_string + f"| Runtimes passed lognormal test")

            return self.__repeaters["HDIRepeater"]["last_decision"] # type: ignore

        elif self._is_multimodal(self._runtimes):
            if self.__decision_verbose:
                print(info_string + f"| Runtimes passed multimodal test")

            return self.__repeaters["GaussianMixtureRepeater"]["last_decision"] # type: ignore

        elif self._is_uniform(self._runtimes):
            # Sample is constant so far, stop execution.
            if self.__decision_verbose:
                print(info_string + f" | Runtimes passed uniform test")

            return False

        elif self.get_count() >= self.__max_repeats:
            # Reached experimental budget, stop execution.
            if self.__decision_verbose:
                print(info_string + f"| Exhausted experimental budget, stop.")

            return False

        else:
            if self.__decision_verbose:
                print(info_string + f"| All tests failed, continue experiments")

            return True

    #########################
    def _is_constant(self, pdata: List[float]) -> bool:
        """
        Helper function used to determine if an array of samples is constant.

        Uses the mean_threshold class parameter determine if the distance
        between the smallest and largest samples is smaller than a percentage
        of the sample mean. If it is, returns True.

        Args:
            pdata: List of samples to be tested
        """
        if self.__decision_verbose:
            print(
                f"[constant test] current max-min interval: {numpy.max(pdata) - numpy.min(pdata)} threshold: {self.__mean_threshold * numpy.mean(pdata)}"
            )

        return bool((
            numpy.max(pdata) - numpy.min(pdata))
            <= self.__mean_threshold * numpy.mean(pdata))

    #########################
    def _is_monotonic(self, pdata: List[float]) -> bool:
        """
        Helper function used to determine if an array of samples is monotonic.

        Returns True if every sample i + 1 is larger than sample i, or if
        every sample i + 1 is smaller than sample i.

        Args:
            pdata: List of samples to be tested
        """
        samples: Any = numpy.array(pdata)
        return (all(samples[1:] >= samples[:-1])) or (all(samples[1:] <= samples[:-1]))

    #########################
    def _is_uniform(self, pdata: List[float]) -> bool:
        """
        Helper function used to determine if an array of samples is uniform.

        First, fits a uniform distribution to samples using scipy.stats.uniform.fit.
        Then, performs a KS test with class parameter uniform_threshold, the
        fitted distribution's parameters, and the uniform distribution, using scipy.stats.kstest.
        Returns True if the test passes.

        Args:
            pdata: List of samples to be tested
        """
        uniform_parameters = scipy.stats.uniform.fit(pdata)
        test_result = scipy.stats.kstest(pdata, "uniform", uniform_parameters)

        if self.__decision_verbose:
            print(
                f"[uniform_test] current gaussian p-value: {test_result.pvalue} threshold: {self.__uniform_threshold}"
            )

        return not (test_result.pvalue <= self.__uniform_threshold)

    #########################
    def _is_gaussian(self, pdata: List[float]) -> bool:
        """
        Helper function used to determine if an array of samples is gaussian.

        First, fits a normal distribution to samples using scipy.stats.norm.fit.
        Then, performs a KS test with class parameter gaussian_threshold, the
        fitted distribution's parameters, and the normal distribution, using scipy.stats.kstest.
        Returns True if the test passes.

        Args:
            pdata: List of samples to be tested
        """
        normal_parameters = scipy.stats.norm.fit(pdata)
        test_result = scipy.stats.kstest(pdata, "norm", normal_parameters)

        if self.__decision_verbose:
            print(
                f"[gaussian_test] current gaussian p-value: {test_result.pvalue} threshold: {self.__gaussian_threshold}"
            )

        # https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.normaltest.html
        # If the p-value of the test is too small, let's say <= 0.01, this means the
        # sample does NOT come from a normal distribution.
        # In other words, the NULL hypothesis is that the data come from a normal distribution.
        return not (test_result.pvalue <= self.__gaussian_threshold)

    def _is_lognormal(self, pdata: List[float]) -> bool:
        """
        Helper function used to determine if an array of samples is lognormal.

        First, fits a lognormal distribution to samples using scipy.stats.lognorm.fit.
        Then, performs a KS test with class parameter lognormal_threshold, the
        fitted distribution's parameters, and the lognormal distribution, using scipy.stats.kstest.
        Returns True if the test passes.

        Args:
            pdata: List of samples to be tested
        """
        lognormal_parameters = scipy.stats.lognorm.fit(pdata)
        test_result = scipy.stats.kstest(pdata, "lognorm", lognormal_parameters)

        if self.__decision_verbose:
            print(
                f"[lognormal_test] current test p-value: {test_result.pvalue} threshold: {self.__lognormal_threshold}"
            )

        # https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.kstest.html
        # If the p-value of the test is too small, let's say <= 0.01, this means the
        # sample does NOT come from a lognormal distribution.
        # In other words, the NULL hypothesis is that the data come from a lognormal distribution.
        return not (test_result.pvalue <= self.__lognormal_threshold)

    #########################
    def _is_multimodal(self, pdata: List[float]) -> bool:
        """
        Helper function used to determine if an array of samples is multimodal.

        This uses a variation of the algorithm described in the
        GaussianMixtureRepeater class, but this function returns True with
        the additional condition that the number of detected modes must be
        more than 1.

        Args:
            pdata: List of samples to be tested
        """
        def gmm_bic_score(estimator: GaussianMixture, X_data: numpy.ndarray) -> Any: # type: ignore
            """
            Callable passed to GridSearchCV using the BIC score.

            It's negative because GridSearchCV maximizes by default.
            """
            return -estimator.bic(X_data)

        param_grid = {
            "n_components": range(1, self.__max_gaussian_components),
            "covariance_type": self.__gaussian_covariances,
        }

        grid_search = GridSearchCV(
            GaussianMixture(), param_grid=param_grid, scoring=gmm_bic_score
        )
        model = grid_search.fit(numpy.array(pdata).reshape(-1, 1))

        best_components = model.best_params_["n_components"]

        model_loglikelihood = numpy.abs(
            model.best_estimator_.score(numpy.array(pdata).reshape(-1, 1))
        )

        if self.__decision_verbose:
            print(
                f"[multimodal_test] current best components: {best_components}, current test likelihood: {model_loglikelihood} threshold: {self.__goodness_threshold}"
            )

        return bool(
            best_components >= 1
            and numpy.abs(
                model.best_estimator_.score(numpy.array(pdata).reshape(-1, 1))
            )
            >= self.__goodness_threshold
        )

    #########################
    def _is_autocorrelated(self, pdata: List[float]) -> bool:
        """
        Determine if an array of samples is autocorrelated.

        This uses a variation of the algorithm described in the autocor function of
        the BBRepeater class, but this function returns True if the coefficient of
        correlation is larger than the autocor_threshold class parameter

        Args:
            pdata: List of samples to be tested
        """
        def __autocor(x: Any) -> Any:
            data = numpy.array(x)
            mean = numpy.mean(data)
            var = numpy.var(data)
            ndata = data - mean
            acorr = numpy.correlate(ndata, ndata, "full")[len(ndata) - 1 :]
            return acorr / var / len(ndata)


        if self.__decision_verbose:
            print(
                f"[autocorrelated_test] current autocorr: {numpy.max(numpy.abs(__autocor(pdata)[1:]))}, threshold: {self.__autocor_threshold}"
            )

        return bool(numpy.max(numpy.abs(__autocor(pdata)[1:])) >= self.__autocor_threshold)


###################
def repeater_factory(options: Dict[str, Any]) -> Repeater:
    """Return a fully-constructed Repeater object based on options."""
    opt = options.get("repeats", "MAX")

    if "repeater_options" not in options:
        options["repeater_options"] = {}

    # First, handle count repeater, whose argument is an integer:
    if type(opt) is int:
        options["repeater_options"]["max"] = opt
        return CountRepeater(options)
    assert type(opt) is str
    if opt.isdigit():
        options["repeater_options"]["max"] = int(opt)
        return CountRepeater(options)
    elif opt == "MAX":
        return CountRepeater(options)

    # Handle all other repeaters
    elif opt == "SE":
        return SERepeater(options)
    elif opt == "CI":
        return CIRepeater(options)
    elif opt == "HDI":
        return HDIRepeater(options)
    elif opt == "BB":
        return BBRepeater(options)
    elif opt == "GMM":
        return GaussianMixtureRepeater(options)
    elif opt == "DC":
        return DecisionRepeater(options)
    elif opt == "KS":
        return KSRepeater(options)
    else:
        raise Exception(f"Unrecognized repeater {opt}")
