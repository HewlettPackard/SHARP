# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Shared utilities for gui services (used by multiple tabs)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import polars as pl

from src.gui.contracts.schemas import FilterSpec

from src.core.config.settings import Settings
from src.core.runlogs.reader import load_table


METRIC_PREFERENCES = ["perf_time", "inner_time", "outer_time"]
_FILTER_METRICS_CACHE: dict[tuple[str, int, int], list[str]] = {}
_OUTCOME_METRICS_CACHE: dict[tuple[str, int, int], list[str]] = {}


def _is_time_string(value: str) -> bool:
    """Check HH:MM:SS(.mmm) format."""
    return bool(re.match(r"^\d{1,2}:\d{2}:\d{2}(\.\d{1,3})?$", str(value).strip()))


def _time_to_seconds(value: str) -> float:
    """Convert HH:MM:SS(.mmm) to total seconds."""
    parts = str(value).strip().split(":")
    if len(parts) != 3:
        raise ValueError("invalid time format")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def _is_time_series(series: pl.Series) -> bool:
    """Return true when string/categorical series looks like HH:MM:SS values."""
    if series.dtype not in (pl.Utf8, pl.Categorical):
        return False
    sample = [str(v) for v in series.drop_nulls().head(12).to_list()]
    if not sample:
        return False
    return all(_is_time_string(v) for v in sample)


def _filter_kind(series: pl.Series) -> str:
    """Classify filter widget kind for a series."""
    dtype = str(series.dtype)
    if any(token in dtype for token in ["Int", "Float", "Decimal"]):
        return "numeric"
    if _is_time_series(series):
        return "time"
    if any(token in dtype for token in ["String", "Utf8", "Categorical"]):
        return "categorical"
    return "unsupported"


def _numeric_columns(df: pl.DataFrame) -> list[str]:
    """Return numeric column names from a DataFrame."""
    out: list[str] = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        if any(token in dtype for token in ("Int", "Float", "Decimal")):
            out.append(col)
    return out


def _filterable_columns(df: pl.DataFrame) -> list[str]:
    """Return columns suitable for filtering (numeric + time-like strings)."""
    out: list[str] = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        if any(token in dtype for token in ("Int", "Float", "Decimal")):
            out.append(col)
        elif df[col].dtype in (pl.Utf8, pl.Categorical):
            if _is_time_series(df[col]):
                out.append(col)
            elif 1 < df[col].n_unique() < df.height:
                out.append(col)
    return out


