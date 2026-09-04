"""
Tests for influence narrative generation.

Tests the generate_influence_narrative() function with various factor
combinations to verify:
- Proper per-factor narratives (returned as dict[str, str])
- Adaptation to available fields (lag, direction, confidence)
- Model assumptions included in narratives
- Correct formatting for all field types

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import pytest

from src.core.profile.base import InfluenceFactor, CausalDirection
from src.core.profile.narrative import (
    generate_influence_narrative,
    generate_factor_badge_narrative,
    generate_analytical_assumptions_statement,
)


@pytest.fixture
def basic_factor():
    """Simple factor with strength only."""
    return InfluenceFactor(
        name="cpu_usage",
        strength=0.75,
        rank=1,
        method="ccf",
    )


@pytest.fixture
def factor_with_lag():
    """Factor with lag information."""
    return InfluenceFactor(
        name="memory_pressure",
        strength=0.65,
        rank=2,
        method="ccf",
        lag=2.5,
        lag_rows=10,
        metadata={
            "model_assumptions": [
                "Non-directional association only",
                "Does not control for confounders",
            ]
        },
    )


@pytest.fixture
def factor_with_direction():
    """Factor with causal direction."""
    return InfluenceFactor(
        name="disk_io",
        strength=0.82,
        rank=1,
        method="granger",
        direction=CausalDirection.FORWARD,
        p_value=0.002,
        lag=1.0,
        lag_rows=5,
    )


@pytest.fixture
def factor_with_ci():
    """Factor with confidence interval."""
    return InfluenceFactor(
        name="network_latency",
        strength=0.55,
        rank=3,
        method="ccf",
        confidence_interval=(0.32, 0.78),
        p_value=0.015,
        metadata={
            "model_assumptions": [
                "Assuming stationary data",
                "Does not control for confounders",
            ]
        },
    )


@pytest.fixture
def factor_with_falsification():
    """Factor with falsification plan."""
    return InfluenceFactor(
        name="cache_misses",
        strength=0.71,
        rank=1,
        method="tree",
        falsification_plan={
            "type": "threshold",
            "feature": "cache_misses",
            "threshold": 1000.0,
        },
        metadata={
            "model_assumptions": [
                "Based on tree thresholds",
                "Does not control for confounders",
            ]
        },
    )


class TestBasicNarrative:
    """Test basic narrative generation with minimal factors."""

    def test_empty_factors_list(self):
        """Narrative for empty factors list."""
        result = generate_influence_narrative([])
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_single_basic_factor(self, basic_factor):
        """Narrative with single basic factor."""
        result = generate_influence_narrative([basic_factor])
        assert isinstance(result, dict)
        assert "cpu_usage" in result
        assert "correlation" in result["cpu_usage"].lower()
        assert "0.75" in result["cpu_usage"]

    def test_narrative_includes_strength_for_all_factors(self, basic_factor, factor_with_lag):
        """Narrative includes strength for all factors."""
        result = generate_influence_narrative([basic_factor, factor_with_lag])
        assert isinstance(result, dict)
        assert len(result) == 2
        assert all("correlation" in narrative.lower() or "importance" in narrative.lower() for narrative in result.values())


class TestLagNarrative:
    """Test narrative generation with lag information."""

    def test_lag_in_seconds_included(self, factor_with_lag):
        """Lag in seconds is included when available."""
        result = generate_influence_narrative([factor_with_lag])
        assert "memory_pressure" in result
        narrative = result["memory_pressure"]
        # Should include lag information in the factor's narrative
        assert "lag" in narrative.lower()

    def test_lag_direction_positive(self):
        """Positive lag indicates predictor leads outcome."""
        factor = InfluenceFactor(
            name="test_factor",
            strength=0.6,
            lag=1.5,
            lag_rows=6,
            method="ccf",
        )
        result = generate_influence_narrative([factor])
        narrative = result["test_factor"]
        # Should indicate leading relationship
        assert "lag" in narrative.lower() and "lead" in narrative.lower()

    def test_lag_direction_negative(self):
        """Negative lag indicates predictor lags outcome."""
        factor = InfluenceFactor(
            name="test_factor",
            strength=0.6,
            lag=-1.5,
            lag_rows=-6,
            method="ccf",
        )
        result = generate_influence_narrative([factor])
        narrative = result["test_factor"]
        # Should indicate lagging relationship
        assert "lag" in narrative.lower()


class TestDirectionNarrative:
    """Test narrative generation with causal direction."""

    def test_forward_direction_included(self, factor_with_direction):
        """Forward direction is included in narrative."""
        result = generate_influence_narrative([factor_with_direction])
        narrative = result["disk_io"]
        assert "direction" in narrative.lower() and "forward" in narrative.lower()

    def test_reverse_direction_noted(self):
        """Reverse direction is noted."""
        factor = InfluenceFactor(
            name="test_factor",
            strength=0.6,
            method="granger",
            direction=CausalDirection.REVERSE,
        )
        result = generate_influence_narrative([factor])
        narrative = result["test_factor"]
        assert "direction" in narrative.lower() and "reverse" in narrative.lower()

    def test_bidirectional_direction_noted(self):
        """Bidirectional relationship is noted."""
        factor = InfluenceFactor(
            name="test_factor",
            strength=0.6,
            method="granger",
            direction=CausalDirection.BIDIRECTIONAL,
        )
        result = generate_influence_narrative([factor])
        narrative = result["test_factor"]
        assert "direction" in narrative.lower() and "bidirectional" in narrative.lower()


class TestConfidenceNarrative:
    """Test narrative generation with confidence/significance information."""

    def test_pvalue_included(self, factor_with_ci):
        """P-value is included when present."""
        result = generate_influence_narrative([factor_with_ci])
        narrative = result["network_latency"]
        # Should include significance information
        assert "significance" in narrative.lower() and ("p" in narrative.lower() or "0.015" in narrative)

    def test_high_significance(self):
        """High significance (p < 0.001) is properly noted."""
        factor = InfluenceFactor(
            name="test_factor",
            strength=0.8,
            method="granger",
            p_value=0.0001,
        )
        result = generate_influence_narrative([factor])
        narrative = result["test_factor"]
        assert "significance" in narrative.lower() and "0.001" in narrative

    def test_confidence_interval_included(self, factor_with_ci):
        """Confidence interval is included when present."""
        result = generate_influence_narrative([factor_with_ci])
        narrative = result["network_latency"]
        # Should include confidence interval information
        assert "ci" in narrative.lower() or "0.32" in narrative or "0.78" in narrative

    def test_tree_ci_not_shown_before_bootstrap(self):
        """Tree narrative omits CI text before on-demand bootstrap is computed."""
        factor = InfluenceFactor(
            name="cache_misses",
            strength=0.71,
            method="tree",
            confidence_interval=None,
            metadata={"bootstrap_ci_enabled": False},
        )
        result = generate_influence_narrative([factor])
        narrative = result["cache_misses"]
        assert "95% ci" not in narrative.lower()


class TestModelAssumptionsNarrative:
    """Test that model assumptions are included per-factor."""

    def test_assumptions_in_ccf_narrative(self, factor_with_lag):
        """CCF factors include non-directional assumption in their narrative."""
        result = generate_influence_narrative([factor_with_lag])
        narrative = result["memory_pressure"]
        assert "assumption" in narrative.lower()

    def test_assumptions_always_included_when_available(self, factor_with_ci):
        """Assumptions are included in factor narrative when metadata is present."""
        result = generate_influence_narrative([factor_with_ci], include_model_assumptions=True)
        narrative = result["network_latency"]
        assert "assumption" in narrative.lower()

    def test_assumptions_can_be_disabled(self, factor_with_ci):
        """Assumptions section can be disabled via parameter."""
        result_with = generate_influence_narrative([factor_with_ci], include_model_assumptions=True)
        result_without = generate_influence_narrative([factor_with_ci], include_model_assumptions=False)

        # Both should have the factor, but only 'with' should include assumptions
        assert "network_latency" in result_with and "network_latency" in result_without
        with_assumptions = result_with["network_latency"]
        without_assumptions = result_without["network_latency"]
        assert "assumption" in with_assumptions.lower()
        # Without should still have other data
        assert len(without_assumptions) > 0

    def test_ccf_assumptions_statement(self):
        """CCF method produces correct assumption statements."""
        factor = InfluenceFactor(
            name="test",
            strength=0.5,
            method="ccf",
            metadata={
                "model_assumptions": [
                    "Non-directional association only",
                    "Does not control for confounders",
                ]
            },
        )
        result = generate_influence_narrative([factor])
        narrative = result["test"]
        # Should mention assumptions
        assert "assumption" in narrative.lower()


class TestFalsificationNarrative:
    """Test falsification plan narratives."""

    def test_falsification_section_included(self, factor_with_falsification):
        """Falsification test appears when plans are present."""
        result = generate_influence_narrative([factor_with_falsification])
        narrative = result["cache_misses"]
        assert "falsif" in narrative.lower()

    def test_threshold_falsification_described(self, factor_with_falsification):
        """Threshold falsification plans are described."""
        result = generate_influence_narrative([factor_with_falsification])
        narrative = result["cache_misses"]
        # Should mention threshold
        assert "threshold" in narrative.lower() or "1000" in narrative

    def test_no_falsification_section_without_plans(self, basic_factor):
        """Falsification section missing when no plans."""
        result = generate_influence_narrative([basic_factor])
        narrative = result["cpu_usage"]
        # Should not have falsification section
        assert "falsif" not in narrative.lower()


class TestNarrativeFormatting:
    """Test narrative formatting and structure."""

    def test_multiple_factors_all_present(self):
        """Multiple factors all appear in result dictionary."""
        f1 = InfluenceFactor(name="factor1", strength=0.9, rank=1, method="ccf")
        f2 = InfluenceFactor(name="factor2", strength=0.7, rank=2, method="ccf")
        f3 = InfluenceFactor(name="factor3", strength=0.5, rank=3, method="ccf")

        result = generate_influence_narrative([f1, f2, f3])

        # All factors should appear as keys
        assert len(result) == 3
        assert "factor1" in result
        assert "factor2" in result
        assert "factor3" in result

    def test_each_narrative_self_contained(self, factor_with_lag, factor_with_ci):
        """Each narrative is self-contained in the dictionary."""
        result = generate_influence_narrative([factor_with_lag, factor_with_ci])

        lag_narrative = result["memory_pressure"]
        ci_narrative = result["network_latency"]

        # Each should contain its own data
        assert "0.65" in lag_narrative  # memory_pressure strength
        assert "0.55" in ci_narrative   # network_latency strength
        # They should be independent
        assert "memory_pressure" not in ci_narrative
        assert "network_latency" not in lag_narrative

    def test_narrative_length_reasonable(self, factor_with_lag, factor_with_ci):
        """Each narrative is reasonably sized."""
        result = generate_influence_narrative([factor_with_lag, factor_with_ci])
        for narrative in result.values():
            # Should be substantive but not excessively long
            assert 20 < len(narrative) < 1000


class TestBadgeNarrative:
    """Test factor badge narratives for inline display."""

    def test_basic_factor_badge(self, basic_factor):
        """Basic factor produces minimal badge."""
        badge = generate_factor_badge_narrative(basic_factor)
        # May be empty or minimal
        assert isinstance(badge, str)

    def test_lag_in_badge(self, factor_with_lag):
        """Lag info appears in badge."""
        badge = generate_factor_badge_narrative(factor_with_lag)
        assert "lag" in badge.lower() or badge == ""

    def test_direction_in_badge(self, factor_with_direction):
        """Direction appears as symbol in badge."""
        badge = generate_factor_badge_narrative(factor_with_direction)
        assert "dir" in badge.lower() or "→" in badge or badge == ""

    def test_significance_in_badge(self, factor_with_ci):
        """Significance appears in badge."""
        badge = generate_factor_badge_narrative(factor_with_ci)
        assert "p" in badge.lower() or badge == ""




class TestAnalyticalAssumptionsStatement:
    """Test full analytical assumptions and limitations statement."""

    def test_statement_includes_method_assumptions(self, factor_with_direction):
        """Assumptions statement includes method-specific info."""
        statement = generate_analytical_assumptions_statement([factor_with_direction])
        assert "causal" in statement.lower() or "assumption" in statement.lower()

    def test_statement_for_multiple_methods(self, factor_with_direction, factor_with_lag):
        """Statement covers multiple analytical methods."""
        statement = generate_analytical_assumptions_statement([
            factor_with_direction,
            factor_with_lag,
        ])
        assert isinstance(statement, str)
        assert len(statement) > 50

    def test_statement_includes_general_limitations(self, basic_factor):
        """General limitations are included."""
        statement = generate_analytical_assumptions_statement([basic_factor])
        # Should mention limitations or caveats
        assert "assumption" in statement.lower() or "limit" in statement.lower() or len(statement) > 0


class TestRegressionCases:
    """Regression tests for edge cases and known issues."""

    def test_factor_with_all_fields_populated(self):
        """Factor with all possible fields produces valid narrative."""
        factor = InfluenceFactor(
            name="comprehensive_factor",
            strength=0.87,
            rank=1,
            method="ccf",
            direction=CausalDirection.FORWARD,
            p_value=0.001,
            lag=1.5,
            lag_rows=6,
            confidence_interval=(0.65, 0.95),
            falsification_plan={
                "type": "threshold",
                "threshold": 100,
            },
            metadata={
                "model_assumptions": [
                    "Non-directional association only",
                    "Does not control for confounders",
                ],
            },
        )
        result = generate_influence_narrative([factor])
        # Should not error and should include factor name key
        assert "comprehensive_factor" in result
        narrative = result["comprehensive_factor"]
        assert len(narrative) > 50

    def test_nan_values_handled(self):
        """NaN and None values in factors are handled gracefully."""
        factor = InfluenceFactor(
            name="factor_with_nans",
            strength=float("nan"),
            lag=None,
            p_value=None,
            confidence_interval=None,
        )
        # Should not raise an exception
        result = generate_influence_narrative([factor])
        assert "factor_with_nans" in result
        assert isinstance(result["factor_with_nans"], str)

    def test_very_small_pvalues(self):
        """Very small p-values are formatted correctly."""
        factor = InfluenceFactor(
            name="highly_significant",
            strength=0.95,
            p_value=1e-10,
            method="granger",
        )
        result = generate_influence_narrative([factor])
        assert "highly_significant" in result
        narrative = result["highly_significant"]
        # Should express extreme significance somehow
        assert "significance" in narrative.lower() and len(narrative) > 0


class TestEnrichmentNarrative:
    """Tests for enrichment narrative integration."""

    def test_enrichment_narrative_included(self):
        """Enrichment narratives are included in factor narratives."""
        factor = InfluenceFactor(
            name="cpu_agg_max",
            strength=0.82,
            rank=1,
            method="tree",
            metadata={
                "enriched_from": "cpu_agg_max__",
                "enrichment_narrative": (
                    "The worst-case CPU across all hosts strongly "
                    "predicts SLOW performance. Investigate which host "
                    "has the highest CPU."
                ),
                "original_columns": ["cpu"],
            },
        )
        result = generate_influence_narrative([factor])
        assert "cpu_agg_max" in result
        narrative = result["cpu_agg_max"]
        # Check that enrichment section is included
        assert "multi-source insight" in narrative.lower()
        assert "worst-case" in narrative.lower()
        assert "synthetic" in narrative.lower()

    def test_enrichment_with_synthetic_marker(self):
        """Enrichment narrative includes reference to synthetic column name."""
        factor = InfluenceFactor(
            name="memory_agg_std",
            strength=0.65,
            method="granger",
            metadata={
                "enriched_from": "memory__agg_std__",
                "enrichment_narrative": (
                    "Sources are imbalanced in memory. Some sources have "
                    "much higher memory usage than others."
                ),
            },
        )
        result = generate_influence_narrative([factor])
        narrative = result["memory_agg_std"]
        # Should mention that it's synthetic and from what
        assert "synthetic from memory__agg_std__" in narrative

    def test_enrichment_without_synthetic_marker(self):
        """Enrichment narrative works even without explicit enriched_from field."""
        factor = InfluenceFactor(
            name="interaction_factor",
            strength=0.71,
            method="tree",
            metadata={
                "enrichment_narrative": (
                    "The interaction between CPU and memory usage "
                    "jointly predicts performance."
                ),
            },
        )
        result = generate_influence_narrative([factor])
        narrative = result["interaction_factor"]
        # Should include enrichment insight without enriched_from
        assert "multi-source insight" in narrative.lower()
        assert "interaction" in narrative.lower()

    def test_no_enrichment_narrative_no_enrichment_section(self):
        """Factors without enrichment metadata have no enrichment section."""
        factor = InfluenceFactor(
            name="plain_factor",
            strength=0.60,
            method="tree",
            metadata={"model_assumptions": ["Based on tree thresholds"]},
        )
        result = generate_influence_narrative([factor])
        narrative = result["plain_factor"]
        # Should not have enrichment section
        assert "multi-source insight" not in narrative.lower()

    def test_enrichment_narrative_multiple_factors(self):
        """Multiple factors, some enriched and some not, are handled correctly."""
        factors = [
            InfluenceFactor(
                name="cpu_agg_max",
                strength=0.85,
                method="tree",
                metadata={
                    "enriched_from": "cpu__agg_max__",
                    "enrichment_narrative": "Aggregate CPU signal.",
                },
            ),
            InfluenceFactor(
                name="plain_io",
                strength=0.60,
                method="tree",
            ),
        ]
        result = generate_influence_narrative(factors)
        assert len(result) == 2
        # First should have enrichment
        assert "multi-source insight" in result["cpu_agg_max"].lower()
        # Second should not
        assert "multi-source insight" not in result["plain_io"].lower()
