"""
Feature importance calculation for classification models.

Provides an abstract interface for computing feature importance scores from
trained models, with concrete implementations for decision trees and potential
future support for permutation-based importance (model-agnostic).

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable, Any
from sklearn.tree import DecisionTreeClassifier


@runtime_checkable
class FeatureImportanceModel(Protocol):
    """Protocol for models that support feature importance calculation."""

    @property
    def feature_names_(self) -> list[str]:
        """Feature names used in the model."""
        ...


class FeatureImportanceCalculator(ABC):
    """Abstract base class for feature importance calculators."""

    @abstractmethod
    def compute_importance(self, model: Any) -> dict[str, float]:
        """
        Compute feature importance scores.

        Args:
            model: Trained model with feature_names_ attribute

        Returns:
            Dictionary mapping feature names to importance scores (0-1 range)
        """
        pass

    @abstractmethod
    def get_ranked_features(self, model: Any) -> list[tuple[str, float]]:
        """
        Get features ranked by importance (descending).

        Args:
            model: Trained model

        Returns:
            List of (feature_name, importance_score) tuples, sorted descending
        """
        pass


class TreeFeatureImportance(FeatureImportanceCalculator):
    """
    Feature importance for decision tree classifiers.

    Uses sklearn's built-in Gini importance (mean decrease in impurity),
    which measures how much each feature contributes to decreasing the
    weighted impurity across all nodes where it's used.
    """

    def compute_importance(self, model: DecisionTreeClassifier) -> dict[str, float]:
        """
        Compute feature importance using Gini importance.

        Args:
            model: Trained DecisionTreeClassifier with feature_names_ attribute

        Returns:
            Dictionary mapping feature names to importance scores (0-1, sum=1)

        Raises:
            ValueError: If model is not a DecisionTreeClassifier or lacks feature_names_
        """
        if not isinstance(model, DecisionTreeClassifier):
            raise ValueError(f"Expected DecisionTreeClassifier, got {type(model)}")

        if not hasattr(model, 'feature_names_'):
            raise ValueError("Model must have feature_names_ attribute")

        # Get Gini importance from sklearn
        # feature_importances_ is normalized to sum to 1.0
        importances = model.feature_importances_

        # Map to feature names
        feature_names = model.feature_names_
        return {name: float(imp) for name, imp in zip(feature_names, importances)}

    def get_ranked_features(self, model: DecisionTreeClassifier) -> list[tuple[str, float]]:
        """
        Get features ranked by Gini importance (descending).

        Args:
            model: Trained DecisionTreeClassifier

        Returns:
            List of (feature_name, importance_score) tuples, sorted by importance

        Examples:
            >>> calculator = TreeFeatureImportance()
            >>> # Assume tree is trained
            >>> ranked = calculator.get_ranked_features(tree)
            >>> # ranked[0] is most important feature
            >>> ranked[0][0]  # feature name
            'cache_misses'
            >>> ranked[0][1]  # importance score
            0.45
        """
        importance_dict = self.compute_importance(model)

        # Sort by importance descending
        return sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)


def get_feature_importance(model: Any) -> dict[str, float]:
    """
    Get feature importance scores for a trained model.

    Automatically selects the appropriate calculator based on model type.

    Args:
        model: Trained model (currently supports DecisionTreeClassifier)

    Returns:
        Dictionary mapping feature names to importance scores

    Raises:
        ValueError: If model type is not supported

    Examples:
        >>> from sklearn.tree import DecisionTreeClassifier
        >>> # ... train tree ...
        >>> importance = get_feature_importance(tree)
        >>> importance['cache_misses']
        0.45
    """
    if isinstance(model, DecisionTreeClassifier):
        calculator = TreeFeatureImportance()
        return calculator.compute_importance(model)
    else:
        raise ValueError(f"Unsupported model type: {type(model)}")


def get_ranked_features(model: Any) -> list[tuple[str, float]]:
    """
    Get features ranked by importance (descending).

    Automatically selects the appropriate calculator based on model type.

    Args:
        model: Trained model (currently supports DecisionTreeClassifier)

    Returns:
        List of (feature_name, importance_score) tuples, sorted descending

    Raises:
        ValueError: If model type is not supported

    Examples:
        >>> from sklearn.tree import DecisionTreeClassifier
        >>> # ... train tree ...
        >>> ranked = get_ranked_features(tree)
        >>> ranked[0]  # Most important feature
        ('cache_misses', 0.45)
        >>> ranked[1]  # Second most important
        ('dTLB_misses', 0.23)
    """
    if isinstance(model, DecisionTreeClassifier):
        calculator = TreeFeatureImportance()
        return calculator.get_ranked_features(model)
    else:
        raise ValueError(f"Unsupported model type: {type(model)}")
