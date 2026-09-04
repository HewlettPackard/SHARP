"""
Consensus influence analyzer: Weighted Reciprocal Rank Fusion across all analyzers.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from typing import Any

import numpy as np
import polars as pl

from src.core.profile.base import InfluenceAnalyzer, InfluenceFactor
from src.core.profile.analyzers.tree import TreeInfluenceAnalyzer
from src.core.profile.analyzers.ccf import LaggedCCFInfluenceAnalyzer
from src.core.profile.analyzers.granger import GrangerInfluenceAnalyzer
from src.core.profile.analyzers.hybrid import HybridCausalInfluenceAnalyzer
from src.core.profile.analyzers.pcmci import PCMCIInfluenceAnalyzer
from src.core.profile.analyzers.te import TransferEntropyInfluenceAnalyzer


#: RRF smoothing constant.  60 is the standard value from the literature.
_RRF_K = 60


def _rrf_score(rank: int, weight: float = 1.0) -> float:
    """Single-factor RRF contribution (1-indexed rank)."""
    return weight / (_RRF_K + rank)


class ConsensusInfluenceAnalyzer(InfluenceAnalyzer):
    """Weighted Reciprocal Rank Fusion (wRRF) consensus across all analyzers.

    Runs all registered base analyzers and
    aggregates their factor rankings via weighted RRF.  Each analyzer is
    weighted by its rank-AUC quality score evaluated on the current data;
    analyzers that fail or return no factors are silently skipped.

    RRF score for factor f:
        consensus_score(f) = Σ_i  w_i / (k + rank_i(f))
    where k=60, rank_i is 1-indexed position (∞ when absent), w_i is the
    per-analyzer quality weight (defaults to 1.0 when quality unavailable).

    Metadata on each returned factor includes:
        consensus_votes:  dict of analyzer_name → {rank, strength, weight}
        agreement:        number of analyzers that ranked this factor
        consensus_score:  raw wRRF score
    """

    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "consensus"

    @property
    def label(self) -> str:
        return "Consensus (all analyzers)"

    @property
    def description(self) -> str:
        return (
            "Runs all analyzers and combines their rankings via Weighted "
            "Reciprocal Rank Fusion (wRRF). Factors appearing near the top of "
            "multiple independent analyses are ranked highest."
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
        outcome_mode: str = "classification",
        lower_is_better: bool | None = None,
        progress_callback: Any | None = None,
        **kwargs: Any,
    ) -> list[InfluenceFactor]:
        """Run all component analyzers and return wRRF-ranked consensus factors."""
        component_classes: dict[str, type] = {
            "tree": TreeInfluenceAnalyzer,
            "ccf": LaggedCCFInfluenceAnalyzer,
            "granger": GrangerInfluenceAnalyzer,
            "hybrid": HybridCausalInfluenceAnalyzer,
            "pcmci": PCMCIInfluenceAnalyzer,
            "te": TransferEntropyInfluenceAnalyzer,
        }

        shared_kwargs: dict[str, Any] = {
            "outcome_col": outcome_col,
            "settings": settings,
            "exclude_cols": exclude_cols,
            "max_predictors": max_predictors,
            "max_correlation": max_correlation,
            "outcome_mode": outcome_mode,
            "lower_is_better": lower_is_better,
            "timestamp_col": timestamp_col,
            "timestamps": timestamps,
        }

        component_names = list(component_classes.keys())
        n_components = len(component_names)
        per_analyzer_factors: dict[str, list[InfluenceFactor]] = {}

        for idx, analyzer_name in enumerate(component_names):
            if progress_callback is not None:
                progress_callback(
                    idx + 1,
                    n_components,
                    f"Consensus ({idx + 1}/{n_components}): {analyzer_name}",
                )
            try:
                analyzer = component_classes[analyzer_name]()
                factors = analyzer.analyze(data, labels, **shared_kwargs)
                if factors:
                    per_analyzer_factors[analyzer_name] = factors
            except Exception:
                import traceback
                traceback.print_exc()

        if not per_analyzer_factors:
            return []

        # Compute per-analyzer quality weights (rank-AUC).
        # Fall back to weight=1.0 when quality is unavailable.
        weights: dict[str, float] = {}
        for aname, factors in per_analyzer_factors.items():
            try:
                qr = self.evaluate_quality(
                    factors=factors,
                    data=data,
                    labels=labels,
                    outcome_col=outcome_col,
                    outcome_mode=outcome_mode,
                )
                weights[aname] = max(qr.score, 0.01) if qr is not None else 1.0
            except Exception:
                weights[aname] = 1.0

        # Build factor name → {analyzer_name: (rank_1indexed, strength, weight)}.
        votes: dict[str, dict[str, tuple[int, float, float]]] = {}
        for aname, factors in per_analyzer_factors.items():
            w = weights[aname]
            for rank_0, factor in enumerate(factors):
                entry = votes.setdefault(factor.name, {})
                entry[aname] = (rank_0 + 1, factor.strength, w)

        # Compute wRRF score for each factor.
        rrf_scores: dict[str, float] = {
            fname: sum(_rrf_score(rank, weight=wt) for _, (rank, _, wt) in v.items())
            for fname, v in votes.items()
        }

        # Sort factors by wRRF score descending.
        sorted_names = sorted(rrf_scores, key=lambda n: rrf_scores[n], reverse=True)

        # Build InfluenceFactor objects, using the best-quality analyzer's factor
        # as the template for fields like strength, direction, lag, p_value.
        def _pick_best_factor(fname: str) -> tuple[InfluenceFactor | None, str | None]:
            """Return the single-analyzer factor with the highest weight for fname."""
            best_factor: InfluenceFactor | None = None
            best_aname: str | None = None
            best_w = -1.0
            for aname, (rank, _, wt) in votes[fname].items():
                if wt > best_w:
                    best_w = wt
                    best_aname = aname
                    # Find the actual factor object.
                    for f in per_analyzer_factors[aname]:
                        if f.name == fname:
                            best_factor = f
                            break
            return best_factor, best_aname

        result: list[InfluenceFactor] = []
        for rank_0, fname in enumerate(sorted_names):
            template, best_src = _pick_best_factor(fname)

            consensus_votes_meta = {
                aname: {
                    "rank": r,
                    "strength": s,
                    "weight": round(wt, 4),
                }
                for aname, (r, s, wt) in votes[fname].items()
            }

            consensus_metadata: dict[str, Any] = {
                "consensus_votes": consensus_votes_meta,
                "agreement": len(votes[fname]),
                "consensus_score": round(rrf_scores[fname], 6),
                "best_source": best_src,
                "analyzer_weights": {an: round(w, 4) for an, w in weights.items()},
            }
            if template is not None:
                # Inherit any existing metadata from the best-source factor.
                if template.metadata:
                    consensus_metadata.update(
                        {k: v for k, v in template.metadata.items()
                         if k not in consensus_metadata}
                    )
                result.append(InfluenceFactor(
                    name=fname,
                    strength=template.strength,
                    rank=rank_0 + 1,
                    method="consensus",
                    direction=template.direction,
                    p_value=template.p_value,
                    lag=template.lag,
                    lag_rows=template.lag_rows,
                    confidence_interval=template.confidence_interval,
                    falsification_plan=template.falsification_plan,
                    metadata=consensus_metadata,
                ))
            else:
                result.append(InfluenceFactor(
                    name=fname,
                    strength=0.0,
                    rank=rank_0 + 1,
                    method="consensus",
                    metadata=consensus_metadata,
                ))

        return result
