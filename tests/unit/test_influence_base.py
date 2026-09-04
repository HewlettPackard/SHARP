"""
Tests for influence analyzer base types.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import pytest
from src.core.profile.base import (
    CausalDirection, InfluenceFactor, InfluenceAnalyzer, AnalyzerVisualizer
)


def test_influence_analyzer_abc_requires_implementation():
    """InfluenceAnalyzer ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
        InfluenceAnalyzer()


def test_analyzer_visualizer_abc_requires_implementation():
    """AnalyzerVisualizer ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
        AnalyzerVisualizer()


def test_influence_factor_required_and_optional_fields():
    """InfluenceFactor correctly combines required (name, strength) and optional fields."""
    # Minimal valid factor
    factor = InfluenceFactor(name="cache_misses", strength=0.72)
    assert factor.name == "cache_misses"
    assert factor.strength == 0.72
    assert factor.rank is None
    assert factor.direction is None

    # With optional fields
    factor = InfluenceFactor(
        name="queue_depth",
        strength=0.85,
        rank=1,
        direction=CausalDirection.FORWARD,
        p_value=0.001,
        confidence_interval=(0.70, 0.95)
    )
    assert factor.rank == 1
    assert factor.direction == CausalDirection.FORWARD
    assert factor.p_value == 0.001
    assert factor.confidence_interval == (0.70, 0.95)


def test_influence_factor_immutability():
    """InfluenceFactor is immutable (dataclass with frozen=True)."""
    factor = InfluenceFactor(name="x", strength=0.5)
    with pytest.raises(AttributeError):
        factor.strength = 0.6
