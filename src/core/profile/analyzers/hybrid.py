"""
Hybrid causal influence analyzer combining Granger causality with confounding control.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from typing import Any

import numpy as np
import polars as pl

from src.core.config.settings import Settings
from src.core.profile.base import CausalDirection, InfluenceAnalyzer, InfluenceFactor
from src.core.profile.direction import detect_direction
from src.core.profile.lag_detection import max_lag_correlation
from src.core.profile import predictor_selection


class HybridCausalInfluenceAnalyzer(InfluenceAnalyzer):
    """Hybrid causal influence analyzer combining Granger causality with confounding control.

    Extends Granger causality testing with conditional independence (CI) pruning
    to identify and remove confounded associations. This provides stronger evidence
    for causal claims by testing whether associations remain after conditioning on
    other strong predictors.

    Capabilities:
    - Lag detection (via CCF)
    - Direction testing (via Granger)
    - Confounding control (via partial correlation pruning)
    - Uncertainty quantification (p-values for direction and confounding tests)
    - Falsification plans with confounding caveats
    """

    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "hybrid"

    @property
    def label(self) -> str:
        return "Hybrid causal"

    @property
    def description(self) -> str:
        return (
            "Extends Granger causality with partial correlation pruning to control "
            "for confounded factors. Provides stronger evidence by testing whether "
            "associations remain after conditioning on stronger predictors."
        )

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "lag_detection": True,
            "direction": True,
            "uncertainty": True,
            "falsification": True,
            "confounding": True,
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
        Perform Granger causality analysis with confounding control.

        First applies Granger causality testing to identify directional associations,
        then applies conditional independence pruning to remove confounded factors.

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
            List of InfluenceFactor objects ranked by forward F-statistic,
            with confounding status in metadata
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

        # Hybrid-specific settings
        max_conditioning_size = int(
            self._get_setting(settings_obj, "profiling.hybrid.max_conditioning_size", 3)
        )
        confounding_significance = float(
            self._get_setting(
                settings_obj, "profiling.hybrid.confounding_significance", 0.05
            )
        )
        min_abs_partial = float(
            self._get_setting(settings_obj, "profiling.hybrid.min_abs_partial", 0.1)
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

        # Phase 1: Granger causality analysis (same as GrangerInfluenceAnalyzer)
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

            # Test causal direction using Granger
            direction_result = detect_direction(
                predictor_vals,
                outcome,
                max_lag=max_lag,
                significance_level=significance_level,
                check_stationarity=True,
            )

            factors.append(
                InfluenceFactor(
                    name=predictor,
                    strength=strength,
                    method=self.name,
                    direction=direction_result.direction,
                    p_value=direction_result.forward_p_value,
                    lag=lag_seconds,
                    lag_rows=lag_rows,
                    confidence_interval=None,
                    falsification_plan=None,  # Will be updated after confounding analysis
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
                        "direction_result": direction_result,
                    },
                )
            )

        # Sort by forward F-statistic (higher = stronger causal evidence)
        factors.sort(
            key=lambda f: f.metadata.get("forward_f_stat", 0) if f.metadata else 0,
            reverse=True,
        )

        # Phase 2: Confounding analysis
        # Test each factor for confounding by conditioning on stronger factors
        confounding_status = self._analyze_confounding(
            data,
            outcome_col,
            factors,
            max_conditioning_size,
            confounding_significance,
            min_abs_partial,
        )

        # Phase 3: Update factors with confounding information
        final_factors = []
        rank = 0

        for factor in factors:
            status = confounding_status.get(factor.name, {})

            # Skip factors that are completely confounded
            if status.get("is_confounded", False):
                continue

            rank += 1

            # Generate falsification plan with confounding caveats
            direction_result = factor.metadata.get("direction_result")
            falsification = self._generate_falsification_plan(
                factor.name,
                factor.strength,
                direction_result,
                status,
            )

            # Build model assumptions including confounding tests
            assumptions = self._build_assumptions(
                direction_result,
                ci_prescreening,
                status,
            )

            final_factors.append(
                InfluenceFactor(
                    name=factor.name,
                    strength=factor.strength,
                    rank=rank,
                    method=factor.method,
                    direction=factor.direction,
                    p_value=factor.p_value,
                    lag=factor.lag,
                    lag_rows=factor.lag_rows,
                    confidence_interval=status.get("partial_r_ci"),
                    falsification_plan=falsification,
                    metadata={
                        **factor.metadata,
                        "confounding_status": status,
                        "model_assumptions": assumptions,
                    },
                )
            )

        return final_factors

    def _ci_prescreening(
        self,
        data: pl.DataFrame,
        outcome_col: str,
        predictors: list[str],
        max_keep: int = 30,
        outcome_correlations: dict[str, float] | None = None,
    ) -> list[str]:
        """C5: Conditional independence pre-screening."""
        from src.core.profile.confounding import ci_pre_screening as confounding_ci_pre_screening

        return confounding_ci_pre_screening(
            data,
            outcome_col,
            predictors,
            max_keep=max_keep,
            max_conditioning_size=3,
            significance_level=0.05,
            outcome_correlations=outcome_correlations,
        )

    def _analyze_confounding(
        self,
        data: pl.DataFrame,
        outcome_col: str,
        factors: list[InfluenceFactor],
        max_conditioning_size: int,
        significance_level: float,
        min_abs_partial: float,
    ) -> dict[str, dict[str, Any]]:
        """
        Analyze each factor for confounding by conditioning on stronger factors.

        For each factor, computes partial correlation with outcome after
        conditioning on top-ranked factors (potential confounders).
        """
        from src.core.profile.confounding import partial_correlation

        outcome = data[outcome_col].to_numpy()
        status_map = {}

        for idx, factor in enumerate(factors):
            conditioning_factors = [
                f.name for f in factors[:idx]
            ][:max_conditioning_size]

            if not conditioning_factors:
                status_map[factor.name] = {
                    "is_confounded": False,
                    "partial_r": factor.strength,
                    "partial_p_value": factor.p_value,
                    "conditioning_on": [],
                    "partial_r_ci": None,
                }
                continue

            predictor_vals = data[factor.name].to_numpy()
            z_vals = data.select(conditioning_factors).to_numpy()

            partial_r, partial_p = partial_correlation(
                predictor_vals,
                outcome,
                z_vals,
            )

            is_confounded = (
                abs(partial_r) < min_abs_partial
                or partial_p > significance_level
            )

            status_map[factor.name] = {
                "is_confounded": is_confounded,
                "partial_r": partial_r,
                "partial_p_value": partial_p,
                "conditioning_on": conditioning_factors,
                "partial_r_ci": (partial_r - 0.1, partial_r + 0.1),
            }

        return status_map

    def _generate_falsification_plan(
        self,
        predictor: str,
        strength: float,
        direction_result: Any,
        confounding_status: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Generate falsification plan with confounding caveats."""
        if direction_result.direction == CausalDirection.INDETERMINATE:
            return None

        is_confounded = confounding_status.get("is_confounded", False)
        conditioning_on = confounding_status.get("conditioning_on", [])
        partial_r = confounding_status.get("partial_r")

        if direction_result.direction == CausalDirection.FORWARD:
            plan = {
                "type": "intervention",
                "predictor": predictor,
                "target_value": None,
                "expected_outcome_change": strength,
                "description": (
                    f"Intervene on {predictor} and observe outcome changes. "
                    f"Forward causality predicts {strength:.2f} correlation."
                ),
            }

            if conditioning_on:
                if is_confounded:
                    plan["confounding_warning"] = (
                        f"WARNING: Association with {predictor} vanishes when "
                        f"conditioning on {', '.join(conditioning_on)}. "
                        "This factor may be confounded or an indirect effect."
                    )
                    plan["confidence"] = "low"
                else:
                    plan["confounding_note"] = (
                        f"Partial correlation remains significant "
                        f"(r={partial_r:.2f}) after conditioning on "
                        f"{', '.join(conditioning_on)}. Stronger evidence for causality."
                    )
                    plan["confidence"] = "medium-high"

            return plan

        if direction_result.direction == CausalDirection.REVERSE:
            return {
                "type": "warning",
                "predictor": predictor,
                "description": (
                    f"{predictor} is an effect of the outcome, not a cause. "
                    f"Intervening on this factor will not improve performance."
                ),
                "confounding_note": (
                    "Reverse causality detected - this is not a confounder "
                    "but an effect."
                ) if conditioning_on else None,
            }

        if direction_result.direction == CausalDirection.BIDIRECTIONAL:
            plan = {
                "type": "controlled_experiment",
                "predictor": predictor,
                "description": (
                    f"{predictor} shows bidirectional relationship (feedback loop). "
                    "Requires controlled experiment to isolate causal direction."
                ),
            }

            if conditioning_on and not is_confounded:
                plan["confounding_note"] = (
                    f"Bidirectional relationship persists after conditioning on "
                    f"{', '.join(conditioning_on)}."
                )

            return plan

        return None

    def _build_assumptions(
        self,
        direction_result: Any,
        ci_prescreening: bool,
        confounding_status: dict[str, Any],
    ) -> list[str]:
        """Build list of model assumptions including confounding tests."""
        assumptions = []

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

        conditioning_on = confounding_status.get("conditioning_on", [])
        if conditioning_on:
            assumptions.append(
                "Tested for confounding by conditioning on: "
                f"{', '.join(conditioning_on)}"
            )

            partial_p = confounding_status.get("partial_p_value")
            if partial_p is not None:
                assumptions.append(
                    f"Partial correlation p={partial_p:.3f}"
                )
        else:
            assumptions.append("Top-ranked factor, no confounding test applied")

        assumptions.append("Does not establish true causation")
        if ci_prescreening:
            assumptions.append("Pre-screened for marginal association")

        return assumptions

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
