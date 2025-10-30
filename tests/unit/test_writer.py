"""
Unit tests for RunLogger - experiment logging to CSV and Markdown.

Tests verify:
- Column (shared) and row (per-run) data handling
- CSV generation with merged columns + rows
- Markdown generation with metadata and system specs
- Directory creation and file handling
"""

import pytest
import csv
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.core.logging.writer import RunLogger


# ========== Test RunLogger basic functionality ==========

def test_init_creates_experiment_directory(tmp_path) -> None:
    """Test that __init__ creates experiment directory."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})

    exp_dir = tmp_path / "test_exp"
    assert exp_dir.exists(), "Experiment directory should be created"


def test_init_nested_experiment_directory(tmp_path) -> None:
    """Test that __init__ creates nested experiment directory."""
    logger = RunLogger(str(tmp_path), "nested/deep/exp", "test_task", {})

    exp_dir = tmp_path / "nested" / "deep" / "exp"
    assert exp_dir.exists(), "Nested experiment directory should be created"


def test_add_column_single(tmp_path) -> None:
    """Test adding a single column."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})
    logger.add_column("runtime", "45.3", "float", "Total runtime in seconds")

    assert len(logger._columns) == 1
    assert logger._columns["runtime"] == "45.3"


def test_add_column_multiple(tmp_path) -> None:
    """Test adding multiple columns."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})
    logger.add_column("backend", "docker", "string", "Execution backend")
    logger.add_column("version", "1.2", "string", "Software version")

    assert len(logger._columns) == 2
    assert logger._columns["backend"] == "docker"
    assert logger._columns["version"] == "1.2"


def test_add_row_data_single_row(tmp_path) -> None:
    """Test adding data for a single row."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})
    logger.add_row_data("iteration", 1, "int", "Run iteration number")
    logger.add_row_data("latency", 12.5, "float", "Latency in ms")

    assert len(logger._rows) == 1
    assert logger._rows[0]["iteration"] == 1
    assert logger._rows[0]["latency"] == 12.5


def test_add_row_data_multiple_rows(tmp_path) -> None:
    """Test adding data for multiple rows."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})

    # First row
    logger.add_row_data("iteration", 1, "int", "Run iteration")
    logger.add_row_data("latency", 12.5, "float", "Latency in ms")

    # Second row (new fields trigger new row)
    logger.add_row_data("iteration", 2, "int", "Run iteration")
    logger.add_row_data("latency", 13.1, "float", "Latency in ms")

    assert len(logger._rows) == 2
    assert logger._rows[0]["iteration"] == 1
    assert logger._rows[1]["iteration"] == 2


def test_clear_rows(tmp_path) -> None:
    """Test that clear_rows resets row data but keeps columns."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})
    logger.add_column("backend", "docker", "string", "Backend")
    logger.add_row_data("iteration", 1, "int", "Iteration")

    assert len(logger._rows) == 1
    assert len(logger._columns) == 1

    logger.clear_rows()

    assert len(logger._rows) == 0
    assert len(logger._columns) == 1, "Columns should persist"
    assert logger._columns["backend"] == "docker"


def test_save_csv_basic(tmp_path) -> None:
    """Test CSV generation with columns and rows."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})

    # Add shared column
    logger.add_column("backend", "docker", "string", "Execution backend")

    # Add two rows
    logger.add_row_data("iteration", 1, "int", "Iteration number")
    logger.add_row_data("latency", 10.5, "float", "Latency ms")

    logger.add_row_data("iteration", 2, "int", "Iteration number")
    logger.add_row_data("latency", 11.2, "float", "Latency ms")

    logger.save_csv()

    # Verify CSV file exists and has correct content
    csv_path = f"{logger._base_path}.csv"
    assert os.path.exists(csv_path), "CSV file should be created"

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 2, "CSV should have 2 rows"
    assert rows[0]["backend"] == "docker"
    assert rows[0]["iteration"] == "1"
    assert rows[0]["latency"] == "10.5"
    assert rows[1]["iteration"] == "2"
    assert rows[1]["latency"] == "11.2"


def test_save_csv_append_mode(tmp_path) -> None:
    """Test CSV append mode."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})
    logger.add_column("backend", "docker", "string", "Backend")
    logger.add_row_data("iteration", 1, "int", "Iteration")
    logger.add_row_data("latency", 10.5, "float", "Latency")

    logger.save_csv(mode="w")

    # Append second row
    logger.clear_rows()
    logger.add_row_data("iteration", 2, "int", "Iteration")
    logger.add_row_data("latency", 11.2, "float", "Latency")
    logger.save_csv(mode="a")

    # Verify both rows in CSV
    csv_path = f"{logger._base_path}.csv"
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 2, "CSV should have 2 rows after append"


