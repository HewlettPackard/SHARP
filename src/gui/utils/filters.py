"""
Reusable data filtering utilities for Shiny GUI.

Provides dynamic filter UI generation and filter application logic
for use across Profile, Explore, and Compare tabs.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Union, List, Any
import polars as pl
from shiny import ui


def create_filter_ui(
    data: pl.DataFrame,
    filter_metric: str,
    filter_input_id: str,
    label: str = "Filter value"
) -> ui.Tag | None:
    """
    Create dynamic filter UI based on the selected metric's data type.

    Args:
        data: Polars DataFrame containing the data
        filter_metric: Name of the column to filter on
        filter_input_id: ID for the filter input element
        label: Label for the filter input

    Returns:
        Shiny UI element (selectize for categorical, slider for numeric), or None
    """
    if filter_metric == "None" or not filter_metric:
        return None

    if data is None or data.is_empty():
        return None

    if filter_metric not in data.columns:
        return None

    col = data[filter_metric]

    # Categorical (factor) filter
    if col.dtype == pl.Categorical or col.dtype == pl.Utf8:
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
        # Categorical filter
        if col.dtype == pl.Categorical or col.dtype == pl.Utf8:
            if isinstance(filter_value, (list, tuple)) and len(filter_value) > 0:
                return data.filter(pl.col(filter_metric).is_in(filter_value))
            else:
                return data

        # Numeric filter
        elif col.dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
            if isinstance(filter_value, (list, tuple)) and len(filter_value) == 2:
                # Range filter
                return data.filter(
                    (pl.col(filter_metric) >= filter_value[0]) &
                    (pl.col(filter_metric) <= filter_value[1])
                )
            elif isinstance(filter_value, (int, float)):
                # Single value filter
                return data.filter(pl.col(filter_metric) == filter_value)
            else:
                return data

        return data

    except Exception:
        return data


def get_filterable_columns(data: pl.DataFrame, exclude_cols: List[str] | None = None) -> List[str]:
    """
    Get list of columns suitable for filtering (non-unique categorical or numeric).

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

        # Check for categorical/string columns with reasonable unique count
        if col.dtype == pl.Categorical or col.dtype == pl.Utf8:
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
    Check if a numeric range filter covers the full range (i.e., no actual filtering).

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

        if col.dtype not in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
            return False

        col_min = float(col.drop_nulls().min())  # type: ignore
        col_max = float(col.drop_nulls().max())  # type: ignore

        # Check if filter range matches data range (within floating point tolerance)
        return bool(abs(float(filter_value[0]) - col_min) < 1e-9 and
                abs(float(filter_value[1]) - col_max) < 1e-9)

    except Exception:
        return False
