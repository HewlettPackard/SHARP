"""
Tests for influence analyzer registry.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import polars as pl
import pytest

from src.core.profile.base import InfluenceAnalyzer, InfluenceFactor
from src.core.profile.analyzers.registry import InfluenceAnalyzerRegistry, create_analyzer_registry


class _DummyAnalyzer(InfluenceAnalyzer):
    def __init__(self, name: str, value: float) -> None:
        self._name = name
        self._value = value

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"direction": False}

    def analyze(self, data, labels, outcome_col=None, settings=None, **kwargs):
        return [InfluenceFactor(name="x", strength=self._value)]


def test_registry_dispatch_and_fallback():
    data = pl.DataFrame({"x": [1, 2, 3]})
    labels = np.array([0, 1, 0])

    registry = InfluenceAnalyzerRegistry()
    registry.register(_DummyAnalyzer("tree", 0.5))
    registry.set_shared_state(data, labels)

    result = registry.analyze_single("missing", fallback="tree")
    assert registry.last_analyzer_name == "tree"
    assert result[0].strength == 0.5


def test_registry_missing_analyzer_raises():
    data = pl.DataFrame({"x": [1, 2, 3]})
    labels = np.array([0, 1, 0])

    registry = InfluenceAnalyzerRegistry()
    registry.set_shared_state(data, labels)

    with pytest.raises(ValueError):
        registry.analyze_single("missing", fallback="")


def test_create_registry_registers_tree():
    registry = create_analyzer_registry()
    analyzer = registry.get_analyzer("tree")
    assert analyzer is not None