def test_save_md_basic(tmp_path) -> None:
    """Test Markdown generation with preamble and field descriptions."""
    options = {"verbose": False, "backend": "docker"}
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", options)

    logger.add_column("backend", "docker", "string", "Execution backend")
    logger.add_row_data("iteration", 1, "int", "Iteration number")
    logger.add_row_data("latency", 10.5, "float", "Latency in ms")

    logger.save_md()

    # Verify markdown file exists
    md_path = f"{logger._base_path}.md"
    assert os.path.exists(md_path), "Markdown file should be created"

    with open(md_path, "r") as f:
        content = f.read()

    # Verify key sections
    assert "Field description" in content
    assert "`backend` (string)" in content
    assert "`iteration` (int)" in content
    assert "`latency` (float)" in content


def test_save_md_with_system_specs(tmp_path) -> None:
    """Test Markdown generation with system configuration section."""
    options = {}
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", options)

    sys_specs = {
        "cpu": "Intel Xeon",
        "memory_gb": 256,
        "os": "Linux"
    }

    logger.save_md(sys_specs=sys_specs)

    md_path = f"{logger._base_path}.md"
    with open(md_path, "r") as f:
        content = f.read()

    assert "System configuration" in content
    assert "Intel Xeon" in content
    assert "256" in content


def test_save_md_skip_append_if_exists(tmp_path) -> None:
    """Test that append mode skips writing if file exists."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})

    # Write initial markdown
    logger.save_md(mode="w")
    md_path = f"{logger._base_path}.md"

    # Get initial size
    initial_size = os.path.getsize(md_path)

    # Append (should do nothing)
    logger.save_md(mode="a")

    # Size should not change
    final_size = os.path.getsize(md_path)
    assert initial_size == final_size, "Append should not write if file exists"


def test_metadata_tracking(tmp_path) -> None:
    """Test that metadata is tracked for columns and rows."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})

    logger.add_column("backend", "docker", "string", "Execution backend")
    logger.add_row_data("iteration", 1, "int", "Iteration number")

    assert "backend" in logger._metadata
    assert "iteration" in logger._metadata

    assert logger._metadata["backend"]["type"] == "string"
    assert logger._metadata["iteration"]["type"] == "int"
    assert logger._metadata["backend"]["desc"] == "Execution backend"


def test_duplicate_field_updates_metadata(tmp_path) -> None:
    """Test that redefining a field updates metadata consistently."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})

    logger.add_column("backend", "docker", "string", "Original description")
    # Add same field again (metadata should be from first definition)
    logger.add_column("backend", "singularity", "string", "Different description")

    assert logger._metadata["backend"]["desc"] == "Original description"


def test_preamble_includes_options(tmp_path) -> None:
    """Test that preamble includes runtime options in JSON format."""
    options = {
        "backend": "docker",
        "debug": True,
        "iterations": 10,
        "sys_spec_commands": {"cpu": "lscpu"}  # Should be excluded
    }
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", options)

    assert "docker" in logger._preamble
    assert "true" in logger._preamble
    assert "sys_spec_commands" not in logger._preamble


@patch("src.core.logging.writer.subprocess.run")
def test_preamble_includes_git_hash(mock_run: MagicMock, tmp_path) -> None:
    """Test that preamble includes git hash when available."""
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "abc1234\n"

    options = {}
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", options)

    assert "abc1234" in logger._preamble


def test_preamble_handles_missing_git(tmp_path) -> None:
    """Test that preamble handles missing git gracefully."""
    with patch("src.core.logging.writer.subprocess.run", side_effect=FileNotFoundError):
        options = {}
        logger = RunLogger(str(tmp_path), "test_exp", "test_task", options)

        # Preamble should be generated without git hash
        assert logger._preamble is not None
        assert "git hash:" not in logger._preamble.lower()


def test_task_name_extraction_from_path(tmp_path) -> None:
    """Test that task name is extracted from path (last component)."""
    logger = RunLogger(str(tmp_path), "test_exp", "path/to/task_name", {})

    # Base path should end with task_name, not the full path
    assert logger._base_path.endswith("task_name")
    assert not "path" in logger._base_path.split("/")[-1]


# ========== Test edge cases and error conditions ==========

def test_save_csv_fails_with_no_rows(tmp_path) -> None:
    """Test that save_csv raises AssertionError with no rows."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})
    logger.add_column("backend", "docker", "string", "Backend")

    with pytest.raises(AssertionError):
        logger.save_csv()


def test_add_row_data_creates_new_row_when_field_repeated(tmp_path) -> None:
    """Test that adding same field twice creates new row."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})

    logger.add_row_data("iteration", 1, "int", "Iteration")
    assert len(logger._rows) == 1

    # Adding same field again should create new row
    logger.add_row_data("iteration", 2, "int", "Iteration")
    assert len(logger._rows) == 2


def test_empty_experiment_name(tmp_path) -> None:
    """Test that empty experiment name works (creates topdir directly)."""
    logger = RunLogger(str(tmp_path), "", "test_task", {})
    # Should still create base_path successfully
    assert logger._base_path is not None
