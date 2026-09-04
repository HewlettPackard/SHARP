"""
Unit tests for profiling data model helpers.

© Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""

import polars as pl

from src.core.profile.data_model import (
    detect_source_columns,
    detect_format,
    tall_to_wide,
    wide_to_tall,
)


def test_detect_source_columns_basic():
    data = pl.DataFrame(
        {
            "time": [1, 2, 3, 4],
            "host": ["h1", "h1", "h2", "h2"],
            "rank": [0, 0, 1, 1],
            "metric": [10.0, 11.0, 12.0, 13.0],
        }
    )

    detected = detect_source_columns(data)
    assert set(detected) == {"host", "rank"}


def test_detect_format_tall_with_sources():
    data = pl.DataFrame(
        {
            "host": ["h1", "h1", "h2", "h2"],
            "metric": [1, 2, 3, 4],
        }
    )

    fmt = detect_format(data, source_columns=["host"])
    assert fmt == "tall"


def test_detect_format_wide_by_pattern():
    """Wide format detected by source column name patterns in column names."""
    data = pl.DataFrame(
        {
            "time": [1, 2, 3, 4],
            "metric_a__host_h1": [10, 11, 12, 13],
            "metric_a__host_h2": [20, 21, 22, 23],
            "metric_b__host_h1": [100, 110, 120, 130],
            "metric_b__host_h2": [200, 210, 220, 230],
        }
    )

    fmt = detect_format(data)
    assert fmt == "wide"


def test_tall_to_wide_round_trip():
    data = pl.DataFrame(
        {
            "time": [1, 1, 2, 2],
            "host": ["h1", "h2", "h1", "h2"],
            "metric_a": [10, 20, 11, 21],
            "metric_b": [100, 200, 110, 210],
        }
    )

    wide = tall_to_wide(
        data,
        source_columns=["host"],
        metric_columns=["metric_a", "metric_b"],
        index_columns=["time"],
    )

    tall = wide_to_tall(
        wide,
        source_columns=["host"],
        index_columns=["time"],
    )

    expected = data.sort(["time", "host"])
    result = tall.sort(["time", "host"]).select(expected.columns)

    assert result.equals(expected)
