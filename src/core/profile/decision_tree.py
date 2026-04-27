"""
Decision tree classifier trainer for performance profiling.

Trains sklearn DecisionTreeClassifier models on performance data,
with support for categorical variable encoding and predictor selection.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import polars as pl
from sklearn.tree import DecisionTreeClassifier

from .base import ClassifierTrainer, TrainedModel, ModelSummary
from . import predictor_selection
from src.core.config.settings import Settings


class DecisionTreeTrainer(ClassifierTrainer):
    """
    Trains decision tree classifiers for performance classification.

    Uses sklearn's DecisionTreeClassifier with one-hot encoding for
    categorical variables and configurable tree parameters.
    """

    def __init__(
        self,
        max_depth: int = 5,
        min_samples_split: int = 5,
        min_samples_leaf: int = 2,
        random_state: int = 42
    ):
        """
        Initialize the decision tree trainer.

        Args:
            max_depth: Maximum depth of the tree
            min_samples_split: Minimum samples required to split a node
            min_samples_leaf: Minimum samples required in a leaf
            random_state: Random seed for reproducibility
        """
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state

    def train(
        self,
        data: pl.DataFrame,
        labels: np.ndarray,
        exclude_cols: list[str] | None = None,
        max_predictors: int = 100,
        max_correlation: float = 0.99,
        predictors: list[str] | None = None
    ) -> TrainedModel | None:
        """
        Train a decision tree classifier.

        Args:
            data: DataFrame containing features
            labels: Array of class labels (0/1)
            exclude_cols: Columns to exclude from features
            max_predictors: Maximum number of predictors to use
            max_correlation: Maximum correlation threshold
            predictors: Pre-selected predictor list (overrides selection)

        Returns:
            TrainedModel wrapper, or None if training fails
        """
        if data is None or data.is_empty():
            return None

        if exclude_cols is None:
            exclude_cols = []

        try:
            # Select predictors if not provided
            if predictors is None:
                # Need a metric column for predictor selection
                # Use a dummy metric based on labels
                predictors = predictor_selection.select_predictors_from_labels(
                    data, labels, exclude_cols, max_predictors, max_correlation
                )

            if not predictors:
                return None

            # Prepare feature matrix
            X_data = data.select(predictors)
            X, encoded_feature_names = predictor_selection.encode_features(X_data, predictors)

            if X is None:
                return None

            # Apply class-aware downsampling for efficient training
            X_sampled, labels_sampled = self._class_aware_downsample(X, labels)

            # Train tree
            # Use class_weight='balanced' to handle imbalanced datasets (e.g. few slow outliers)
            # This ensures that rare "Slow" cases are prioritized in splitting and classification
            tree = DecisionTreeClassifier(
                max_depth=self.max_depth,
                min_samples_split=self.min_samples_split,
                min_samples_leaf=self.min_samples_leaf,
                random_state=self.random_state,
                class_weight='balanced'
            )
            tree.fit(X_sampled, labels_sampled)

            return TrainedModel(
                model=tree,
                feature_names=encoded_feature_names,
                original_predictors=predictors,
                parameters={
                    "max_depth": self.max_depth,
                    "min_samples_split": self.min_samples_split,
                    "min_samples_leaf": self.min_samples_leaf,
                    "n_samples": len(labels),
                }
            )

        except Exception:
            import traceback
            traceback.print_exc()
            return None

    def _class_aware_downsample(
        self,
        X: np.ndarray,
        y: np.ndarray,
        min_class_size: int = 300,
        cv_threshold: float = 0.15,
        base_ratio: float = 0.20
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Intelligently downsample training data based on class characteristics.

        Preserves all samples from:
        - Small classes (count < min_class_size) - these are often the interesting outliers
        - Large but spread classes (CV > cv_threshold) - these have internal structure

        Aggressively downsamples:
        - Large concentrated classes (count >= min_class_size AND CV < cv_threshold)

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Class labels (n_samples,)
            min_class_size: Classes smaller than this are kept entirely
            cv_threshold: CV below this indicates a "concentrated" class suitable for downsampling
            base_ratio: For concentrated classes, fraction of samples to keep

        Returns:
            Tuple of (X_sampled, y_sampled)
        """
        settings = Settings()
        min_class_size = settings.get("profiling.tree_training.min_class_size", min_class_size)
        cv_threshold = settings.get("profiling.tree_training.cv_threshold", cv_threshold)
        base_ratio = settings.get("profiling.tree_training.base_sample_ratio", base_ratio)

        unique_classes = np.unique(y)

        # If only 2 classes or already small dataset, no downsampling needed
        if len(unique_classes) <= 2 and len(y) < 10000:
            return X, y

        # If dataset is very small, no downsampling
        if len(y) < 5000:
            return X, y

        indices_to_keep = []
        for cls in unique_classes:
            cls_mask = y == cls
            cls_indices = np.where(cls_mask)[0]
            n_cls = len(cls_indices)

            # Always keep small classes entirely
            if n_cls < min_class_size:
                indices_to_keep.extend(cls_indices)
                continue

            # For larger classes, check if they're concentrated
            # Use first feature as proxy for concentration (assumes features are normalized)
            # Better: compute CV across all features, but that's more expensive
            cls_X = X[cls_indices]

            # Compute coefficient of variation for each feature
            cvs = []
            for feature_idx in range(X.shape[1]):
                feature_vals = cls_X[:, feature_idx]
                mean_val = np.mean(feature_vals)
                if abs(mean_val) > 1e-10:  # Avoid division by zero
                    cv = np.std(feature_vals) / abs(mean_val)
                    cvs.append(cv)

            # Use mean CV across features as concentration measure
            mean_cv = np.mean(cvs) if cvs else 1.0

            # Decide on sampling ratio
            if mean_cv < cv_threshold:
                # Concentrated class - aggressive downsampling
                keep_ratio = base_ratio
            else:
                # Spread class - keep more samples (scale with CV)
                keep_ratio = min(1.0, base_ratio * (1 + mean_cv))

            n_keep = max(min_class_size, int(n_cls * keep_ratio))
            n_keep = min(n_keep, n_cls)

            # Random sampling within the class
            if n_keep < n_cls:
                sampled_cls_indices = np.random.choice(cls_indices, n_keep, replace=False)
                indices_to_keep.extend(sampled_cls_indices)
            else:
                indices_to_keep.extend(cls_indices)

        indices_to_keep = np.array(indices_to_keep)
        return X[indices_to_keep], y[indices_to_keep]

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
            ModelSummary with statistics
        """
        if trained_model is None:
            return None

        tree = trained_model.model
        if tree is None:
            return None

        try:
            n_nodes = tree.tree_.node_count
            n_leaves = tree.tree_.n_leaves

            # Re-encode features for prediction
            X_data = data.select(trained_model.original_predictors)
            X, _ = predictor_selection.encode_features(X_data, trained_model.original_predictors)
            if X is None:
                return None

            # Drop NaN rows
            mask = ~np.isnan(X).any(axis=1)
            X_clean = X[mask]
            y_clean = labels[mask] if len(labels) == len(mask) else labels[:len(X_clean)]

            if len(X_clean) == 0:
                return None

            # Compute predictions
            y_pred = tree.predict(X_clean)

            # Compute metrics
            metrics = self.calculate_metrics(y_clean, y_pred, n_nodes)
            if metrics is None:
                return None

            accuracy, log_likelihood, aic = metrics

            return ModelSummary(
                n_nodes=n_nodes,
                n_leaves=n_leaves,
                aic=aic,
                accuracy=accuracy,
                log_likelihood=log_likelihood
            )

        except Exception:
            import traceback
            traceback.print_exc()
            return None


from .base import FactorAnalyzer, FactorImportance

class TreeFactorAnalyzer(FactorAnalyzer):
    """
    Analyzes factor importance from trained decision tree models.

    Uses sklearn's feature_importances_ which measures Gini importance
    (mean decrease in impurity) for each feature.
    """

    def analyze(self, trained_model: TrainedModel) -> list[FactorImportance]:
        """
        Analyze factor importance in a trained decision tree.

        Args:
            trained_model: TrainedModel containing a DecisionTreeClassifier

        Returns:
            List of FactorImportance objects sorted by importance (descending)
        """
        if trained_model is None or trained_model.model is None:
            return []

        tree = trained_model.model

        # Get feature importances from sklearn
        if not hasattr(tree, 'feature_importances_'):
            return []

        importances = tree.feature_importances_
        feature_names = trained_model.feature_names

        if len(importances) != len(feature_names):
            return []

        # Build list of FactorImportance objects
        factors = []
        for name, importance in zip(feature_names, importances):
            # Extract original column name for encoded features
            original_name = self._extract_original_name(name)

            factors.append(FactorImportance(
                name=name,
                importance=float(importance),
                original_name=original_name
            ))

        # Sort by importance descending
        factors.sort(key=lambda f: f.importance, reverse=True)

        return factors
