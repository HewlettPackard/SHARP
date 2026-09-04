"""
Lagged cross-correlation (CCF) influence analyzer.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from typing import Any

import numpy as np
import polars as pl

from src.core.config.settings import Settings
from src.core.profile.base import InfluenceAnalyzer, InfluenceFactor
from src.core.profile.lag_detection import max_lag_correlation
from src.core.profile import predictor_selection


class LaggedCCFInfluenceAnalyzer(InfluenceAnalyzer):
    """Lagged cross-correlation influence analyzer."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = np.random.default_rng(seed)

    @property
    def name(self) -> str:
        return "ccf"

    @property
    def label(self) -> str:
        return "CCF (Lagged cross-correlation)"

    @property
    def description(self) -> str:
        return (
            "Measures peak cross-correlation between each predictor and the outcome "
            "across time lags."
        )

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "lag_detection": True,
            "direction": False,
            "uncertainty": True,
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
        timestamp_col: str | None = None,
        timestamps: np.ndarray | None = None,
            progress_callback: Any = None,
        outcome_mode: str = "classification",
        **kwargs: Any,
    ) -> list[InfluenceFactor]:
        if data is None or data.is_empty():
            return []

        exclude_cols = exclude_cols or []
        settings_obj = settings if settings is not None else Settings()

        # Resolve outcome: classification (labels) or regression (continuous)
        outcome, data, outcome_col = self._resolve_outcome(
            data, labels, outcome_col, outcome_mode
        )
        if len(outcome) == 0:
            return []

        # Use provided values, then check settings, then defaults
        if max_predictors is None:
            max_predictors = self._get_setting(
                settings_obj, "profiling.max_predictors", 100
            )
        if max_correlation is None:
            max_correlation = self._get_setting(
                settings_obj, "profiling.max_correlation", 0.99
            )

        predictors = predictor_selection.select_predictors(
            data,
            outcome_col,
            exclude_cols,
            max_predictors=max_predictors,
            max_correlation=max_correlation,
        )

        if not predictors:
            return []

        timestamps_arr = self._resolve_timestamps(data, timestamp_col, timestamps, settings_obj)

        permutations = int(
            self._get_setting(settings_obj, "profiling.lag_detection.permutations", 200)
        )

        factors: list[InfluenceFactor] = []
        total = len(predictors)
        for idx, predictor in enumerate(predictors, start=1):
            if progress_callback:
                progress_callback(idx, total, predictor)

            predictor_vals = data[predictor].to_numpy()
            strength, lag_rows, lag_seconds = max_lag_correlation(
                outcome,
                predictor_vals,
                timestamps=timestamps_arr,
            )
            p_value, ci = self._permutation_test(
                outcome,
                predictor_vals,
                strength,
                lag_rows,
                timestamps_arr,
                permutations,
            )

            factors.append(
                InfluenceFactor(
                    name=predictor,
                    strength=strength,
                    method=self.name,
                    p_value=p_value,
                    lag=lag_seconds,
                    lag_rows=lag_rows,
                    confidence_interval=ci,
                    metadata={
                        "permutations": permutations,
                        "timestamp_col": timestamp_col,
                        "model_assumptions": [
                            "Non-directional association only",
                            "Does not control for confounders",
                            "Does not establish causation",
                        ],
                    },
                )
            )

        factors.sort(key=lambda f: f.strength, reverse=True)
        for idx, factor in enumerate(factors, start=1):
            factors[idx - 1] = InfluenceFactor(
                name=factor.name,
                strength=factor.strength,
                rank=idx,
                method=factor.method,
                direction=factor.direction,
                p_value=factor.p_value,
                lag=factor.lag,
                lag_rows=factor.lag_rows,
                confidence_interval=factor.confidence_interval,
                falsification_plan=factor.falsification_plan,
                metadata=factor.metadata,
            )

        return factors

    def _resolve_timestamps(
        self,
        data: pl.DataFrame,
        timestamp_col: str | None,
        timestamps: np.ndarray | None,
        settings: Any,
    ) -> np.ndarray | None:
        if timestamps is not None:
            return self._coerce_timestamps(timestamps)

        if timestamp_col and timestamp_col in data.columns:
            return self._coerce_timestamps(data[timestamp_col].to_numpy())

        settings_col = self._get_setting(
            settings, "profiling.lag_detection.timestamp_column", None
        )
        if settings_col and settings_col in data.columns:
            return self._coerce_timestamps(data[settings_col].to_numpy())

        return None

    def _permutation_test(
        self,
        outcome: np.ndarray,
        predictor: np.ndarray,
        observed: float,
        lag_rows: int,
        timestamps: np.ndarray | None,
        permutations: int,
    ) -> tuple[float | None, tuple[float, float] | None]:
        if permutations <= 0:
            return None, None

        mask = ~np.isnan(outcome) & ~np.isnan(predictor)
        outcome_vals = outcome[mask]
        predictor_vals = predictor[mask]

        if len(outcome_vals) < 3:
            return None, None

        max_lag = max(1, min(abs(lag_rows), len(outcome_vals) - 1))
        perm_values: list[float] = []

        for _ in range(permutations):
            shuffled = self._rng.permutation(predictor_vals)
            perm_corr, _, _ = max_lag_correlation(
                outcome_vals,
                shuffled,
                max_lag=max_lag,
                timestamps=timestamps,
            )
            perm_values.append(perm_corr)

        perm_array = np.asarray(perm_values, dtype=float)
        count = int(np.sum(perm_array >= observed))
        p_value = float((count + 1) / (permutations + 1))
        ci_low = float(np.percentile(perm_array, 2.5))
        ci_high = float(np.percentile(perm_array, 97.5))
        return p_value, (ci_low, ci_high)
