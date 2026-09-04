"""
Data model utilities for profiling analysis.

Implements tall-canonical detection and conversion helpers for multi-source data.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

from dataclasses import dataclass
from typing import Iterable

import polars as pl

from src.core.config.settings import Settings


DEFAULT_SOURCE_COLUMN_NAMES = [
    "host",
    "hostname",
    "node",
    "rank",
    "device",
    "nic",
    "thread",
    "pid",
]


@dataclass(frozen=True)
class DataModelInfo:
    """Detected data model metadata.

    format: "tall" or "wide" (tall is canonical)
    source_columns: auto-detected source identifier columns
    """

    format: str
    source_columns: list[str]


def _get_candidate_source_columns(
    data: pl.DataFrame,
    candidate_names: Iterable[str],
) -> list[str]:
    """Return columns that match candidate names (case-insensitive)."""
    candidates = {name.lower() for name in candidate_names}
    return [col for col in data.columns if col.lower() in candidates]


def detect_source_columns(
    data: pl.DataFrame,
    candidate_names: Iterable[str] | None = None,
) -> list[str]:
    """Detect source identifier columns that exist in the data.

    Returns all candidates from source_column_names that are present in the data.
    """
    if data.is_empty():
        return []

    settings = Settings()
    candidate_names = candidate_names or settings.get(
        "profiling.source_column_names",
        DEFAULT_SOURCE_COLUMN_NAMES,
    )

    return _get_candidate_source_columns(data, candidate_names)


def detect_format(
    data: pl.DataFrame,
    source_columns: list[str] | None = None,
) -> str:
    """Detect whether data is tall or wide.

    Returns "tall" if source columns are present.
    Returns "wide" if columns match source column name patterns (wide-format derived columns).
    Returns "tall" by default when uncertain.
    """
    source_columns = source_columns or detect_source_columns(data)
    if source_columns:
        return "tall"

    settings = Settings()
    candidate_names = settings.get(
        "profiling.source_column_names",
        DEFAULT_SOURCE_COLUMN_NAMES,
    )
    candidates_lower = {name.lower() for name in candidate_names}

    # Check for wide-format pattern: columns that include source column names
    for col in data.columns:
        col_lower = col.lower()
        for candidate in candidates_lower:
            if candidate in col_lower:
                return "wide"

    return "tall"


def detect_data_model(data: pl.DataFrame) -> DataModelInfo:
    """Detect data model info (format + source columns)."""
    source_columns = detect_source_columns(data)
    fmt = detect_format(data, source_columns=source_columns)
    return DataModelInfo(format=fmt, source_columns=source_columns)


def _add_source_label(
    data: pl.DataFrame,
    source_columns: list[str],
    source_label_col: str,
) -> pl.DataFrame:
    if len(source_columns) == 1:
        return data.with_columns(
            pl.col(source_columns[0]).cast(pl.Utf8).alias(source_label_col)
        )

    parts = [pl.col(c).cast(pl.Utf8) for c in source_columns]
    return data.with_columns(
        pl.concat_str(parts, separator="_").alias(source_label_col)
    )


def tall_to_wide(
    data: pl.DataFrame,
    source_columns: list[str],
    metric_columns: list[str] | None = None,
    index_columns: list[str] | None = None,
    source_label_col: str = "__source_label__",
) -> pl.DataFrame:
    """Pivot tall data into wide form.

    Each metric column becomes multiple columns, one per source.
    """
    if not source_columns:
        return data

    if metric_columns is None:
        metric_columns = [
            col for col in data.columns
            if col not in source_columns
        ]

    if index_columns is None:
        index_columns = []

    working = data
    if not index_columns:
        working = working.with_row_index("__row_id__")
        index_columns = ["__row_id__"]

    working = _add_source_label(working, source_columns, source_label_col)

    wide_df: pl.DataFrame | None = None
    for metric in metric_columns:
        pivoted = (
            working
            .select(index_columns + [source_label_col, metric])
            .pivot(
                index=index_columns,
                on=source_label_col,
                values=metric,
                aggregate_function="first",
            )
        )
        rename_map = {
            col: f"{metric}__{col}"
            for col in pivoted.columns
            if col not in index_columns
        }
        pivoted = pivoted.rename(rename_map)

        if wide_df is None:
            wide_df = pivoted
        else:
            wide_df = wide_df.join(pivoted, on=index_columns, how="left")

    if wide_df is None:
        return working

    return wide_df


def _split_source_label(
    data: pl.DataFrame,
    source_label_col: str,
    source_columns: list[str] | None,
    label_separator: str,
) -> pl.DataFrame:
    if not source_columns:
        return data.with_columns(
            pl.col(source_label_col).alias("source")
        )

    if len(source_columns) == 1:
        return data.with_columns(
            pl.col(source_label_col).alias(source_columns[0])
        )

    split_col = pl.col(source_label_col).str.split(label_separator)
    for idx, col_name in enumerate(source_columns):
        data = data.with_columns(
            split_col.list.get(idx).alias(col_name)
        )

    return data


def wide_to_tall(
    data: pl.DataFrame,
    source_columns: list[str] | None = None,
    index_columns: list[str] | None = None,
    metric_source_sep: str = "__",
    source_label_sep: str = "_",
) -> pl.DataFrame:
    """Unpivot wide data into tall form.

    Assumes wide columns are named {metric}__{source_label}.
    """
    if index_columns is None:
        index_columns = [
            col for col in data.columns
            if metric_source_sep not in col
        ]

    metric_cols = [
        col for col in data.columns
        if metric_source_sep in col
    ]

    if not metric_cols:
        return data

    long_parts: list[pl.DataFrame] = []
    for col in metric_cols:
        metric, source_label = col.rsplit(metric_source_sep, 1)
        part = data.select(
            index_columns
            + [
                pl.lit(metric).alias("__metric__"),
                pl.lit(source_label).alias("__source_label__"),
                pl.col(col).alias("__value__"),
            ]
        )
        long_parts.append(part)

    long_df = pl.concat(long_parts, how="vertical")

    tall_df = long_df.pivot(
        index=index_columns + ["__source_label__"],
        on="__metric__",
        values="__value__",
        aggregate_function="first",
    )

    tall_df = _split_source_label(
        tall_df,
        source_label_col="__source_label__",
        source_columns=source_columns,
        label_separator=source_label_sep,
    ).drop("__source_label__")

    return tall_df
