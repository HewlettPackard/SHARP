#!/usr/bin/env python3
"""
Unit tests for profile file detection and loading utilities.

Tests the file state detection, path resolution, and validation
functions used in the profile workflow.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
from pathlib import Path
import polars as pl

from src.gui.utils.profile.files import (
    detect_file_state,
    get_markdown_path,
    validate_markdown,
    load_csv_with_validation,
)
from src.gui.utils.profile.execution import determine_task_name_for_profiling


class TestDetectFileState:
    """Tests for detect_file_state function."""

    def test_original_csv_only(self, tmp_path):
        """Test detection when only original CSV exists."""
        csv_path = tmp_path / "task.csv"
        csv_path.write_text("col1,col2\n1,2\n")

        md_path = tmp_path / "task.md"
        md_path.write_text("# Task metadata\n")

        state, paths = detect_file_state(str(csv_path))

        assert paths["csv"] == csv_path
        assert paths["md"] == md_path
        assert "prof_csv" not in paths or not paths.get("prof_csv", Path("nonexistent")).exists()

    def test_original_csv_with_prof(self, tmp_path):
        """Test detection when both original and prof CSV exist."""
        csv_path = tmp_path / "task.csv"
        csv_path.write_text("col1,col2\n1,2\n")

        prof_csv_path = tmp_path / "task-prof.csv"
        prof_csv_path.write_text("col1,col2,perf_time\n1,2,0.5\n")

        md_path = tmp_path / "task.md"
        md_path.write_text("# Task metadata\n")

        state, paths = detect_file_state(str(csv_path))

        assert paths["csv"] == csv_path
        assert paths["prof_csv"] == prof_csv_path

    def test_prof_csv_resolves_to_original(self, tmp_path):
        """Test that selecting -prof.csv resolves original paths."""
        csv_path = tmp_path / "task.csv"
        csv_path.write_text("col1,col2\n1,2\n")

        prof_csv_path = tmp_path / "task-prof.csv"
        prof_csv_path.write_text("col1,col2,perf_time\n1,2,0.5\n")

        md_path = tmp_path / "task.md"
        md_path.write_text("# Task metadata\n")

        state, paths = detect_file_state(str(prof_csv_path))

        assert paths["csv"] == csv_path
        assert paths["prof_csv"] == prof_csv_path


class TestGetMarkdownPath:
    """Tests for get_markdown_path function."""

    def test_csv_to_md(self, tmp_path):
        """Test CSV path converts to MD path."""
        csv_path = tmp_path / "task.csv"

        md_path = get_markdown_path(str(csv_path))

        assert Path(md_path) == tmp_path / "task.md"

    def test_prof_csv_to_prof_md(self, tmp_path):
        """Test -prof.csv converts to -prof.md."""
        prof_csv = tmp_path / "task-prof.csv"

        md_path = get_markdown_path(str(prof_csv))

        assert Path(md_path) == tmp_path / "task-prof.md"


class TestValidateMarkdown:
    """Tests for validate_markdown function."""

    def test_valid_markdown(self, tmp_path):
        """Test validation of valid markdown file."""
        md_path = tmp_path / "task.md"
        md_path.write_text("""Experiment completed.

## Runtime options

```json
{
  "timeout": 3600,
  "repeats": "10",
  "entry_point": "test_benchmark"
}
```

## Measured Fields

- inner_time
""")

        is_valid, error = validate_markdown(md_path)

        assert is_valid is True

    def test_missing_markdown(self, tmp_path):
        """Test validation of non-existent file."""
        md_path = tmp_path / "nonexistent.md"

        is_valid, error = validate_markdown(md_path)

        assert is_valid is False


class TestLoadCsvWithValidation:
    """Tests for load_csv_with_validation function."""

    def test_load_valid_csv(self, tmp_path):
        """Test loading a valid CSV file."""
        csv_path = tmp_path / "data.csv"
        csv_path.write_text("col1,col2\n1,2\n3,4\n")

        data, error = load_csv_with_validation(str(csv_path))

        assert error is None
        assert data is not None
        assert len(data) == 2
        assert "col1" in data.columns

    def test_load_missing_csv(self, tmp_path):
        """Test loading non-existent CSV."""
        csv_path = tmp_path / "nonexistent.csv"

        data, error = load_csv_with_validation(str(csv_path))

        assert data is None
        assert error is not None


class TestDetermineTaskNameForProfiling:
    """Tests for determine_task_name_for_profiling function."""

    def test_original_md_gets_prof_suffix(self, tmp_path):
        """Test that original markdown gets -prof suffix."""
        md_path = tmp_path / "task.md"
        md_path.write_text("# metadata\n")

        task_name = determine_task_name_for_profiling(str(md_path))

        assert task_name == "task-prof"

    def test_prof_md_keeps_name(self, tmp_path):
        """Test that -prof.md keeps the same name."""
        md_path = tmp_path / "task-prof.md"
        md_path.write_text("# metadata\n")

        task_name = determine_task_name_for_profiling(str(md_path))

        assert task_name == "task-prof"
