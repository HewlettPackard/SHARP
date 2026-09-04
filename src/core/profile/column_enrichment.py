"""
Enrichment decorator for influence analyzers.

Provides automatic synthetic column generation from base predictors,
including aggregates, temporal derivatives, and pairwise interactions.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Any

import numpy as np
import polars as pl

from src.core.profile.base import LABEL_OUTCOME_COL, InfluenceAnalyzer, InfluenceFactor
from src.core.profile.data_model import detect_source_columns

# Synthetic column naming suffixes and infixes
AGG_MAX_SUFFIX = "__agg_max__"
AGG_MEAN_SUFFIX = "__agg_mean__"
AGG_STD_SUFFIX = "__agg_std__"
IX_INFIX = "__ix__"
RATIO_INFIX = "__ratio__"
TMP_DIFF_SUFFIX = "__tmp_diff__"
TMP_RSTD_SUFFIX = "__tmp_rstd__"


class ColumnEnricher(ABC):
    """Base class for column enrichers."""

    @abstractmethod
    def enrich(
        self,
        data: pl.DataFrame,
        exclude_cols: list[str] | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """Enrich data with synthetic columns."""
        pass

    @abstractmethod
    def get_synthetic_columns(self) -> dict[str, str]:
        """Return mapping of synthetic column names to their sources."""
        pass

    def trace_to_originals(self, enriched_col: str) -> list[str]:
        """Return original column names for a synthetic column."""
        return []

    def narrative_fragment(self, enriched_col: str) -> str:
        """Return a narrative fragment for a synthetic column."""
        return ""


class AggregateEnricher(ColumnEnricher):
    """Enricher for aggregate columns (max, std, mean) for multi-source data."""

    def __init__(self, functions: list[str] | None = None) -> None:
        """Initialize aggregate enricher with selected functions."""
        self.functions = functions or ["max", "std", "mean"]
        self._synthetic_columns: dict[str, str] = {}

    def enrich(
        self,
        data: pl.DataFrame,
        exclude_cols: list[str] | None = None,
        source_columns: list[str] | None = None,
        semantic_groups: dict[str, list[str]] | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """Enrich data with aggregate columns."""
        if data is None or data.is_empty():
            return data

        exclude = set(exclude_cols or [])
        source_columns = source_columns or []
        semantic_groups = semantic_groups or {}

        self._synthetic_columns = {}

        if semantic_groups:
            exprs: list[pl.Expr] = []
            for group_name, cols in semantic_groups.items():
                group_cols = [c for c in cols if c in data.columns and c not in exclude]
                if len(group_cols) < 2:
                    continue
                group_list = pl.concat_list([pl.col(c) for c in group_cols])
                if "max" in self.functions:
                    exprs.append(group_list.list.max().alias(f"{group_name}{AGG_MAX_SUFFIX}"))
                    self._synthetic_columns[f"{group_name}{AGG_MAX_SUFFIX}"] = group_name
                if "std" in self.functions:
                    exprs.append(group_list.list.std().alias(f"{group_name}{AGG_STD_SUFFIX}"))
                    self._synthetic_columns[f"{group_name}{AGG_STD_SUFFIX}"] = group_name
                if "mean" in self.functions:
                    exprs.append(group_list.list.mean().alias(f"{group_name}{AGG_MEAN_SUFFIX}"))
                    self._synthetic_columns[f"{group_name}{AGG_MEAN_SUFFIX}"] = group_name
            if not exprs:
                return data
            return data.with_columns(exprs)

        if not source_columns:
            return data

        numeric_cols = [
            col for col in data.columns
            if col not in exclude
            and col not in source_columns
            and not is_enriched_column(col)
            and data[col].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32)
        ]

        if not numeric_cols:
            return data

        group_cols = [
            col for col in data.columns
            if col not in source_columns and col not in numeric_cols
        ]

        if "timestamp" in data.columns and "timestamp" not in group_cols:
            group_cols.append("timestamp")

        if not group_cols:
            return data

        exprs = []
        for metric in numeric_cols:
            if "max" in self.functions:
                exprs.append(pl.col(metric).max().over(group_cols).alias(f"{metric}{AGG_MAX_SUFFIX}"))
                self._synthetic_columns[f"{metric}{AGG_MAX_SUFFIX}"] = metric
            if "std" in self.functions:
                exprs.append(pl.col(metric).std().over(group_cols).alias(f"{metric}{AGG_STD_SUFFIX}"))
                self._synthetic_columns[f"{metric}{AGG_STD_SUFFIX}"] = metric
            if "mean" in self.functions:
                exprs.append(pl.col(metric).mean().over(group_cols).alias(f"{metric}{AGG_MEAN_SUFFIX}"))
                self._synthetic_columns[f"{metric}{AGG_MEAN_SUFFIX}"] = metric

        if not exprs:
            return data

        return data.with_columns(exprs)

    def get_synthetic_columns(self) -> dict[str, str]:
        """Return synthetic column mappings."""
        return dict(self._synthetic_columns)

    def trace_to_originals(self, enriched_col: str) -> list[str]:
        """Return original columns for an aggregate synthetic column."""
        if enriched_col.endswith(AGG_MAX_SUFFIX):
            return [enriched_col[: -len(AGG_MAX_SUFFIX)]]
        if enriched_col.endswith(AGG_STD_SUFFIX):
            return [enriched_col[: -len(AGG_STD_SUFFIX)]]
        if enriched_col.endswith(AGG_MEAN_SUFFIX):
            return [enriched_col[: -len(AGG_MEAN_SUFFIX)]]
        return []

    def narrative_fragment(self, enriched_col: str) -> str:
        """Return a narrative fragment for an aggregate synthetic column."""
        originals = self.trace_to_originals(enriched_col)
        if not originals:
            return ""
        base = originals[0]
        if enriched_col.endswith(AGG_MAX_SUFFIX):
            return f"Worst-case {base} across sources."
        if enriched_col.endswith(AGG_STD_SUFFIX):
            return f"Variability of {base} across sources."
        if enriched_col.endswith(AGG_MEAN_SUFFIX):
            return f"Average {base} across sources."
        return ""


class InteractionEnricher(ColumnEnricher):
    """Enricher for pairwise interactions (products and ratios)."""

    def __init__(
        self,
        top_k: int = 30,
        min_abs_correlation: float = 0.1,
        include_ratios: bool = True,
    ) -> None:
        """Initialize interaction enricher settings."""
        self.top_k = top_k
        self.min_abs_correlation = min_abs_correlation
        self.include_ratios = include_ratios
        self._synthetic_columns: dict[str, str] = {}

    def enrich(
        self,
        data: pl.DataFrame,
        exclude_cols: list[str] | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """Enrich data with interaction columns."""
        if data is None or data.is_empty():
            return data

        if LABEL_OUTCOME_COL not in data.columns:
            return data

        outcome = data[LABEL_OUTCOME_COL].to_numpy()
        if outcome.size == 0 or np.std(outcome) == 0:
            return data

        exclude = set(exclude_cols or [])
        numeric_cols = [
            col for col in data.columns
            if col not in exclude
            and col != LABEL_OUTCOME_COL
            and not is_enriched_column(col)
            and data[col].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32)
        ]

        if len(numeric_cols) < 2:
            return data

        correlations: list[tuple[str, float]] = []
        for col in numeric_cols:
            values = data[col].to_numpy()
            if values.size == 0 or np.std(values) == 0:
                continue
            corr = np.corrcoef(values, outcome)[0, 1]
            if np.isnan(corr):
                continue
            correlations.append((col, abs(corr)))

        if not correlations:
            return data

        correlations = [c for c in correlations if c[1] >= self.min_abs_correlation]
        if not correlations:
            return data

        correlations.sort(key=lambda item: -item[1])
        selected = [col for col, _ in correlations[: self.top_k]]

        if len(selected) < 2:
            return data

        exprs: list[pl.Expr] = []
        self._synthetic_columns = {}

        for i in range(len(selected)):
            for j in range(i + 1, len(selected)):
                left = selected[i]
                right = selected[j]
                ix_name = f"{left}{IX_INFIX}{right}"
                exprs.append((pl.col(left) * pl.col(right)).alias(ix_name))
                self._synthetic_columns[ix_name] = f"{left},{right}"

                if self.include_ratios:
                    ratio_name = f"{left}{RATIO_INFIX}{right}"
                    ratio_expr = (
                        pl.when(pl.col(right) != 0)
                        .then(pl.col(left) / pl.col(right))
                        .otherwise(None)
                        .alias(ratio_name)
                    )
                    exprs.append(ratio_expr)
                    self._synthetic_columns[ratio_name] = f"{left},{right}"

        if not exprs:
            return data

        return data.with_columns(exprs)

    def get_synthetic_columns(self) -> dict[str, str]:
        """Return synthetic column mappings."""
        return dict(self._synthetic_columns)

    def trace_to_originals(self, enriched_col: str) -> list[str]:
        """Return original columns for an interaction synthetic column."""
        if IX_INFIX in enriched_col:
            return enriched_col.split(IX_INFIX, 1)
        if RATIO_INFIX in enriched_col:
            return enriched_col.split(RATIO_INFIX, 1)
        return []

    def narrative_fragment(self, enriched_col: str) -> str:
        """Return a narrative fragment for an interaction synthetic column."""
        originals = self.trace_to_originals(enriched_col)
        if len(originals) != 2:
            return ""
        left, right = originals
        if IX_INFIX in enriched_col:
            return f"Interaction between {left} and {right}."
        if RATIO_INFIX in enriched_col:
            return f"Ratio of {left} to {right}."
        return ""


class TemporalEnricher(ColumnEnricher):
    """Enricher for temporal features (first differences, rolling volatility)."""

    def __init__(self, include_diff: bool = True, rolling_std_window: int = 10) -> None:
        """Initialize temporal enricher settings."""
        self.include_diff = include_diff
        self.rolling_std_window = rolling_std_window
        self._synthetic_columns: dict[str, str] = {}

    def enrich(
        self,
        data: pl.DataFrame,
        exclude_cols: list[str] | None = None,
        source_columns: list[str] | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """Enrich data with temporal columns."""
        if data is None or data.is_empty():
            return data

        if data.height < 3:
            return data

        exclude = set(exclude_cols or [])
        source_columns = source_columns or []

        numeric_cols = [
            col for col in data.columns
            if col not in exclude
            and col not in source_columns
            and not is_enriched_column(col)
            and data[col].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32)
        ]

        if not numeric_cols:
            return data

        exprs: list[pl.Expr] = []
        self._synthetic_columns = {}

        if self.include_diff:
            for col in numeric_cols:
                diff_name = f"{col}{TMP_DIFF_SUFFIX}"
                exprs.append(pl.col(col).diff().alias(diff_name))
                self._synthetic_columns[diff_name] = col

        if self.rolling_std_window and self.rolling_std_window > 1:
            for col in numeric_cols:
                rstd_name = f"{col}{TMP_RSTD_SUFFIX}{self.rolling_std_window}__"
                exprs.append(pl.col(col).rolling_std(self.rolling_std_window).alias(rstd_name))
                self._synthetic_columns[rstd_name] = col

        if not exprs:
            return data

        return data.with_columns(exprs)

    def get_synthetic_columns(self) -> dict[str, str]:
        """Return synthetic column mappings."""
        return dict(self._synthetic_columns)

    def trace_to_originals(self, enriched_col: str) -> list[str]:
        """Return original columns for a temporal synthetic column."""
        if TMP_DIFF_SUFFIX in enriched_col:
            return [enriched_col.split(TMP_DIFF_SUFFIX, 1)[0]]
        if TMP_RSTD_SUFFIX in enriched_col:
            return [enriched_col.split(TMP_RSTD_SUFFIX, 1)[0]]
        return []

    def narrative_fragment(self, enriched_col: str) -> str:
        """Return a narrative fragment for a temporal synthetic column."""
        originals = self.trace_to_originals(enriched_col)
        if not originals:
            return ""
        base = originals[0]
        if TMP_DIFF_SUFFIX in enriched_col:
            return f"Rate of change in {base}."
        if TMP_RSTD_SUFFIX in enriched_col:
            return f"Volatility (rolling standard deviation) of {base}."
        return ""


def create_enrichers_from_settings(
    settings: Any,
    has_source_columns: bool = False,
    has_timestamp: bool = False,
) -> list[ColumnEnricher]:
    """Create enrichers based on settings."""
    def _get_setting(key: str, default: Any) -> Any:
        """Read a setting from settings or dict with a default."""
        if settings is None:
            return default
        if isinstance(settings, dict):
            return settings.get(key, default)
        if hasattr(settings, "get"):
            return settings.get(key, default)
        return default

    enabled = _get_setting("profiling.enrichment.enabled", "auto")
    if enabled in (False, "false"):
        return []

    enrichers: list[ColumnEnricher] = []

    agg_setting = _get_setting("profiling.enrichment.aggregates.enabled", "auto")
    if agg_setting in (True, "true") or (agg_setting == "auto" and has_source_columns):
        functions = _get_setting(
            "profiling.enrichment.aggregates.functions",
            ["max", "std", "mean"],
        )
        enrichers.append(AggregateEnricher(functions=list(functions)))

    temporal_setting = _get_setting("profiling.enrichment.temporal.enabled", "auto")
    if temporal_setting in (True, "true") or (temporal_setting == "auto" and has_timestamp):
        include_diff = bool(_get_setting("profiling.enrichment.temporal.diff", True))
        rstd_window = int(_get_setting("profiling.enrichment.temporal.rolling_std_window", 10))
        enrichers.append(TemporalEnricher(include_diff=include_diff, rolling_std_window=rstd_window))

    interactions_setting = _get_setting("profiling.enrichment.interactions.enabled", False)
    if interactions_setting in (True, "true"):
        top_k = int(_get_setting("profiling.enrichment.interactions.top_k", 30))
        enrichers.append(InteractionEnricher(top_k=top_k, min_abs_correlation=0.0))

    return enrichers


def is_enriched_column(col_name: str) -> bool:
    """
    Check if a column is synthetic (enriched).

    A column is considered enriched if it contains one of the synthetic suffixes or infixes.
    """
    suffixes = (AGG_MAX_SUFFIX, AGG_MEAN_SUFFIX, AGG_STD_SUFFIX,
                TMP_DIFF_SUFFIX, TMP_RSTD_SUFFIX)
    infixes = (IX_INFIX, RATIO_INFIX)

    if not isinstance(col_name, str):
        return False

    # Check for suffixes
    for suffix in suffixes:
        if suffix in col_name:
            return True

    # Check for infixes (anywhere in the name)
    for infix in infixes:
        if infix in col_name:
            return True

    return False


class EnrichedInfluenceAnalyzer(InfluenceAnalyzer):
    """
    Decorator that enriches data with synthetic columns before delegating to an inner analyzer.

    Synthetic columns include aggregates (max, std), temporal derivatives (diff, volatility),
    and pairwise interactions (products, ratios).

    The decorator stores enriched data for later use (e.g., tree visualization) and
    resolves synthetic factors back to display-friendly names.
    """

    def __init__(self, inner: InfluenceAnalyzer, enrichers: list[ColumnEnricher] | None = None) -> None:
        """
        Initialize enrichment decorator.

        Args:
            inner: Inner analyzer to wrap
        """
        self.inner = inner
        self.enrichers = enrichers
        self._last_enriched_data: pl.DataFrame | None = None
        self._last_outcome_col: str | None = None
        self._lower_is_better: bool = True

    @property
    def capabilities(self) -> dict[str, bool]:
        """Return inner analyzer capabilities with enrichment flag when active."""
        caps = {}
        if hasattr(self.inner, "capabilities"):
            caps = dict(self.inner.capabilities)
        if self.enrichers:
            caps["enrichment"] = True
        return caps

    @property
    def name(self) -> str:
        """Return the inner analyzer's name."""
        return self.inner.name

    @property
    def label(self) -> str:
        """Delegate human-readable label to the inner analyzer."""
        return self.inner.label

    @property
    def description(self) -> str:
        """Delegate description to the inner analyzer."""
        return self.inner.description

    @property
    def last_enriched_data(self) -> pl.DataFrame | None:
        """Return the last enriched dataset used during analysis."""
        return self._last_enriched_data

    def analyze(
        self,
        data: pl.DataFrame,
        outcome: np.ndarray,
        outcome_mode: str = "regression",
        **kwargs: Any,
    ) -> list[InfluenceFactor]:
        """
        Analyze data with optional enrichment.

        For now, this is a pass-through to the inner analyzer.
        Full enrichment implementation would:
        1. Extract numeric columns and group structures
        2. Generate synthetic columns (aggregates, temporal, interactions)
        3. Combine with original data
        4. Call inner analyzer
        5. Store enriched data for later use
        6. Resolve factors back to original names with metadata

        Args:
            data: Input data frame
            outcome: Outcome labels/values (n_samples,)
            outcome_mode: "regression" or "classification"
            **kwargs: Additional analysis parameters

        Returns:
            List of InfluenceFactor instances
        """
        self._last_outcome_col = kwargs.get("outcome_col")
        self._lower_is_better = kwargs.get("lower_is_better", True)

        enrichers = self.enrichers
        if enrichers is None:
            settings = kwargs.get("settings")
            enrichers = self._create_enrichers_for_data(data, settings, kwargs)

        if not enrichers:
            self._last_enriched_data = data
            return self.inner.analyze(
                data,
                outcome,
                outcome_mode=outcome_mode,
                **kwargs,
            )

        source_columns = self._extract_source_columns(data, kwargs.get("settings"), kwargs)
        semantic_groups = self._extract_semantic_groups(kwargs.get("settings"), kwargs)

        enriched_data = data
        exclude_cols = list(kwargs.get("exclude_cols") or [])

        # Never generate synthetic predictors from the outcome column.
        # This guards against leakage when callers forget to include the
        # effective/original outcome in exclude_cols.
        outcome_col = kwargs.get("outcome_col")
        if isinstance(outcome_col, str) and outcome_col:
            exclude_cols.append(outcome_col)
        original_outcome_col = kwargs.get("original_outcome_col")
        if isinstance(original_outcome_col, str) and original_outcome_col:
            exclude_cols.append(original_outcome_col)
        exclude_cols.append(LABEL_OUTCOME_COL)
        exclude_cols = list(dict.fromkeys(exclude_cols))

        for enricher in enrichers:
            enriched_data = enricher.enrich(
                enriched_data,
                exclude_cols=exclude_cols,
                source_columns=source_columns,
                semantic_groups=semantic_groups,
            )

        self._last_enriched_data = enriched_data
        raw_factors = self.inner.analyze(
            enriched_data,
            outcome,
            outcome_mode=outcome_mode,
            **kwargs,
        )
        return self._resolve_factors(raw_factors, enrichers)

    def _resolve_factors(
        self,
        factors: list[InfluenceFactor],
        enrichers: list[ColumnEnricher] | None = None,
    ) -> list[InfluenceFactor]:
        """Resolve synthetic factor names back to original columns."""
        if not factors:
            return []

        if enrichers is None:
            enrichers = self.enrichers or []
        resolved: list[InfluenceFactor] = []

        for factor in factors:
            if not is_enriched_column(factor.name):
                resolved.append(factor)
                continue

            originals: list[str] = []
            narrative = ""
            for enricher in enrichers:
                originals = enricher.trace_to_originals(factor.name)
                if originals:
                    narrative = enricher.narrative_fragment(factor.name)
                    break

            if not originals:
                resolved.append(factor)
                continue

            metadata = dict(factor.metadata or {})
            metadata["enriched_from"] = factor.name
            metadata["original_columns"] = originals
            metadata["enrichment_narrative"] = narrative
            metadata["encoded_name"] = factor.name

            display_name = originals[0]
            resolved.append(replace(factor, name=display_name, metadata=metadata))

        return resolved

    def _extract_source_columns(
        self,
        data: pl.DataFrame,
        settings: Any,
        context: dict[str, Any],
    ) -> list[str]:
        """Return source identifier columns for enrichment."""
        if isinstance(context.get("source_columns"), list):
            return list(context["source_columns"])
        return detect_source_columns(data)

    def _extract_semantic_groups(
        self,
        settings: Any,
        context: dict[str, Any],
    ) -> dict[str, list[str]]:
        """Return semantic groups mapping for wide data enrichment."""
        if isinstance(context.get("semantic_groups"), dict):
            return dict(context["semantic_groups"])
        return {}

    def _has_timestamp_column(self, data: pl.DataFrame, settings: Any, context: dict[str, Any]) -> bool:
        """Check whether data contains a timestamp column for temporal enrichment."""
        timestamp_col = context.get("timestamp_col")
        if isinstance(timestamp_col, str) and timestamp_col in data.columns:
            return True
        if "timestamp" in data.columns:
            return True
        if settings is None:
            return False
        if isinstance(settings, dict):
            ts = settings.get("profiling.lag_detection.timestamp_column")
        else:
            ts = settings.get("profiling.lag_detection.timestamp_column", None)
        return isinstance(ts, str) and ts in data.columns

    def _create_enrichers_for_data(
        self,
        data: pl.DataFrame,
        settings: Any,
        context: dict[str, Any],
    ) -> list[ColumnEnricher]:
        """Build enrichers based on detected data characteristics."""
        source_columns = self._extract_source_columns(data, settings, context)
        semantic_groups = self._extract_semantic_groups(settings, context)
        has_source_columns = bool(source_columns) or bool(semantic_groups)
        has_timestamp = self._has_timestamp_column(data, settings, context)
        return create_enrichers_from_settings(
            settings=settings,
            has_source_columns=has_source_columns,
            has_timestamp=has_timestamp,
        )

    @property
    def trained_model(self) -> Any:
        """Forward trained_model property from inner analyzer."""
        return getattr(self.inner, 'trained_model', None)
