"""
Cutoff-based performance class selector.

Classifies data points into two categories based on a cutoff threshold:
- LEFT: metric value <= cutoff (typically "better" performance)
- RIGHT: metric value > cutoff (typically "worse" performance)

Also provides utilities for suggesting and searching for optimal cutoffs.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any, Callable
import numpy as np
import polars as pl
from scipy import stats

from .base import ClassSelector, ClassificationResult, ClassifierTrainer
from src.core.stats.distribution import _is_unimodal, _is_amodal, _find_modes
from src.core.config.settings import Settings


class CutoffClassSelector(ClassSelector):
    """
    Binary classification based on a cutoff threshold.

    Points with metric <= cutoff are labeled based on lower_is_better setting.
    Points with metric > cutoff are labeled oppositely.

    If lower_is_better=True: values <=cutoff get fast_label, >cutoff get slow_label
    If lower_is_better=False: values <=cutoff get slow_label, >cutoff get fast_label
    """

    def __init__(self, cutoff: float | None = None, lower_is_better: bool = True):
        """
        Initialize the cutoff selector.

        Args:
            cutoff: The cutoff threshold. If None, must be set before classify().
            lower_is_better: If True, lower values are better. If False, higher values are better.
        """
        self._cutoff = cutoff
        self._lower_is_better = lower_is_better

        # Load labels from settings
        settings = Settings()
        dist_settings = settings.get("gui.distribution", {})
        self.CLASS_FAST = dist_settings.get("fast_label", "FAST")
        self.CLASS_SLOW = dist_settings.get("slow_label", "SLOW")

    @property
    def cutoff(self) -> float | None:
        """Current cutoff value."""
        return self._cutoff

    @cutoff.setter
    def cutoff(self, value: float) -> None:
        """Set the cutoff value."""
        self._cutoff = value

    @property
    def lower_is_better(self) -> bool:
        """Whether lower values are better."""
        return self._lower_is_better

    @lower_is_better.setter
    def lower_is_better(self, value: bool) -> None:
        """Set the lower_is_better flag."""
        self._lower_is_better = value

    @property
    def class_names(self) -> list[str]:
        """Names of the classes: ['FAST', 'SLOW'] with order determined by lower_is_better."""
        if self._lower_is_better:
            # Lower is better: LEFT (<=cutoff) is FAST, RIGHT (>cutoff) is SLOW
            return [self.CLASS_FAST, self.CLASS_SLOW]
        else:
            # Higher is better: LEFT (<=cutoff) is SLOW, RIGHT (>cutoff) is FAST
            return [self.CLASS_SLOW, self.CLASS_FAST]

    def classify(self, data: pl.DataFrame, metric_col: str) -> ClassificationResult:
        """
        Classify data points based on cutoff.

        Args:
            data: DataFrame containing the performance data
            metric_col: Name of the column containing the performance metric

        Returns:
            ClassificationResult with 'FAST'/'SLOW' labels

        Raises:
            ValueError: If cutoff is not set or metric_col doesn't exist
        """
        if self._cutoff is None:
            raise ValueError("Cutoff must be set before classification")

        if metric_col not in data.columns:
            raise ValueError(f"Column '{metric_col}' not found in data")

        values = data[metric_col].to_numpy()
        # Determine labels based on lower_is_better
        if self._lower_is_better:
            # Lower is better: <=cutoff is FAST, >cutoff is SLOW
            labels = np.where(values <= self._cutoff, self.CLASS_FAST, self.CLASS_SLOW)
        else:
            # Higher is better: <=cutoff is SLOW, >cutoff is FAST
            labels = np.where(values <= self._cutoff, self.CLASS_SLOW, self.CLASS_FAST)

        return ClassificationResult(
            labels=labels,
            class_names=self.class_names,
            parameters={"cutoff": self._cutoff, "metric_col": metric_col, "lower_is_better": self._lower_is_better}
        )

    def get_class_counts(self, data: pl.DataFrame, metric_col: str) -> dict[str, int]:
        """
        Count points in FAST and SLOW classes.

        Args:
            data: DataFrame containing the performance data
            metric_col: Name of the column containing the performance metric

        Returns:
            Dictionary with 'FAST' and 'SLOW' counts
        """
        if self._cutoff is None:
            return {self.CLASS_FAST: 0, self.CLASS_SLOW: 0}

        if data is None or data.is_empty():
            return {self.CLASS_FAST: 0, self.CLASS_SLOW: 0}

        if metric_col not in data.columns:
            return {self.CLASS_FAST: 0, self.CLASS_SLOW: 0}

        values = data[metric_col].drop_nulls()
        if len(values) == 0:
            return {self.CLASS_FAST: 0, self.CLASS_SLOW: 0}

        n_below = int((values <= self._cutoff).sum())
        n_above = int((values > self._cutoff).sum())

        # Map counts to FAST/SLOW based on lower_is_better
        if self._lower_is_better:
            return {self.CLASS_FAST: n_below, self.CLASS_SLOW: n_above}
        else:
            return {self.CLASS_FAST: n_above, self.CLASS_SLOW: n_below}

    def classify_binary(self, data: pl.DataFrame, metric_col: str) -> np.ndarray:
        """
        Classify data points to binary string labels ("FAST"/"SLOW") for model training.

        Args:
            data: DataFrame containing the performance data
            metric_col: Name of the column containing the performance metric

        Returns:
            Array of "FAST" and "SLOW" string labels
        """
        result = self.label(data, metric_col)
        return result.labels


def suggest_cutoff(x: np.ndarray) -> float:
    """
    Suggest an initial cutoff point for classification based on distribution shape.

    Logic:
    - Very small samples (<=5): return median
    - Unimodal or amodal:
      - If left-skewed (skew <= -0.5): return 25th percentile
      - If right-skewed (skew >= 0.5): return 75th percentile
      - If symmetric: return first mode
    - Multimodal: return midpoint between two largest modes

    Args:
        x: 1D array of numeric values

    Returns:
        Suggested cutoff value
    """
    x_clean = x[~np.isnan(x)]

    if len(x_clean) <= 5:
        return float(np.median(x_clean))

    # Determine distribution shape
    if _is_unimodal(x_clean) or _is_amodal(x_clean):
        try:
            skewness = stats.skew(x_clean)
        except Exception:
            return float(np.median(x_clean))

        if np.isnan(skewness):
            return float(np.median(x_clean))

        if skewness <= -0.5:  # Left-tailed
            return float(np.percentile(x_clean, 25))
        elif skewness >= 0.5:  # Right-tailed
            return float(np.percentile(x_clean, 75))
        else:  # Symmetric distribution
            modes = _find_modes(x_clean)
            return float(modes[0]) if modes else float(np.median(x_clean))
    else:  # Multimodal: midpoint between two largest modes
        modes = _find_modes(x_clean)
        if len(modes) >= 2:
            return (modes[0] + modes[1]) / 2
        else:
            return float(np.median(x_clean))


def suggest_cutoff_from_data(data: pl.DataFrame, metric_col: str) -> float | None:
    """
    Compute suggested cutoff for a given metric in profiling data.

    Args:
        data: Polars DataFrame with profiling data
        metric_col: Column name to use. Must be provided and valid.

    Returns:
        Suggested cutoff value, or None if unable to compute
    """
    if data is None or data.is_empty():
        return None

    if not metric_col or metric_col.strip() == "":
        return None

    if metric_col not in data.columns:
        return None

    values = data[metric_col].drop_nulls().to_numpy()
    if len(values) < 2:
        return None

    try:
        return suggest_cutoff(values)
    except Exception:
        return None


def validate_cutoff_range(
    data: pl.DataFrame,
    metric_col: str,
    cutoff: float,
    lower_is_better: bool = True
) -> tuple[int, int]:
    """
    Check how many points fall into FAST and SLOW classes.

    Args:
        data: Polars DataFrame with metric data
        metric_col: Name of the metric column
        cutoff: Cutoff value to validate
        lower_is_better: Whether lower metric values are better

    Returns:
        Tuple of (n_fast, n_slow)
    """
    selector = CutoffClassSelector(cutoff, lower_is_better)
    counts = selector.get_class_counts(data, metric_col)
    return (counts[selector.CLASS_FAST],
            counts[selector.CLASS_SLOW])

def search_optimal_cutoff(
    data: pl.DataFrame,
    metric_col: str,
    trainer: ClassifierTrainer,
    class_selector_factory: Callable[[float], Any],
    exclusions: list[str],
    max_search_points: int = 100,
    progress_callback: Callable[[float, str], None] | None = None
) -> float | None:
    """
    Search for optimal cutoff point that minimizes the classifier's AIC.

    Args:
        data: DataFrame containing the data
        metric_col: Metric column for classification
        trainer: ClassifierTrainer instance
        class_selector_factory: Factory function that creates a ClassSelector given a cutoff
        exclusions: Predictor names to exclude
        max_search_points: Maximum cutoff points to search
        progress_callback: Optional progress callback(progress_pct, detail_str)

    Returns:
        Optimal cutoff value, or None if no valid models found
    """
    try:
        perf = data[metric_col].drop_nulls().to_numpy()
        if len(perf) == 0:
            return None

        # Select predictors once
        predictors = trainer.select_predictors(
            data, metric_col, exclusions, max_predictors=100, max_correlation=0.99
        )
        if not predictors:
            return None

        min_aic = float('inf')
        best_cutoff = None  # Initialize as None - only set if we find a valid tree

        max_points = min(max_search_points, len(perf))
        search_points = np.linspace(perf.min(), perf.max(), max_points)

        for i, cutoff_candidate in enumerate(search_points):
            cutoff = float(cutoff_candidate)

            # Create selector and get labels
            selector = class_selector_factory(cutoff)
            try:
                labels = selector.classify_binary(data, metric_col)
                label_counts = np.bincount(labels)

                # Skip if classes are too imbalanced (minimum 5% in each class)
                min_class_size = int(0.05 * len(labels))
                if any(count < min_class_size for count in label_counts):
                    continue
            except Exception:
                continue

            # Train tree with pre-selected predictors
            trained = trainer.train(
                data, labels, exclude_cols=exclusions, predictors=predictors
            )

            if trained is not None:
                summary = trainer.summarize(trained, data, labels)
                if summary is not None and summary.n_nodes > 1:
                    if summary.aic is not None and summary.aic < min_aic:
                        min_aic = summary.aic
                        best_cutoff = cutoff

            if progress_callback:
                progress_callback((i + 1) / max_points, f"Point {i+1} of {max_points}")

        return best_cutoff  # Will be None if no valid trees found

    except Exception:
        import traceback
        traceback.print_exc()
        return None


def search_optimal_cutoff_with_classifier(
    data: pl.DataFrame,
    metric_col: str,
    trainer: ClassifierTrainer,
    labeler_factory: Callable[[float], Any],
    exclusions: list[str] | None = None,
    max_search_points: int = 100,
    progress_callback: Callable[..., Any] | None = None
) -> float | None:
    """
    Search for optimal cutoff point that minimizes decision tree AIC using labelers.

    This searches through potential cutoff points to find the one that produces
    the best decision tree classifier (in terms of AIC).

    Args:
        data: Polars DataFrame with features and metric
        metric_col: Name of the metric column
        trainer: ClassifierTrainer instance (e.g., DecisionTreeTrainer)
        labeler_factory: Function that takes cutoff and returns a PerformanceLabeler
        exclusions: List of columns to exclude from features
        max_search_points: Maximum number of cutoff points to try
        progress_callback: Optional callback(progress_pct: float, detail: str)

    Returns:
        Optimal cutoff value, or None if search fails
    """
    if data is None or data.is_empty():
        return None

    if exclusions is None:
        exclusions = []

    try:
        # Get valid metric values
        valid_mask = data[metric_col].is_not_null()
        valid_data = data.filter(valid_mask)

        if len(valid_data) < 10:
            return None

        perf = valid_data[metric_col].to_numpy()

        # Get potential predictors
        exclude_cols = set(exclusions) | {metric_col, "start", "task"}
        candidate_cols = [c for c in valid_data.columns if c not in exclude_cols]

        # Filter to columns with variance
        n_unique_expr = [pl.col(c).n_unique().alias(c) for c in candidate_cols]
        n_unique_counts = valid_data.select(n_unique_expr).row(0)
        predictors = [col for col, n_uniq in zip(candidate_cols, n_unique_counts) if n_uniq > 1]

        if not predictors:
            return None

        # Search for optimal cutoff
        min_aic = float('inf')
        best_cutoff = None  # Initialize as None - only set if we find a valid tree

        max_points = min(max_search_points, len(perf))
        search_points = np.linspace(perf.min(), perf.max(), max_points)

        for i, cutoff_candidate in enumerate(search_points):
            cutoff = float(cutoff_candidate)

            # Create labeler and get labels
            labeler = labeler_factory(cutoff)
            try:
                metric_values = valid_data[metric_col].to_numpy()
                str_labels = labeler.label(metric_values)

                # Convert string labels to numeric
                unique_labels = labeler.get_class_names()
                label_to_int = {label: idx for idx, label in enumerate(unique_labels)}
                labels = np.array([label_to_int[label] for label in str_labels])

                label_counts = np.bincount(labels)

                # Skip if classes are too imbalanced (minimum 5% in each class)
                min_class_size = int(0.05 * len(labels))
                if any(count < min_class_size for count in label_counts):
                    continue
            except Exception:
                continue

            # Train tree with pre-selected predictors
            trained = trainer.train(
                valid_data, labels, exclude_cols=list(exclude_cols), predictors=predictors
            )

            if trained is not None:
                summary = trainer.summarize(trained, valid_data, labels)
                if summary is not None and summary.n_nodes > 1:
                    if summary.aic is not None and summary.aic < min_aic:
                        min_aic = summary.aic
                        best_cutoff = cutoff

            if progress_callback:
                progress_callback((i + 1) / max_points, f"Point {i+1} of {max_points}")

        return best_cutoff  # Will be None if no valid trees found

    except Exception:
        import traceback
        traceback.print_exc()
        return None
