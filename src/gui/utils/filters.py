"""
Reusable data filtering utilities for Shiny GUI.

Provides dynamic filter UI generation and filter application logic
for use across Profile, Explore, and Compare tabs.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Union, List, Any
import polars as pl
from shiny import ui
import re


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


def format_seconds_as_time(seconds: float) -> str:
    """Convert total seconds to HH:MM:SS format (public API for UI display)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def get_time_filter_display(
    data: pl.DataFrame | None,
    filter_metric: str | None,
    filter_value: Union[List[Any], int, float, str, dict, None]
) -> str:
    """
    Get formatted time range display for UI (only for time columns).

    Args:
        data: DataFrame containing the filter metric
        filter_metric: Name of the column being filtered
        filter_value: Current filter value from the slider

    Returns:
        Formatted string like "Selected: 00:01:23 → 00:05:45" or empty string
    """
    try:
        if not filter_metric or not filter_metric.strip():
            return ""

        if data is None or filter_metric not in data.columns:
            return ""

        # Only show time display if this is actually a time column
        if not is_time_column(data[filter_metric]):
            return ""

        if filter_value and isinstance(filter_value, (list, tuple)) and len(filter_value) == 2:
            if isinstance(filter_value[0], (int, float)):
                start_time = format_seconds_as_time(filter_value[0])
                end_time = format_seconds_as_time(filter_value[1])
                return f"Selected: {start_time} → {end_time}"
    except Exception:
        pass
    return ""


def _seconds_to_time(seconds: float) -> str:
    """Convert total seconds back to HH:MM:SS.mmm format (for internal use)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"



def get_filter_value(input_obj, filter_input_id: str) -> Union[List[Any], int, float, str, dict, None]:
    """
    Extract filter value from Shiny inputs, handling both time and non-time filters.

    For time filters, the slider returns [min_seconds, max_seconds] directly.
    For other filters, returns the direct input value.

    Args:
        input_obj: Shiny input object (input from server function)
        filter_input_id: Base ID for the filter input (e.g., "profile_filter_value")

    Returns:
        Filter value - list [start, end] for time/range filters, or standard value for other filter types
    """
    try:
        # Access input dynamically via getattr; returns a callable
        input_accessor = getattr(input_obj, filter_input_id, None)
        if input_accessor is None:
            return None
        val = input_accessor()
        return val
    except Exception:
        return None


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


def create_filter_ui(
    data: pl.DataFrame,
    filter_metric: str,
    filter_input_id: str,
    label: str = "Filter value"
) -> ui.Tag | None:
    """
    Create dynamic filter UI based on the selected metric's data type.

    Supports categorical (selectize), numeric (range slider), and time (range slider with seconds).

    Args:
        data: Polars DataFrame containing the data
        filter_metric: Name of the column to filter on
        filter_input_id: ID for the filter input element
        label: Label for the filter input

    Returns:
        Shiny UI element (selectize for categorical, slider for numeric/time), or None
    """
    if filter_metric == "None" or not filter_metric:
        return None

    if data is None or data.is_empty():
        return None

    if filter_metric not in data.columns:
        return None

    col = data[filter_metric]

    # Time format filter (HH:MM:SS or HH:MM:SS.mmm)
    if is_time_column(col):
        time_values = col.drop_nulls().to_list()
        if not time_values:
            return None
        # Convert all times to seconds and find min/max
        seconds_values = [_time_to_seconds(t) for t in time_values]
        min_secs = min(seconds_values)
        max_secs = max(seconds_values)
        min_time_str = _seconds_to_time(min_secs)
        max_time_str = _seconds_to_time(max_secs)

        # Use numeric slider with seconds - completely timezone-agnostic
        # Keep the display text outside, colocated with load status in the header row
        return ui.input_slider(
            filter_input_id,
            label,
            min=min_secs,
            max=max_secs,
            value=[min_secs, max_secs],
            step=1
        )

    # Categorical (factor) filter
    elif col.dtype == pl.Categorical or col.dtype == pl.Utf8:
        unique_vals = sorted([str(v) for v in col.unique().to_list() if v is not None])
        if not unique_vals:
            return None

        return ui.input_selectize(
            filter_input_id,
            label,
            choices=unique_vals,
            selected=unique_vals,
            multiple=True
        )

    # Numeric filter
    elif col.dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
        values = col.drop_nulls().to_numpy()
        if len(values) == 0:
            return None

        min_val = float(values.min())
        max_val = float(values.max())

        # Check if all integers and not too diverse (use single slider)
        if col.dtype in (pl.Int64, pl.Int32):
            unique_count = col.n_unique()
            if len(values) / unique_count > 3:
                return ui.input_slider(
                    filter_input_id,
                    label,
                    min=min_val,
                    max=max_val,
                    value=min_val,
                    step=1
                )

        # Use range slider for continuous data
        return ui.input_slider(
            filter_input_id,
            label,
            min=min_val,
            max=max_val,
            value=[min_val, max_val]
        )

    return None


def apply_filter(
    data: pl.DataFrame,
    filter_metric: str,
    filter_value: Union[List[Any], int, float, str, None]
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

            # Debug: show sample values
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
    filter_value: Union[List[Any], int, float, str, dict, None],
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
