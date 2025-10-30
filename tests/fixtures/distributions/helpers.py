#!/usr/bin/env python3
"""
Helper functions for synthetic distribution generation in tests.

Provides convenient access to distributions.py functions with preset parameters
for common test scenarios (convergence testing, boundary testing, etc.).

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import List
import numpy
from . import distributions


def generate_constant_data(
    value: float = 12.34, noise_scale: float = 0.0, count: int = 100
) -> List[float]:
    """
    Generate constant data for boundary testing.

    Useful for testing repeaters at metric extremes (RSE=0, CI≈0, HDI width≈0, etc).

    Args:
        value: The constant value
        noise_scale: Standard deviation of added normal noise (0 for perfectly constant)
        count: Number of samples

    Returns:
        List of constant samples
    """
    data = distributions._constant(
        {"loc": value, "scale": noise_scale, "repetitions": count}
    )
    return data.tolist() if hasattr(data, "tolist") else list(data)


def generate_normal_data(
    mean: float = 10.0, std_dev: float = 1.0, count: int = 50
) -> List[float]:
    """
    Generate normally distributed data.

    Args:
        mean: Mean of the distribution
        std_dev: Standard deviation
        count: Number of samples

    Returns:
        List of normally distributed samples
    """
    data = distributions._normal(
        {"mean": mean, "std_dev": std_dev, "repetitions": count}
    )
    return data.tolist() if hasattr(data, "tolist") else list(data)


def generate_tight_normal_data(
    mean: float = 10.0, std_dev: float = 0.5, count: int = 50
) -> List[float]:
    """
    Generate tight normal distribution (low variance) for convergence testing.

    Args:
        mean: Mean of the distribution
        std_dev: Standard deviation (default: 0.5 for tight distribution)
        count: Number of samples

    Returns:
        List of tightly distributed samples
    """
    return generate_normal_data(mean, std_dev, count)


def generate_high_variance_normal_data(
    mean: float = 10.0, std_dev: float = 5.0, count: int = 50
) -> List[float]:
    """
    Generate high-variance normal data for non-convergence testing.

    Args:
        mean: Mean of the distribution
        std_dev: Standard deviation (default: 5.0 for high variance)
        count: Number of samples

    Returns:
        List of high-variance samples
    """
    return generate_normal_data(mean, std_dev, count)


def generate_uniform_data(
    loc: float = 2.5, scale: float = 8.0, count: int = 50
) -> List[float]:
    """
    Generate uniformly distributed data.

    Args:
        loc: Lower bound
        scale: Size of the interval
        count: Number of samples

    Returns:
        List of uniformly distributed samples
    """
    data = distributions._uniform(
        {"loc": loc, "scale": scale, "repetitions": count}
    )
    return data.tolist() if hasattr(data, "tolist") else list(data)


def generate_bimodal_data(
    modes_params: dict = None, count: int = 50
) -> List[float]:
    """
    Generate bimodal distribution data.

    Useful for testing repeaters' sensitivity to multimodal data.

    Args:
        modes_params: Optional dict with 'parameters' key containing mode specs
        count: Number of samples

    Returns:
        List of bimodally distributed samples
    """
    if modes_params is None:
        params_dict = {
            "parameters": [
                {"mean": 20, "std_dev": 1},
                {"mean": 27, "std_dev": 1.7},
            ],
            "modes": 2,
            "repetitions": count,
        }
    else:
        params_dict = modes_params
        params_dict["repetitions"] = count

    data = distributions._bimodal({"parameters": params_dict, "repetitions": count})
    return data.tolist() if hasattr(data, "tolist") else list(data)


def generate_multimodal_data(
    modes: int = 3, count: int = 50
) -> List[float]:
    """
    Generate multimodal distribution data.

    Useful for testing repeaters' sensitivity to complex distributions.

    Args:
        modes: Number of modes
        count: Number of samples

    Returns:
        List of multimodally distributed samples
    """
    mode_params_dict = {
        "parameters": [
            {"mean": 20 + i * 5, "std_dev": 1.0 + i * 0.1}
            for i in range(modes)
        ],
        "modes": modes,
        "repetitions": count,
    }
    data = distributions._multimodal(
        {"parameters": mode_params_dict, "repetitions": count}
    )
    return data.tolist() if hasattr(data, "tolist") else list(data)


def generate_lognormal_data(
    shape: float = 0.95, mean: float = 10.0, std_dev: float = 1.8, count: int = 50
) -> List[float]:
    """
    Generate log-normally distributed data.

    Useful for testing repeaters with skewed distributions.

    Args:
        shape: Shape parameter
        mean: Mean of the distribution
        std_dev: Standard deviation
        count: Number of samples

    Returns:
        List of log-normally distributed samples
    """
    data = distributions._lognormal(
        {"shape": shape, "mean": mean, "std_dev": std_dev, "repetitions": count}
    )
    return data.tolist() if hasattr(data, "tolist") else list(data)


def generate_cauchy_data(
    loc: float = 8.0, scale: float = 2.5, count: int = 50
) -> List[float]:
    """
    Generate heavy-tailed Cauchy distribution data.

    Useful for testing repeaters' robustness to outliers.

    Args:
        loc: Location parameter
        scale: Scale parameter
        count: Number of samples

    Returns:
        List of Cauchy distributed samples
    """
    data = distributions._cauchy(
        {"loc": loc, "scale": scale, "repetitions": count}
    )
    return data.tolist() if hasattr(data, "tolist") else list(data)


def generate_logistic_data(
    loc: float = 12.0, scale: float = 2.5, count: int = 50
) -> List[float]:
    """
    Generate logistically distributed data.

    Args:
        loc: Location parameter
        scale: Scale parameter
        count: Number of samples

    Returns:
        List of logistically distributed samples
    """
    data = distributions._logistic(
        {"loc": loc, "scale": scale, "repetitions": count}
    )
    return data.tolist() if hasattr(data, "tolist") else list(data)


def generate_sine_data(
    norm_mean: float = 1.0, norm_std: float = 0.1, count: int = 50
) -> List[float]:
    """
    Generate sinusoidal distribution data with noise.

    Useful for testing repeaters with periodic patterns.

    Args:
        norm_mean: Mean of added normal noise
        norm_std: Std dev of added normal noise
        count: Number of samples

    Returns:
        List of sinusoidally distributed samples
    """
    try:
        data = distributions._sine(
            {
                "norm_mean": norm_mean,
                "norm_std": norm_std,
                "pi_scale": 16,
                "sample_offset": 3,
                "repetitions": count,
            }
        )
        return data.tolist() if hasattr(data, "tolist") else list(data)
    except TypeError:
        # Work around bug in _sine that tries to call List[float]() as constructor
        # Generate sine data manually
        samples = numpy.sin(
            numpy.linspace(-16 * numpy.pi, 16 * numpy.pi, count)
        )
        samples += 3
        samples += numpy.random.normal(norm_mean, norm_std, size=count)
        return samples.tolist()
