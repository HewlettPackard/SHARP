"""
Unit tests for runlogs reader.

Tests verify:
- Loading CSV data
- Merging invariant parameters from Markdown metadata
"""

import json
import polars as pl
import pytest
from pathlib import Path

from src.core.runlogs.reader import load_runlog, load_csv


def test_load_csv_basic(tmp_path):
    """Test basic CSV loading."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text("col1,col2\n1,2\n3,4")

    df = load_csv(csv_path)
    assert df.shape == (2, 2)
    assert df["col1"][0] == 1


def test_load_runlog_legacy(tmp_path):
    """Test loading legacy CSV (no launch_id)."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text("col1,col2\n1,2\n3,4")

    df = load_runlog(csv_path)
    assert df.shape == (2, 2)
    assert "launch_id" not in df.columns


def test_load_runlog_with_invariants(tmp_path):
    """Test loading runlog with invariants in MD."""
    csv_path = tmp_path / "test.csv"
    md_path = tmp_path / "test.md"

    # Create CSV with launch_id
    csv_path.write_text("launch_id,metric\nrun1,10.5\nrun1,11.0\nrun2,20.0")

    # Create MD with invariants
    invariants = {
        "backend": {
            "type": "string",
            "description": "Backend",
            "values": {
                "run1": "docker",
                "run2": "singularity"
            }
        },
        "cores": {
            "type": "int",
            "description": "Cores",
            "values": {
                "run1": 4,
                "run2": 8
            }
        }
    }

    md_content = f"""
## Invariant parameters

Parameters are listed by name, with values keyed by launch ID.

```json
{json.dumps(invariants)}
```
"""
    md_path.write_text(md_content)

    df = load_runlog(csv_path)

    assert "backend" in df.columns
    assert "cores" in df.columns

    # Check values for run1
    run1_df = df.filter(pl.col("launch_id") == "run1")
    assert run1_df["backend"][0] == "docker"
    assert run1_df["cores"][0] == 4

    # Check values for run2
    run2_df = df.filter(pl.col("launch_id") == "run2")
    assert run2_df["backend"][0] == "singularity"
    assert run2_df["cores"][0] == 8


def test_load_runlog_missing_md(tmp_path):
    """Test loading runlog when MD file is missing."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text("launch_id,metric\nrun1,10.5")

    df = load_runlog(csv_path)
    assert "launch_id" in df.columns
    assert "metric" in df.columns
    # Should not fail, just no extra columns


def test_load_runlog_malformed_md(tmp_path):
    """Test loading runlog with malformed MD."""
    csv_path = tmp_path / "test.csv"
    md_path = tmp_path / "test.md"

    csv_path.write_text("launch_id,metric\nrun1,10.5")
    md_path.write_text("## Invariant parameters\n\n```json\n{invalid json}\n```")

    df = load_runlog(csv_path)
    assert "launch_id" in df.columns
    # Should ignore malformed JSON
