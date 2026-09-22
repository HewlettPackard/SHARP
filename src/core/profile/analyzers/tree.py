"""
Decision tree influence analyzer.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from typing import Any

import numpy as np
import polars as pl

from src.core.config.settings import Settings
from src.core.profile.base import InfluenceFactor, TrainedModel
from src.core.profile.decision_tree import (
    DecisionTreeRegressorTrainer,
    DecisionTreeTrainer,
    TreeFactorAnalyzer,
)
from src.core.profile.analyzers._trained_model_base import TrainedModelInfluenceAnalyzer


class TreeInfluenceAnalyzer(TrainedModelInfluenceAnalyzer):
    """Decision tree influence analyzer."""

    def __init__(self) -> None:
        super().__init__()
        self._trainer = DecisionTreeTrainer()
        self._regression_trainer = DecisionTreeRegressorTrainer()
        self._factor_analyzer = TreeFactorAnalyzer()

    @property
    def name(self) -> str:
        return "tree"

    @property
    def label(self) -> str:
        return "Decision tree"

    @property
    def description(self) -> str:
        return (
            "Trains a decision tree classifier to find predictor thresholds "
            "that split performance classes."
        )

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "lag_detection": False,
            "direction": False,
            "uncertainty": False,
            "falsification": False,
        }

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
        if data is None or data.is_empty():
            self._trained_model = None
            return []

        exclude_cols = exclude_cols or []
        settings_obj = settings if settings is not None else Settings()

        # Downsample large datasets before tree training.
        # Decision trees find splits based on distribution shape, not raw count,
        # so training on a representative sample gives equivalent results while
        # keeping training time bounded. The seed is deterministic (derived from
        # the row count) so the same data always produces the same sample.
        target_rows = settings_obj.get("profiling.tree_training.target_rows", 1000)
        if len(data) > target_rows:
            rng = np.random.default_rng(len(data))
            indices = sorted(rng.choice(len(data), size=target_rows, replace=False))
            data = data[indices]
            labels = labels[indices]

        # Remember the original outcome column name before resolve
        original_outcome_col = outcome_col

        # Resolve outcome based on outcome_mode
        outcome, data, outcome_col = self._resolve_outcome(
            data, labels, outcome_col, outcome_mode
        )
        if len(outcome) == 0:
            self._trained_model = None
            return []

        # In classification mode, labels are already the outcome;
        # in regression mode, use the continuous column as target.
        effective_labels = labels if outcome_mode == "classification" else outcome

        # Exclude the synthetic label column and original outcome from predictors
        tree_exclude = list(exclude_cols)
        if outcome_col and outcome_col not in tree_exclude:
            tree_exclude.append(outcome_col)
        if original_outcome_col and original_outcome_col not in tree_exclude:
            tree_exclude.append(original_outcome_col)

        max_predictors = self._get_setting(
            settings_obj, "profiling.max_predictors", max_predictors
        )
        max_correlation = self._get_setting(
            settings_obj, "profiling.max_correlation", max_correlation
        )

        trained_model = None
        if outcome_mode == "regression":
            trained_model = self._regression_trainer.train(
                data,
                effective_labels,
                exclude_cols=tree_exclude,
                max_predictors=max_predictors,
                max_correlation=max_correlation,
                predictors=predictors,
                outcome_col=original_outcome_col,
            )
        else:
            trained_model = self._trainer.train(
                data,
                effective_labels,
                exclude_cols=tree_exclude,
                max_predictors=max_predictors,
                max_correlation=max_correlation,
                predictors=predictors,
            )

        if trained_model is None:
            self._trained_model = None
            return []

        self._trained_model = trained_model
        factors = self._factor_analyzer.analyze(trained_model)

        ci_lookup = {}

        plans = self._falsification_plans(trained_model)

        # Exclude both the effective outcome col and the original metric col
        exclude_names = {outcome_col, original_outcome_col} - {None}

        influence_factors = []
        rank = 0
        for factor in factors:
            fname = factor.original_name or factor.name
            if fname in exclude_names or factor.name in exclude_names:
                continue
            rank += 1
            factor_name = factor.original_name or factor.name
            influence_factors.append(
                InfluenceFactor(
                    name=factor_name,
                    strength=factor.importance,
                    rank=rank,
                    method=self.name,
                    confidence_interval=ci_lookup.get(factor.name),
                    falsification_plan=plans.get(factor.name),
                    metadata={
                        "encoded_name": factor.name,
                        "original_name": factor.original_name,
                        "bootstrap_ci_enabled": False,
                        "model_assumptions": [
                            "Based on tree thresholds",
                            "Does not control for confounders",
                            "Does not establish causation",
                        ],
                    },
                )
            )

        return influence_factors

    def _falsification_plans(self, trained_model: TrainedModel) -> dict[str, dict[str, Any]]:
        tree = trained_model.model
        if not hasattr(tree, "tree_"):
            return {}

        plans = {}
        features = tree.tree_.feature
        thresholds = tree.tree_.threshold

        for idx, feature_idx in enumerate(features):
            if feature_idx < 0:
                continue
            try:
                feature_name = trained_model.feature_names[feature_idx]
            except IndexError:
                continue
            if feature_name in plans:
                continue
            plans[feature_name] = {
                "type": "threshold",
                "feature": feature_name,
                "threshold": float(thresholds[idx]),
            }

        return plans
