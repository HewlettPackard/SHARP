"""
Decision (DC) meta-heuristic repeater strategy.

Uses multiple sub-repeaters to decide when to stop.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any, Dict, List

import numpy
import scipy.stats  # type: ignore
from sklearn.mixture import GaussianMixture  # type: ignore
from sklearn.model_selection import GridSearchCV  # type: ignore

from .base import RunData
from .bb import BBRepeater
from .ci import CIRepeater
from .count import CountRepeater
from .gmm import GaussianMixtureRepeater
from .hdi import HDIRepeater
from .rse import RSERepeater


class DecisionRepeater(CountRepeater):
    """
    Meta-heuristic stopping rule

    The DecisionRepeater uses other repeaters in this file to determine when to
    stop. It employs a series of statistical tests, described in this classes'
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
                   as "RSERepeater", and the corresponding values are dictionaries with
                   instances of the repeater and a boolean for the last decision made
                   by the repeater. For example, a valid repeaters dictionary is:
                   { "RSERepeater": { "repeater": RSERepeater(options), "last_decision": True } }.
                   (default (looks for sub-repeater options in the same dictionary):
                       {"RSERepeater": {"repeater": RSERepeater(options),
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

    _DEFAULT_VALUES = {
        "max": {
            "default": 400,
            "type": int,
            "help": "Maximum number of runs allowed",
        },
        "starting_sample": {
            "default": 25,
            "type": int,
            "help": "Number of samples to collect before testing",
        },
        "test_after": {
            "default": 10,
            "type": int,
            "help": "Test decision every N additional runs",
        },
        "p_threshold": {
            "default": 0.05,
            "type": float,
            "help": "P-value threshold for statistical tests (0-1)",
        },
        "lognormal_threshold": {
            "default": 0.1,
            "type": float,
            "help": "P-value threshold for lognormal test (0-1)",
        },
        "gaussian_threshold": {
            "default": 0.1,
            "type": float,
            "help": "P-value threshold for gaussian test (0-1)",
        },
        "uniform_threshold": {
            "default": 0.1,
            "type": float,
            "help": "P-value threshold for uniform test (0-1)",
        },
        "mean_threshold": {
            "default": 0.05,
            "type": float,
            "help": "Threshold for mean stability test (0-1)",
        },
        "autocor_threshold": {
            "default": 0.8,
            "type": float,
            "help": "Threshold for autocorrelation test (0-1)",
        },
        "goodness_threshold": {
            "default": 2,
            "type": float,
            "help": "Likelihood threshold for multimodal detection",
        },
        "max_gaussian_components": {
            "default": 6,
            "type": int,
            "help": "Maximum Gaussian components for multimodal test",
        },
        "gaussian_covariances": {
            "default": ["spherical", "tied", "diag", "full"],
            "type": list,
            "help": "Covariance types for Gaussian model",
        },
        "decision_verbose": {
            "default": False,
            "type": bool,
            "help": "Enable verbose output for distribution detection",
        },
    }

    def __init__(self, options: Dict[str, Any]):
        """Initialize meta-parameters from options."""
        super().__init__(options)
        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("DC", ropts)

        self.__max_repeats: int = ropts.get("max", self._DEFAULT_VALUES["max"]["default"])

        self.__starting_sample: int = min(
            ropts.get("starting_sample", self._DEFAULT_VALUES["starting_sample"]["default"]), self.__max_repeats
        )
        self.__test_after: int = ropts.get("test_after", self._DEFAULT_VALUES["test_after"]["default"])

        assert self.__test_after != 0, "test_after must be positive"

        self.__p_threshold: float = ropts.get("p_threshold", self._DEFAULT_VALUES["p_threshold"]["default"])
        self.__lognormal_threshold: float = ropts.get("lognormal_threshold", self._DEFAULT_VALUES["lognormal_threshold"]["default"])
        self.__gaussian_threshold: float = ropts.get("gaussian_threshold", self._DEFAULT_VALUES["gaussian_threshold"]["default"])
        self.__uniform_threshold: float = ropts.get("uniform_threshold", self._DEFAULT_VALUES["uniform_threshold"]["default"])
        self.__mean_threshold: float = ropts.get("mean_threshold", self._DEFAULT_VALUES["mean_threshold"]["default"])

        self.__autocor_threshold: float = ropts.get("autocor_threshold", self._DEFAULT_VALUES["autocor_threshold"]["default"])

        self.__goodness_threshold: float = ropts.get("goodness_threshold", self._DEFAULT_VALUES["goodness_threshold"]["default"])
        self.__max_gaussian_components: int = ropts.get("max_gaussian_components", self._DEFAULT_VALUES["max_gaussian_components"]["default"])
        self.__gaussian_covariances: int = ropts.get(
            "gaussian_covariances", self._DEFAULT_VALUES["gaussian_covariances"]["default"]
        )

        self.__decision_verbose: bool = ropts.get("decision_verbose", self._DEFAULT_VALUES["decision_verbose"]["default"])

        self.__default_repeaters: Dict[str, Any] = {
            "RSERepeater": {"repeater": RSERepeater(options), "last_decision": True},
            "CIRepeater": {"repeater": CIRepeater(options), "last_decision": True},
            "HDIRepeater": {"repeater": HDIRepeater(options), "last_decision": True},
            "BBRepeater": {"repeater": BBRepeater(options), "last_decision": True},
            "GaussianMixtureRepeater": {
                "repeater": GaussianMixtureRepeater(options),
                "last_decision": True,
            },
        }
        self.__repeaters = ropts.get("repeaters", self.__default_repeaters)

    def _get_detected_distribution(self, pdata: List[float]) -> str:
        """Return the name of the distribution detected for the given data.

        Performs the same tests as __call__ but only returns the detected
        distribution name without making a decision.

        Args:
            pdata: List of runtime samples to analyze

        Returns:
            String name of detected distribution: "constant", "monotonic", "autocorrelated",
            "gaussian", "lognormal", "multimodal", "uniform", or "unknown"
        """
        if self._is_constant(pdata):
            return "constant"
        elif self._is_monotonic(pdata):
            return "monotonic"
        elif self._is_autocorrelated(pdata):
            return "autocorrelated"
        elif self._is_gaussian(pdata):
            return "gaussian"
        elif self._is_lognormal(pdata):
            return "lognormal"
        elif self._is_multimodal(pdata):
            return "multimodal"
        elif self._is_uniform(pdata):
            return "uniform"
        else:
            return "unknown"

    def __log_decision(self, message: str) -> None:
        """Log decision message if verbose mode is enabled.

        Args:
            message: Message to print if verbose mode is on
        """
        if self.__decision_verbose:
            print(message)

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
            self.__log_decision(info_string + " | Runtimes passed constant test")
            return False

        elif self._is_monotonic(self._runtimes):
            # Something is wrong if the sample is monotonic, stop execution.
            self.__log_decision(info_string + "| Runtimes passed monotonic test")
            return False

        elif self._is_autocorrelated(self._runtimes):
            self.__log_decision(info_string + "| Runtimes passed autocorrelated test")
            return self.__repeaters["BBRepeater"]["last_decision"]  # type: ignore

        elif self._is_gaussian(self._runtimes):
            # Sample is gaussian so far, use Gaussian stopping criteria.
            self.__log_decision(info_string + "| Runtimes passed gaussian test")
            return self.__repeaters["CIRepeater"]["last_decision"]  # type: ignore

        elif self._is_lognormal(self._runtimes):
            self.__log_decision(info_string + "| Runtimes passed lognormal test")
            return self.__repeaters["HDIRepeater"]["last_decision"]  # type: ignore

        elif self._is_multimodal(self._runtimes):
            self.__log_decision(info_string + "| Runtimes passed multimodal test")
            return self.__repeaters["GaussianMixtureRepeater"]["last_decision"]  # type: ignore

        elif self._is_uniform(self._runtimes):
            # Sample is constant so far, stop execution.
            self.__log_decision(info_string + " | Runtimes passed uniform test")
            return False

        elif self.get_count() >= self.__max_repeats:
            # Reached experimental budget, stop execution.
            self.__log_decision(info_string + "| Exhausted experimental budget, stop.")
            return False

        else:
            self.__log_decision(info_string + "| All tests failed, continue experiments")
            return True

    def _is_constant(self, pdata: List[float]) -> bool:
        """
        Helper function to determine if an array of samples is constant.

        Uses the mean_threshold class parameter determine if the distance
        between the smallest and largest samples is smaller than a percentage
        of the sample mean. If it is, returns True.

        Args:
            pdata: List of samples to be tested
        """
        self.__log_decision(
            f"[constant test] current max-min interval: {numpy.max(pdata) - numpy.min(pdata)} threshold: {self.__mean_threshold * numpy.mean(pdata)}"
        )

        return bool(
            (numpy.max(pdata) - numpy.min(pdata))
            <= self.__mean_threshold * numpy.mean(pdata)
        )

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

        self.__log_decision(
            f"[uniform_test] current gaussian p-value: {test_result.pvalue} threshold: {self.__uniform_threshold}"
        )

        return not (test_result.pvalue <= self.__uniform_threshold)

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

        self.__log_decision(
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

        self.__log_decision(
            f"[lognormal_test] current test p-value: {test_result.pvalue} threshold: {self.__lognormal_threshold}"
        )

        # https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.kstest.html
        # If the p-value of the test is too small, let's say <= 0.01, this means the
        # sample does NOT come from a lognormal distribution.
        # In other words, the NULL hypothesis is that the data come from a lognormal distribution.
        return not (test_result.pvalue <= self.__lognormal_threshold)

    def _is_multimodal(self, pdata: List[float]) -> bool:
        """
        Helper function used to determine if an array of samples is multimodal.

        This uses a variation of the algorithm described in the
        GaussianMixtureRepeater class, but this function returns True with
        the additional condition that the number of detected modes must be
        more than 1.

        Strengthened detection prevents false positives on uniform distributions by:
          1. Requiring BIC to strongly prefer 2 components (not exploring 3+)
             - Bimodal: BIC is minimized at 2, adding more hurts BIC
             - Uniform: BIC keeps improving as components increase (adding them helps fit flat data)
          2. Requiring component means to be well-separated
          3. Requiring minimum samples per component
          4. Using significant BIC penalty

        Args:
            pdata: List of samples to be tested
        """
        X_data = numpy.array(pdata).reshape(-1, 1)
        n_samples = len(pdata)
        data_std = numpy.std(pdata)

        # Fit models with different numbers of components to check BIC trend
        max_components = min(self.__max_gaussian_components, max(2, n_samples // 50))

        param_grid = {
            "n_components": range(1, max_components + 1),
            "covariance_type": self.__gaussian_covariances,
        }

        grid_search = GridSearchCV(
            GaussianMixture(), param_grid=param_grid, scoring=lambda est, X: -est.bic(X)
        )
        multi_model = grid_search.fit(X_data)

        best_components = multi_model.best_params_["n_components"]
        multi_bic = multi_model.best_estimator_.bic(X_data)
        model_loglikelihood = numpy.abs(multi_model.best_estimator_.score(X_data))

        # For true multimodal (especially bimodal), fit 3 components to check if BIC gets worse
        # Bimodal: BIC(3 components) >> BIC(2 components) - adding a 3rd mode hurts fit
        # Uniform: BIC(3 components) ≈ BIC(2 components) or better - can always add more
        if best_components >= 2:
            model_3 = GaussianMixture(n_components=3, covariance_type=multi_model.best_params_["covariance_type"])
            model_3.fit(X_data)
            bic_3 = model_3.bic(X_data)
            # For bimodal, BIC should increase significantly when forcing 3 components
            # For uniform, BIC should stay similar or decrease (can fit flat data with 3 as well as 2)
            bic_penalty_for_3 = bic_3 - multi_bic
        else:
            bic_penalty_for_3 = 0.0

        # Get component means from best model
        component_means = multi_model.best_estimator_.means_.flatten()

        # Calculate mean separation
        sorted_means = numpy.sort(component_means)
        if len(sorted_means) >= 2:
            mean_gaps = numpy.diff(sorted_means)
            min_gap = numpy.min(mean_gaps)
            # For multimodal: gaps should be significant (at least 0.5 * data_std)
            mean_separation_threshold = 0.5 * data_std
        else:
            min_gap = 0.0
            mean_separation_threshold = 1.0

        # Samples per component ratio
        samples_per_component = n_samples / float(best_components)
        min_samples_per_component = 10.0

        # BIC improvement threshold (single vs best multi)
        single_model = GaussianMixture(n_components=1)
        single_model.fit(X_data)
        single_bic = single_model.bic(X_data)
        bic_improvement = single_bic - multi_bic
        bic_threshold = 15.0

        self.__log_decision(
            f"[multimodal_test] components: {best_components}, samples/component: {samples_per_component:.1f}, "
            f"min_mean_gap: {min_gap:.2f} (threshold: {mean_separation_threshold:.2f}), "
            f"BIC(best) - BIC(3): {bic_penalty_for_3:.1f} (should be >0 for true multimodal), "
            f"BIC improvement: {bic_improvement:.1f} (threshold: {bic_threshold}), "
            f"likelihood: {model_loglikelihood:.3f}"
        )

        # True multimodal requires ALL of:
        # 1. More than 1 component
        # 2. Well-separated component means
        # 3. Adequate samples per component
        # 4. Significant BIC evidence for multi-component
        # 5. Good likelihood fit
        # 6. BIC penalty for adding 3rd component (bimodal has this, uniform doesn't)
        return bool(
            best_components >= 2
            and min_gap >= mean_separation_threshold
            and samples_per_component >= min_samples_per_component
            and bic_improvement >= bic_threshold
            and model_loglikelihood >= self.__goodness_threshold
            and bic_penalty_for_3 > 5.0  # Adding 3rd component should hurt (true multimodal)
        )

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

        self.__log_decision(
            f"[autocorrelated_test] current autocorr: {numpy.max(numpy.abs(__autocor(pdata)[1:]))}, threshold: {self.__autocor_threshold}"
        )

        return bool(numpy.max(numpy.abs(__autocor(pdata)[1:])) >= self.__autocor_threshold)
