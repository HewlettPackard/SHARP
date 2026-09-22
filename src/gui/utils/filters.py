"""
Reusable data filtering utilities for the GUI.

Provides filter application logic for use across Profile, Explore, and Compare tabs.

© Copyright 2025--2026 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

from enum import Enum
from typing import Union, List, Any

import polars as pl
import re


class _KeepCurrent(Enum):
    """Sentinel: tell ``update_filter_widget`` to keep the current slider value."""
    TOKEN = "KEEP_CURRENT"


KEEP_CURRENT: Any = _KeepCurrent.TOKEN
"""Pass as ``preset_value`` to preserve the user's current slider/select value."""


def _is_time_format(value: str) -> bool:
    """Check if a string value matches time format HH:MM:SS or HH:MM:SS.mmm"""
    return bool(re.match(r'^\d{1,2}:\d{2}:\d{2}(\.\d{1,3})?$', str(value).strip()))


def _time_to_seconds(time_str: str) -> float:
    """Convert HH:MM:SS or HH:MM:SS.mmm format to total seconds."""
    try:
        time_str = str(time_str).strip()
        parts = time_str.split(':')
        if len(parts) != 3:
            return 0.0
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    except (ValueError, IndexError):
        return 0.0


def is_time_column(col: pl.Series) -> bool:
    """Check if a column contains time values in HH:MM:SS format."""
    if col.dtype != pl.Utf8:
        return False
    # Sample up to 10 non-null values
    sample = col.drop_nulls().head(10).to_list()
    if not sample:
        return False
    # Check if all samples match time format
    is_time = all(_is_time_format(v) for v in sample)
    return is_time


def apply_filter(
    data: pl.DataFrame,
    filter_metric: str,
    filter_value: Union[List[Any], int, float, str, dict[str, Any], None]
) -> pl.DataFrame:
    """
    Apply filter to data based on metric and value.

    Handles unselected/empty filters gracefully by returning data unchanged:
    - None or empty filter_metric
    - None filter_value
    - Empty list/tuple filter_value
    - List containing only empty string (placeholder selection)

    Args:
        data: Polars DataFrame to filter
        filter_metric: Name of the column to filter on
        filter_value: Filter value(s) - can be list, single value, or range

    Returns:
        Filtered Polars DataFrame (or original if no filter applied)
    """
    if data is None or data.is_empty():
        return data

    if filter_metric is None or (isinstance(filter_metric, str) and not filter_metric.strip()):
        return data

    if filter_metric not in data.columns:
        return data

    if filter_value is None:
        return data

    # Handle empty list/tuple or placeholder selection
    if isinstance(filter_value, (list, tuple)):
        if not filter_value or (len(filter_value) == 1 and filter_value[0] == ""):
            return data

    col = data[filter_metric]

    try:
        # Time format filter (convert times for comparison)
        if is_time_column(col):
            # For time filters, filter_value should be a list [start_seconds, end_seconds]
            if filter_value is None:
                return data

            # Handle list input - now always numeric seconds from our slider
            if isinstance(filter_value, (list, tuple)) and len(filter_value) == 2:
                # Numeric seconds (from our fixed slider)
                if isinstance(filter_value[0], (int, float)):
                    min_secs = float(filter_value[0])
                    max_secs = float(filter_value[1])
                else:
                    return data
            else:
                return data

            # Convert time column to seconds using apply and filter
            seconds_col = col.map_elements(
                lambda t: _time_to_seconds(t) if t is not None else -1,
                return_dtype=pl.Float64
            )

            # Compute actual data range if available
            try:
                seconds_clean = seconds_col.drop_nulls().drop_nans()
                if len(seconds_clean) == 0:
                    return data
            except Exception:
                pass

            filtered = data.filter(
                (seconds_col >= min_secs) &
                (seconds_col <= max_secs)
            )
            return filtered

        # Categorical filter
        elif col.dtype == pl.Categorical or col.dtype == pl.Utf8:
            if isinstance(filter_value, (list, tuple)) and len(filter_value) > 0:
                filtered = data.filter(pl.col(filter_metric).is_in(filter_value))
                return filtered
            else:
                return data

        # Numeric filter
        elif col.dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
            if isinstance(filter_value, (list, tuple)) and len(filter_value) == 2:
                # Range filter
                filtered = data.filter(
                    (pl.col(filter_metric) >= filter_value[0]) &
                    (pl.col(filter_metric) <= filter_value[1])
                )
                return filtered
            elif isinstance(filter_value, (int, float)):
                # Single value filter
                filtered = data.filter(pl.col(filter_metric) == filter_value)
                return filtered
            else:
                return data

        return data

    except Exception:
        return data


