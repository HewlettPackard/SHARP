"""
Akaike Information Criterion (AIC) calculation for model comparison.

Provides utilities for computing AIC, which is a metric for model selection
based on likelihood and complexity penalty.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np


def calculate_aic(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_parameters: int
) -> float | None:
    """
    Calculate AIC (Akaike Information Criterion) for a classification model.

    AIC = 2k - 2*ln(L), where:
    - k = number of parameters in the model
    - L = likelihood of the data given the model
    - ln(L) = sum of log probabilities of observations

    Lower AIC values indicate better model fit with appropriate complexity.

    Args:
        y_true: True class labels (numpy array)
        y_pred: Predicted class labels (numpy array)
        n_parameters: Number of parameters in the model (k)

    Returns:
        AIC value as float, or None if calculation fails or input is invalid

    Examples:
        >>> y_true = np.array([0, 1, 0, 1])
        >>> y_pred = np.array([0, 1, 0, 1])
        >>> aic = calculate_aic(y_true, y_pred, n_parameters=3)
        >>> aic  # Perfect accuracy: 6.0
        6.0

        >>> y_pred = np.array([0, 0, 0, 1])  # 75% accuracy
        >>> aic = calculate_aic(y_true, y_pred, n_parameters=3)
        >>> aic > 6.0  # Worse model has higher AIC
        True
    """
    try:
        # Validate inputs
        if len(y_true) != len(y_pred):
            return None

        if len(y_true) == 0:
            return None

        # Calculate accuracy (probability each sample is correct)
        n_samples = len(y_true)
        n_correct = (y_true == y_pred).sum()
        accuracy = n_correct / n_samples

        # Compute log-likelihood
        # For each correct prediction: ln(accuracy)
        # For each wrong prediction: ln(1 - accuracy)
        # Total: n_correct * ln(accuracy) + n_wrong * ln(1 - accuracy)

        if accuracy == 1.0:
            # Perfect accuracy: ln(1) = 0, so log-likelihood = 0
            log_likelihood = 0.0
        elif accuracy == 0.0:
            # No correct predictions: ln(0) undefined, use epsilon
            log_likelihood = n_samples * np.log(1e-10)
        else:
            # Standard case: mix of correct and incorrect
            n_wrong = n_samples - n_correct
            log_likelihood = n_correct * np.log(accuracy) + n_wrong * np.log(1 - accuracy)

        # AIC = 2k - 2*ln(L)
        aic = 2 * n_parameters - 2 * log_likelihood

        return float(aic)

    except Exception:
        return None
