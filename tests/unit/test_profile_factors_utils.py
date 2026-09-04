"""Tests for profile factor UI helpers."""

from src.core.profile.base import InfluenceFactor
from src.gui.utils.profile.factors import factor_label


class TestFactorLabel:
    def test_enriched_factor_always_shows_source_suffix(self):
        factor = InfluenceFactor(
            name="Avg_msec_per_Transfer",
            strength=0.42,
            metadata={"enriched_from": "Avg_msec_per_Transfer__tmp_diff__"},
        )

        label = factor_label(factor, {"Avg_msec_per_Transfer": 1})

        assert "__tmp_diff__" in label
        assert "from" in label
