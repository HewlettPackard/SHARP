"""
Abstract base class for trained-model influence analyzers.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import numpy as np
import polars as pl

from src.core.profile.base import InfluenceAnalyzer, InfluenceFactor, TrainedModel


class TrainedModelInfluenceAnalyzer(InfluenceAnalyzer, ABC):
    """Abstract base class for analyzers that fit a trained model."""

    def __init__(self) -> None:
        self._trained_model: TrainedModel | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable analyzer key."""

    @property
    @abstractmethod
    def capabilities(self) -> dict[str, bool]:
        """Analyzer capability flags."""

    @property
    def trained_model(self) -> TrainedModel | None:
        return self._trained_model

    @abstractmethod
    def analyze(
        self,
        data: pl.DataFrame,
        labels: np.ndarray,
        outcome_col: str | None = None,
        settings: Any | None = None,
        exclude_cols: list[str] | None = None,
        max_predictors: int | None = None,
        max_correlation: float | None = None,
        predictors: list[str] | None = None,
        outcome_mode: str = "classification",
        **kwargs: Any,
    ) -> list[InfluenceFactor]:
        """Train model and return ranked influence factors."""

    def _bootstrap_ci(
        self,
        data: pl.DataFrame,
        labels: np.ndarray,
        trained_model: TrainedModel,
        exclude_cols: list[str],
        max_predictors: int,
        max_correlation: float,
        n_samples: int,
        feature_names: list[str] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, tuple[float, float]]:
        n_rows = len(data)
        if n_rows < 3 or n_samples <= 0:
            return {}

        requested = set(feature_names) if feature_names else set(trained_model.feature_names)
        importances_by_feature: dict[str, list[float]] = {
            name: [] for name in trained_model.feature_names if name in requested
        }
        if not importances_by_feature:
            return {}
        indexed_data = data.with_row_index("_sample_idx")

        for i in range(n_samples):
            # Preserve class proportions during bootstrap when labels represent
            # a small number of classes (classification mode).
            idx = self._draw_bootstrap_indices(labels, n_rows)
            sample_data = (
                pl.DataFrame({"_sample_idx": idx.tolist()})
                .join(indexed_data, on="_sample_idx", how="left")
                .drop("_sample_idx")
            )
            sample_labels = labels[idx]
            sample_model = self._trainer.train(
                sample_data,
                sample_labels,
                exclude_cols=exclude_cols,
                max_predictors=max_predictors,
                max_correlation=max_correlation,
            )
            if sample_model is None:
                continue
            sample_factors = self._factor_analyzer.analyze(sample_model)
            sample_importances = {f.name: f.importance for f in sample_factors}
            for feature in importances_by_feature:
                importances_by_feature[feature].append(sample_importances.get(feature, 0.0))

            if progress_callback is not None:
                progress_callback(i + 1, n_samples)

        ci = {}
        for feature, values in importances_by_feature.items():
            if not values:
                continue
            low = float(np.percentile(values, 2.5))
            high = float(np.percentile(values, 97.5))
            ci[feature] = (low, high)
        return ci

    @staticmethod
    def _draw_bootstrap_indices(labels: np.ndarray, n_rows: int) -> np.ndarray:
        """Draw bootstrap indices with stratification for low-cardinality labels."""
        if n_rows <= 0:
            return np.array([], dtype=int)

        unique_labels, label_counts = np.unique(labels, return_counts=True)

        # If labels look continuous (regression), use standard bootstrap.
        if len(unique_labels) <= 1 or len(unique_labels) > max(10, n_rows // 5):
            return np.random.choice(n_rows, size=n_rows, replace=True)

        sampled_parts: list[np.ndarray] = []
        for label, count in zip(unique_labels, label_counts):
            cls_indices = np.where(labels == label)[0]
            if len(cls_indices) == 0:
                continue
            sampled_parts.append(
                np.random.choice(cls_indices, size=int(count), replace=True)
            )

        if not sampled_parts:
            return np.random.choice(n_rows, size=n_rows, replace=True)

        idx = np.concatenate(sampled_parts)
        np.random.shuffle(idx)
        return idx
