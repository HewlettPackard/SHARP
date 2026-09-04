"""
Registry for influence analyzers.

Encapsulates shared state and routes analysis to registered analyzers.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from src.core.profile.base import InfluenceAnalyzer, InfluenceFactor
from src.core.profile.analyzers.tree import TreeInfluenceAnalyzer
from src.core.config.settings import Settings


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
        return analyzer.analyze(
            self._data,
            self._labels,
            outcome_col=self._outcome_col,
            settings=self._settings,
            **self._context,
        )


def create_analyzer_registry(settings: Settings | None = None) -> InfluenceAnalyzerRegistry:
    """Factory to build the analyzer registry with defaults."""
    registry = InfluenceAnalyzerRegistry()
    registry.register(TreeInfluenceAnalyzer())
    return registry
