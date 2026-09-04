"""Analyzer-specific visualizers for the Profile tab.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import re
from typing import Any

import numpy as np
import polars as pl
from shiny import ui

from src.core.profile.base import AnalyzerVisualizer, CausalDirection, InfluenceFactor
from src.core.profile.narrative import generate_influence_narrative
from src.gui.utils.profile.tree import render_tree_for_ui


class TrainedModelVisualizer(AnalyzerVisualizer):
    """Visualizer for trained-model analyzers (currently tree-only)."""

    def __init__(
        self,
        tree: Any | None,
        metric_col: str,
        labeler: Any,
    ) -> None:
        self._tree = tree
        self._metric_col = metric_col
        self._labeler = labeler

    def render_primary(
        self,
        factors: list[InfluenceFactor],
        data: pl.DataFrame,
        labels: np.ndarray,
        class_names: list[str],
        class_colors: list[str],
    ) -> ui.TagChild:
        if self._tree is not None:
            return ui.HTML(
                render_tree_for_ui(
                    tree=self._tree,
                    data=data,
                    metric_col=self._metric_col,
                    labeler=self._labeler,
                )
            )

        return ui.p(
            "Visualization for this model type is not yet implemented.",
            style="color: #999; padding: 10px; font-style: italic;",
        )

    def generate_narrative(
        self,
        factors: list[InfluenceFactor],
        class_names: list[str],
    ) -> dict[str, str]:
        return generate_influence_narrative(factors, class_names=class_names)


def _render_factor_list(
    title: str,
    subtitle: str,
    factors: list[InfluenceFactor],
    row_fn: Any,
) -> ui.TagChild:
    """Shared helper: render a titled sorted factor list."""
    if not factors:
        return ui.p("No factors available", style="color: #999; padding: 10px;")
    rows = [row_fn(f) for f in factors[:10]]
    return ui.card(
        ui.tags.p(title, style="font-weight: 600; margin-bottom: 2px;"),
        ui.tags.p(subtitle, style="color: #666; font-size: 0.85em; margin-bottom: 8px;"),
        ui.tags.ul(*rows, style="margin: 0; padding-left: 20px;"),
        style="padding: 10px; height: 100%; overflow: auto;",
    )


class GrangerVisualizer(AnalyzerVisualizer):
    """Visualizer for Granger direction analysis."""

    def render_primary(
        self,
        factors: list[InfluenceFactor],
        data: pl.DataFrame,
        labels: np.ndarray,
        class_names: list[str],
        class_colors: list[str],
    ) -> ui.TagChild:
        def row(factor: InfluenceFactor) -> ui.TagChild:
            arrow = _direction_symbol(factor.direction)
            corr_text = f"r = {factor.strength:.3f}"
            p_text = ""
            if factor.p_value is not None:
                p_text = " (p < 0.001)" if factor.p_value < 0.001 else f" (p = {factor.p_value:.3f})"
            lag_text = ""
            if factor.lag is not None:
                lag_text = f", lag {factor.lag:.2f}s"
            elif factor.lag_rows is not None:
                lag_text = f", lag {factor.lag_rows} rows"
            return ui.tags.li(
                f"{factor.name} {arrow} {corr_text}{lag_text}{p_text}",
                style="margin-bottom: 4px;",
            )

        return _render_factor_list(
            "Granger causality summary",
            "Tests whether past values of each predictor help forecast the outcome, "
            "determining causal direction and temporal lag. Sorted by forward Granger F-statistic.",
            factors,
            row,
        )

    def generate_narrative(
        self,
        factors: list[InfluenceFactor],
        class_names: list[str],
    ) -> dict[str, str]:
        return generate_influence_narrative(factors, class_names=class_names)


class CCFVisualizer(AnalyzerVisualizer):
    """Visualizer for lagged cross-correlation analysis."""

    def render_primary(
        self,
        factors: list[InfluenceFactor],
        data: pl.DataFrame,
        labels: np.ndarray,
        class_names: list[str],
        class_colors: list[str],
    ) -> ui.TagChild:
        def row(factor: InfluenceFactor) -> ui.TagChild:
            strength_text = f"r = {factor.strength:.3f}"
            lag_text = ""
            if factor.lag is not None:
                lag_text = f", lag {factor.lag:.2f}s"
            elif factor.lag_rows is not None:
                lag_text = f", lag {factor.lag_rows} rows"
            p_text = ""
            if factor.p_value is not None:
                p_text = " (p < 0.001)" if factor.p_value < 0.001 else f" (p = {factor.p_value:.3f})"
            ci_text = ""
            if factor.confidence_interval is not None:
                lo, hi = factor.confidence_interval
                ci_text = f" [95% CI: {lo:.3f}, {hi:.3f}]"
            return ui.tags.li(
                f"{factor.name}: {strength_text}{lag_text}{p_text}{ci_text}",
                style="margin-bottom: 4px;",
            )

        return _render_factor_list(
            "Lagged cross-correlation summary",
            "Measures the peak correlation between each predictor and the outcome "
            "across different time lags.",
            factors,
            row,
        )

    def generate_narrative(
        self,
        factors: list[InfluenceFactor],
        class_names: list[str],
    ) -> dict[str, str]:
        return generate_influence_narrative(factors, class_names=class_names)


class PCMCIVisualizer(AnalyzerVisualizer):
    """Visualizer for PCMCI causal graph discovery."""

    def render_primary(
        self,
        factors: list[InfluenceFactor],
        data: pl.DataFrame,
        labels: np.ndarray,
        class_names: list[str],
        class_colors: list[str],
    ) -> ui.TagChild:
        """Render causal DAG with edge confidence coloring."""
        def row(factor: InfluenceFactor) -> ui.TagChild:
            arrow = "→"
            strength_text = f"r = {factor.strength:.3f}"
            p_text = ""
            if factor.p_value is not None:
                p_text = " (p < 0.001)" if factor.p_value < 0.001 else f" (p = {factor.p_value:.3f})"

            # Edge type annotation - find confounding variables if v-structure
            edge_type = factor.metadata.get("edge_type", "causal_parent")
            edge_label = ""
            if edge_type == "v_structure":
                # Find which other variables are in the v-structure with this factor
                # v_structures are (A, B, C) tuples meaning A→B←C
                v_structures = factor.metadata.get("full_causal_graph", {}).get("v_structures", [])
                confounders = []
                for (a, b, c) in v_structures:
                    # Check if this factor is involved in the v-structure
                    if a == factor.name:
                        # Factor is A in A→B←C, so C is the confounder
                        confounders.append(c)
                    elif c == factor.name:
                        # Factor is C in A→B←C, so A is the confounder
                        confounders.append(a)

                if confounders:
                    confounders_str = ", ".join(confounders)
                    edge_label = f" [v-structure with {confounders_str}]"
                else:
                    edge_label = " [v-structure]"

            # Confidence color (use proper None check - p_value can be 0.0 for very strong correlations)
            confidence = 1.0 - (factor.p_value if factor.p_value is not None else 1.0)
            color = "green" if confidence > 0.95 else "orange" if confidence > 0.90 else "gray"

            return ui.tags.li(
                ui.tags.span(
                    f"{factor.name} {arrow} outcome: {strength_text}{p_text}{edge_label}",
                    style=f"color: {color}; font-weight: {'bold' if confidence > 0.95 else 'normal'};",
                ),
                style="margin-bottom: 4px;",
            )

        return _render_factor_list(
            "Causal graph (PCMCI)",
            "Direct causal parents of the outcome, sorted by statistical significance (p-value). "
            "Confidence indicated by color (green=high, orange=moderate). "
            "V-structures [marked in brackets] indicate potential confounders.",
            factors,
            row,
        )

    def generate_narrative(
        self,
        factors: list[InfluenceFactor],
        class_names: list[str],
    ) -> dict[str, str]:
        narratives = {}
        for factor in factors:
            edge_type = factor.metadata.get("edge_type", "causal_parent")
            is_confounded = factor.metadata.get("is_confounded", False)

            parts = [
                f"{factor.name} is a direct causal parent of the outcome "
                f"(causal strength r={factor.strength:.3f}, p={factor.p_value:.3f})."
            ]

            if is_confounded:
                # Find which other variables are in the v-structure
                # v_structures are (A, B, C) tuples meaning A→B←C
                v_structures = factor.metadata.get("full_causal_graph", {}).get("v_structures", [])
                confounders = []
                for (a, b, c) in v_structures:
                    if a == factor.name:
                        # Factor is A in A→B←C, so C is the confounder
                        confounders.append((b, c))  # Store both middle and third for explanation
                    elif c == factor.name:
                        # Factor is C in A→B←C, so A is the confounder
                        confounders.append((b, a))

                if confounders:
                    # Take first v-structure for explanation
                    middle, other = confounders[0]
                    parts.append(
                        f"**V-structure detected**: Both {factor.name} and {other} "
                        f"independently influence {middle}, forming a '{factor.name}→{middle}←{other}' pattern. "
                        "This indicates these factors have independent causal pathways to the same target."
                    )
                else:
                    parts.append("**Confounding detected**: This factor appears in a v-structure "
                                "(A→B←C pattern), indicating potential confounding relationships.")

            if factor.p_value and factor.p_value < 0.05:
                parts.append("This causal edge is statistically significant (p < 0.05).")
            else:
                parts.append("Note: p-value suggests caution in causal claims.")

            bayes = (factor.metadata or {}).get("bayes_confidence") if factor.metadata else None
            if isinstance(bayes, dict):
                prob = bayes.get("prob_positive")
                ci95 = bayes.get("ci95")
                if prob is not None:
                    if isinstance(ci95, tuple) and len(ci95) == 2:
                        parts.append(
                            f"Bayesian confidence: P(effect > 0)={float(prob):.3f}, "
                            f"95% credible interval [{float(ci95[0]):.3f}, {float(ci95[1]):.3f}]."
                        )
                    else:
                        parts.append(f"Bayesian confidence: P(effect > 0)={float(prob):.3f}.")

            narratives[factor.name] = " ".join(parts)

        return narratives


class TransferEntropyVisualizer(AnalyzerVisualizer):
    """Visualizer for Transfer Entropy direction analysis."""

    #: Classification-mode caveat shown at the top of the factor list.
    _CLASSIFICATION_CAVEAT = (
        "⚠ Classification mode: Transfer Entropy is optimized for continuous "
        "outcomes (regression). In classification mode it measures information "
        "flow toward the raw metric, not toward the class boundary. "
        "For independent benchmark runs (little/no temporal dependence), "
        "directional TE can be weak or hard to interpret. "
        "Results are still valid as a complementary signal, but consider "
        "Granger or Tree for direct class-boundary analysis."
    )

    def render_primary(
        self,
        factors: list[InfluenceFactor],
        data: pl.DataFrame,
        labels: np.ndarray,
        class_names: list[str],
        class_colors: list[str],
    ) -> ui.TagChild:
        # Detect classification mode: ≥2 class names means classification.
        is_classification = len(class_names) >= 2

        def row(factor: InfluenceFactor) -> ui.TagChild:
            arrow = _direction_symbol(factor.direction)
            strength_text = f"s = {factor.strength:.3f}"
            meta = factor.metadata or {}
            te_fwd = meta.get("te_forward_nats")
            te_rev = meta.get("te_reverse_nats")
            te_text = ""
            if te_fwd is not None and te_rev is not None:
                te_text = f" (TE\u2191={te_fwd:.3f} nat, TE\u2193={te_rev:.3f} nat)"
            elif te_fwd is not None:
                te_text = f" (TE={te_fwd:.3f} nat)"
            p_text = ""
            if factor.p_value is not None:
                p_text = " (p < 0.001)" if factor.p_value < 0.001 else f" (p = {factor.p_value:.3f})"
            return ui.tags.li(
                f"{factor.name} {arrow} {strength_text}{te_text}{p_text}",
                style="margin-bottom: 4px;",
            )

        if not factors:
            return ui.card(
                ui.tags.p(
                    "Transfer Entropy summary",
                    style="font-weight: 600; margin-bottom: 2px;",
                ),
                ui.tags.p(
                    "⚠ Transfer Entropy was not run for this data. "
                    "TE is only enabled for regression with a continuous outcome "
                    "and detectable temporal dependence. "
                    "These runs may be temporally independent — e.g., repeated "
                    "independent benchmarks where run\u00a0t has no causal "
                    "effect on run\u00a0t+1 — or the analysis may be in classification mode. "
                    "In these cases TE is skipped to avoid polluting rankings. "
                    "Consider Granger, Hybrid, or Tree for this dataset.",
                    style="color: #666; font-size: 0.85em;",
                ),
                style="padding: 10px; height: 100%; overflow: auto;",
            )

        rows = [row(f) for f in factors[:10]]

        elements: list[ui.TagChild] = [
            ui.tags.p(
                "Transfer Entropy summary",
                style="font-weight: 600; margin-bottom: 2px;",
            ),
            ui.tags.p(
                "Measures directed information flow (Schreiber, 2000) via a nonparametric "
                "KSG estimator. Strength s = 1 \u2212 e\u207b\u1d40\u1d31; TE values in nats. "
                "Direction: \u2192 means factor\u2192outcome, \u2190 means outcome\u2192factor, "
                "\u2194 means bidirectional; TE\u2191 and TE\u2193 use the same convention.",
                style="color: #666; font-size: 0.85em; margin-bottom: 8px;",
            ),
        ]

        if is_classification:
            elements.append(
                ui.tags.p(
                    self._CLASSIFICATION_CAVEAT,
                    style=(
                        "color: #856404; background: #fff3cd; border: 1px solid #ffc107; "
                        "border-radius: 4px; padding: 6px 10px; font-size: 0.82em; "
                        "margin-bottom: 8px;"
                    ),
                )
            )

        elements.append(
            ui.tags.ul(*rows, style="margin: 0; padding-left: 20px;")
        )

        return ui.card(
            *elements,
            style="padding: 10px; height: 100%; overflow: auto;",
        )

    def generate_narrative(
        self,
        factors: list[InfluenceFactor],
        class_names: list[str],
    ) -> dict[str, str]:
        return generate_influence_narrative(factors, class_names=class_names)


class ConsensusVisualizer(AnalyzerVisualizer):
    """Visualizer for the consensus (wRRF) analyzer.

    Renders an agreement table: one row per top factor, one column per
    component analyzer.  Each cell shows the rank the analyzer assigned to
    that factor (green for top-3, lighter shades for lower ranks, dash when
    absent).

    Column names and labels are derived from the ``consensus_votes`` metadata
    stored on each factor, so the table automatically reflects whatever
    analyzers the consensus actually ran — no hard-coded list needed.
    """

    @staticmethod
    def _rank_cell_style(rank: int | None) -> str:
        """Return inline CSS for a rank cell."""
        if rank is None:
            return "background:#f5f5f5; color:#bbb; text-align:center;"
        if rank <= 3:
            return "background:#c8f0c8; color:#1a6b1a; font-weight:bold; text-align:center;"
        if rank <= 7:
            return "background:#e8f5e8; color:#2a5f2a; text-align:center;"
        return "background:#f8f8f8; color:#555; text-align:center;"

    @staticmethod
    def _col_labels(columns: list[str]) -> dict[str, str]:
        """Return display labels for each analyzer name, sourced from the registry."""
        from src.core.profile.analyzers.registry import create_analyzer_registry
        registry = create_analyzer_registry()
        return {
            name: (registry.get_analyzer(name).label if registry.get_analyzer(name) else name.title())
            for name in columns
        }

    def render_primary(
        self,
        factors: list[InfluenceFactor],
        data: pl.DataFrame,
        labels: np.ndarray,
        class_names: list[str],
        class_colors: list[str],
    ) -> ui.TagChild:
        if not factors:
            return ui.p("No consensus factors available.", style="color:#999; padding:10px;")

        # Derive the column set from the votes actually present in the data.
        vote_keys: list[str] = []
        seen: set[str] = set()
        for factor in factors[:20]:
            for key in (factor.metadata or {}).get("consensus_votes", {}):
                if key not in seen:
                    seen.add(key)
                    vote_keys.append(key)
        columns = vote_keys
        col_labels = self._col_labels(columns)

        col_style = "padding:4px 8px; border:1px solid #ddd; white-space:nowrap;"
        header_style = (
            "padding:4px 8px; border:1px solid #ddd; background:#f0f0f0; "
            "font-weight:600; white-space:nowrap; text-align:center;"
        )

        # Header row.
        header_cells = [
            ui.tags.th("Factor", style=header_style + " text-align:left;"),
            ui.tags.th("Agreement", style=header_style),
        ]
        for col in columns:
            header_cells.append(
                ui.tags.th(col_labels[col], style=header_style)
            )

        # Data rows (top 20 factors).
        rows: list[ui.TagChild] = []
        for factor in factors[:20]:
            votes: dict[str, Any] = (factor.metadata or {}).get("consensus_votes", {})
            agreement: int = (factor.metadata or {}).get("agreement", 0)

            cells = [
                ui.tags.td(factor.name, style=col_style),
                ui.tags.td(
                    f"{agreement}/{len(columns)}",
                    style=col_style + " text-align:center; font-weight:600;",
                ),
            ]
            for col in columns:
                vote_info = votes.get(col)
                rank = vote_info["rank"] if vote_info else None
                display = str(rank) if rank is not None else "—"
                cells.append(
                    ui.tags.td(display, style=self._rank_cell_style(rank))
                )
            rows.append(ui.tags.tr(*cells))

        table = ui.tags.table(
            ui.tags.thead(ui.tags.tr(*header_cells)),
            ui.tags.tbody(*rows),
            style=(
                "border-collapse:collapse; width:100%; font-size:0.88em; "
                "font-family: monospace;"
            ),
        )

        return ui.card(
            ui.tags.p(
                "Consensus ranking (all analyzers)",
                style="font-weight:600; margin-bottom:2px;",
            ),
            ui.tags.p(
                "Factors are ranked by Weighted RRF across all analyzers. "
                "Numbers show rank position per analyzer; — = not ranked. "
                "Green = top 3.",
                style="color:#666; font-size:0.85em; margin-bottom:8px;",
            ),
            table,
            style="padding:10px; height:100%; overflow:auto;",
        )

    def generate_narrative(
        self,
        factors: list[InfluenceFactor],
        class_names: list[str],
    ) -> dict[str, str]:
        return generate_influence_narrative(factors, class_names=class_names)


def get_visualizer_for(
    analyzer_name: str,
    tree: Any | None,
    metric_col: str,
    labeler: Any,
) -> AnalyzerVisualizer:
    """Factory for analyzer visualizers."""
    if analyzer_name == "granger":
        return GrangerVisualizer()
    if analyzer_name == "hybrid":
        # Hybrid reuses Granger's visualizer since it's based on Granger causality
        # with additional confounding control (not reflected in visualization)
        return GrangerVisualizer()
    if analyzer_name == "pcmci":
        return PCMCIVisualizer()
    if analyzer_name == "ccf":
        return CCFVisualizer()
    if analyzer_name == "te":
        return TransferEntropyVisualizer()
    if analyzer_name == "consensus":
        return ConsensusVisualizer()
    return TrainedModelVisualizer(tree=tree, metric_col=metric_col, labeler=labeler)


def _markdown_to_html(text: str) -> str:
    """Convert simple markdown (bold, newlines) to inline HTML."""
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    html = html.replace("\n", "<br>")
    return html


def build_analysis_narrative_html(
    narrative_map: dict[str, str],
    selected_factor: str | None,
) -> str:
    """Build HTML for analysis narrative panel."""
    if not narrative_map:
        return "<p style='color:#999;'>No narrative available.</p>"

    if selected_factor and selected_factor in narrative_map:
        text = narrative_map[selected_factor]
        html = _markdown_to_html(text)
        return f"<p style='margin: 0;'>{html}</p>"

    items = []
    for factor_name, text in list(narrative_map.items())[:5]:
        html = _markdown_to_html(text)
        items.append(f"<li><strong>{factor_name}</strong><br>{html}</li>")

    return "<ul style='padding-left: 18px; margin-bottom: 0;'>" + "".join(items) + "</ul>"


def _direction_symbol(direction: CausalDirection | None) -> str:
    if direction == CausalDirection.FORWARD:
        return "→"
    if direction == CausalDirection.REVERSE:
        return "←"
    if direction == CausalDirection.BIDIRECTIONAL:
        return "↔"
    return "?"
