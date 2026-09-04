"""
Registry for influence analyzers.

Encapsulates shared state and routes analysis to registered analyzers.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

from dataclasses import dataclass
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
from src.core.profile.analyzers.consensus import ConsensusInfluenceAnalyzer
from src.core.profile.column_enrichment import EnrichedInfluenceAnalyzer
from src.core.config.settings import Settings


@dataclass
class DataContext:
    """Observable properties of the input data, used to rank analyzers by suitability.

    Attributes:
        has_timestamp: True when a usable timestamp column is present, enabling
            time-ordered lag analysis.
        n_rows: Number of data rows after reduction.  Very small counts make
            statistical causal tests unreliable.
        n_predictors: Number of candidate predictor columns.  Large counts
            increase the cost of multivariate methods like Hybrid and PCMCI.
        outcome_mode: ``"classification"`` (discrete performance groups) or
            ``"regression"`` (continuous outcome).  Affects how causal tests
            handle the target variable.
    """

    has_timestamp: bool = False
    n_rows: int = 0
    n_predictors: int = 0
    outcome_mode: str = "classification"


# Base scores reflect general usefulness ranking independent of data context.
# Granger is the recommended default (best balance of rigor and speed).
#
# MAINTENANCE NOTE: This dict is tightly coupled with _score_analyzer_for_context(),
# which has name-based branches for scoring adjustments. When adding or removing an
# analyzer, update both this dict and the branching logic in _score_analyzer_for_context().
# Future refactors should consider moving to introspection-based scoring using analyzer
# metadata (capabilities, runtime_tier, needs_timestamp, min_rows) to reduce brittleness.
_ANALYZER_BASE_SCORES: dict[str, int] = {
    "tree": 70,
    "ccf": 65,
    "granger": 75,
    "hybrid": 70,
    "pcmci": 60,
    "te": 68,
    "consensus": 80,
}


def _score_analyzer_for_context(name: str, context: DataContext) -> int:
    """Compute a suitability score for *name* given *context*.

    Higher scores indicate the analyzer is a better fit for the current data.
    Scores are ordinal — only their relative order matters.
    """
    score = _ANALYZER_BASE_SCORES.get(name, 50)

    # Temporal methods rely on row ordering / timestamps.  Without a
    # timestamp column, lag detection is much less meaningful.
    if not context.has_timestamp:
        if name in ("ccf", "granger", "hybrid", "te"):
            score -= 35
        elif name == "pcmci":
            score -= 20

    n = context.n_rows

    # Very few rows: simple tree is most reliable; statistical causal tests
    # have insufficient power.
    if n < 30:
        if name == "tree":
            score += 15
        elif name in ("granger", "hybrid"):
            score -= 40
        elif name in ("pcmci", "te"):
            score -= 50
        elif name == "ccf":
            score -= 20
    elif n < 100:
        if name == "granger":
            score -= 15
        elif name == "hybrid":
            score -= 20
        elif name == "pcmci":
            score -= 30
        elif name == "te":
            score -= 35  # KSG estimator needs ≥100 samples for reliable estimates
    elif n > 100_000:
        # Very large datasets: avoid slow multivariate methods.
        if name == "pcmci":
            score -= 40
        elif name == "hybrid":
            score -= 20
        elif name == "te":
            score -= 25  # KSG k-NN search scales poorly with N
        elif name == "granger":
            score -= 10
    elif n > 50_000:
        if name == "pcmci":
            score -= 30
        elif name == "hybrid":
            score -= 10
        elif name == "te":
            score -= 15

    # Regression mode: continuous target suits causal methods; tree is less
    # natural for a pure regression objective.
    if context.outcome_mode == "regression":
        if name == "tree":
            score -= 10
        elif name == "te":
            score += 10  # TE is optimized for continuous outcomes

    # Classification mode: TE uses the continuous metric as a proxy (not the
    # discrete labels), so it is disabled in ranking by default.
    if context.outcome_mode == "classification":
        if name == "te":
            score -= 100

    # Many predictors: expensive multivariate methods become slower.
    if context.n_predictors > 500:
        if name == "pcmci":
            score -= 20
        elif name == "hybrid":
            score -= 10

    # Consensus runs all 6 analyzers; penalise when the overhead is wasteful.
    if name == "consensus":
        if n < 30:
            # Very few rows: running 5 analyzers adds cost with no benefit.
            score -= 40
        elif n > 100_000:
            # Very large datasets: consensus is slow (runs all sub-analyzers).
            score -= 20

    return score


class InfluenceAnalyzerRegistry:
    """Registry for managing and dispatching influence analyzers."""

    def __init__(self) -> None:
        self._analyzers: dict[str, InfluenceAnalyzer] = {}
        self._data: pl.DataFrame | None = None
        self._labels: np.ndarray | None = None
        self._outcome_col: str | None = None
        self._settings: Any | None = None
        self._context: dict[str, Any] = {}
        self._last_analyzer_name: str | None = None

    def register(self, analyzer: InfluenceAnalyzer) -> None:
        """Register an analyzer instance by name."""
        self._analyzers[analyzer.name] = analyzer

    def get_analyzer(self, name: str) -> InfluenceAnalyzer | None:
        """Get a registered analyzer by name."""
        return self._analyzers.get(name)

    def get_analyzer_metadata(self) -> dict[str, dict[str, str]]:
        """
        Get metadata for all registered analyzers for UI display.

        Returns:
            Dictionary mapping analyzer name to metadata dict containing:
            - label: Human-readable label for UI (pulldown menu)
            - description: Tooltip/help description
        """
        return {
            name: {
                "label": analyzer.label,
                "description": analyzer.description,
            }
            for name, analyzer in sorted(self._analyzers.items())
        }

    def get_analyzer_choices(self) -> dict[str, str]:
        """
        Get analyzer choices formatted for UI dropdown.

        Returns:
            Dictionary mapping analyzer name to label, suitable for ui.input_select()
        """
        metadata = self.get_analyzer_metadata()
        return {name: info["label"] for name, info in metadata.items()}

    def rank_analyzers_for_context(self, context: DataContext) -> list[str]:
        """Return analyzer names ordered from most to least suitable for *context*.

        The first element is the recommended default for the current data.
        """
        names = list(self._analyzers.keys())
        if context.outcome_mode == "classification":
            names = [n for n in names if n != "te"]
        return sorted(
            names,
            key=lambda n: _score_analyzer_for_context(n, context),
            reverse=True,
        )

    def best_analyzer_for_context(self, context: DataContext) -> str | None:
        """Return the single best non-consensus analyzer for *context*.

        Consensus is excluded because it runs all other analyzers internally
        and is too expensive to use as the default auto-selected choice.
        """
        ranked = [
            n for n in self.rank_analyzers_for_context(context) if n != "consensus"
        ]
        return ranked[0] if ranked else None

    def get_ranked_analyzer_choices(self, context: DataContext | None = None) -> dict[str, str]:
        """Get analyzer choices ordered by suitability for *context*.

        Consensus is always placed last in the menu so it is not accidentally
        selected as the default, even though its scoring weight is high.

        When *context* is None, falls back to the default (alphabetical) order.

        Returns:
            Ordered dict mapping analyzer name to human-readable label.
        """
        if context is None:
            choices = self.get_analyzer_choices()
        else:
            ranked_names = self.rank_analyzers_for_context(context)
            metadata = {
                name: info["label"]
                for name, info in self.get_analyzer_metadata().items()
            }
            choices = {name: metadata[name] for name in ranked_names if name in metadata}
        # Always move consensus to the end of the menu.
        if "consensus" in choices:
            label = choices.pop("consensus")
            choices["consensus"] = label
        return choices

    def get_analyzer_tooltips(self) -> dict[str, str]:
        """
        Get analyzer tooltips for UI hover/title attributes.

        Returns:
            Dictionary mapping analyzer name to description tooltip
        """
        metadata = self.get_analyzer_metadata()
        return {name: info["description"] for name, info in metadata.items()}

    def set_shared_state(
        self,
        data: pl.DataFrame,
        labels: np.ndarray,
        settings: Any | None = None,
        outcome_col: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Set shared analysis state for all analyzers."""
        self._data = data
        self._labels = labels
        self._outcome_col = outcome_col
        self._settings = settings
        self._context = dict(context or {})

    @property
    def last_analyzer_name(self) -> str | None:
        """Return the analyzer name used in the last analyze_single call."""
        return self._last_analyzer_name

    def analyze_single(self, name: str, fallback: str = "tree") -> list[InfluenceFactor]:
        """Run a single analyzer by name, with optional fallback."""
        if self._data is None or self._labels is None:
            return []

        analyzer = self._analyzers.get(name)
        if analyzer is None and fallback:
            analyzer = self._analyzers.get(fallback)
            if analyzer is not None:
                name = fallback

        if analyzer is None:
            raise ValueError(f"Analyzer '{name}' is not registered")

        self._last_analyzer_name = name

        # Extract progress_callback from context if present
        context_copy = dict(self._context)
        progress_callback = context_copy.pop("progress_callback", None)

        return analyzer.analyze(
            self._data,
            self._labels,
            outcome_col=self._outcome_col,
            settings=self._settings,
            progress_callback=progress_callback,
            **context_copy,
        )


