"""Tests for profile visualizers and analyzer dispatch.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import numpy as np
import polars as pl

from src.core.profile.base import CausalDirection, InfluenceFactor
from src.gui.utils.profile.visualizers import (
    GrangerVisualizer,
    TrainedModelVisualizer,
    build_analysis_narrative_html,
    get_visualizer_for,
)


class _DummyLabeler:
    def get_class_names(self) -> list[str]:
        return ["FAST", "SLOW"]


def _sample_factors() -> list[InfluenceFactor]:
    return [
        InfluenceFactor(
            name="cpu_usage",
            strength=0.82,
            rank=1,
            method="granger",
            direction=CausalDirection.FORWARD,
            p_value=0.0004,
            lag=2.5,
            lag_rows=3,
            falsification_plan={"type": "intervention"},
            metadata={
                "model_assumptions": [
                    "Assumes stationary time series",
                    "Does not control for all confounders",
                ]
            },
        ),
        InfluenceFactor(
            name="page_faults",
            strength=0.43,
            rank=2,
            method="granger",
            direction=CausalDirection.REVERSE,
            p_value=0.02,
            lag=1.0,
            lag_rows=1,
            falsification_plan={"type": "warning"},
            metadata={"model_assumptions": ["Does not establish true causation"]},
        ),
    ]


class TestVisualizerFactory:
    def test_get_visualizer_for_granger(self):
        visualizer = get_visualizer_for(
            analyzer_name="granger",
            tree=None,
            metric_col="latency",
            labeler=_DummyLabeler(),
        )
        assert isinstance(visualizer, GrangerVisualizer)

    def test_get_visualizer_for_model_default(self):
        visualizer = get_visualizer_for(
            analyzer_name="model",
            tree=None,
            metric_col="latency",
            labeler=_DummyLabeler(),
        )
        assert isinstance(visualizer, TrainedModelVisualizer)


class TestGrangerVisualizer:
    def test_generate_narrative_structure(self):
        visualizer = GrangerVisualizer()
        narrative = visualizer.generate_narrative(_sample_factors(), ["FAST", "SLOW"])

        assert isinstance(narrative, dict)
        assert "cpu_usage" in narrative
        assert "page_faults" in narrative
        assert "**Significance**" in narrative["cpu_usage"]
        assert "**Assumptions**" in narrative["cpu_usage"]
        assert "**Falsification test**" in narrative["cpu_usage"]

    def test_render_primary_returns_ui_tag(self):
        visualizer = GrangerVisualizer()
        data = pl.DataFrame({"cpu_usage": [1.0, 2.0], "latency": [10.0, 12.0]})
        labels = np.array([0, 1])

        content = visualizer.render_primary(
            factors=_sample_factors(),
            data=data,
            labels=labels,
            class_names=["FAST", "SLOW"],
            class_colors=[],
        )
        assert content is not None


class TestNarrativeHtmlBuilder:
    def test_selected_factor_narrative_html(self):
        narrative_map = {
            "cpu_usage": "**Correlation**: 0.82\n**Significance**: p < 0.001",
            "page_faults": "**Importance**: 0.43",
        }
        html = build_analysis_narrative_html(narrative_map, selected_factor="cpu_usage")

        assert "Correlation" in html
        assert "Significance" in html

    def test_multi_factor_narrative_html(self):
        narrative_map = {
            "a": "**Strength**: 0.8",
            "b": "**Strength**: 0.7",
        }
        html = build_analysis_narrative_html(narrative_map, selected_factor=None)

        assert "<ul" in html
        assert "<li>" in html
        assert "a" in html
        assert "b" in html
