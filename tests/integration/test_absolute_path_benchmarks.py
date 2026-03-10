#!/usr/bin/env python3
"""
Test that absolute paths to benchmarks still load their metrics.

This test ensures that when a benchmark is specified by absolute path
(e.g., from a --repro run), the benchmark's metrics are still loaded
from its YAML definition.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
from pathlib import Path


def test_absolute_path_loads_benchmark_metrics(launcher_helper) -> None:
    """Test that using absolute path to benchmark loads its metrics."""
    # Get the absolute path to matmul benchmark
    matmul_path = Path(__file__).parent.parent.parent / "benchmarks" / "micro" / "cpu" / "matmul.py"
    assert matmul_path.exists(), f"matmul.py not found at {matmul_path}"

    # Run with absolute path (simulating what happens on rerun)
    stdout, stderr, returncode = launcher_helper.run_launcher(
        f'-d {launcher_helper.runlogs_dir} -e {launcher_helper.experiment_name} '
        f'-t abs_path_test --skip-sys-specs {matmul_path} 100'
    )

    assert returncode == 0, f"Command failed with code {returncode}\nstdout: {stdout}\nstderr: {stderr}"
    assert stderr == "", f"Expected empty stderr, got: {stderr}"

    # Check that inner_time metric was extracted (from benchmark YAML)
    csv_path = launcher_helper.runlogs_path / launcher_helper.experiment_name / "abs_path_test.csv"
    assert csv_path.exists(), f"CSV not found at {csv_path}"

    with open(csv_path, 'r') as f:
        header = f.readline().strip()
        assert "inner_time" in header, \
            f"inner_time metric missing from CSV (absolute path didn't load benchmark YAML). Header: {header}"

    # Verify inner_time has a value (not NA)
    inner_time = launcher_helper.read_csv_column(f"{launcher_helper.experiment_name}/abs_path_test", "inner_time", 0)
    assert inner_time != "NA", "inner_time should have been extracted, not NA"
    assert inner_time != "", "inner_time should not be empty"


def test_absolute_path_with_backend_metrics(launcher_helper) -> None:
    """Test that absolute path benchmarks work with backend metrics too."""
    matmul_path = Path(__file__).parent.parent.parent / "benchmarks" / "micro" / "cpu" / "matmul.py"
    assert matmul_path.exists(), f"matmul.py not found at {matmul_path}"

    # Run with bintime backend to get both backend and benchmark metrics
    stdout, stderr, returncode = launcher_helper.run_launcher(
        f'-d {launcher_helper.runlogs_dir} -e {launcher_helper.experiment_name} '
        f'-t abs_path_bintime -b bintime --skip-sys-specs {matmul_path} 100'
    )

    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", f"Expected empty stderr, got: {stderr}"

    # Check that both backend metrics (max_rss) and benchmark metrics (inner_time) are present
    csv_path = launcher_helper.runlogs_path / launcher_helper.experiment_name / "abs_path_bintime.csv"
    with open(csv_path, 'r') as f:
        header = f.readline().strip()
        assert "max_rss" in header, f"max_rss (backend metric) missing. Header: {header}"
        assert "inner_time" in header, f"inner_time (benchmark metric) missing. Header: {header}"

    # Verify both metrics have values
    max_rss = launcher_helper.read_csv_column(f"{launcher_helper.experiment_name}/abs_path_bintime", "max_rss", 0)
    inner_time = launcher_helper.read_csv_column(f"{launcher_helper.experiment_name}/abs_path_bintime", "inner_time", 0)
    assert max_rss != "NA" and max_rss != "", "max_rss should have a value"
    assert inner_time != "NA" and inner_time != "", "inner_time should have a value"
