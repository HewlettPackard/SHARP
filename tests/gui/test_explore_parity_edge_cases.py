# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
from __future__ import annotations

from pathlib import Path

import polars as pl

from src.gui.utils.filters import apply_filter, get_filterable_columns
from src.gui.services.explore import _load_filtered_dataframe, load_explore_dataset


def _build_edge_case_csv(tmp_path: Path) -> Path:
    df = pl.DataFrame(
        {
            "num": [1, 2, 3, 4, 5],
            "const_num": [7, 7, 7, 7, 7],
            "cat": ["a", "b", "a", "c", "c"],
            "id_str": ["u1", "u2", "u3", "u4", "u5"],
            "time": ["00:00:01", "00:00:02", "00:00:03", "00:00:04", "00:00:05"],
        }
    )
    path = tmp_path / "edge.csv"
    df.write_csv(path)
    return path


def test_filterable_metrics_match_old_gui_rules(tmp_path: Path) -> None:
    csv_path = _build_edge_case_csv(tmp_path)
    df = pl.read_csv(csv_path)

    old_filterable = get_filterable_columns(df)
    new_filterable = load_explore_dataset("tmp", str(csv_path))["filter_metrics"]

    assert new_filterable == old_filterable


def test_categorical_multiselect_filter_matches_old_gui(tmp_path: Path) -> None:
    csv_path = _build_edge_case_csv(tmp_path)
    df = pl.read_csv(csv_path)

    old_filtered = apply_filter(df, "cat", ["a", "c"])
    new_filtered = _load_filtered_dataframe(str(csv_path), "cat", None, filter_values=["a", "c"])

    assert new_filtered.height == old_filtered.height


def test_numeric_range_filter_matches_old_gui(tmp_path: Path) -> None:
    csv_path = _build_edge_case_csv(tmp_path)
    df = pl.read_csv(csv_path)

    old_filtered = apply_filter(df, "num", [2, 4])
    new_filtered = _load_filtered_dataframe(str(csv_path), "num", None, filter_min="2", filter_max="4")

    assert new_filtered.height == old_filtered.height


def test_time_range_filter_matches_old_gui(tmp_path: Path) -> None:
    csv_path = _build_edge_case_csv(tmp_path)
    df = pl.read_csv(csv_path)

    old_filtered = apply_filter(df, "time", [2, 4])
    new_filtered = _load_filtered_dataframe(
        str(csv_path),
        "time",
        None,
        filter_min="00:00:02",
        filter_max="00:00:04",
    )

    assert new_filtered.height == old_filtered.height


def test_invalid_time_filter_is_noop_like_old_gui(tmp_path: Path) -> None:
    csv_path = _build_edge_case_csv(tmp_path)
    df = pl.read_csv(csv_path)

    old_filtered = apply_filter(df, "time", ["bad", "value"])
    new_filtered = _load_filtered_dataframe(
        str(csv_path),
        "time",
        None,
        filter_min="bad",
        filter_max="value",
    )

    assert new_filtered.height == old_filtered.height == df.height
