"""
Classification utilities for performance data.

Binary classification of runtime measurements into "slow" and "fast" categories
using decision trees.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.metrics import accuracy_score, precision_score, recall_score
from typing import Dict
import polars as pl


def format_tree_text(tree: DecisionTreeClassifier, feature_names: list[str]) -> str:
    """
    Format decision tree as text for display.

    Args:
        tree: Fitted DecisionTreeClassifier
        feature_names: List of feature column names

    Returns:
        Text representation of tree structure
    """
    try:
        if not feature_names:
            feature_names = [f"Feature_{i}" for i in range(tree.n_features_in_)]
        tree_text = export_text(tree, feature_names=feature_names)
        return str(tree_text)
    except Exception as e:
        return f"Error formatting tree: {str(e)}"


def get_tree_metrics(tree: DecisionTreeClassifier, X: pl.DataFrame, y: pl.Series) -> Dict[str, float]:
    """
    Calculate classification metrics for decision tree.

    Args:
        tree: Fitted DecisionTreeClassifier
        X: Feature dataframe
        y: Target series (0 for fast, 1 for slow)

    Returns:
        Dict with accuracy, precision, recall
    """
    try:
        X_array = X.to_numpy() if isinstance(X, pl.DataFrame) else X
        y_array = y.to_numpy() if isinstance(y, pl.Series) else y

        # Get predictions
        y_pred = tree.predict(X_array)

        # Calculate metrics with zero_division handling
        acc = accuracy_score(y_array, y_pred)
        prec = precision_score(y_array, y_pred, zero_division=0)
        rec = recall_score(y_array, y_pred, zero_division=0)

        return {
            "accuracy": float(acc),
            "precision": float(prec),
            "recall": float(rec)
        }
    except Exception:
        return {
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0
        }