def create_analyzer_registry(settings: Settings | None = None) -> InfluenceAnalyzerRegistry:
    """Factory to build the analyzer registry with defaults.

    If column enrichment is enabled (default), wraps analyzers with
    EnrichedInfluenceAnalyzer for automatic synthetic column generation.
    """
    registry = InfluenceAnalyzerRegistry()

    # Check if enrichment is enabled (default: auto, which means True)
    enrichment_enabled = True
    if settings is not None:
        enrichment_setting = settings.get("profiling.enrichment.enabled", "auto")
        # Explicitly disabled only if set to False or "false"
        enrichment_enabled = enrichment_setting not in (False, "false")

    # Register all analyzers
    analyzers = [
        TreeInfluenceAnalyzer(),
        LaggedCCFInfluenceAnalyzer(),
        GrangerInfluenceAnalyzer(),
        HybridCausalInfluenceAnalyzer(),
        PCMCIInfluenceAnalyzer(),
        TransferEntropyInfluenceAnalyzer(),
    ]

    for analyzer in analyzers:
        if enrichment_enabled:
            # Wrap with enrichment decorator (enrichers will be auto-created at analysis time)
            enriched = EnrichedInfluenceAnalyzer(inner=analyzer)
            registry.register(enriched)
        else:
            # Register directly without enrichment
            registry.register(analyzer)

    # Consensus runs all 5 sub-analyzers internally; never wrap with enrichment.
    registry.register(ConsensusInfluenceAnalyzer())

    return registry
