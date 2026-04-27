"""
Abstract base classes for profile analysis components.

Defines the interfaces for:
- ClassSelector: Assigns performance class labels to data points
- ClassifierTrainer: Trains classification models
- FactorAnalyzer: Extracts influential factors from trained models

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl


@dataclass
class ClassificationResult:
    """Result of classification containing labels and metadata."""
    labels: np.ndarray
    """Array of class labels (e.g., 'SLOW', 'FAST' or 0, 1)"""
    class_names: list[str]
    """Names of the classes in order"""
    parameters: dict[str, Any]
    """Parameters used for classification (e.g., cutoff value)"""


@dataclass
class TrainedModel:
    """Wrapper for a trained classification model with metadata."""
    model: Any
    """The trained model object"""
    feature_names: list[str]
    """Names of features used for training"""
    original_predictors: list[str]
    """Original predictor column names (before encoding)"""
    parameters: dict[str, Any]
    """Training parameters"""

    @property
    def n_features(self) -> int:
        """Number of features used in training."""
        return len(self.feature_names)


@dataclass
class FactorImportance:
    """Importance score for a single factor."""
    name: str
    """Factor name"""
    importance: float
    """Importance score (higher = more influential)"""
    original_name: str | None = None
    """Original column name if encoded (e.g., 'category=A' -> 'category')"""


@dataclass
class ModelSummary:
    """Statistical summary of a trained model."""
    n_nodes: int
    """Number of nodes in the model"""
    n_leaves: int
    """Number of leaf/terminal nodes"""
    aic: float | None
    """Akaike Information Criterion (lower is better)"""
    accuracy: float
    """Classification accuracy on training data"""
    log_likelihood: float | None
    """Log-likelihood of the model"""


class ClassSelector(ABC):
    """
    Abstract base class for performance class selectors.

    A ClassSelector assigns class labels (e.g., 'LEFT'/'RIGHT', 'FAST'/'SLOW')
    to data points based on a performance metric. Different implementations
    can use different strategies (cutoff-based, quantile-based, clustering, etc.)
    """

    @abstractmethod
    def classify(self, data: pl.DataFrame, metric_col: str) -> ClassificationResult:
        """
        Classify data points into performance classes.

        Args:
            data: DataFrame containing the performance data
            metric_col: Name of the column containing the performance metric

        Returns:
            ClassificationResult containing labels and metadata
        """
        pass

    @abstractmethod
    def get_class_counts(self, data: pl.DataFrame, metric_col: str) -> dict[str, int]:
        """
        Count data points in each class without returning full labels.

        Args:
            data: DataFrame containing the performance data
            metric_col: Name of the column containing the performance metric

        Returns:
            Dictionary mapping class names to counts
        """
        pass

    @property
    @abstractmethod
    def class_names(self) -> list[str]:
        """Names of the classes this selector produces."""
        pass


class ClassifierTrainer(ABC):
    """
    Abstract base class for classification model trainers.

    A ClassifierTrainer takes labeled performance data and trains a model
    to predict class membership based on other features/factors.
    """

    @abstractmethod
    def train(
        self,
        data: pl.DataFrame,
        labels: np.ndarray,
        exclude_cols: list[str] | None = None,
        max_predictors: int = 100,
        max_correlation: float = 0.99
    ) -> TrainedModel | None:
        """
        Train a classification model.

        Args:
            data: DataFrame containing features
            labels: Array of class labels (same length as data)
            exclude_cols: Columns to exclude from features
            max_predictors: Maximum number of predictors to use
            max_correlation: Maximum correlation threshold for predictors

        Returns:
            TrainedModel wrapper, or None if training fails
        """
        pass

    @abstractmethod
    def summarize(
        self,
        trained_model: TrainedModel,
        data: pl.DataFrame,
        labels: np.ndarray
    ) -> ModelSummary | None:
        """
        Compute summary statistics for a trained model.

        Args:
            trained_model: The trained model to summarize
            data: Original training data
            labels: Training labels

        Returns:
            ModelSummary with statistics, or None if computation fails
        """
        pass

    def calculate_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        n_parameters: int
    ) -> tuple[float, float, float] | None:
        """
        Calculate classification metrics: Accuracy, Log-Likelihood, and AIC.

        Args:
            y_true: True class labels
            y_pred: Predicted class labels
            n_parameters: Number of parameters in the model (k)

        Returns:
            Tuple of (accuracy, log_likelihood, aic), or None if calculation fails
        """
        try:
            correct = (y_true == y_pred).sum()
            n = len(y_true)

            if n == 0:
                return None

            accuracy = correct / n
            log_likelihood = n * np.log(max(accuracy, 1e-10))
            aic = float(2 * n_parameters - 2 * log_likelihood)

            return accuracy, log_likelihood, aic
        except Exception:
            return None

    def _calculate_aic(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        n_parameters: int
    ) -> float | None:
        """
        Calculate AIC (Akaike Information Criterion) for a classification model.

        Delegates to src.core.stats.aic.calculate_aic.

        Args:
            y_true: True class labels
            y_pred: Predicted class labels
            n_parameters: Number of parameters in the model

        Returns:
            AIC value, or None if calculation fails
        """
        from src.core.stats.aic import calculate_aic
        return calculate_aic(y_true, y_pred, n_parameters)


class FactorAnalyzer(ABC):
    """
    Abstract base class for factor importance analyzers.

    A FactorAnalyzer extracts and ranks factors by their influence
    on the classification outcome.
    """

    @abstractmethod
    def analyze(self, trained_model: TrainedModel) -> list[FactorImportance]:
        """
        Analyze factor importance in a trained model.

        Args:
            trained_model: A trained classification model

        Returns:
            List of FactorImportance objects sorted by importance (descending)
        """
        pass

    def get_top_factors(
        self,
        trained_model: TrainedModel,
        n: int = 10
    ) -> list[FactorImportance]:
        """
        Get the top N most important factors.

        Args:
            trained_model: A trained classification model
            n: Number of top factors to return

        Returns:
            List of top N FactorImportance objects
        """
        all_factors = self.analyze(trained_model)
        return all_factors[:n]

    def get_aggregated_importance(
        self,
        trained_model: TrainedModel
    ) -> dict[str, float]:
        """
        Get importance aggregated by original column name.

        For one-hot encoded categorical variables, sums the importance
        across all encoded indicator columns.

        Args:
            trained_model: A trained classification model

        Returns:
            Dictionary mapping original column names to aggregated importance
        """
        factors = self.analyze(trained_model)

        aggregated: dict[str, float] = {}
        for factor in factors:
            key = factor.original_name or factor.name
            aggregated[key] = aggregated.get(key, 0.0) + factor.importance

        return aggregated

    def get_top_aggregated_factors(
        self,
        trained_model: TrainedModel,
        n: int = 10
    ) -> list[tuple[str, float]]:
        """
        Get top factors with aggregated importance by original column.

        Args:
            trained_model: A trained classification model
            n: Number of top factors to return

        Returns:
            List of (column_name, aggregated_importance) tuples
        """
        aggregated = self.get_aggregated_importance(trained_model)
        sorted_factors = sorted(aggregated.items(), key=lambda x: x[1], reverse=True)
        return sorted_factors[:n]

    def _extract_original_name(self, encoded_name: str) -> str | None:
        """
        Extract original column name from an encoded feature name.

        For encoded categorical features like 'category=A', returns 'category'.
        For numeric features, returns None (name is already original).

        Args:
            encoded_name: Feature name (possibly encoded)

        Returns:
            Original column name, or None if not encoded
        """
        if '=' in encoded_name:
            return encoded_name.split('=')[0]
        return None
