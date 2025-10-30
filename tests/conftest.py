#!/usr/bin/env python3
"""
Pytest configuration and fixtures for SHARP test suite.

© Copyright 2025 Hewlett Packard Enterprise Development LP
"""

import csv
import os
import pytest
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_backend_config():
    """Sample backend configuration for testing."""
    return {
        'backend_options': {
            'local': {
                'run': '$CMD $ARGS',
                'reset': '',
                'run_sys_spec': '$SPEC_COMMAND'
            }
        },
        'metrics': {}
    }


@pytest.fixture
def sample_benchmark_spec():
    """Sample benchmark specification for testing."""
    return {
        'task': 'test_benchmark',
        'entry_point': './test_script.py',
        'args': []
    }


@pytest.fixture
def sample_experiment_config(sample_benchmark_spec, sample_backend_config):
    """Sample experiment configuration for testing."""
    return {
        'benchmark_spec': sample_benchmark_spec,
        'backend_names': ['local'],
        'backend_options': sample_backend_config['backend_options'],
        'timeout': 3600,
        'verbose': False,
        'directory': 'runlogs',
        'start': 'normal',
        'mode': 'w',
        'skip_sys_specs': True,
        'metrics': {}
    }


class LauncherTestHelper:
    """Helper class for launcher integration testing.

    Provides utilities for running the launcher CLI and verifying results.
    """

    def __init__(self, project_root: Path):
        """Initialize launcher test helper.

        Args:
            project_root: Path to project root directory
        """
        self.project_root = project_root
        self.launcher_path = project_root / "src" / "cli" / "launch.py"
        self.runlogs_dir = "runlogs"
        self.runlogs_path = project_root / self.runlogs_dir
        self.fns_dir = project_root / "fns"
        self.experiment_name = "tests"
        self.skip_sys_specs = False

    def run_command(self, command: str) -> Tuple[str, str, int]:
        """Run a shell command and return output, error and exit status.

        Args:
            command: Shell command to execute

        Returns:
            Tuple of (stdout, stderr, returncode)
        """
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
        )
        stdout, stderr = process.communicate()
        return stdout.decode(), stderr.decode(), process.returncode

    def run_launcher(self, args: str) -> Tuple[str, str, int]:
        """Run the launcher with given arguments and return results.

        Args:
            args: String containing launcher arguments

        Returns:
            Tuple of (stdout, stderr, returncode)
        """
        # Prepend --skip-sys-specs if enabled (for faster testing)
        if self.skip_sys_specs and "--skip-sys-specs" not in args:
            args = f"--skip-sys-specs {args}"
        command = f"{self.launcher_path} {args}"
        return self.run_command(command)

    def read_csv_column(self, experiment_name: str, column_name: str, line_number: int = 0) -> str:
        """Read a specific column from a CSV results file.

        Args:
            experiment_name: Name of the experiment (used in CSV filename)
            column_name: Name of the column to read
            line_number: Which line to read (0-based, excluding header). Default is first line.

        Returns:
            The value from the specified column and line as a string

        Raises:
            FileNotFoundError: If the CSV file doesn't exist
            KeyError: If the column doesn't exist in the CSV
            IndexError: If line_number is out of range
        """
        csv_path = self.runlogs_path / f"{experiment_name}.csv"
        with open(csv_path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
            return rows[line_number][column_name]

    def count_csv_rows(self, experiment_name: str) -> int:
        """Count the number of data rows in a CSV file (excluding header).

        Args:
            experiment_name: Path to CSV file relative to runlogs directory

        Returns:
            Number of data rows in the CSV

        Raises:
            FileNotFoundError: If the CSV file doesn't exist
        """
        csv_path = self.runlogs_path / f"{experiment_name}.csv"
        with open(csv_path, newline='') as csvfile:
            return sum(1 for _ in csv.DictReader(csvfile))

    def cleanup(self):
        """Clean up runlogs directory after test."""
        if self.runlogs_path.exists():
            shutil.rmtree(self.runlogs_path)


@pytest.fixture
def launcher_helper(tmp_path, monkeypatch):
    """Fixture providing launcher test helper with automatic cleanup.

    Args:
        tmp_path: pytest's temporary path fixture
        monkeypatch: pytest's monkeypatch fixture

    Yields:
        LauncherTestHelper instance configured for testing
    """
    # Get project root (go up from tests/ to project root)
    project_root = Path(__file__).parent.parent

    # Create helper
    helper = LauncherTestHelper(project_root)

    # Change to project root for test execution
    monkeypatch.chdir(project_root)

    yield helper

    # Cleanup after test
    helper.cleanup()
