"""
Abstract base classes for profile analysis components.

Defines the interfaces for:
- ClassSelector: Assigns performance class labels to data points
- ClassifierTrainer: Trains classification models
- FactorAnalyzer: Extracts influential factors from trained models

© Copyright 2025--2026 Hewlett Packard Enterprise Development LP
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

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
            Ordered list of FactorImportance objects sorted by importance (descending).
            Each factor appears exactly once (no duplicates).
        """
        pass


class CausalDirection(Enum):
    """Direction of influence when causal direction is available."""

    FORWARD = "forward"
    REVERSE = "reverse"
    BIDIRECTIONAL = "bidirectional"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class InfluenceFactor:
    """Unified representation of an influential factor for analyzers."""

    name: str
    strength: float
    rank: int | None = None
    method: str | None = None
    direction: CausalDirection | None = None
    p_value: float | None = None
    lag: float | None = None
    lag_rows: int | None = None
    confidence_interval: tuple[float, float] | None = None
    falsification_plan: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class QualityResult:
    """Cross-validated predictive quality of an analyzer's factor selection.

    The same standardised evaluation is applied to every analyzer: build a
    cumulative cross-validated score curve by adding factors one at a time in
    the analyzer's ranked order, then average the per-step scores.  This is
    a rank-AUC: a model that places the most predictive columns *first* earns
    higher early-step scores and therefore a higher average, even when all
    analyzers ultimately return the same set of columns.

    Attributes:
        score: Mean of per-step CV scores across all evaluated prefix sizes
            (Balanced Accuracy for classification, R² for regression).
        std: Standard deviation of the per-step scores (spread over prefix sizes,
            not over folds — reflects how much the score grows as more factors
            are added).
        metric_name: Human-readable name of the scoring metric used.
        n_folds: Number of cross-validation folds used at each step.
        n_factors: Total number of factor columns actually evaluated.
    """

    score: float
    std: float
    metric_name: str
    n_folds: int
    n_factors: int


# Synthetic column name used when labels are injected as the outcome
LABEL_OUTCOME_COL = "__perf_label__"


