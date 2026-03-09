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
import re
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.core.runlogs import RunLogger


def _extract_invariants(md_path: Path) -> dict:
    content = md_path.read_text()
    match = re.search(r"## Invariant parameters.*?```json\s+(.*?)\s+```", content, re.DOTALL)
    assert match, "Invariant block missing in markdown"
    return json.loads(match.group(1))


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


def test_add_invariant_single(tmp_path) -> None:
    """Test adding a single invariant."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})
    logger.add_invariant("runtime", "45.3", "float", "Total runtime in seconds")

    assert len(logger._constants) == 1
    assert logger._constants["runtime"]["value"] == "45.3"


def test_add_invariant_multiple(tmp_path) -> None:
    """Test adding multiple invariants."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})
    logger.add_invariant("backend", "docker", "string", "Execution backend")
    logger.add_invariant("version", "1.2", "string", "Software version")

    assert len(logger._constants) == 2
    assert logger._constants["backend"]["value"] == "docker"
    assert logger._constants["version"]["value"] == "1.2"


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
    """Test that clear_rows resets row data but keeps constants."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})
    logger.add_invariant("backend", "docker", "string", "Backend")
    logger.add_row_data("iteration", 1, "int", "Iteration")

    assert len(logger._rows) == 1
    assert len(logger._constants) == 1

    logger.clear_rows()

    assert len(logger._rows) == 0
    assert len(logger._constants) == 1, "Invariants should persist"
    assert logger._constants["backend"]["value"] == "docker"


def test_save_csv_basic(tmp_path) -> None:
    """Test CSV generation with invariants and rows."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})

    # Add constant (should NOT be in CSV)
    logger.add_invariant("backend", "docker", "string", "Execution backend")

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
    assert "launch_id" in rows[0], "CSV should have launch_id"
    assert "backend" not in rows[0], "CSV should NOT have invariants"
    assert rows[0]["iteration"] == "1"
    assert rows[0]["latency"] == "10.5"
    assert rows[1]["iteration"] == "2"
    assert rows[1]["latency"] == "11.2"


def test_save_csv_append_mode(tmp_path) -> None:
    """Test CSV append mode."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})
    logger.add_invariant("backend", "docker", "string", "Backend")
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
    assert rows[0]["launch_id"] == rows[1]["launch_id"], "Launch ID should be same for same logger instance"


def test_save_md_basic(tmp_path) -> None:
    """Test Markdown generation with preamble and field descriptions."""
    options = {"verbose": False, "backend": "docker"}
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", options)

    logger.add_invariant("backend", "docker", "string", "Execution backend")
    logger.add_row_data("iteration", 1, "int", "Iteration number")
    logger.add_row_data("latency", 10.5, "float", "Latency in ms")

    logger.save_md()

    # Verify markdown file exists
    md_path = f"{logger._base_path}.md"
    assert os.path.exists(md_path), "Markdown file should be created"

    with open(md_path, "r") as f:
        content = f.read()

    # Verify key sections
    assert "CSV field description" in content
    assert "`launch_id` (string)" in content
    assert "`iteration` (int)" in content
    assert "`latency` (float)" in content

    # Verify invariant sections
    assert "Invariant field description" in content
    assert "Invariant parameters" in content

    # Backend should be in invariant field description, not CSV field description
    csv_section = content.split("## Invariant field description")[0]
    invariant_section = content.split("## Invariant field description")[1].split("## Invariant parameters")[0]
    assert "`backend` (string)" not in csv_section, "Invariants should not be in CSV field description"
    assert "`backend` (string)" in invariant_section, "Invariants should be in Invariant field description"

    assert "Initial runtime options" in content


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

    assert "Initial system configuration" in content
    assert "Intel Xeon" in content
    assert "256" in content


def test_save_md_appends_invariants(tmp_path) -> None:
    """Test that append mode updates invariants."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})
    logger.add_invariant("run", "1", "int", "Run 1")

    # Write initial markdown
    logger.save_md(mode="w")
    md_path = f"{logger._base_path}.md"

    # Create new logger (simulating new run)
    logger2 = RunLogger(str(tmp_path), "test_exp", "test_task", {})
    logger2.add_invariant("run", "2", "int", "Run 2")

    # Append
    logger2.save_md(mode="a")

    invariants = _extract_invariants(Path(md_path))
    # New structure: { launch_id: { param: value, ... }, ... }
    assert logger._launch_id in invariants
    assert logger2._launch_id in invariants
    assert invariants[logger._launch_id]["run"] == "1"
    assert invariants[logger2._launch_id]["run"] == "2"


def test_metadata_tracking(tmp_path) -> None:
    """Test that metadata is tracked for invariants and rows."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})

    logger.add_invariant("backend", "docker", "string", "Execution backend")
    logger.add_row_data("iteration", 1, "int", "Iteration number")

    assert "backend" in logger._metadata
    assert "iteration" in logger._metadata

    assert logger._metadata["backend"]["type"] == "string"
    assert logger._metadata["iteration"]["type"] == "int"
    assert logger._metadata["backend"]["desc"] == "Execution backend"


def test_duplicate_field_updates_metadata(tmp_path) -> None:
    """Test that redefining a field updates metadata consistently."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})

    logger.add_invariant("backend", "docker", "string", "Original description")
    # Add same field again (metadata should be from first definition)
    logger.add_invariant("backend", "singularity", "string", "Different description")

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


@patch("src.core.runlogs.writer.subprocess.run")
def test_preamble_includes_git_hash(mock_run: MagicMock, tmp_path) -> None:
    """Test that preamble includes git hash when available."""
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "abc1234\n"

    options = {}
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", options)

    assert "abc1234" in logger._preamble


def test_preamble_handles_missing_git(tmp_path) -> None:
    """Test that preamble handles missing git gracefully."""
    with patch("src.core.runlogs.writer.subprocess.run", side_effect=FileNotFoundError):
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
    logger.add_invariant("backend", "docker", "string", "Backend")

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


def test_repeated_field_records_distinct_values(tmp_path) -> None:
    """Ensure repeated columns keep their values across multiple rows."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})

    # First row: rank 0, measurement 1
    logger.add_row_data("rank", 0, "int", "MPI rank")
    logger.add_row_data("value", 1, "int", "Sample value")

    # Second row: rank 1, measurement 2 (should be a new row)
    logger.add_row_data("rank", 1, "int", "MPI rank")
    logger.add_row_data("value", 2, "int", "Sample value")

    assert logger._rows[0]["rank"] == 0
    assert logger._rows[1]["rank"] == 1


def test_empty_experiment_name(tmp_path) -> None:
    """Test that empty experiment name works (creates topdir directly)."""
    logger = RunLogger(str(tmp_path), "", "test_task", {})
    # Should still create base_path successfully
    assert logger._base_path is not None


def test_markdown_includes_row_count(tmp_path) -> None:
    """Test that markdown includes total rows count in summary line."""
    logger = RunLogger(str(tmp_path), "test_exp", "test_task", {})

    # Add multiple rows
    logger.add_row_data("iteration", 1, "int", "Iteration")
    logger.add_row_data("latency", 10.5, "float", "Latency")

    logger.add_row_data("iteration", 2, "int", "Iteration")
    logger.add_row_data("latency", 11.2, "float", "Latency")

    logger.add_row_data("iteration", 3, "int", "Iteration")
    logger.add_row_data("latency", 12.0, "float", "Latency")

    logger.save_md()

    md_path = f"{logger._base_path}.md"
    with open(md_path, "r") as f:
        content = f.read()

    # Verify row count appears in summary line
    assert "total rows: 3" in content, "Markdown should include row count"