def get_filterable_columns(data: pl.DataFrame, exclude_cols: List[str] | None = None) -> List[str]:
    """
    Get list of columns suitable for filtering (categorical, numeric, or time).

    Args:
        data: Polars DataFrame
        exclude_cols: Optional list of column names to exclude

    Returns:
        List of column names suitable for filtering
    """
    if data is None or data.is_empty():
        return []

    if exclude_cols is None:
        exclude_cols = []

    filterable = []

    for col_name in data.columns:
        if col_name in exclude_cols:
            continue

        col = data[col_name]

        # Check for time format strings (HH:MM:SS or HH:MM:SS.mmm)
        if is_time_column(col):
            filterable.append(col_name)

        # Check for categorical/string columns with reasonable unique count
        elif col.dtype == pl.Categorical or col.dtype == pl.Utf8:
            unique_count = col.n_unique()
            # Only include if not all unique (which would make filtering useless)
            if unique_count > 1 and unique_count < len(data):
                filterable.append(col_name)

        # Include all numeric columns
        elif col.dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
            if col.n_unique() > 1:  # At least some variance
                filterable.append(col_name)

    return sorted(filterable)


def is_full_range_filter(
    data: pl.DataFrame,
    filter_column: str,
    filter_value: Union[List[Any], int, float, str, None]
) -> bool:
    """
    Check if a range filter covers the full range (i.e., no actual filtering).

    Handles numeric columns and time-formatted string columns.

    Args:
        data: Polars DataFrame
        filter_column: Column name
        filter_value: Filter value (should be [min, max])

    Returns:
        True if filter covers full range, False otherwise
    """
    if data is None or data.is_empty():
        return False

    if filter_column not in data.columns:
        return False

    if not isinstance(filter_value, (list, tuple)) or len(filter_value) != 2:
        return False

    try:
        col = data[filter_column]

        # Handle time-formatted string columns
        if is_time_column(col):
            # Convert filter values to seconds (numeric from slider)
            if isinstance(filter_value[0], (int, float)):
                filter_min = float(filter_value[0])
                filter_max = float(filter_value[1])
            else:
                return False

            # Convert column to seconds and get min/max
            time_values = col.drop_nulls().to_list()
            if not time_values:
                return True  # No data to filter
            col_min = _time_to_seconds(min(time_values))
            col_max = _time_to_seconds(max(time_values))

            # Check if filter covers full range (with small tolerance)
            return filter_min <= col_min + 0.5 and filter_max >= col_max - 0.5

        # Handle numeric columns
        elif col.dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
            col_min = float(col.drop_nulls().min())  # type: ignore
            col_max = float(col.drop_nulls().max())  # type: ignore

            # Check if filter range matches data range (within floating point tolerance)
            return bool(abs(float(filter_value[0]) - col_min) < 1e-9 and
                    abs(float(filter_value[1]) - col_max) < 1e-9)

        return False

    except Exception:
        return False


def should_apply_filter(
    filter_value: Union[List[Any], int, float, str, dict[str, Any], None],
    data: pl.DataFrame | None = None,
    filter_metric: str | None = None
) -> bool:
    """
    Determine if a filter should be applied based on the filter value.

    Handles all filter types:
    - None: no filter
    - Empty list/tuple: no filter
    - List with single empty string: no filter (categorical placeholder)
    - Numeric range matching full data range: no filter
    - Time filter dict with missing values: no filter

    Args:
        filter_value: The filter value to check
        data: Optional DataFrame (needed for full-range numeric check)
        filter_metric: Optional column name (needed for full-range numeric check)

    Returns:
        True if filter should be applied, False otherwise
    """
    # None or empty means no filter
    if filter_value is None:
        return False

    # Empty list/tuple means no filter
    if isinstance(filter_value, (list, tuple)):
        if not filter_value:
            return False
        # Single empty string is categorical placeholder
        if len(filter_value) == 1 and filter_value[0] == "":
            return False
        # Check if it's a full-range numeric filter
        if len(filter_value) == 2 and data is not None and filter_metric is not None:
            if is_full_range_filter(data, filter_metric, filter_value):
                return False
        return True

    # Dict (time filter) - must have both start and end
    if isinstance(filter_value, dict):
        return bool(filter_value.get('start') and filter_value.get('end'))

    # All other scalar values should be applied
    return True
