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


def test_create_registry_registers_consensus():
    registry = create_analyzer_registry()
    assert registry.get_analyzer("consensus") is not None


def test_consensus_analyzer_properties():
    from src.core.profile.analyzers import ConsensusInfluenceAnalyzer

    a = ConsensusInfluenceAnalyzer()
    assert a.name == "consensus"
    assert a.label == "Consensus (all analyzers)"
    assert isinstance(a.capabilities, dict)
    assert a.capabilities.get("lag_detection") is True


def test_consensus_returns_empty_on_empty_data():
    from src.core.profile.analyzers import ConsensusInfluenceAnalyzer

    a = ConsensusInfluenceAnalyzer()
    result = a.analyze(
        data=pl.DataFrame({"x": [], "y": []}),
        labels=np.array([], dtype=int),
        outcome_col="y",
        outcome_mode="classification",
    )
    assert result == []


def test_consensus_factors_have_metadata():
    """ConsensusInfluenceAnalyzer should produce factors with consensus_votes."""
    from src.core.profile.analyzers import ConsensusInfluenceAnalyzer

    rng = np.random.default_rng(0)
    n = 40
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    labels = (x1 + rng.normal(scale=0.1, size=n) > 0).astype(int)
    data = pl.DataFrame({"x1": x1, "x2": x2})

    a = ConsensusInfluenceAnalyzer()
    factors = a.analyze(
        data=data,
        labels=labels,
        outcome_col=None,
        outcome_mode="classification",
        max_predictors=10,
        max_correlation=0.99,
    )

    assert len(factors) > 0
    for f in factors:
        assert f.method == "consensus"
        assert f.metadata is not None
        assert "consensus_votes" in f.metadata
        assert "agreement" in f.metadata
        assert "consensus_score" in f.metadata
        assert f.metadata["agreement"] >= 1


def test_consensus_sorted_by_score():
    """Factors must be in descending order of consensus_score."""
    from src.core.profile.analyzers import ConsensusInfluenceAnalyzer

    rng = np.random.default_rng(1)
    n = 60
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    labels = (x1 + rng.normal(scale=0.1, size=n) > 0).astype(int)
    data = pl.DataFrame({"x1": x1, "x2": x2})

    a = ConsensusInfluenceAnalyzer()
    factors = a.analyze(
        data=data,
        labels=labels,
        outcome_col=None,
        outcome_mode="classification",
        max_predictors=10,
        max_correlation=0.99,
    )

    scores = [f.metadata["consensus_score"] for f in factors]
    assert scores == sorted(scores, reverse=True)


def test_consensus_base_score_highest():
    """Consensus should not be auto-selected and should appear last in menu choices."""
    from src.core.profile.analyzers.registry import DataContext

    registry = create_analyzer_registry()
    ctx = DataContext(has_timestamp=True, n_rows=500, n_predictors=10)

    # best_analyzer_for_context must never return consensus.
    best = registry.best_analyzer_for_context(ctx)
    assert best != "consensus"
    assert best is not None

    # consensus must be the last key in the ranked choices dict.
    choices = registry.get_ranked_analyzer_choices(ctx)
    assert list(choices.keys())[-1] == "consensus"

