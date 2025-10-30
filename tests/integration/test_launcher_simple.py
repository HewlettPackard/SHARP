#!/usr/bin/env python3
"""
Tests to ensure launcher.py handles command-line operations correctly.

This test suite verifies that the launcher script processes command-line inputs
appropriately, including handling missing arguments, displaying help messages,
executing basic commands, and managing error cases.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

import os
import pytest


@pytest.fixture
def helper(launcher_helper, request):
    """Configure launcher helper for simple tests."""
    launcher_helper.skip_sys_specs = True  # Skip sys_specs for faster simple tests
    launcher_helper.task_name = request.node.name  # Use test name as task name
    yield launcher_helper


def test_launcher_no_arguments(helper):
    """Launcher without arguments produces an error."""
    stdout, stderr, returncode = helper.run_launcher("")
    assert returncode != 0, "Expected non-zero exit code"
    assert stderr, "Expected runtime error of missing argument"


def test_launcher_help_message(helper):
    """Launcher with -h displays help message."""
    stdout, stderr, returncode = helper.run_launcher("-h")
    assert returncode == 0, "Expected zero exit code"
    assert stdout, "Expected output in stdout"
    assert stderr == "", "Expected empty stderr"


def test_launcher_silent_run_nope(helper):
    """Silent run of nope creates output files."""
    task_name = helper.task_name
    stdout, stderr, returncode = helper.run_launcher(
        f"-d {helper.runlogs_dir} -e {helper.experiment_name} -t {task_name} nope"
    )
    assert returncode == 0, "Expected zero exit code"
    assert stderr == "", "Expected empty stderr"

    csv_path = helper.runlogs_path / helper.experiment_name / f"{task_name}.csv"
    md_path = helper.runlogs_path / helper.experiment_name / f"{task_name}.md"
    assert csv_path.is_file(), "Expected CSV output file to exist"
    assert md_path.is_file(), "Expected MD output file to exist"


def test_launcher_verbose_run_nope(helper):
    """Verbose run of nope produces output and log files."""
    task_name = helper.task_name
    stdout, stderr, returncode = helper.run_launcher(
        f"-d {helper.runlogs_dir} -e {helper.experiment_name} -t {task_name} -v nope"
    )
    assert returncode == 0, "Expected zero exit code"
    assert stdout, "Expected output in stdout"
    assert stderr == "", "Expected empty stderr"

    csv_path = helper.runlogs_path / helper.experiment_name / f"{task_name}.csv"
    md_path = helper.runlogs_path / helper.experiment_name / f"{task_name}.md"
    assert csv_path.is_file(), "Expected CSV file to exist in tests directory"
    assert md_path.is_file(), "Expected MD output file to exist"


def test_non_existent_command(helper):
    """Execution with non-existent command produces an error."""
    task_name = helper.task_name
    stdout, stderr, returncode = helper.run_launcher(
        f"-d {helper.runlogs_dir} -e {helper.experiment_name} -t {task_name} -v foo"
    )
    assert returncode != 0, "Expected non-zero exit code"
    assert stderr, "Expected runtime error for foo indicating no such file or directory"


def test_sleep_command(helper):
    """Execution with sleep command measures correct inner time."""
    task_name = helper.task_name
    stdout, stderr, returncode = helper.run_launcher(
        f"-d {helper.runlogs_dir} -f backends/inner_time.yaml "
        f"-e {helper.experiment_name} -t {task_name} -v sleep 1"
    )

    assert returncode == 0, "Expected zero exit code"
    assert stderr == "", "Expected empty stderr"

    # Read inner time from CSV
    inner_time = float(helper.read_csv_column(f"{helper.experiment_name}/{task_name}", "inner_time", 0))

    assert inner_time >= 1.0, "Inner time should be at least 1 second"
    assert inner_time < 1.1, "Inner time should be less than 1.1 seconds"


def test_auto_metrics(helper):
    """Generation of metrics from 'auto' directive works correctly."""
    task_name = helper.task_name
    # First create the source experiment
    helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} -t {task_name} '
        f'-f backends/strace.yaml -b strace inc 10000'
    )

    # Even nope should be calling these system calls:
    expected_syscalls = ['execve', 'read', 'write', 'mmap']
    for scall in expected_syscalls:
        time = float(helper.read_csv_column(f"{helper.experiment_name}/{task_name}", scall))
        assert time >= 0, f"Any program should call {scall}."


def test_arg_repetition(helper):
    """Two local backends don't cause argument repetition."""
    task_name = helper.task_name
    stdout, stderr, returncode = helper.run_launcher(
        f"-b local -b local -d {helper.runlogs_dir} "
        f"-e {helper.experiment_name} -t {task_name} -v echo test"
    )
    assert "test test" not in stdout, "Expected single print of the argument 'test'"
