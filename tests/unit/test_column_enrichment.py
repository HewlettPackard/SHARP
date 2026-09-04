"""
Tests for column enrichment (Phase 7).

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import polars as pl
import pytest

from src.core.profile.column_enrichment import (
    AGG_MAX_SUFFIX,
    AGG_MEAN_SUFFIX,
    AGG_STD_SUFFIX,
    IX_INFIX,
    RATIO_INFIX,
    TMP_DIFF_SUFFIX,
    TMP_RSTD_SUFFIX,
    AggregateEnricher,
    ColumnEnricher,
    EnrichedInfluenceAnalyzer,
    InteractionEnricher,
    TemporalEnricher,
    create_enrichers_from_settings,
    is_enriched_column,
)
from src.core.profile.base import (
    LABEL_OUTCOME_COL,
    InfluenceAnalyzer,
    InfluenceFactor,
)


# ============================================================================
# Helpers
# ============================================================================

def _tall_multi_source_data() -> pl.DataFrame:
    """Tall-format data: 2 hosts, 4 timestamps, 2 metrics."""
    return pl.DataFrame({
        "timestamp": [1, 1, 2, 2, 3, 3, 4, 4],
        "host": ["h1", "h2", "h1", "h2", "h1", "h2", "h1", "h2"],
        "cpu": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
        "mem": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0],
    })


def _wide_data_with_groups() -> tuple[pl.DataFrame, dict[str, list[str]]]:
    """Wide-format data with semantic groups."""
    data = pl.DataFrame({
        "cpu__h1": [10.0, 30.0, 50.0, 70.0],
        "cpu__h2": [20.0, 40.0, 60.0, 80.0],
        "mem__h1": [100.0, 300.0, 500.0, 700.0],
        "mem__h2": [200.0, 400.0, 600.0, 800.0],
    })
    groups = {
        "cpu": ["cpu__h1", "cpu__h2"],
        "mem": ["mem__h1", "mem__h2"],
    }
    return data, groups


class _StubAnalyzer(InfluenceAnalyzer):
    """Stub analyzer that returns factors named after columns."""

    @property
    def name(self) -> str:
        return "stub"

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"lag_detection": False, "direction": False, "uncertainty": False, "falsification": False}

    def analyze(self, data, labels, outcome_col=None, settings=None, outcome_mode="classification", **kwargs):
        factors = []
        for i, col in enumerate(data.columns):
            if col == outcome_col or col == LABEL_OUTCOME_COL:
                continue
            factors.append(
                InfluenceFactor(name=col, strength=1.0 / (i + 1), rank=i + 1, method="stub")
            )
        return factors


# ============================================================================
# is_enriched_column
# ============================================================================

class TestIsEnrichedColumn:
    def test_plain_column(self):
        assert not is_enriched_column("cpu_usage")

    def test_agg_columns(self):
        assert is_enriched_column(f"cpu{AGG_MAX_SUFFIX}")
        assert is_enriched_column(f"mem{AGG_STD_SUFFIX}")
        assert is_enriched_column(f"io{AGG_MEAN_SUFFIX}")

    def test_interaction_columns(self):
        assert is_enriched_column(f"a{IX_INFIX}b")
        assert is_enriched_column(f"cpu{RATIO_INFIX}mem")

    def test_temporal_columns(self):
        assert is_enriched_column(f"cpu{TMP_DIFF_SUFFIX}")
        assert is_enriched_column(f"cpu{TMP_RSTD_SUFFIX}10__")


# ============================================================================
# AggregateEnricher
# ============================================================================

class TestAggregateEnricher:
    def test_tall_enrichment_adds_columns(self):
        data = _tall_multi_source_data()
        enricher = AggregateEnricher()
        result = enricher.enrich(data, source_columns=["host"])

        assert result.height == data.height
        # Original columns still present
        for col in data.columns:
            assert col in result.columns

        # Synthetic columns created for numeric metrics (cpu, mem)
        for metric in ("cpu", "mem"):
            assert f"{metric}{AGG_MAX_SUFFIX}" in result.columns
            assert f"{metric}{AGG_STD_SUFFIX}" in result.columns
            assert f"{metric}{AGG_MEAN_SUFFIX}" in result.columns

    def test_tall_max_values_correct(self):
        data = _tall_multi_source_data()
        enricher = AggregateEnricher(functions=["max"])
        result = enricher.enrich(data, source_columns=["host"])

        cpu_max = result[f"cpu{AGG_MAX_SUFFIX}"].to_list()
        # timestamp=1: max(10,20)=20 for both rows in that group
        assert cpu_max[0] == 20.0
        assert cpu_max[1] == 20.0
        # timestamp=4: max(70,80)=80
        assert cpu_max[6] == 80.0
        assert cpu_max[7] == 80.0

    def test_tall_mean_values_correct(self):
        data = _tall_multi_source_data()
        enricher = AggregateEnricher(functions=["mean"])
        result = enricher.enrich(data, source_columns=["host"])

        cpu_mean = result[f"cpu{AGG_MEAN_SUFFIX}"].to_list()
        # timestamp=1: mean(10,20)=15 for both rows
        assert cpu_mean[0] == 15.0
        assert cpu_mean[1] == 15.0

    def test_wide_enrichment_with_semantic_groups(self):
        data, groups = _wide_data_with_groups()
        enricher = AggregateEnricher()
        result = enricher.enrich(data, semantic_groups=groups)

        assert f"cpu{AGG_MAX_SUFFIX}" in result.columns
        assert f"mem{AGG_STD_SUFFIX}" in result.columns

        # Check max values: max(cpu__h1, cpu__h2) per row
        cpu_max = result[f"cpu{AGG_MAX_SUFFIX}"].to_list()
        assert cpu_max[0] == 20.0  # max(10, 20)
        assert cpu_max[1] == 40.0  # max(30, 40)

    def test_no_source_returns_unchanged(self):
        data = pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        enricher = AggregateEnricher()
        result = enricher.enrich(data)
        assert result.columns == data.columns

    def test_subset_of_functions(self):
        data = _tall_multi_source_data()
        enricher = AggregateEnricher(functions=["max"])
        result = enricher.enrich(data, source_columns=["host"])

        assert f"cpu{AGG_MAX_SUFFIX}" in result.columns
        assert f"cpu{AGG_STD_SUFFIX}" not in result.columns
        assert f"cpu{AGG_MEAN_SUFFIX}" not in result.columns

    def test_trace_to_originals(self):
        enricher = AggregateEnricher()
        assert enricher.trace_to_originals(f"cpu{AGG_MAX_SUFFIX}") == ["cpu"]
        assert enricher.trace_to_originals(f"mem{AGG_STD_SUFFIX}") == ["mem"]
        assert enricher.trace_to_originals("plain_col") == []

    def test_narrative_fragment(self):
        enricher = AggregateEnricher()
        narr = enricher.narrative_fragment(f"cpu{AGG_MAX_SUFFIX}")
        assert "cpu" in narr
        assert "worst-case" in narr.lower() or "highest" in narr.lower()

        assert enricher.narrative_fragment("plain_col") == ""


# ============================================================================
# InteractionEnricher
# ============================================================================

class TestInteractionEnricher:
    def _data_with_outcome(self) -> pl.DataFrame:
        """Data with label outcome column for interaction screening."""
        np.random.seed(42)
        n = 50
        a = np.random.randn(n)
        b = np.random.randn(n)
        labels = (a * b > 0).astype(float)
        return pl.DataFrame({
            "col_a": a,
            "col_b": b,
            "noise": np.random.randn(n),
            LABEL_OUTCOME_COL: labels,
        })

    def test_enrichment_adds_interaction_columns(self):
        data = self._data_with_outcome()
        enricher = InteractionEnricher(top_k=5, min_abs_correlation=0.0)
        result = enricher.enrich(data)

        # Should have at least one product interaction
        ix_cols = [c for c in result.columns if IX_INFIX in c]
        assert len(ix_cols) > 0, "No interaction columns created"

    def test_enrichment_adds_ratio_columns(self):
        data = self._data_with_outcome()
        enricher = InteractionEnricher(top_k=5, min_abs_correlation=0.0)
        result = enricher.enrich(data)

        ratio_cols = [c for c in result.columns if RATIO_INFIX in c]
        assert len(ratio_cols) > 0, "No ratio columns created"

    def test_no_ratios_when_disabled(self):
        data = self._data_with_outcome()
        enricher = InteractionEnricher(top_k=5, min_abs_correlation=0.0, include_ratios=False)
        result = enricher.enrich(data)

        ratio_cols = [c for c in result.columns if RATIO_INFIX in c]
        assert len(ratio_cols) == 0, "Ratio columns created when disabled"

    def test_no_outcome_returns_unchanged(self):
        data = pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        enricher = InteractionEnricher()
        result = enricher.enrich(data)
        assert result.columns == data.columns

    def test_high_min_correlation_filters_all(self):
        data = self._data_with_outcome()
        enricher = InteractionEnricher(min_abs_correlation=0.99)
        result = enricher.enrich(data)

        ix_cols = [c for c in result.columns if IX_INFIX in c]
        assert len(ix_cols) == 0, "Should filter all columns with high threshold"

    def test_trace_to_originals(self):
        enricher = InteractionEnricher()
        assert enricher.trace_to_originals(f"a{IX_INFIX}b") == ["a", "b"]
        assert enricher.trace_to_originals(f"cpu{RATIO_INFIX}mem") == ["cpu", "mem"]
        assert enricher.trace_to_originals("plain_col") == []

    def test_narrative_fragment(self):
        enricher = InteractionEnricher()
        narr = enricher.narrative_fragment(f"cpu{IX_INFIX}mem")
        assert "cpu" in narr
        assert "mem" in narr
        assert "interaction" in narr.lower()

        narr_ratio = enricher.narrative_fragment(f"cpu{RATIO_INFIX}mem")
        assert "ratio" in narr_ratio.lower()
        assert enricher.narrative_fragment("plain") == ""

    def test_does_not_enrich_synthetic_columns(self):
        """Interactions should only be between original columns."""
        data = self._data_with_outcome()
        # Add a synthetic aggregate column — should be excluded
        data = data.with_columns(
            pl.lit(1.0).alias(f"fake{AGG_MAX_SUFFIX}")
        )
        enricher = InteractionEnricher(top_k=10, min_abs_correlation=0.0)
        result = enricher.enrich(data)

        # No interaction should involve the synthetic column
        for col in result.columns:
            if IX_INFIX in col or RATIO_INFIX in col:
                assert AGG_MAX_SUFFIX not in col


# ============================================================================
# TemporalEnricher
# ============================================================================

class TestTemporalEnricher:
    def test_adds_diff_columns(self):
        data = pl.DataFrame({"x": [1.0, 3.0, 6.0, 10.0], "y": [2.0, 4.0, 8.0, 16.0]})
        enricher = TemporalEnricher(include_diff=True, rolling_std_window=0)
        result = enricher.enrich(data)

        assert f"x{TMP_DIFF_SUFFIX}" in result.columns
        diffs = result[f"x{TMP_DIFF_SUFFIX}"].to_list()
        assert diffs[1] == pytest.approx(2.0)
        assert diffs[2] == pytest.approx(3.0)

    def test_adds_rolling_std_columns(self):
        data = pl.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
        enricher = TemporalEnricher(include_diff=False, rolling_std_window=3)
        result = enricher.enrich(data)

        rstd_col = f"x{TMP_RSTD_SUFFIX}3__"
        assert rstd_col in result.columns

    def test_too_few_rows_returns_unchanged(self):
        data = pl.DataFrame({"x": [1.0, 2.0]})
        enricher = TemporalEnricher()
        result = enricher.enrich(data)
        assert result.columns == data.columns

    def test_excludes_source_columns(self):
        data = pl.DataFrame({
            "host": [1, 2, 3, 4],
            "cpu": [10.0, 20.0, 30.0, 40.0],
        })
        enricher = TemporalEnricher(rolling_std_window=0)
        result = enricher.enrich(data, source_columns=["host"])

        # Should NOT create diff for host column
        assert f"host{TMP_DIFF_SUFFIX}" not in result.columns
        assert f"cpu{TMP_DIFF_SUFFIX}" in result.columns

    def test_excludes_synthetic_columns(self):
        data = pl.DataFrame({
            "x": [1.0, 2.0, 3.0, 4.0],
            f"y{AGG_MAX_SUFFIX}": [10.0, 20.0, 30.0, 40.0],
        })
        enricher = TemporalEnricher(rolling_std_window=0)
        result = enricher.enrich(data)

        assert f"x{TMP_DIFF_SUFFIX}" in result.columns
        # The synthetic column should be skipped
        assert f"y{AGG_MAX_SUFFIX}{TMP_DIFF_SUFFIX}" not in result.columns

    def test_trace_to_originals(self):
        enricher = TemporalEnricher()
        assert enricher.trace_to_originals(f"cpu{TMP_DIFF_SUFFIX}") == ["cpu"]
        assert enricher.trace_to_originals(f"mem{TMP_RSTD_SUFFIX}10__") == ["mem"]
        assert enricher.trace_to_originals("plain") == []

    def test_narrative_fragment(self):
        enricher = TemporalEnricher()
        narr = enricher.narrative_fragment(f"cpu{TMP_DIFF_SUFFIX}")
        assert "rate of change" in narr.lower()
        assert "cpu" in narr

        narr_rstd = enricher.narrative_fragment(f"mem{TMP_RSTD_SUFFIX}10__")
        assert "volatility" in narr_rstd.lower() or "rolling" in narr_rstd.lower()


# ============================================================================
# EnrichedInfluenceAnalyzer (decorator)
# ============================================================================

class TestEnrichedInfluenceAnalyzer:
    def test_decorator_delegates_and_enriches(self):
        """Enriched analyzer adds columns before delegating."""
        data = pl.DataFrame({
            "timestamp": [1, 1, 2, 2, 3, 3],
            "host": ["h1", "h2", "h1", "h2", "h1", "h2"],
            "metric": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        })
        labels = np.array([0, 0, 1, 1, 1, 1])

        stub = _StubAnalyzer()
        enriched = EnrichedInfluenceAnalyzer(
            inner=stub,
            enrichers=[AggregateEnricher(functions=["max"])],
        )

        factors = enriched.analyze(
            data, labels,
            outcome_col="metric",
            source_columns=["host"],
        )

        # The stub sees extra columns, so it should return more factors
        factor_names = [f.name for f in factors]
        assert len(factors) > 0
        # Synthetic agg column should have been resolved back to "metric"
        enriched_meta = [
            f for f in factors
            if f.metadata and "enriched_from" in f.metadata
        ]
        for f in enriched_meta:
            assert f.metadata["enrichment_narrative"]
            assert f.metadata["original_columns"]

    def test_name_delegates_to_inner(self):
        stub = _StubAnalyzer()
        enriched = EnrichedInfluenceAnalyzer(inner=stub, enrichers=[])
        assert enriched.name == "stub"

    def test_capabilities_adds_enrichment_flag(self):
        stub = _StubAnalyzer()
        no_enrichers = EnrichedInfluenceAnalyzer(inner=stub, enrichers=[])
        assert "enrichment" not in no_enrichers.capabilities

        with_enrichers = EnrichedInfluenceAnalyzer(
            inner=stub, enrichers=[TemporalEnricher()]
        )
        assert with_enrichers.capabilities["enrichment"] is True

    def test_passthrough_without_enrichers(self):
        """With no enrichers, behaves identically to inner analyzer."""
        data = pl.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
        labels = np.array([0, 1, 1])

        stub = _StubAnalyzer()
        enriched = EnrichedInfluenceAnalyzer(inner=stub, enrichers=[])

        plain_factors = stub.analyze(data, labels, outcome_col="b")
        enriched_factors = enriched.analyze(data, labels, outcome_col="b")

        assert len(plain_factors) == len(enriched_factors)
        for pf, ef in zip(plain_factors, enriched_factors):
            assert pf.name == ef.name
            assert pf.strength == ef.strength

    def test_resolve_maps_synthetic_back_to_original(self):
        """Synthetic factor names are resolved back to originals."""
        stub = _StubAnalyzer()
        enricher = AggregateEnricher(functions=["max"])
        enriched_analyzer = EnrichedInfluenceAnalyzer(
            inner=stub, enrichers=[enricher]
        )

        # Simulate: factory returns a synthetic column factor
        synthetic_name = f"cpu{AGG_MAX_SUFFIX}"
        raw = [InfluenceFactor(name=synthetic_name, strength=0.5, rank=1, method="stub")]
        resolved = enriched_analyzer._resolve_factors(raw)

        assert resolved[0].name == "cpu"
        assert resolved[0].metadata["enriched_from"] == synthetic_name

    def test_non_synthetic_factors_pass_through(self):
        """Original column factors are not modified by resolution."""
        stub = _StubAnalyzer()
        enriched_analyzer = EnrichedInfluenceAnalyzer(
            inner=stub, enrichers=[AggregateEnricher()]
        )

        raw = [InfluenceFactor(name="plain_col", strength=0.7, rank=1, method="stub")]
        resolved = enriched_analyzer._resolve_factors(raw)

        assert resolved[0].name == "plain_col"
        assert resolved[0].metadata is None or "enriched_from" not in resolved[0].metadata


# ============================================================================
# create_enrichers_from_settings
# ============================================================================

class TestCreateEnrichersFromSettings:
    def test_auto_with_source_columns(self):
        enrichers = create_enrichers_from_settings(
            settings=None,
            has_source_columns=True,
            has_timestamp=False,
        )
        # By default, auto enables aggregates when sources present
        assert any(isinstance(e, AggregateEnricher) for e in enrichers)
        assert not any(isinstance(e, TemporalEnricher) for e in enrichers)

    def test_auto_with_timestamp(self):
        enrichers = create_enrichers_from_settings(
            settings=None,
            has_source_columns=False,
            has_timestamp=True,
        )
        assert any(isinstance(e, TemporalEnricher) for e in enrichers)
        assert not any(isinstance(e, AggregateEnricher) for e in enrichers)

    def test_auto_with_both(self):
        enrichers = create_enrichers_from_settings(
            settings=None,
            has_source_columns=True,
            has_timestamp=True,
        )
        assert any(isinstance(e, AggregateEnricher) for e in enrichers)
        assert any(isinstance(e, TemporalEnricher) for e in enrichers)
        # Interactions disabled by default
        assert not any(isinstance(e, InteractionEnricher) for e in enrichers)

    def test_interactions_opt_in(self):
        settings = {"profiling.enrichment.interactions.enabled": True}
        enrichers = create_enrichers_from_settings(settings=settings)
        assert any(isinstance(e, InteractionEnricher) for e in enrichers)

    def test_master_disabled(self):
        settings = {"profiling.enrichment.enabled": False}
        enrichers = create_enrichers_from_settings(
            settings=settings,
            has_source_columns=True,
            has_timestamp=True,
        )
        assert enrichers == []

    def test_no_conditions_no_enrichers(self):
        enrichers = create_enrichers_from_settings(
            settings=None,
            has_source_columns=False,
            has_timestamp=False,
        )
        assert enrichers == []

    def test_explicit_enable_overrides_auto(self):
        settings = {
            "profiling.enrichment.aggregates.enabled": True,
        }
        enrichers = create_enrichers_from_settings(
            settings=settings,
            has_source_columns=False,  # no sources, but explicit enabled
        )
        assert any(isinstance(e, AggregateEnricher) for e in enrichers)
