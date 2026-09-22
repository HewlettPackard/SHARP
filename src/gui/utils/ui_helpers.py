"""
Shared UI helper functions for the GUI.

Provides reusable logic for common UI patterns.

© Copyright 2025--2026 Hewlett Packard Enterprise Development LP
"""

from typing import Dict, List, Union
from src.gui.utils import ui_kit as ui
import polars as pl
import numpy as np
def get_numeric_columns(df: pl.DataFrame) -> Dict[str, str]:
    """
    Get numeric columns from DataFrame formatted for selectize choices.

    Returns:
        Dict mapping column name to label.
    """
    if df is None:
        return {}

    return {
        col: col
        for col in df.columns
        if df[col].dtype in [pl.Float64, pl.Float32, pl.Int64, pl.Int32, pl.Int16, pl.Int8, pl.UInt64, pl.UInt32, pl.UInt16, pl.UInt8]
    }

def select_preferred_metric(
    metrics: Union[List[str], Dict[str, str]],
    preferences: List[str] | None = None
) -> str:
    """
    Select a default metric from available metrics based on preference order.

    Args:
        metrics: List of metric names or dict of metric choices
        preferences: List of preferred metrics in order. Defaults to ["perf_time", "inner_time", "outer_time"]

    Returns:
        Selected metric name, or empty string if no metrics available
    """
    if preferences is None:
        preferences = ["perf_time", "inner_time", "outer_time"]

    available = list(metrics.keys()) if isinstance(metrics, dict) else metrics

    if not available:
        return ""

    for pref in preferences:
        if pref in available:
            return pref

    # If no preference found, return the first available (sorted for stability)
    return sorted(available)[0]

def find_nearest_point(
    df: pl.DataFrame | None,
    metric_col: str | None,
    hover_x: float,
    max_scatter_points: int,
    row_column: str = "__sharp_row_index__",
    rng_seed: int = 43
) -> tuple[float, str] | None:
    if df is None or df.is_empty() or not metric_col or metric_col not in df.columns:
        return None

    if "repeat" in df.columns:
        row_ids = df["repeat"].to_numpy()
        id_prefix = "repeat="
    elif row_column in df.columns:
        row_ids = df[row_column].to_numpy()
        id_prefix = "#"
    else:
        row_ids = np.arange(df.shape[0])
        id_prefix = "#"

    try:
        values = df[metric_col].to_numpy().astype(float)
    except Exception:
        return None

    finite_mask = np.isfinite(values)
    if not np.any(finite_mask):
        return None

    clean_values = values[finite_mask]
    clean_rows = row_ids[finite_mask]

    if len(clean_values) > max_scatter_points:
        rng = np.random.default_rng(rng_seed)
        scatter_idx = rng.choice(len(clean_values), size=max_scatter_points, replace=False)
        scatter_values = clean_values[scatter_idx]
        scatter_rows = clean_rows[scatter_idx]
    else:
        scatter_values = clean_values
        scatter_rows = clean_rows

    nearest = int(np.argmin(np.abs(scatter_values - hover_x)))
    nearest_value = float(scatter_values[nearest])
    nearest_row = scatter_rows[nearest]
    return nearest_value, f"{id_prefix}{nearest_row}"


def render_hover_overlay(nearest_value: float, nearest_label: str) -> ui.TagChild:
    return ui.tags.div(
        ui.tags.span("Nearest point: ", style="font-weight: 600;"),
        ui.tags.span(f"{nearest_value:.6g} ({nearest_label})"),
        style=(
            "position: absolute; bottom: 16px; left: 50%; z-index: 5; "
            "transform: translateX(-50%); pointer-events: none; "
            "display: inline-block; max-width: 75%; padding: 3px 8px; "
            "border: 1px solid #d0d7de; border-radius: 999px; "
            "background: #f6f8fa; color: #57606a; font-size: 0.85rem;"
        )
    )


def render_point_inspector(
    hover: dict[str, float] | None,
    df: pl.DataFrame | None,
    metric_col: str | None,
    max_scatter_points: int
) -> ui.TagChild:
    if not hover:
        return ui.div()

    try:
        hover_x_raw = hover.get("x")
        if hover_x_raw is None:
            return ui.div()
        hover_x = float(hover_x_raw)
    except Exception:
        return ui.div()

    nearest = find_nearest_point(df, metric_col, hover_x, max_scatter_points=max_scatter_points)
    if nearest is None:
        return ui.div()

    nearest_value, nearest_label = nearest
    return render_hover_overlay(nearest_value, nearest_label)