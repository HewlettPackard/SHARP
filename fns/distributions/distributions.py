#!/usr/bin/env python3
r"""
Produce synthetically generated outputs based on a chosen distribution.

This function produces samples from several parametrized distributions,
providing a synthetic benchmark to test SHARP stopping criteria.

The code uses `scipy` and `numpy` to compute statistics, statistical tests, and
to fit statistical models to generate samples from the following distributions:

    * Normal distribution
    * Log-Normal distribution
    * Multimodal distribution
    * Bimodal distribution
    * Cauchy distribution
    * Uniform distribution
    * Log-Uniform distribution
    * Logistic distribution
    * Sine distribution
    * Constant distribution (with noise)

The Bash code below shows how you can obtain multiple samples from different
distributions. The output will be 1000 samples of each of the 4 distributions
named in the for loop range. We will run it locally and properly tag experiments
with the distribution name.

```bash
for i in normal multimodal uniform constant
do
    echo "$i"
    launchers/launch.py -v -e $i -b local -r 1 -t $i distributions "{\"method\":\"$i\",\"repetitions\":1000}"
done
```

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

from flask import request, Flask
from typing import *
import sys
import time
import json
import numpy
import os

import scipy.stats  # type: ignore
from scipy.stats import (
    halfcauchy,
    cosine,
    lognorm,
    norm,
    loglaplace,
    loguniform,
    logistic,
    uniform,
    randint,
)

_app = Flask(__name__)


def _normal(options: Dict[str, Any]) -> Union[float, List[float]]:
    """
    Produce samples from a Normal distribution.

    (See https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.norm.html)

    Arguments from JSON configuration file:

    mean:         The mean of the distribution (default: 10.0)
    std_dev:      The standard deviation of the distribution (default: 1.2)
    repetitions:  Number of samples. Use "None" instead of 1 for consistency in output type (default: None)
    """
    mean: float = options.get("mean", 10.0)
    std_dev: float = options.get("std_dev", 1.2)
    repetitions: int = options.get("repetitions", None)

    return norm.rvs(loc=mean, scale=std_dev, size=repetitions) # type: ignore


def _lognormal(options: Dict[str, Any]) -> Union[float, List[float]]:
    """
    Produce samples from a Log-Normal distribution.

    (See https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.lognorm.html)

    Arguments from JSON configuration file:

    shape:        Shape parameter for the distribution (default: 0.95)
    mean:         The mean of the distribution (default: 10.0)
    std_dev:      The standard deviation of the distribution (default: 1.8)
    repetitions:  Number of samples. Use "None" instead of 1 for consistency in output type (default: None)
    """
    shape: float = options.get("shape", 0.95)
    mean: float = options.get("mean", 10.0)
    std_dev: float = options.get("std_dev", 1.8)
    repetitions: int = options.get("repetitions", None)

    return lognorm.rvs(s=shape, loc=mean, scale=std_dev, size=repetitions) # type: ignore


def multimodal(options: Dict[str, Any]) -> Union[float, List[float]]:
    """
    Produce samples from a multimodal distribution.

    Arguments from JSON configuration file:

    modes:        Number of modes to sample from (default: random int in [2, 6])
    parameters:   List of dictionaries with mean and standard deviation for each mode (default: random float in [20, 60] (mean) and [0.5, 2] (std_dev))
    repetitions:  Number of samples. Use "None" instead of 1 for consistency in output type (default: None)
    """
    default_modes: int = randint.rvs(low=2, high=6)
    default_parameters: List[Dict[str, Any]] = [
        {
            "mean": uniform.rvs(loc=20, scale=60),
            "std_dev": uniform.rvs(loc=0.5, scale=2),
        }
        for m in range(default_modes)
    ]

    modes: int = options.get("modes", default_modes)
    parameters: List[Dict[str, Any]] = options.get("parameters", default_parameters)
    repetitions: int = options.get("repetitions", None)

    samples: Union[float, List[float]] = []

    if repetitions is None:
        chosen_mode: int = randint.rvs(low=0, high=modes)
        mode_parameters = parameters[chosen_mode].copy()
        mode_parameters["repetitions"] = None
        samples = _normal(mode_parameters)
    else:
        chosen_modes: List[int] = randint.rvs(low=0, high=modes, size=repetitions)

        samples = []

        for mode in chosen_modes:
            mode_parameters = parameters[mode].copy()
            mode_parameters["repetitions"] = None
            sample: Union[float, List[float]] = _normal(mode_parameters)

            if isinstance(sample, List):
                samples += sample
            else:
                samples.append(sample)

    return samples


def _multimodal(options: Dict[str, Any]) -> Union[float, List[float]]:
    """
    Produce samples from a multimodal distribution.

    Arguments from JSON configuration file:

    modes:        Number of modes to sample from (default: 3)
    parameters:   List of dictionaries with mean and standard deviation for each mode (default: [20, 12, 30] (mean), [1.3, 1, 1.4] (std_dev)
    repetitions:  Number of samples. Use "None" instead of 1 for consistency in output type (default: None)
    """
    repetitions: int = options.get("repetitions", None)
    default_parameters: Dict[str, Any] = {
        "parameters": [
            {"mean": 20, "std_dev": 1.3},
            {"mean": 12, "std_dev": 1},
            {"mean": 30, "std_dev": 1.4},
        ],
        "modes": 3,
        "repetitions": repetitions,
    }

    parameters: Dict[str, Any] = options.get("parameters", default_parameters)

    return multimodal(parameters)


def _bimodal(options: Dict[str, Any]) -> Union[float, List[float]]:
    """
    Produce samples from a bimodal distribution.

    Arguments from JSON configuration file:

    parameters:   List of dictionaries with mean and standard deviation for each mode (default: [20, 27] (mean), [1, 1.7] (std_dev)
    repetitions:  Number of samples. Use "None" instead of 1 for consistency in output type (default: None)
    """
    repetitions: int = options.get("repetitions", None)

    default_parameters: Dict[str, Any] = {
        "parameters": [{"mean": 20, "std_dev": 1}, {"mean": 27, "std_dev": 1.7}],
        "modes": 2,
        "repetitions": repetitions,
    }

    parameters: Dict[str, Any] = options.get("parameters", default_parameters)

    return multimodal(parameters)


def _cauchy(options: Dict[str, Any]) -> Union[float, List[float]]:
    """
    Produce samples from a Cauchy distribution.

    (See https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.cauchy.html)
    (See also https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.halfcauchy.html)

    Arguments from JSON configuration file:

    loc:          Location, or center, of the distribution (default: 8.0)
    scale:        Spread, or deviation, of the distribution (default: 2.5)
    repetitions:  Number of samples. Use "None" instead of 1 for consistency in output type (default: None)
    """
    loc: float = options.get("loc", 8.0)
    scale: float = options.get("scale", 2.5)
    repetitions: int = options.get("repetitions", None)

    return halfcauchy.rvs(loc=loc, scale=scale, size=repetitions) # type: ignore


def _uniform(options: Dict[str, Any]) -> Union[float, List[float]]:
    """
    Produce samples from a Uniform distribution.

    (See https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.uniform.html)

    Arguments from JSON configuration file:

    loc:          Location, or lower bound, of the uniform interval (default: 2.5)
    scale:        Size of the uniform interval starting at loc (default: 8.0)
    repetitions:  Number of samples. Use "None" instead of 1 for consistency in output type (default: None)
    """
    loc: float = options.get("loc", 2.5)
    scale: float = options.get("scale", 8.0)
    repetitions: int = options.get("repetitions", None)

    return uniform.rvs(loc=loc, scale=scale, size=repetitions) # type: ignore


def _loguniform(options: Dict[str, Any]) -> Union[float, List[float]]:
    """
    Produce samples from a Log-Uniform distribution.

    (See https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.loguniform.html)

    Arguments from JSON configuration file:

    a and b:      Distribution parameters (default: 10 (a) and 30 (b))
    loc:          Location, or center, of the distribution (default: 13)
    scale:        Spread, or deviation, of the distribution (default: 2.5)
    repetitions:  Number of samples. Use "None" instead of 1 for consistency in output type (default: None)
    """
    a: float = options.get("a", 10)
    b: float = options.get("b", 30)
    loc: float = options.get("loc", 13)
    scale: float = options.get("scale", 2.5)
    repetitions: int = options.get("repetitions", None)

    return loguniform.rvs(a=a, b=b, loc=loc, scale=scale, size=repetitions) # type: ignore


def _logistic(options: Dict[str, Any]) -> Union[float, List[float]]:
    """
    Produce samples from a Logistic distribution.

    (See https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.logistic.html)

    Arguments from JSON configuration file:

    loc:          Location, or center, of the distribution (default: 12)
    scale:        Spread, or deviation, of the distribution (default: 2.5)
    repetitions:  Number of samples. Use "None" instead of 1 for consistency in output type (default: None)
    """
    loc: float = options.get("loc", 12.0)
    scale: float = options.get("scale", 2.5)
    repetitions: int = options.get("repetitions", None)

    return logistic.rvs(loc=loc, scale=scale, size=repetitions) # type: ignore


def _sine(options: Dict[str, Any]) -> Union[float, List[float]]:
    """
    Produce samples from a Sinusiodal distribution with added Normal noise.

    (See https://numpy.org/doc/stable/reference/generated/numpy.sin.html)
    (See also https://numpy.org/doc/stable/reference/random/generated/numpy.random.normal.html)

    Arguments from JSON configuration file:

    norm_mean:      Mean of the added noise Normal (default: 1)
    norm_std:       Standard deviation of the added noise Normal (default: 0.1)
    pi_scale:       How many half periods to sample in each direction (default: 16)
    sample_offset:  Added offset to numpy.sin samples, which are in [-1, 1] (default: 3)
    repetitions:    Number of samples. Use "None" instead of 1 for consistency in output type (default: None)
    """
    norm_mean: float = options.get("norm_mean", 1)
    norm_std: float = options.get("norm_std", 0.1)
    pi_scale: float = options.get("pi_scale", 16)
    sample_offset: int = options.get("sample_offset", 3)
    repetitions: int = options.get("repetitions", None)

    samples = numpy.sin(
        numpy.linspace(-pi_scale * numpy.pi, pi_scale * numpy.pi, repetitions)
    )

    samples += sample_offset
    samples += numpy.random.normal(norm_mean, norm_std, size=repetitions)

    return List[float](samples.tolist())


def _constant(options: Dict[str, Any]) -> Union[float, List[float]]:
    """
    Produce samples from a Constant (Delta) distribution with added Normal noise.

    (See https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.uniform.html)

    Arguments from JSON configuration file:

    loc:          Constant value of the distribution (default: 12.34)
    scale:        Standard deviation of the added Normal noise, with mean = 0.0 (default: 0.1)
    repetitions:  Number of samples. Use "None" instead of 1 for consistency in output type (default: None)
    """
    loc: float = options.get("loc", 12.34)
    scale: float = options.get("scale", 0.1)
    repetitions: Union[int, None] = options.get("repetitions", None)

    if repetitions is None:
        return loc + uniform.rvs(loc=0.0, scale=scale) # type: ignore
    else:
        return numpy.array([loc] * repetitions) + norm.rvs( # type: ignore
            loc=0.0, scale=scale, size=repetitions
        )


@_app.route("/", methods=["POST"])
def sample(options: Union[str, Dict[str, Any]] = {}) -> str:
    """
    Produce samples from a number of distributions.

    Distribution choice is controlled by the "method" parameter (default: "normal"),
    which can have the following values:

    "normal":      Normal distribution<br>
    "lognormal":   Log-Normal distribution<br>
    "multimodal":  Multimodal distribution<br>
    "bimodal":     Bimodal distribution<br>
    "cauchy":      Cauchy distribution<br>
    "uniform":     Uniform distribution<br>
    "loguniform":  Log-Uniform distribution<br>
    "logistic":    Logistic distribution<br>
    "sine":        Sine distribution<br>
    "constant":    Constant distribution (with noise)<br>

    Other arguments from JSON configuration file:

    repetitions:  Number of samples. Use "None" instead of 1 for consistency in output type (default: None)

    Distribution-specific parameters: Check each function's documentation
    """
    if not options or isinstance(options, str):
        options_text: str = request.get_data(as_text=True)
        options = json.loads(options_text)

    if isinstance(options, Dict):
        method = options.get("method", "normal")
    else:
        raise (
            ValueError("Failed reading options dictionary, check parameter formatting")
        )

    sampler: Callable = available_methods[method] # type: ignore
    results: Union[float, List[float]] = sampler(options=options)

    if type(results) is numpy.float64: # type: ignore
        output = f"@@@ [single-sample] Sample produced with method {method}: {results}"

    elif isinstance(results, List):
        output = ""

        for result in results:
            output += (
                f"@@@ [multi-sample] Sample produced with method {method}: {result}\n"
            )

    else:
        raise (ValueError("Returned sample is not a list or float"))

    return output


# Method dictionary matching input strings with function names
available_methods: Dict[str, Any] = {
    "normal": _normal,
    "lognormal": _lognormal,
    "multimodal": _multimodal,
    "bimodal": _bimodal,
    "cauchy": _cauchy,
    "uniform": _uniform,
    "loguniform": _loguniform,
    "logistic": _logistic,
    "sine": _sine,
    "constant": _constant,
}


def main() -> str:
    """Fission entry point."""
    return sample()


#################################
if __name__ == "__main__":
    if os.getenv("FAAS_ENV") == "knative":
        ## Knative entry point
        _app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

    method: str = ""
    if len(sys.argv) < 2:
        try:
            method = input(f"Chose sampling method among {available_methods.keys()}: ")
        except Exception as ex:
            print(
                f"Arguments: string specifying sampling method, can be in {available_methods.keys()}"
            )
            exit(-1)
    else:
        method = sys.argv[1]

    print(sample(method))
