# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Unit tests for multi-task CSV merging in the profile workflow."""

import tempfile
from pathlib import Path

import polars as pl
import pytest

from src.gui.utils.profile.files import load_and_merge_tasks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(path: Path, df: pl.DataFrame) -> None:
    df.write_csv(path)


# ---------------------------------------------------------------------------
# Single-task passthrough
# ---------------------------------------------------------------------------

class TestSingleTask:
    """Single task must return the original path and an unchanged DataFrame."""

    def test_returns_original_path(self, tmp_path):
        csv = tmp_path / "a.csv"
        _write_csv(csv, pl.DataFrame({"x": [1, 2], "y": [3, 4]}))

        df, path = load_and_merge_tasks([("task_a", str(csv))])

        assert path == str(csv)

    def test_returns_data_unchanged(self, tmp_path):
        csv = tmp_path / "a.csv"
        _write_csv(csv, pl.DataFrame({"x": [1, 2], "y": [3, 4]}))

        df, _ = load_and_merge_tasks([("task_a", str(csv))])

        assert df.shape == (2, 2)
        assert "x" in df.columns

    def test_no_task_column_added_for_single(self, tmp_path):
        csv = tmp_path / "a.csv"
        _write_csv(csv, pl.DataFrame({"x": [1, 2]}))

        df, _ = load_and_merge_tasks([("task_a", str(csv))])

        assert "task" not in df.columns


# ---------------------------------------------------------------------------
# Multi-task merging
# ---------------------------------------------------------------------------

class TestMultiTaskMerge:
    """Multi-task merging with identical column sets."""

    def test_row_count_is_sum(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        _write_csv(a, pl.DataFrame({"x": [1, 2]}))
        _write_csv(b, pl.DataFrame({"x": [3, 4, 5]}))

        df, _ = load_and_merge_tasks([("ta", str(a)), ("tb", str(b))])

        assert df.height == 5

    def test_task_column_prepended(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        _write_csv(a, pl.DataFrame({"x": [1]}))
        _write_csv(b, pl.DataFrame({"x": [2]}))

        df, _ = load_and_merge_tasks([("alpha", str(a)), ("beta", str(b))])

        assert df.columns[0] == "task"

    def test_task_values_match_names(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        _write_csv(a, pl.DataFrame({"x": [1, 2]}))
        _write_csv(b, pl.DataFrame({"x": [3]}))

        df, _ = load_and_merge_tasks([("alpha", str(a)), ("beta", str(b))])

        tasks = df["task"].to_list()
        assert tasks.count("alpha") == 2
        assert tasks.count("beta") == 1

    def test_returns_temp_path(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        _write_csv(a, pl.DataFrame({"x": [1]}))
        _write_csv(b, pl.DataFrame({"x": [2]}))

        _, path = load_and_merge_tasks([("ta", str(a)), ("tb", str(b))])

        assert Path(path).exists()
        assert "sharp_merged_" in Path(path).name

    def test_temp_path_is_deterministic(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        _write_csv(a, pl.DataFrame({"x": [1]}))
        _write_csv(b, pl.DataFrame({"x": [2]}))

        pairs = [("ta", str(a)), ("tb", str(b))]
        _, path1 = load_and_merge_tasks(pairs)
        _, path2 = load_and_merge_tasks(pairs)

        assert path1 == path2


# ---------------------------------------------------------------------------
# Disjoint columns (outer union / NA filling)
# ---------------------------------------------------------------------------

class TestDisjointColumns:
    """Columns present in one CSV but absent from others get null values."""

    def test_missing_columns_filled_with_null(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        _write_csv(a, pl.DataFrame({"x": [1, 2], "only_a": [10, 20]}))
        _write_csv(b, pl.DataFrame({"x": [3], "only_b": [30]}))

        df, _ = load_and_merge_tasks([("ta", str(a)), ("tb", str(b))])

        assert "only_a" in df.columns
        assert "only_b" in df.columns
        # Rows from file b have null for only_a; rows from a have null for only_b
        assert df.filter(pl.col("task") == "tb")["only_a"].is_null().all()
        assert df.filter(pl.col("task") == "ta")["only_b"].is_null().all()

    def test_shared_columns_kept_single(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        _write_csv(a, pl.DataFrame({"x": [1], "shared": [100]}))
        _write_csv(b, pl.DataFrame({"x": [2], "shared": [200]}))

        df, _ = load_and_merge_tasks([("ta", str(a)), ("tb", str(b))])

        assert df.columns.count("shared") == 1

    def test_column_union_across_three_tasks(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        c = tmp_path / "c.csv"
        _write_csv(a, pl.DataFrame({"m": [1], "col_a": [1]}))
        _write_csv(b, pl.DataFrame({"m": [2], "col_b": [2]}))
        _write_csv(c, pl.DataFrame({"m": [3], "col_c": [3]}))

        df, _ = load_and_merge_tasks([("ta", str(a)), ("tb", str(b)), ("tc", str(c))])

        assert {"task", "m", "col_a", "col_b", "col_c"} <= set(df.columns)
        assert df.height == 3


# ---------------------------------------------------------------------------
# CSV already has a task column
# ---------------------------------------------------------------------------

class TestExistingTaskColumn:
    """When the CSV already has a 'task' column its values are preserved."""

    def test_existing_task_column_preserved(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        _write_csv(a, pl.DataFrame({"task": ["run1", "run2"], "x": [1, 2]}))
        _write_csv(b, pl.DataFrame({"x": [3], "task": ["run3"]}))

        df, _ = load_and_merge_tasks([("name_a", str(a)), ("name_b", str(b))])

        tasks = set(df["task"].to_list())
        # Original CSV values are preserved, not overwritten by task name
        assert tasks == {"run1", "run2", "run3"}

    def test_task_column_remains_first(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        # task column not in first position in source file
        _write_csv(a, pl.DataFrame({"x": [1], "task": ["t1"]}))
        _write_csv(b, pl.DataFrame({"x": [2], "task": ["t2"]}))

        df, _ = load_and_merge_tasks([("na", str(a)), ("nb", str(b))])

        assert df.columns[0] == "task"


# ---------------------------------------------------------------------------
# Type coercion (diagonal_relaxed)
# ---------------------------------------------------------------------------

class TestTypeCoercion:
    """Mismatched column types are coerced to a common supertype."""

    def test_int_and_float_coerced(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        # polars reads bare integers from CSV as Int64, floats as Float64
        # Writing a float-looking value forces Float64 on read
        a.write_text("x\n1\n2\n")
        b.write_text("x\n1.5\n2.5\n")

        df, _ = load_and_merge_tasks([("ta", str(a)), ("tb", str(b))])

        assert df.height == 4
        assert df["x"].dtype in (pl.Float64, pl.Float32)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Guard rails and edge-case behaviour."""

    def test_empty_pairs_raises(self):
        with pytest.raises(ValueError):
            load_and_merge_tasks([])

    def test_three_tasks_row_count(self, tmp_path):
        csvs = []
        for i in range(3):
            p = tmp_path / f"t{i}.csv"
            _write_csv(p, pl.DataFrame({"v": [i, i + 10]}))
            csvs.append((f"task{i}", str(p)))

        df, _ = load_and_merge_tasks(csvs)

        assert df.height == 6
        assert df["task"].n_unique() == 3
