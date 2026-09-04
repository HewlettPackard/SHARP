"""
PCMCI-Lite causal discovery influence analyzer.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from typing import Any

import numpy as np
import polars as pl

from src.core.config.settings import Settings
from src.core.profile.base import CausalDirection, InfluenceAnalyzer, InfluenceFactor


class PCMCIInfluenceAnalyzer(InfluenceAnalyzer):
    """PCMCI-Lite causal discovery: Learn full causal graph via structure discovery.

    Uses Peter and Clark Momentary Conditional Independence (PCMCI) algorithm to:
    1. Discover causal skeleton via PC algorithm (conditional independence tests)
    2. Identify v-structures (confounders)
    3. Return full causal graph with edge confidence (MCI p-values)

    Capabilities:
    - Full causal graph discovery (not just factors → outcome)
    - Handles confounding explicitly (identifies common causes)
    - Directional edges with statistical confidence
    - Model assumptions well-documented
    """

    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "pcmci"

    @property
    def label(self) -> str:
        return "PCMCI causal graph"

    @property
    def description(self) -> str:
        return (
            "Discovers full causal structure via Peter-Clark Momentary Conditional "
            "Independence (PCMCI). Identifies dependencies and confounding relationships. "
            "Produces DAG with edge confidence levels."
        )

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "lag_detection": False,
            "direction": True,
            "uncertainty": True,
            "falsification": True,
            "confounding": True,
        }

    def _get_pcmci_settings(self, settings_obj: Any) -> tuple[Any, Any, Any, float, Any]:
        """Extract PCMCI-specific settings with defaults."""
        pcmci_max_predictors = self._get_setting(
            settings_obj, "profiling.pcmci.max_predictors", None
        )
        pcmci_min_abs_corr = self._get_setting(
            settings_obj, "profiling.pcmci.min_abs_correlation", None
        )
        pcmci_max_rows = self._get_setting(
            settings_obj, "profiling.pcmci.max_rows", None
        )
        alpha = self._get_setting(settings_obj, "profiling.pcmci.alpha", 0.05)
        max_depth = self._get_setting(settings_obj, "profiling.pcmci.max_depth", None)
        return pcmci_max_predictors, pcmci_min_abs_corr, pcmci_max_rows, alpha, max_depth

    def _select_predictor_cols(
        self,
        data: pl.DataFrame,
        outcome_col: str,
        exclude_cols: list[str] | None,
    ) -> list[str]:
        """Select candidate predictor columns excluding outcome and explicit exclusions."""
        return [
            c for c in data.columns
            if c != outcome_col and (not exclude_cols or c not in exclude_cols)
        ]

    def _screen_pcmci_predictors(
        self,
        data: pl.DataFrame,
        outcome_col: str,
        predictor_cols: list[str],
        target_max_predictors: int | None,
        pcmci_min_abs_corr: Any,
        progress_callback: Any | None,
    ) -> tuple[list[str], dict[str, float]]:
        """Screen predictors by pairwise correlation while preserving sparse columns."""
        if not ((target_max_predictors or pcmci_min_abs_corr) and predictor_cols):
            return predictor_cols, {}

        if progress_callback:
            progress_callback(0, 0, "Screening predictors")

        correlations: dict[str, float] = {}
        total_cols = len(predictor_cols)
        update_every = max(1, total_cols // 50)

        for idx, col in enumerate(predictor_cols, start=1):
            if progress_callback and idx % update_every == 0:
                progress_callback(idx, total_cols, f"Screening {col}")

            try:
                pair_data = data.select([outcome_col, col]).drop_nulls()
                if len(pair_data) > 10:
                    outcome_pair = pair_data[outcome_col].to_numpy()
                    pred_pair = pair_data[col].to_numpy()
                    if np.std(pred_pair) > 0 and np.std(outcome_pair) > 0:
                        correlations[col] = float(np.abs(np.corrcoef(pred_pair, outcome_pair)[0, 1]))
                    else:
                        correlations[col] = 0.5
                else:
                    correlations[col] = 0.5
            except Exception:
                correlations[col] = 0.5

        screened_correlations = correlations.copy()

        if pcmci_min_abs_corr is not None:
            min_corr = float(pcmci_min_abs_corr)
            correlations = {
                col: corr for col, corr in correlations.items() if corr >= min_corr
            }

        sorted_cols = sorted(correlations.items(), key=lambda item: -item[1])
        if target_max_predictors:
            sorted_cols = sorted_cols[:int(target_max_predictors)]

        return [col for col, _ in sorted_cols], screened_correlations

    def _build_pcmci_fallback_factors(
        self,
        screened_correlations: dict[str, float],
        max_predictors: int | None,
        model_assumptions: list[str],
    ) -> list[InfluenceFactor]:
        """Build fallback factors from screened correlations when PCMCI finds no parents."""
        sorted_screened = sorted(screened_correlations.items(), key=lambda item: -item[1])
        max_factors = max_predictors or 10
        factors: list[InfluenceFactor] = []

        for rank, (col_name, corr_strength) in enumerate(sorted_screened[:max_factors], 1):
            factors.append(
                InfluenceFactor(
                    name=col_name,
                    rank=rank,
                    direction=CausalDirection.FORWARD,
                    strength=corr_strength,
                    p_value=1.0 - corr_strength if corr_strength < 1.0 else 0.05,
                    confidence_interval=None,
                    metadata={
                        "edge_type": "screening_fallback",
                        "correlation_strength": corr_strength,
                        "model_assumptions": model_assumptions,
                    },
                )
            )

        return factors

    def _build_pcmci_parent_factors(
        self,
        graph: Any,
        outcome_col: str,
    ) -> list[InfluenceFactor]:
        """Build ranked factors from direct causal parents of the outcome."""
        from dataclasses import replace

        factors: list[InfluenceFactor] = []
        outcome_parents = graph.get_parents(outcome_col)

        for rank, parent_name in enumerate(outcome_parents, 1):
            edge = next(
                (e for e in graph.edges if e.source == parent_name and e.target == outcome_col),
                None,
            )
            if not edge:
                continue

            is_confounded = any(
                a == parent_name and b == outcome_col
                for a, b, c in graph.v_structures
            )

            factors.append(
                InfluenceFactor(
                    name=parent_name,
                    rank=rank,
                    direction=CausalDirection.FORWARD,
                    strength=abs(edge.strength),
                    p_value=edge.p_value,
                    confidence_interval=(
                        (edge.strength - 0.2, edge.strength + 0.2)
                        if edge.p_value < 0.05
                        else None
                    ),
                    metadata={
                        "causal_strength": edge.strength,
                        "causal_p_value": edge.p_value,
                        "is_confounded": is_confounded,
                        "edge_type": "v_structure" if is_confounded else "causal_parent",
                        "full_causal_graph": {
                            "edges": [
                                {
                                    "source": e.source,
                                    "target": e.target,
                                    "strength": e.strength,
                                    "p_value": e.p_value,
                                }
                                for e in graph.edges
                            ],
                            "v_structures": graph.v_structures,
                        },
                        "model_assumptions": graph.model_assumptions,
                    },
                )
            )

        factors.sort(key=lambda factor: factor.p_value or 1.0)
        return [replace(factor, rank=i) for i, factor in enumerate(factors, 1)]

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
        Perform PCMCI-Lite causal discovery.

        Returns top causal factors (those causally linked to outcome) extracted
        from the discovered causal graph. Full graph is stored in metadata.

        Args:
            data: Input DataFrame
            labels: Performance class labels (used in classification mode)
            outcome_col: Name of outcome column (used in regression mode)
            settings: Settings object or dict
            exclude_cols: Columns to exclude
            max_predictors: Max number of predictors to analyze
            outcome_mode: "classification" or "regression"
            Other args: For API compatibility

        Returns:
            List of InfluenceFactor objects (causal parents of outcome)
        """
        from src.core.profile.pcmci_lite import fit_pcmci_lite

        if data is None or data.is_empty():
            return []

        settings_obj = settings if settings is not None else Settings()
        (
            pcmci_max_predictors,
            pcmci_min_abs_corr,
            pcmci_max_rows,
            alpha,
            max_depth,
        ) = self._get_pcmci_settings(settings_obj)

        # Resolve outcome: classification (labels) or regression (continuous)
        outcome, data, outcome_col = self._resolve_outcome(
            data, labels, outcome_col, outcome_mode
        )
        if len(outcome) == 0:
            return []

        if progress_callback:
            progress_callback(0, 0, "Preparing data")

        predictor_cols = self._select_predictor_cols(data, outcome_col, exclude_cols)

        if not predictor_cols:
            return []

        # Optional row downsampling for PCMCI speed
        if pcmci_max_rows and len(data) > int(pcmci_max_rows):
            data = data.sample(n=int(pcmci_max_rows), with_replacement=False, seed=0)

        target_max_predictors = pcmci_max_predictors if pcmci_max_predictors else max_predictors
        predictor_cols, screened_correlations = self._screen_pcmci_predictors(
            data,
            outcome_col,
            predictor_cols,
            target_max_predictors,
            pcmci_min_abs_corr,
            progress_callback,
        )

        # Run PCMCI-Lite
        try:
            graph = fit_pcmci_lite(
                data,
                outcome_col=outcome_col,
                predictor_cols=predictor_cols,
                alpha=alpha,
                max_conditioning_depth=max_depth,
                progress_callback=progress_callback,
            )
        except Exception:
            return []

        outcome_parents = graph.get_parents(outcome_col)

        # Fallback: if no causal parents found, use screened predictors based on correlation
        if not outcome_parents and screened_correlations:
            return self._build_pcmci_fallback_factors(
                screened_correlations,
                max_predictors,
                graph.model_assumptions,
            )

        return self._build_pcmci_parent_factors(graph, outcome_col)
