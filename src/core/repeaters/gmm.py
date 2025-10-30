"""
Gaussian Mixture Model (GMM) repeater strategy.

Stops when goodness of fit of Gaussian Mixture model exceeds threshold.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any, Dict, List

import numpy
from sklearn.mixture import GaussianMixture  # type: ignore
from sklearn.model_selection import GridSearchCV  # type: ignore

from .base import RunData
from .count import CountRepeater


class GaussianMixtureRepeater(CountRepeater):
    """
    Gaussian Mixture stopping rule

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

    _DEFAULT_VALUES = {
        "goodness_threshold": {
            "default": 2,
            "type": float,
            "help": "Likelihood threshold for stopping (higher = stricter)",
        },
        "max_gaussian_components": {
            "default": 8,
            "type": int,
            "help": "Maximum number of Gaussian components in model",
        },
        "gaussian_covariances": {
            "default": ["spherical", "tied", "diag", "full"],
            "type": list,
            "help": "Covariance types to test: spherical, tied, diag, full",
        },
        "max": {
            "default": 100,
            "type": int,
            "help": "Maximum number of runs allowed",
        },
        "starting_sample": {
            "default": 20,
            "type": int,
            "help": "Minimum number of runs before checking threshold",
        },
    }

    def __init__(self, options: Dict[str, Any]):
        """Initialize GMM from options."""
        super().__init__(options)

        ropts: Dict[str, Any] = options.get("repeater_options", {})
        ropts = ropts.get("GMM", ropts)

        self.__max_repeats: int = int(ropts.get("max", self._DEFAULT_VALUES["max"]["default"]))
        self.__min_repeats: int = int(ropts.get("starting_sample", ropts.get("min", self._DEFAULT_VALUES["starting_sample"]["default"])))
        self.__goodness_threshold: float = float(ropts.get("goodness_threshold", self._DEFAULT_VALUES["goodness_threshold"]["default"]))
        self.__max_gaussian_components: int = int(
            ropts.get("max_gaussian_components", self._DEFAULT_VALUES["max_gaussian_components"]["default"])
        )
        self.__gaussian_covariances: List[str] = ropts.get(
            "gaussian_covariances", self._DEFAULT_VALUES["gaussian_covariances"]["default"]
        )

    def __call__(self, pdata: RunData) -> bool:
        """Stopping heuristic using Gaussian Mixture model."""
        super().__call__(pdata)

        def gmm_bic_score(estimator: GaussianMixture, X_data: numpy.ndarray) -> Any:  # type: ignore
            """
            Callable passed to GridSearchCV using the BIC score.

            It's negative because GridSearchCV maximizes by default.
            """
            return -estimator.bic(X_data)

        if self.get_count() < self.__min_repeats or self.get_count() <= min(
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
