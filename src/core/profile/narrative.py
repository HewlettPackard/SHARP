"""
Narrative generation for influence analysis results.

Provides human-readable text descriptions of influence factors, adapting
content based on available fields (lag, direction, confidence, falsification,
model_assumptions).

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from typing import Any

from src.core.profile.base import InfluenceFactor
from src.core.stats.narrative import format_sig_figs


def generate_influence_narrative(
    factors: list[InfluenceFactor],
    class_names: list[str] | None = None,
    include_model_assumptions: bool = True,
) -> dict[str, str]:
    """
    Generate per-factor narrative summaries for influence factors.

    Returns a dictionary mapping each factor name to its individual narrative string.
    Each narrative includes all available metadata (lag, direction, confidence,
    falsification plan, model assumptions) for that specific factor.

    This design allows flexible UI presentation: tooltips on factor selection dropdown,
    expandable cards, sidebar panels, etc.

    Args:
        factors: List of InfluenceFactor objects ranked by strength
        class_names: Optional class names for context (e.g., ['FAST', 'SLOW'])
        include_model_assumptions: If True, include model assumptions in each narrative

    Returns:
        Dictionary mapping factor name → narrative string. Each narrative is self-contained
        and documents that factor's properties and assumptions independently.
    """
    if not factors:
        return {}

    narratives: dict[str, str] = {}

    for factor in factors:
        narrative_parts = _build_narrative_parts(
            factor=factor,
            class_names=class_names,
            include_model_assumptions=include_model_assumptions,
        )

        narratives[factor.name] = "\n".join(narrative_parts)

    return narratives


def _build_narrative_parts(
    factor: InfluenceFactor,
    class_names: list[str] | None,
    include_model_assumptions: bool,
) -> list[str]:
    parts: list[str] = []
    parts.append(_format_strength(factor))

    lag_part = _format_lag(factor)
    if lag_part:
        parts.append(lag_part)

    direction_part = _format_direction(factor)
    if direction_part:
        parts.append(direction_part)

    confidence_part = _format_confidence(factor)
    if confidence_part:
        parts.append(confidence_part)

    ci_part = _format_confidence_interval(factor)
    if ci_part:
        parts.append(ci_part)

    bayes_part = _format_bayesian_confidence(factor)
    if bayes_part:
        parts.append(bayes_part)

    enrichment_part = _format_enrichment(factor, class_names)
    if enrichment_part:
        parts.append(enrichment_part)

    assumptions_part = _format_assumptions(
        factor=factor,
        include_model_assumptions=include_model_assumptions,
    )
    if assumptions_part:
        parts.append(assumptions_part)

    falsification_part = _format_falsification(factor)
    if falsification_part:
        parts.append(falsification_part)

    return parts


def _format_strength(factor: InfluenceFactor) -> str:
    strength_str = format_sig_figs(factor.strength, sig_figs=3)
    if factor.method in ("ccf", "granger"):
        return f"**Peak correlation**: r = {strength_str}"
    if factor.method == "tree":
        return (
            f"**Importance**: {strength_str} "
            "(unitless relative split importance; higher means more influence in this tree)"
        )
    return f"**Importance**: {strength_str}"


def _format_lag(factor: InfluenceFactor) -> str:
    if factor.lag is not None:
        lag_str = format_sig_figs(abs(factor.lag), sig_figs=2)
        if factor.lag > 0:
            direction = "leads"
        elif factor.lag < 0:
            direction = "lags"
        else:
            direction = "simultaneous with"
        return f"**Lag**: {direction} outcome by ~{lag_str}s"

    if factor.lag_rows is not None and factor.lag_rows != 0:
        rows = abs(factor.lag_rows)
        suffix = "s" if rows != 1 else ""
        return f"**Lag**: {rows} row{suffix}"

    return ""


def _format_direction(factor: InfluenceFactor) -> str:
    if factor.direction and factor.direction.value != "indeterminate":
        return f"**Direction**: {factor.direction.value.title()} causality"
    return ""


def _format_confidence(factor: InfluenceFactor) -> str:
    if factor.p_value is None:
        return ""

    if factor.p_value < 0.001:
        return "**Significance**: p < 0.001"
    if factor.p_value < 0.01:
        return "**Significance**: p < 0.01"
    if factor.p_value < 0.05:
        return "**Significance**: p < 0.05"

    p_str = format_sig_figs(factor.p_value, sig_figs=2)
    return f"**Significance**: p ≈ {p_str}"


def _format_confidence_interval(factor: InfluenceFactor) -> str:
    if factor.confidence_interval is None:
        if factor.method == "tree":
            metadata = factor.metadata or {}
            bootstrap_enabled = bool(metadata.get("bootstrap_ci_enabled", False))
            if bootstrap_enabled:
                return "**95% CI**: unavailable (bootstrap did not produce stable estimates)"
            return ""
        return ""

    ci_low, ci_high = factor.confidence_interval
    ci_low_str = format_sig_figs(ci_low, sig_figs=2)
    ci_high_str = format_sig_figs(ci_high, sig_figs=2)
    return f"**95% CI**: [{ci_low_str}, {ci_high_str}]"


def _format_bayesian_confidence(factor: InfluenceFactor) -> str:
    metadata = factor.metadata or {}
    bayes = metadata.get("bayes_confidence")
    if not isinstance(bayes, dict):
        return ""

    coef = bayes.get("coef_std")
    prob_positive = bayes.get("prob_positive")
    ci95 = bayes.get("ci95")

    if coef is None or prob_positive is None:
        return ""

    coef_str = format_sig_figs(float(coef), sig_figs=3)
    prob_str = format_sig_figs(float(prob_positive), sig_figs=3)

    ci_text = ""
    if isinstance(ci95, tuple) and len(ci95) == 2:
        lo = format_sig_figs(float(ci95[0]), sig_figs=3)
        hi = format_sig_figs(float(ci95[1]), sig_figs=3)
        ci_text = f", 95% credible interval [{lo}, {hi}]"

    mode = bayes.get("mode", "")
    model = bayes.get("model", "")
    model_text = f" ({model})" if model else ""

    return (
        f"**Bayesian confidence{model_text}**: standardized effect = {coef_str}{ci_text}; "
        f"P(effect > 0) = {prob_str} in {mode or 'current'} mode"
    )


def _format_enrichment(factor: InfluenceFactor, class_names: list[str] | None) -> str:
    """
    Format enrichment narrative for synthetic/enriched factors.

    Enriched factors (aggregates, interactions, temporal features) provide
    insights that raw columns alone cannot reveal. The enrichment narrative
    explains what the synthetic column represents and why it's important.

    Args:
        factor: InfluenceFactor with optional enrichment metadata

    Returns:
        Narrative string explaining the enrichment, or empty string if not enriched
    """
    if not factor.metadata:
        return ""

    enrichment_narrative = factor.metadata.get("enrichment_narrative")
    if not enrichment_narrative:
        return ""

    enrichment_narrative = _apply_outcome_effect(enrichment_narrative, factor.metadata, class_names)

    enriched_from = factor.metadata.get("enriched_from")
    if enriched_from:
        return f"**Multi-source insight** (synthetic from {enriched_from}): {enrichment_narrative}"

    return f"**Multi-source insight**: {enrichment_narrative}"


def _apply_worse_label(text: str, class_names: list[str] | None) -> str:
    worse_label = _resolve_worse_label(class_names)
    if not worse_label:
        return text

    replacements = {
        "worse performance": f"{worse_label} performance",
        "slow performance": f"{worse_label} performance",
        "SLOW performance": f"{worse_label} performance",
    }
    for needle, replacement in replacements.items():
        if needle in text:
            text = text.replace(needle, replacement)
    return text


def _apply_outcome_effect(
    text: str,
    metadata: dict[str, Any],
    class_names: list[str] | None,
) -> str:
    effect = metadata.get("enrichment_outcome_effect")
    if not isinstance(effect, str):
        return text

    label = _resolve_effect_label(effect, class_names)
    speed_label = "faster" if effect == "better" else "slower"
    replacements = {
        "worse performance": f"{speed_label} performance",
        "slow performance": f"{speed_label} performance",
        "SLOW performance": f"{speed_label} performance",
        "better performance": f"{speed_label} performance",
        "FAST performance": f"{speed_label} performance",
    }
    for needle, replacement in replacements.items():
        if needle in text:
            text = text.replace(needle, replacement)
    return text


def _resolve_effect_label(effect: str, class_names: list[str] | None) -> str:
    if class_names:
        if effect == "worse":
            for name in class_names:
                if name.lower() == "slow":
                    return name
        if effect == "better":
            for name in class_names:
                if name.lower() == "fast":
                    return name
    return "worse" if effect == "worse" else "better"


def _resolve_worse_label(class_names: list[str] | None) -> str | None:
    if not class_names:
        return None

    for name in class_names:
        if name.lower() == "slow":
            return name

    if len(class_names) == 2:
        for name in class_names:
            if name.lower() == "fast":
                other = class_names[1] if class_names[0] == name else class_names[0]
                return other

    return class_names[-1]


def _format_assumptions(
    factor: InfluenceFactor,
    include_model_assumptions: bool,
) -> str:
    if not include_model_assumptions:
        return ""
    if not factor.metadata or "model_assumptions" not in factor.metadata:
        return ""

    factor_assumptions = factor.metadata["model_assumptions"]
    if isinstance(factor_assumptions, list) and factor_assumptions:
        assumptions_text = "; ".join(factor_assumptions)
        return f"**Assumptions**: {assumptions_text}"

    return ""


def _format_falsification(factor: InfluenceFactor) -> str:
    if factor.falsification_plan is None:
        return ""

    plan_text = _describe_falsification_plan(factor)
    if not plan_text:
        return ""

    return f"**Falsification test**: {plan_text}"


def _describe_falsification_plan(factor: InfluenceFactor) -> str:
    """
    Generate a falsification suggestion from a factor's falsification plan.

    Args:
        factor: InfluenceFactor with falsification_plan

    Returns:
        Narrative string for falsification test
    """
    if not factor.falsification_plan:
        return ""

    plan = factor.falsification_plan
    plan_type = plan.get("type", "unknown")

    if plan_type == "threshold":
        threshold = plan.get("threshold")
        if threshold is not None:
            threshold_str = format_sig_figs(threshold, sig_figs=3)
            return (
                f"Check if {factor.name} > {threshold_str} reliably predicts "
                f"the target outcome. Testing the threshold boundary "
                f"can confirm the causal relationship."
            )

    elif plan_type == "intervention":
        target = plan.get("target_value")
        if target is not None:
            target_str = format_sig_figs(target, sig_figs=3)
            return (
                f"Attempt a controlled intervention setting {factor.name} to {target_str} "
                f"and observe outcome changes. This establishes causality if "
                f"outcome changes as predicted."
            )

    elif plan_type == "correlation":
        min_corr = plan.get("min_correlation", 0.05)
        return (
            f"Verify that {factor.name} maintains correlation ≥ {min_corr} with the outcome "
            f"across different system states. Correlation collapse under state change "
            f"would indicate confounding."
        )

    # Fallback description
    return f"Test {factor.name} to confirm its causal relationship with the outcome."


def generate_factor_badge_narrative(factor: InfluenceFactor) -> str:
    """
    Generate a short badge-style description for inline display.

    Used in GUI to show quick metadata about a factor.

    Args:
        factor: InfluenceFactor

    Returns:
        Short string suitable for display in a badge/label
    """
    badges: list[str] = []

    # Lag badge
    if factor.lag is not None:
        lag_str = format_sig_figs(abs(factor.lag), sig_figs=1)
        direction = "+" if factor.lag > 0 else "-"
        badges.append(f"lag: {direction}{lag_str}s")
    elif factor.lag_rows is not None and factor.lag_rows != 0:
        badges.append(f"lag: {factor.lag_rows}rows")

    # Direction badge
    if factor.direction:
        dir_abbrev = {
            "forward": "→",
            "reverse": "←",
            "bidirectional": "↔",
            "indeterminate": "?",
        }
        badge = dir_abbrev.get(factor.direction.value, "?")
        badges.append(f"dir: {badge}")

    # Significance badge
    if factor.p_value is not None:
        if factor.p_value < 0.001:
            badges.append("p<0.001")
        elif factor.p_value < 0.05:
            badges.append(f"p<0.05")

    # Falsification badge
    if factor.falsification_plan is not None:
        badges.append("falsifiable")

    return " | ".join(badges) if badges else ""


def generate_analytical_assumptions_statement(factors: list[InfluenceFactor]) -> str:
    """
    Generate a statement about analytical assumptions and limitations.

    Used at the end of analysis to help users understand what claims are valid.

    Args:
        factors: List of InfluenceFactor objects analyzed

    Returns:
        Detailed assumptions and limitations statement
    """
    statements: list[str] = []

    # Determine what methods were used
    methods = set()
    has_lag_detection = False
    has_direction = False
    has_uncertainty = False

    for factor in factors:
        if factor.method:
            methods.add(factor.method)
        if factor.lag_rows is not None or factor.lag is not None:
            has_lag_detection = True
        if factor.direction and factor.direction.value != "indeterminate":
            has_direction = True
        if factor.p_value is not None or factor.confidence_interval is not None:
            has_uncertainty = True

    # Method-specific assumptions
    if "tree" in methods:
        statements.append(
            "Tree-based analysis assumes that decision boundaries captured in the "
            "trained model reflect causal effects rather than correlation artifacts."
        )
    if "ccf" in methods:
        statements.append(
            "Cross-correlation analysis detects non-directional associations and temporal lags. "
            "This method cannot establish causation without additional evidence."
        )
    if "granger" in methods:
        statements.append(
            "Granger causality testing assumes stationarity of the input time series. "
            "Non-stationary data may produce spurious results."
        )

    # Lag detection assumptions
    if has_lag_detection:
        statements.append(
            "Lag detection assumes regular, relatively consistent sampling intervals. "
            "Irregular timestamps may affect lag estimates."
        )

    # Direction assumptions
    if has_direction:
        statements.append(
            "Directional claims require additional validation through intervention testing "
            "or domain knowledge, as statistical methods alone cannot rule out hidden confounders."
        )

    # General limitations
    statements.append(
        "This analysis identifies associations in the observed data. "
        "Causal claims require subject matter expertise and intervention testing."
    )

    if statements:
        return "\n".join(f"• {s}" for s in statements)
    return ""
