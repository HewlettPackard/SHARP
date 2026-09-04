"""
Granger causality influence analyzer.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from typing import Any

import numpy as np
import polars as pl

from src.core.config.settings import Settings
from src.core.profile.base import CausalDirection, InfluenceAnalyzer, InfluenceFactor
from src.core.profile.confounding import ci_pre_screening
from src.core.profile.direction import DirectionResult, detect_direction
from src.core.profile.lag_detection import max_lag_correlation
from src.core.profile import predictor_selection


class GrangerInfluenceAnalyzer(InfluenceAnalyzer):
    """Granger causality influence analyzer with lag detection and direction testing."""

    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "granger"

    @property
    def label(self) -> str:
        return "Granger causality"

    @property
    def description(self) -> str:
        return (
            "Tests whether past values of each predictor help forecast the outcome "
            "(Granger causality). Sorted by forward Granger F-statistic."
        )

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "lag_detection": True,
            "direction": True,
            "uncertainty": True,
            "falsification": True,
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
        progress_callback: Any | None = None,
        outcome_mode: str = "classification",
        **kwargs: Any,
    ) -> list[InfluenceFactor]:
        """
        Perform Granger causality analysis with lag detection and direction testing.

        Args:
            data: Input DataFrame
            labels: Performance class labels
            outcome_col: Name of outcome column for correlation
            settings: Settings object or dict
            exclude_cols: Columns to exclude from analysis
            max_predictors: Maximum number of predictors to analyze
            max_correlation: Maximum correlation threshold for redundancy filtering
            timestamp_col: Name of timestamp column
            timestamps: Timestamp array (if not in data)
            progress_callback: Optional callback for progress updates
            outcome_mode: "classification" or "regression"

        Returns:
            List of InfluenceFactor objects ranked by forward F-statistic
        """
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

        # Get settings
        if max_predictors is None:
            max_predictors = self._get_setting(
                settings_obj, "profiling.max_predictors", 100
            )
        if max_correlation is None:
            max_correlation = self._get_setting(
                settings_obj, "profiling.max_correlation", 0.99
            )

        max_lag = int(
            self._get_setting(settings_obj, "profiling.granger.max_lag", 5)
        )
        significance_level = float(
            self._get_setting(settings_obj, "profiling.granger.significance_level", 0.05)
        )
        ci_prescreening = bool(
            self._get_setting(settings_obj, "profiling.granger.ci_prescreening", True)
        )

        correlations = predictor_selection.compute_predictor_correlations(
            data,
            outcome_col,
            exclude_cols,
        )

        predictors = predictor_selection.select_predictors_from_correlations(
            correlations,
            max_predictors=max_predictors,
            max_correlation=max_correlation,
        )

        if not predictors:
            return []

        # Apply C5 conditional independence pre-screening if enabled
        if ci_prescreening and len(predictors) > 30:
            predictors = self._ci_prescreening(
                data,
                outcome_col,
                predictors,
                max_keep=30,
                outcome_correlations=correlations,
            )

        timestamps_arr = self._resolve_timestamps(data, timestamp_col, timestamps, settings_obj)

        factors: list[InfluenceFactor] = []
        total = len(predictors)

        for idx, predictor in enumerate(predictors, start=1):
            if progress_callback:
                progress_callback(idx, total, predictor)

            predictor_vals = data[predictor].to_numpy()

            # Detect lag using CCF
            strength, lag_rows, lag_seconds = max_lag_correlation(
                outcome,
                predictor_vals,
                timestamps=timestamps_arr,
            )

            # Test causal direction using Granger.
            # A ValueError (e.g. too few non-null rows after pair-dropping)
            # for one predictor must not abort the whole analysis.
            direction_skip_reason: str | None = None
            try:
                direction_result = detect_direction(
                    predictor_vals,
                    outcome,
                    max_lag=max_lag,
                    significance_level=significance_level,
                    check_stationarity=True,
                )
            except ValueError as exc:
                direction_skip_reason = str(exc)
                direction_result = DirectionResult(
                    direction=CausalDirection.UNKNOWN,
                    forward_f_stat=float("nan"),
                    forward_p_value=float("nan"),
                    reverse_f_stat=float("nan"),
                    reverse_p_value=float("nan"),
                    max_lag=max_lag,
                    x_stationary=False,
                    y_stationary=False,
                    x_adf_p_value=float("nan"),
                    y_adf_p_value=float("nan"),
                )

            # Generate falsification plan
            falsification = self._generate_falsification_plan(
                predictor, strength, direction_result
            )

            # Build model assumptions list
            assumptions = self._build_assumptions(direction_result, ci_prescreening)

            factors.append(
                InfluenceFactor(
                    name=predictor,
                    strength=strength,
                    method=self.name,
                    direction=direction_result.direction,
                    p_value=direction_result.forward_p_value,
                    lag=lag_seconds,
                    lag_rows=lag_rows,
                    confidence_interval=None,  # Could add bootstrap CI on lag estimate
                    falsification_plan=falsification,
                    metadata={
                        "forward_f_stat": direction_result.forward_f_stat,
                        "reverse_f_stat": direction_result.reverse_f_stat,
                        "reverse_p_value": direction_result.reverse_p_value,
                        "x_stationary": direction_result.x_stationary,
                        "y_stationary": direction_result.y_stationary,
                        "x_adf_p_value": direction_result.x_adf_p_value,
                        "y_adf_p_value": direction_result.y_adf_p_value,
                        "max_lag": max_lag,
                        "ci_prescreening": ci_prescreening,
                        "model_assumptions": assumptions,
                        **({
                            "direction_skip_reason": direction_skip_reason,
                        } if direction_skip_reason else {}),
                    },
                )
            )

        # Sort by forward F-statistic (higher = stronger causal evidence)
        factors.sort(
            key=lambda f: f.metadata.get("forward_f_stat", 0) if f.metadata else 0,
            reverse=True,
        )

        # Assign ranks
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
        """Resolve timestamp array from various sources."""
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

    def _ci_prescreening(
        self,
        data: pl.DataFrame,
        outcome_col: str,
        predictors: list[str],
        max_keep: int = 30,
        outcome_correlations: dict[str, float] | None = None,
    ) -> list[str]:
        """
        C5: Conditional independence pre-screening.

        Reduces predictor set by keeping only factors that remain correlated
        with outcome after conditioning on top factors. This is a simplified
        version - full CI testing would use partial correlation or PC algorithm.

        For now, we use a simpler heuristic: keep predictors with highest
        marginal correlation, as they're most likely to be directly causal.
        """
        return ci_pre_screening(
            data,
            outcome_col,
            predictors,
            max_keep=max_keep,
            max_conditioning_size=3,
            significance_level=0.05,
            outcome_correlations=outcome_correlations,
        )

    def _generate_falsification_plan(
        self,
        predictor: str,
        strength: float,
        direction_result: Any,
    ) -> dict[str, Any] | None:
        """Generate falsification plan based on direction and strength."""
        if direction_result.direction == CausalDirection.INDETERMINATE:
            return None

        if direction_result.direction == CausalDirection.FORWARD:
            # For forward causality, suggest intervention test
            return {
                "type": "intervention",
                "predictor": predictor,
                "target_value": None,  # Would need domain knowledge
                "expected_outcome_change": strength,
                "description": (
                    f"Intervene on {predictor} and observe outcome changes. "
                    f"Forward causality predicts {strength:.2f} correlation."
                ),
            }

        if direction_result.direction == CausalDirection.REVERSE:
            # For reverse causality, warn against intervention
            return {
                "type": "warning",
                "predictor": predictor,
                "description": (
                    f"{predictor} is an effect of the outcome, not a cause. "
                    f"Intervening on this factor will not improve performance."
                ),
            }

        if direction_result.direction == CausalDirection.BIDIRECTIONAL:
            # For bidirectional, suggest controlled experiment
            return {
                "type": "controlled_experiment",
                "predictor": predictor,
                "description": (
                    f"{predictor} shows bidirectional relationship (feedback loop). "
                    f"Requires controlled experiment to isolate causal direction."
                ),
            }

        return None

    def _build_assumptions(
        self, direction_result: Any, ci_prescreening: bool
    ) -> list[str]:
        """Build list of model assumptions and warnings."""
        assumptions = []

        # Stationarity assumption
        if not direction_result.x_stationary:
            assumptions.append(
                f"Predictor non-stationary (ADF p={direction_result.x_adf_p_value:.3f})"
            )
        if not direction_result.y_stationary:
            assumptions.append(
                f"Outcome non-stationary (ADF p={direction_result.y_adf_p_value:.3f})"
            )

        if direction_result.x_stationary and direction_result.y_stationary:
            assumptions.append("Assumes stationary time series")

        # General Granger assumptions
        assumptions.append("Does not control for all confounders")
        assumptions.append("Does not establish true causation")

        # CI pre-screening note
        if ci_prescreening:
            assumptions.append("Pre-screened for marginal association")

        return assumptions