def cached_filter_metrics(csv_path: str) -> list[str]:
    """Return cached filter metrics for a CSV, invalidating on file metadata changes."""
    path = Path(csv_path)
    try:
        stat = path.stat()
    except OSError:
        return []

    key = (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    cached = _FILTER_METRICS_CACHE.get(key)
    if cached is not None:
        return cached

    df = load_table(str(path))
    metrics = _filterable_columns(df)
    _FILTER_METRICS_CACHE[key] = metrics

    settings = Settings()
    max_entries = int(
        settings.get(
            "gui.filter_metrics_cache_max_entries",
            settings.get("gui.profile.filter_metrics_cache_max_entries", 8),
        )
    )
    while len(_FILTER_METRICS_CACHE) > max_entries:
        oldest_key = next(iter(_FILTER_METRICS_CACHE))
        _FILTER_METRICS_CACHE.pop(oldest_key, None)

    return metrics


def cached_outcome_metrics(csv_path: str) -> list[str]:
    """Return cached numeric column names for a CSV, invalidating on file metadata changes."""
    path = Path(csv_path)
    try:
        stat = path.stat()
    except OSError:
        return []

    key = (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    cached = _OUTCOME_METRICS_CACHE.get(key)
    if cached is not None:
        return cached

    df = load_table(str(path))
    metrics = _numeric_columns(df)
    _OUTCOME_METRICS_CACHE[key] = metrics

    settings = Settings()
    max_entries = int(
        settings.get(
            "gui.filter_metrics_cache_max_entries",
            settings.get("gui.profile.filter_metrics_cache_max_entries", 8),
        )
    )
    while len(_OUTCOME_METRICS_CACHE) > max_entries:
        oldest_key = next(iter(_OUTCOME_METRICS_CACHE))
        _OUTCOME_METRICS_CACHE.pop(oldest_key, None)

    return metrics


def search_outcome_metrics(csv_path: str, query: str, limit: int = 150) -> list[str]:
    """Search numeric columns for a CSV with prefix-first ranking."""
    if not csv_path:
        return []

    metrics = cached_outcome_metrics(csv_path)
    term = (query or "").strip().lower()
    if not term:
        return metrics[:limit]

    prefix_matches: list[str] = []
    contains_matches: list[str] = []
    for metric in metrics:
        lowered = metric.lower()
        if lowered.startswith(term):
            prefix_matches.append(metric)
        elif term in lowered:
            contains_matches.append(metric)

    return (prefix_matches + contains_matches)[:max(1, int(limit))]


def search_filter_metrics(csv_path: str, query: str, limit: int = 150) -> list[str]:
    """Search filterable columns for a CSV with prefix-first ranking."""
    if not csv_path:
        return []

    metrics = cached_filter_metrics(csv_path)
    term = (query or "").strip().lower()
    if not term:
        return metrics[:limit]

    prefix_matches: list[str] = []
    contains_matches: list[str] = []
    for metric in metrics:
        lowered = metric.lower()
        if lowered.startswith(term):
            prefix_matches.append(metric)
        elif term in lowered:
            contains_matches.append(metric)

    return (prefix_matches + contains_matches)[: max(1, int(limit))]


def _order_metric_candidates(metrics: list[str]) -> list[str]:
    """Order metrics with old-gui preferred metrics first."""
    preferred = [metric for metric in METRIC_PREFERENCES if metric in metrics]
    remaining = sorted(metric for metric in metrics if metric not in preferred)
    return preferred + remaining


def filter_kwargs_from_specs(filters: list[FilterSpec]) -> dict[str, Any]:
    """Convert public FilterSpec list to legacy one-filter service arguments.

    The public API is standardized on ``filters`` now; the existing GUI services
    still accept one flat filter column. Multiple filters deliberately return a
    validation error until the internals are refactored to handle AND-composed
    filters directly.
    """
    if not filters:
        return {
            "filter_metric": None,
            "filter_value": None,
            "filter_values": None,
            "filter_min": None,
            "filter_max": None,
        }
    if len(filters) > 1:
        raise ValueError("Only one filter is currently supported")
    spec = filters[0]
    if spec.kind == "equals":
        if spec.value in (None, ""):
            raise ValueError("equals filter requires value")
        return {
            "filter_metric": spec.metric,
            "filter_value": spec.value,
            "filter_values": [spec.value],
            "filter_min": None,
            "filter_max": None,
        }
    if spec.kind == "in":
        if not spec.values:
            raise ValueError("in filter requires values")
        return {
            "filter_metric": spec.metric,
            "filter_value": None,
            "filter_values": spec.values,
            "filter_min": None,
            "filter_max": None,
        }
    if spec.kind == "range":
        if spec.min in (None, "") and spec.max in (None, ""):
            raise ValueError("range filter requires min or max")
        return {
            "filter_metric": spec.metric,
            "filter_value": None,
            "filter_values": None,
            "filter_min": spec.min,
            "filter_max": spec.max,
        }
    raise ValueError(f"Unsupported filter kind: {spec.kind}")


def _load_filtered_dataframe(
    csv_path: str,
    filter_metric: str | None,
    filter_value: str | None,
    filter_values: list[str] | None = None,
    filter_min: str | None = None,
    filter_max: str | None = None,
) -> pl.DataFrame:
    """Load dataset and apply optional type-aware filter."""
    df = load_table(csv_path)
    if not filter_metric or filter_metric not in df.columns:
        return df

    series = df[filter_metric]
    kind = _filter_kind(series)

    try:
        if kind == "categorical":
            selected = [str(v) for v in (filter_values or []) if str(v).strip()]
            if selected:
                df = df.filter(pl.col(filter_metric).cast(str).is_in(selected))
            elif filter_value:
                df = df.filter(pl.col(filter_metric).cast(str) == str(filter_value))
            return df

        if kind == "numeric":
            min_v = float(str(filter_min)) if filter_min not in (None, "") else None
            max_v = float(str(filter_max)) if filter_max not in (None, "") else None

            if min_v is not None:
                df = df.filter(pl.col(filter_metric).cast(float, strict=False) >= min_v)
            if max_v is not None:
                df = df.filter(pl.col(filter_metric).cast(float, strict=False) <= max_v)

            if min_v is None and max_v is None and filter_value not in (None, ""):
                scalar = float(str(filter_value))
                df = df.filter(pl.col(filter_metric).cast(float, strict=False) == scalar)
            return df

        if kind == "time":
            if filter_min not in (None, "") or filter_max not in (None, ""):
                min_s = _time_to_seconds(str(filter_min)) if filter_min not in (None, "") else None
                max_s = _time_to_seconds(str(filter_max)) if filter_max not in (None, "") else None

                sec_col = pl.col(filter_metric).map_elements(
                    lambda t: _time_to_seconds(str(t)) if t is not None else None,
                    return_dtype=pl.Float64,
                )
                if min_s is not None:
                    df = df.filter(sec_col >= min_s)
                if max_s is not None:
                    df = df.filter(sec_col <= max_s)
            elif filter_value:
                df = df.filter(pl.col(filter_metric).cast(str) == str(filter_value))
            return df
    except Exception:
        return df

    return df


def _filter_config_for_metric(df: pl.DataFrame, filter_metric: str | None) -> dict[str, Any]:
    """Build UI config for filter controls based on selected filter metric type."""
    if not filter_metric or filter_metric not in df.columns:
        return {
            "filter_kind": "none",
            "filter_options": [],
            "filter_min_bound": None,
            "filter_max_bound": None,
            "filter_min_bound_num": None,
            "filter_max_bound_num": None,
            "filter_is_timestamp_like": False,
        }

    series = df[filter_metric]
    kind = _filter_kind(series)

    if kind == "categorical":
        options = sorted([str(v) for v in series.drop_nulls().unique().to_list()])
        return {
            "filter_kind": kind,
            "filter_options": options,
            "filter_min_bound": None,
            "filter_max_bound": None,
            "filter_min_bound_num": None,
            "filter_max_bound_num": None,
            "filter_is_timestamp_like": False,
        }

    if kind == "numeric":
        vals = series.cast(float, strict=False).drop_nulls().to_numpy()
        if len(vals) == 0:
            return {
                "filter_kind": "none",
                "filter_options": [],
                "filter_min_bound": None,
                "filter_max_bound": None,
            }
        dtype_str = str(series.dtype)
        is_integer = "Int" in dtype_str and "Float" not in dtype_str
        return {
            "filter_kind": kind,
            "filter_options": [],
            "filter_min_bound": float(vals.min()),
            "filter_max_bound": float(vals.max()),
            "filter_min_bound_num": float(vals.min()),
            "filter_max_bound_num": float(vals.max()),
            "filter_is_timestamp_like": "timestamp" in str(filter_metric).lower(),
            "filter_is_integer": is_integer,
        }

    if kind == "time":
        times = [str(v) for v in series.drop_nulls().to_list() if _is_time_string(str(v))]
        if not times:
            return {
                "filter_kind": "none",
                "filter_options": [],
                "filter_min_bound": None,
                "filter_max_bound": None,
            }
        return {
            "filter_kind": kind,
            "filter_options": [],
            "filter_min_bound": min(times),
            "filter_max_bound": max(times),
            "filter_min_bound_num": float(min(_time_to_seconds(t) for t in times)),
            "filter_max_bound_num": float(max(_time_to_seconds(t) for t in times)),
            "filter_is_timestamp_like": False,
        }

    return {
        "filter_kind": "none",
        "filter_options": [],
        "filter_min_bound": None,
        "filter_max_bound": None,
        "filter_min_bound_num": None,
        "filter_max_bound_num": None,
        "filter_is_timestamp_like": False,
    }
