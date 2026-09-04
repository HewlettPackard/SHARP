"""
Helpers for computing profile analysis results.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from dataclasses import replace
from typing import Any

import numpy as np
import polars as pl

from src.core.config.settings import Settings
from src.core.profile.analyzers import TreeInfluenceAnalyzer
from src.core.profile.base import InfluenceFactor, QualityResult
from src.core.profile.data_reduction import reduce_rows
from src.core.profile.analyzers.registry import create_analyzer_registry
from src.core.profile.labeler import PerformanceLabeler
from src.core.stats.bayes_confidence import estimate_bayes_confidence_for_columns
from src.gui.utils.profile.predictor_stats import get_auto_excluded_predictors

# Bootstrap CI sample size determination
BOOTSTRAP_CI_LARGE_DATASET_THRESHOLD = 1000
BOOTSTRAP_CI_SAMPLES_LARGE = 50
BOOTSTRAP_CI_SAMPLES_SMALL = 200


def resolve_analysis_limits(
    modal_filters: dict[str, Any] | None,
    settings: Settings,
) -> tuple[int, float]:
    """Resolve predictor selection limits using modal filters or defaults."""
    max_predictors = modal_filters.get("max_predictors") if modal_filters else None
    max_correlation = modal_filters.get("max_corr") if modal_filters else None

    if max_predictors is None:
        max_predictors = settings.get("profiling.max_predictors", 100)
    if max_correlation is None:
        max_correlation = settings.get("profiling.max_correlation", 0.99)

    return int(max_predictors), float(max_correlation)


def merge_auto_exclusions(
    current_exclusions: list[str],
    predictor_stats: list[dict[str, Any]] | None,
    max_correlation: float,
) -> list[str]:
    """Combine current exclusions with auto-excluded predictors."""
    if not predictor_stats:
        return list(current_exclusions)

    auto_excluded = get_auto_excluded_predictors(predictor_stats, max_correlation)
    return list(set(current_exclusions) | auto_excluded)


def prepare_analysis_data(
    data: pl.DataFrame,
    metric_col: str,
    current_exclusions: list[str],
    labeler: PerformanceLabeler,
    settings: Settings,
    outcome_mode: str,
) -> tuple[pl.DataFrame, np.ndarray, np.ndarray, list[str]] | None:
    """Prepare filtered data and labels for analysis."""
    predictor_cols = [
        c for c in data.columns if c != metric_col and c not in current_exclusions
    ]
    row_reduced = reduce_rows(data, metric_col, predictor_cols)

    valid_mask = row_reduced[metric_col].is_not_null()
    valid_data = row_reduced.filter(valid_mask)

    if len(valid_data) < 3:
        return None

    target_rows = settings.get("profiling.tree_training.target_rows", 1000)
    if len(valid_data) > target_rows:
        sample_indices = np.random.choice(len(valid_data), size=target_rows, replace=False)
        valid_data = valid_data[sorted(sample_indices)]

    metric_values = valid_data[metric_col].to_numpy()
    labels = labeler.label(metric_values)
    class_names = labeler.get_class_names()

    # Regression mode: labels are already continuous floats
    if outcome_mode == "regression":
        numeric_labels = labels.astype(float)
        return valid_data, labels, numeric_labels, class_names

    if labels.dtype.kind in ("U", "S", "O"):
        label_to_int = {label: i for i, label in enumerate(class_names)}
        numeric_labels = np.array([label_to_int[label] for label in labels])
    else:
        numeric_labels = labels.astype(int)

    return valid_data, labels, numeric_labels, class_names


def run_influence_analysis(
    data: pl.DataFrame,
    numeric_labels: np.ndarray,
    settings: Settings,
    metric_col: str,
    current_exclusions: list[str],
    max_predictors: int,
    max_correlation: float,
    analyzer_name: str | None = None,
    outcome_mode: str = "classification",
    lower_is_better: bool | None = None,
    progress_callback: Any = None,
) -> tuple[list[InfluenceFactor], str, Any | None, str | None]:
    """Run the configured influence analyzer and return factors + analyzer.

    Returns:
        Tuple of (factors, used_analyzer_name, analyzer_instance, fallback_warning).
        ``fallback_warning`` is a human-readable message when the requested
        analyzer failed and the tree analyzer was used as a fallback, or None
        when the requested analyzer succeeded.
    """
    registry = create_analyzer_registry(settings)
    registry.set_shared_state(
        data,
        numeric_labels,
        settings=settings,
        outcome_col=metric_col,
        context={
            "exclude_cols": current_exclusions,
            "max_predictors": max_predictors,
            "max_correlation": max_correlation,
            "outcome_mode": outcome_mode,
            "lower_is_better": lower_is_better,
            "progress_callback": progress_callback,
        },
    )
    analyzer_name = analyzer_name or settings.get("profiling.influence_analyzer", "tree")

    fallback_warning: str | None = None
    try:
        factors = registry.analyze_single(analyzer_name)
    except Exception as exc:
        # If the preferred analyzer fails and it is not already the tree
        # fallback, retry with the tree analyzer so the user still gets results.
        if analyzer_name != "tree":
            import traceback
            traceback.print_exc()
            analyzer_label = registry.get_analyzer(analyzer_name)
            label = getattr(analyzer_label, "label", analyzer_name) if analyzer_label else analyzer_name
            fallback_warning = (
                f"{label} analysis failed ({type(exc).__name__}: {exc}). "
                "Showing Decision tree results instead."
            )
            factors = registry.analyze_single("tree")
            analyzer_name = "tree"
        else:
            raise

    used_name = registry.last_analyzer_name or analyzer_name
    analyzer = registry.get_analyzer(used_name)
    return factors, used_name, analyzer, fallback_warning


def enrich_factors_with_bayesian_confidence(
    factors: list[InfluenceFactor],
    data: pl.DataFrame,
    outcome: np.ndarray,
    outcome_mode: str,
    max_factors: int = 20,
) -> list[InfluenceFactor]:
    """Attach Bayesian confidence metadata to factors.

    This keeps the profile server logic concise by isolating:
    1) factor->column resolution
    2) Bayes stats estimation
    3) metadata merge back into factors
    """
    if not factors or data is None or data.is_empty():
        return factors

    bayes_columns = _resolve_bayes_columns(factors, data, max_factors)
    bayes_stats = estimate_bayes_confidence_for_columns(
        data=data,
        outcome=outcome,
        outcome_mode=outcome_mode,
        columns=bayes_columns,
        max_columns=max_factors,
    )

    if not bayes_stats:
        return factors

    enriched: list[InfluenceFactor] = []
    for factor in factors:
        metadata = dict(factor.metadata or {})
        target_name = _resolve_factor_data_column(factor, data)
        effect = bayes_stats.get(target_name) if target_name else None

        if effect is not None:
            metadata["bayes_confidence"] = effect
            enriched.append(replace(factor, metadata=metadata))
        else:
            enriched.append(factor)

    return enriched


def compute_factor_quality(
    factors: list[InfluenceFactor],
    data: pl.DataFrame,
    labels: np.ndarray,
    metric_col: str | None,
    outcome_mode: str,
    analyzer: Any,
    top_k: int = 20,
    n_folds: int = 5,
) -> QualityResult | None:
    """Evaluate the cross-validated predictive quality of an analyzer's factors.

    Thin wrapper that calls :meth:`InfluenceAnalyzer.evaluate_quality` via the
    concrete analyzer instance, centralising error handling and fall-through
    to allow the caller (profile server) to stay simple.

    Args:
        factors: Ranked factors returned by the analyzer.
        data: Prepared analysis data (same as what was passed to the analyzer).
        labels: Numeric labels/outcome values.
        metric_col: Continuous outcome column name (used in regression mode).
        outcome_mode: ``"classification"`` or ``"regression"``.
        analyzer: Concrete :class:`InfluenceAnalyzer` instance (or enriched wrapper).
        top_k: Maximum number of top factors to evaluate.
        n_folds: Number of CV folds.

    Returns:
        :class:`QualityResult` or ``None`` if evaluation is not possible.
    """
    if analyzer is None or not factors or data is None or data.is_empty():
        return None
    try:
        return analyzer.evaluate_quality(
            factors=factors,
            data=data,
            labels=labels,
            outcome_col=metric_col,
            outcome_mode=outcome_mode,
            n_folds=n_folds,
            top_k=top_k,
        )
    except Exception:
        import traceback
        traceback.print_exc()
        return None


def _resolve_bayes_columns(
    factors: list[InfluenceFactor],
    data: pl.DataFrame,
    max_factors: int,
) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()

    for factor in factors[:max_factors]:
        column_name = _resolve_factor_data_column(factor, data)
        if column_name and column_name not in seen:
            seen.add(column_name)
            columns.append(column_name)

    return columns


def _resolve_factor_data_column(
    factor: InfluenceFactor,
    data: pl.DataFrame,
) -> str | None:
    if factor.name in data.columns:
        return factor.name

    metadata = factor.metadata or {}
    original_name = metadata.get("original_name")
    if isinstance(original_name, str) and original_name in data.columns:
        return original_name

    encoded_name = metadata.get("encoded_name")
    if isinstance(encoded_name, str) and "=" in encoded_name:
        base = encoded_name.split("=", 1)[0]
        if base in data.columns:
            return base

    return None


def get_bootstrap_ci_sample_count(n_rows: int) -> int:
    """Determine bootstrap sample count based on dataset size.

    Larger datasets (>1000 rows) use fewer samples for speed.
    Smaller datasets use more samples for robustness.
    """
    if n_rows > BOOTSTRAP_CI_LARGE_DATASET_THRESHOLD:
        return BOOTSTRAP_CI_SAMPLES_LARGE
    return BOOTSTRAP_CI_SAMPLES_SMALL


def compute_tree_factor_bootstrap_ci(
    analyzer: Any,
    data: pl.DataFrame,
    labels: np.ndarray,
    selected_factor: InfluenceFactor,
    exclude_cols: list[str],
    max_predictors: int,
    max_correlation: float,
    progress_callback: Any | None = None,
) -> tuple[float, float] | None:
    """Compute bootstrap CI for one selected tree factor on demand."""
    if data is None or data.is_empty() or len(labels) < 3:
        return None

    # Handle both TreeInfluenceAnalyzer and wrapped analyzers
    from src.core.profile.column_enrichment import EnrichedInfluenceAnalyzer

    # Determine if we have an enriched analyzer and extract the inner tree analyzer
    is_enriched = False
    actual_analyzer = analyzer

    if isinstance(analyzer, EnrichedInfluenceAnalyzer):
        is_enriched = True
        inner = analyzer.inner
        if not isinstance(inner, TreeInfluenceAnalyzer):
            return None
        actual_analyzer = inner
    elif not isinstance(analyzer, TreeInfluenceAnalyzer):
        return None

    trained = analyzer.trained_model
    if trained is None:
        return None

    metadata = selected_factor.metadata or {}
    encoded_name = metadata.get("encoded_name")
    if not isinstance(encoded_name, str) or not encoded_name:
        encoded_name = selected_factor.name

    # If the analyzer is enriched, we need to use the enriched data
    # The trained model was trained on enriched features, so bootstrap samples
    # must also use enriched features
    data_for_bootstrap = data
    if is_enriched:
        # Re-enrich the data using the same enrichers that were used during analysis
        # This ensures bootstrap samples have the same enriched features
        settings = Settings()
        # Detect source columns and re-create enrichers
        enrichers = analyzer._create_enrichers_for_data(data, settings, {})

        # Extract source info
        source_cols = analyzer._extract_source_columns(data, settings, {})
        sem_groups = analyzer._extract_semantic_groups(settings, {})

        # Enrich the data
        data_for_bootstrap = data
        for enricher in enrichers:
            data_for_bootstrap = enricher.enrich(
                data_for_bootstrap,
                exclude_cols=exclude_cols,
                source_columns=source_cols,
                semantic_groups=sem_groups,
            )

    n_samples = get_bootstrap_ci_sample_count(len(data))

    ci_map = actual_analyzer._bootstrap_ci(
        data=data_for_bootstrap,
        labels=labels,
        trained_model=trained,
        exclude_cols=exclude_cols,
        max_predictors=max_predictors,
        max_correlation=max_correlation,
        n_samples=n_samples,
        feature_names=[encoded_name],
        progress_callback=progress_callback,
    )
    return ci_map.get(encoded_name)