class InfluenceAnalyzer(ABC):
    """Abstract base class for influence analyzers."""

    def evaluate_quality(
        self,
        factors: list["InfluenceFactor"],
        data: "pl.DataFrame",
        labels: "np.ndarray",
        outcome_col: str | None = None,
        outcome_mode: str = "classification",
        n_folds: int = 5,
        top_k: int = 10,
    ) -> "QualityResult | None":
        """Estimate cross-validated predictive quality of this analyzer's factors.

        Computes a **rank-AUC** score: for each prefix size k = 1, 2, …,
        min(n_factors, top_k), build a model trained on only the top-k features
        (in the analyzer's ranked order) and measure its cross-validated score.
        The final ``QualityResult.score`` is the mean across all prefix sizes.

        This design ensures that *ordering* is captured: two analyzers returning
        the same ten columns but in different order will receive different scores
        because the one that places more predictive columns at the top accumulates
        higher scores at the early prefix steps.

        Args:
            factors: Ranked influence factors from a prior ``analyze()`` call.
            data: DataFrame used in the analysis.
            labels: Numeric class labels (classification, integers 0/1/2…) or
                continuous outcome values (regression).
            outcome_col: Continuous metric column name (regression mode).
            outcome_mode: ``"classification"`` or ``"regression"``.
            n_folds: Number of cross-validation folds (default 5).
            top_k: Maximum prefix length to evaluate (default 10).

        Returns:
            :class:`QualityResult` with rank-AUC score and metadata, or ``None``
            if evaluation is not possible (too few samples, no valid predictors).
        """
        try:
            from sklearn.linear_model import LogisticRegression, Ridge
            from sklearn.model_selection import cross_val_score
            from sklearn.pipeline import make_pipeline
            from sklearn.preprocessing import StandardScaler

            if not factors or data is None or data.is_empty():
                return None

            # Build ranked list of unique numeric columns present in data.
            numeric_names: list[str] = []
            seen_names: set[str] = set()
            for factor in factors[:top_k]:
                name = factor.name
                if (
                    name in seen_names
                    or name not in data.columns
                    or name == LABEL_OUTCOME_COL
                    or data[name].dtype in (pl.Utf8, pl.Categorical)
                ):
                    continue
                seen_names.add(name)
                numeric_names.append(name)
            if not numeric_names:
                return None

            # Pre-fetch full matrix and impute NaN with column means once.
            X_full = data.select(numeric_names).to_numpy().astype(np.float64)
            col_means = np.nanmean(X_full, axis=0)
            nan_mask = np.isnan(X_full)
            X_full[nan_mask] = np.take(col_means, np.where(nan_mask)[1])

            if outcome_mode == "regression":
                if outcome_col and outcome_col in data.columns:
                    y = data[outcome_col].to_numpy().astype(np.float64)
                else:
                    y = labels.astype(np.float64)
                def make_pipe() -> Any:  # noqa: E306
                    return make_pipeline(StandardScaler(), Ridge())
                scoring = "r2"
                metric_name = "R\u00b2"
            else:
                y = labels.astype(int)
                def make_pipe() -> Any:  # noqa: E306
                    return make_pipeline(
                        StandardScaler(),
                        LogisticRegression(max_iter=300, random_state=42),
                    )
                scoring = "balanced_accuracy"
                metric_name = "Balanced Accuracy"

            effective_folds = min(n_folds, len(X_full) // 2)
            if effective_folds < 2:
                return None

            # Rank-AUC: evaluate score at each prefix k = 1 … len(numeric_names).
            step_scores: list[float] = []
            for k in range(1, len(numeric_names) + 1):
                X_k = X_full[:, :k]
                cv_scores = cross_val_score(
                    make_pipe(), X_k, y,
                    cv=effective_folds, scoring=scoring,
                )
                step_scores.append(float(np.mean(cv_scores)))

            return QualityResult(
                score=float(np.mean(step_scores)),
                std=float(np.std(step_scores)),
                metric_name=metric_name,
                n_folds=effective_folds,
                n_factors=len(numeric_names),
            )
        except Exception:
            import traceback
            traceback.print_exc()
            return None

    def _get_setting(self, settings: Any, key_path: str, default: Any = None) -> Any:
        """Safely retrieve a setting from a Settings-like object or dict."""
        if settings is None:
            return default
        if isinstance(settings, dict):
            return settings.get(key_path, default)
        if hasattr(settings, "get"):
            return settings.get(key_path, default)
        return default

    @property
    @abstractmethod
    def name(self) -> str:
        """Analyzer identifier used in settings and registry."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> dict[str, bool]:
        """Capability flags (e.g., lag, direction, uncertainty)."""
        pass

    @property
    def label(self) -> str:
        """Human-readable label for UI display (pulldown menu)."""
        # Default implementation: convert name to title case
        return self.name.replace("_", " ").title()

    @property
    def description(self) -> str:
        """Tooltip/help description explaining the analyzer."""
        # Default implementation: generic description
        return f"Analyze performance factors using {self.label}"

    def _resolve_outcome(
        self,
        data: pl.DataFrame,
        labels: np.ndarray,
        outcome_col: str | None,
        outcome_mode: str = "classification",
    ) -> tuple[np.ndarray, pl.DataFrame, str]:
        """Resolve the outcome array and column based on outcome_mode.

        VGO focuses on reshaping the performance distribution (classification),
        not just optimizing absolute performance (regression). By default, causal
        analyzers use the discrete performance labels as the outcome, matching
        the tree analyzer's approach. Regression mode is available when users
        want to analyze continuous metric relationships instead.

        Args:
            data: Input DataFrame
            labels: Performance class labels (numeric: 0, 1, 2, ...)
            outcome_col: Name of the continuous outcome column
            outcome_mode: "classification" (use labels) or "regression" (use
                continuous metric column). Passed from the GUI; defaults to
                "classification".

        Returns:
            (outcome_array, data_with_outcome, effective_outcome_col) where:
            - outcome_array: The outcome values to use for analysis
            - data_with_outcome: DataFrame with the effective outcome column
            - effective_outcome_col: Name of the column to use as outcome
        """
        use_labels = (
            outcome_mode == "classification"
            and labels is not None
            and len(labels) > 0
            and len(labels) == len(data)
            and len(np.unique(labels)) >= 2  # need at least 2 classes
        )

        if use_labels:
            # Inject labels as a synthetic column
            label_series = pl.Series(LABEL_OUTCOME_COL, labels.astype(np.float64))
            data_with_labels = data.with_columns(label_series)
            return labels.astype(np.float64), data_with_labels, LABEL_OUTCOME_COL

        # Regression mode (or classification fallback): use continuous outcome column
        if outcome_col and outcome_col in data.columns:
            return data[outcome_col].to_numpy(), data, outcome_col

        # Fallback: no valid outcome
        return np.array([]), data, outcome_col or ""

    @staticmethod
    def _coerce_timestamps(timestamps: np.ndarray) -> np.ndarray | None:
        """Coerce timestamps to numeric seconds for lag detection.

        Accepts numeric arrays, numpy datetime64 arrays, or string timestamps.
        Returns None when coercion fails.
        """
        from datetime import datetime, time as time_type

        if timestamps is None:
            return None

        arr = np.asarray(timestamps)
        if arr.size == 0:
            return None

        if arr.dtype.kind in ("i", "u", "f"):
            return arr.astype(float)

        if np.issubdtype(arr.dtype, np.datetime64):
            ns = arr.astype("datetime64[ns]").astype("int64")
            return ns.astype(float) / 1e9

        parsed: list[float] = []
        for value in arr:
            if value is None:
                parsed.append(float("nan"))
                continue
            if isinstance(value, (int, float, np.number)):
                parsed.append(float(value))
                continue

            text = str(value).strip()
            if not text:
                parsed.append(float("nan"))
                continue

            try:
                if "T" in text or "-" in text or "/" in text:
                    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
                    parsed.append(dt.timestamp())
                else:
                    tval = time_type.fromisoformat(text)
                    seconds = (
                        tval.hour * 3600
                        + tval.minute * 60
                        + tval.second
                        + tval.microsecond / 1_000_000
                    )
                    parsed.append(seconds)
            except Exception:
                return None

        parsed_arr = np.asarray(parsed, dtype=float)
        finite = parsed_arr[np.isfinite(parsed_arr)]
        if finite.size == 0:
            return None
        return parsed_arr - float(np.min(finite))

    @abstractmethod
    def analyze(
        self,
        data: pl.DataFrame,
        labels: np.ndarray,
        outcome_col: str | None = None,
        settings: Any | None = None,
        outcome_mode: str = "classification",
        **kwargs: Any,
    ) -> list[InfluenceFactor]:
        """Run analysis and return ranked influence factors.

        Args:
            data: Input DataFrame
            labels: Performance class labels
            outcome_col: Name of continuous outcome column
            settings: Settings object or dict
            outcome_mode: "classification" (use labels, default) or
                "regression" (use continuous metric column)
        """
        pass


class AnalyzerVisualizer(ABC):
    """Abstract base class for analyzer-specific visualization."""

    @abstractmethod
    def render_primary(
        self,
        factors: list[InfluenceFactor],
        data: pl.DataFrame,
        labels: np.ndarray,
        class_names: list[str],
        class_colors: list[str],
    ) -> Any:
        """Render analyzer-specific visualization output."""
        pass

    @abstractmethod
    def generate_narrative(
        self,
        factors: list[InfluenceFactor],
        class_names: list[str],
    ) -> str:
        """Generate a human-readable narrative summary."""
        pass

    def render_factor_badges(self, factor: InfluenceFactor) -> list[Any]:
        """Render inline badges for a factor; optional override."""
        return []

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
        analyze_fn = getattr(self, "analyze", None)
        if callable(analyze_fn):
            all_factors = cast(list[FactorImportance], analyze_fn(trained_model))
            return all_factors[:n]
        return []

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
        analyze_fn = getattr(self, "analyze", None)
        if callable(analyze_fn):
            factors = cast(list[FactorImportance], analyze_fn(trained_model))
        else:
            factors = []

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
