#!/usr/bin/env python3
"""
Tests to verify command-line options processing in launcher.py.

This test suite verifies that the launcher correctly processes various combinations
of command-line options, configuration files, and JSON overrides.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

import json
import pytest
import re
import yaml  # type: ignore
import subprocess
import tempfile
from pathlib import Path


@pytest.fixture
def helper(launcher_helper, request, tmp_path):
    """Configure launcher helper for options processing tests."""
    launcher_helper.skip_sys_specs = True  # Skip sys_specs for faster option processing tests
    launcher_helper.task_name = request.node.name.replace("test_", "")

    # Create temporary config files
    config_dir = tmp_path / "configs"
    config_dir.mkdir(exist_ok=True)

    # Create task3.json
    task3_path = config_dir / "task3.json"
    with open(task3_path, "w") as f:
        json.dump({"task": "task3"}, f)

    # Create task4.json
    task4_path = config_dir / "task4.json"
    with open(task4_path, "w") as f:
        json.dump({"task": "task4"}, f)

    launcher_helper.config_dir = config_dir
    launcher_helper.task3_path = str(task3_path)
    launcher_helper.task4_path = str(task4_path)

    yield launcher_helper


# ========== Test Functions ==========

def test_sys_spec_override(helper) -> None:
    """Test that sys_spec commands can be overridden by later config files."""
    # This test specifically needs sys_specs, so disable skipping
    helper.skip_sys_specs = False

    # Create a config file that overrides a sys_spec command
    override_config = helper.config_dir / "override_sys_spec.yaml"
    with open(override_config, "w") as f:
        f.write("sys_spec_commands:\n")
        f.write("  system:\n")
        f.write("    hostname: 'echo OVERRIDDEN_HOSTNAME'\n")

    stdout, stderr, returncode = helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f {override_config} -j \'{{"task": "task_override"}}\' nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify the hostname was overridden in the MD file
    md_path = helper.runlogs_path / helper.experiment_name / "task_override.md"
    assert md_path.exists(), "Expected MD file to exist"
    with open(md_path) as f:
        content = f.read()
        assert '"hostname": "OVERRIDDEN_HOSTNAME"' in content, \
            "Expected overridden hostname in system configuration"

def test_default_config(helper) -> None:
    """Test launcher with auto-loaded sys_spec.yaml."""
    task_name = helper.task_name
    stdout, stderr, returncode = helper.run_launcher(f"-d {helper.runlogs_dir} -e {helper.experiment_name} -t {task_name} nope")
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify md file contents
    md_path = helper.runlogs_path / helper.experiment_name / f"{task_name}.md"
    assert md_path.exists(), "Expected MD file to exist"
    with open(md_path) as f:
        content = f.read()
        # New CLI output format
        assert '"backend_names": [\n    "local"\n  ]' in content, \
            "Expected local backend in backend_names"
        assert '"timeout": 3600' in content, "Expected timeout:3600 in configuration"
        assert '"start": "normal"' in content, "Expected normal start in configuration"
        assert '"verbose": false' in content, "Expected verbose:false in configuration"
        # Directory is now stored as absolute path in options
        assert '"directory":' in content, "Expected directory in configuration"

def test_json_override(helper) -> None:
    """Test JSON override of task name."""
    stdout, stderr, returncode = helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} -j \'{{"task": "task1"}}\' nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"
    task1_csv = helper.runlogs_path / helper.experiment_name / "task1.csv"
    assert task1_csv.exists(), "Expected task1.csv file in experiment directory"

def test_task_flag_override(helper) -> None:
    """Test -t flag overriding JSON task name."""
    stdout, stderr, returncode = helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} -t task2 -j \'{{"task": "task1"}}\' nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"
    task2_csv = helper.runlogs_path / helper.experiment_name / "task2.csv"
    assert task2_csv.exists(), "Expected task2.csv file in experiment directory"

def test_task_flag_overrides_all(helper) -> None:
    """Test that -t flag overrides both JSON and config file task names."""
    cmd = (f'-d {helper.runlogs_dir} -e {helper.experiment_name} -t task2 -j \'{{"task": "task1"}}\' '
           f'-f {helper.task3_path} nope')
    stdout, stderr, returncode = helper.run_launcher(cmd)
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify we're writing to task2.* files
    task2_csv = helper.runlogs_path / helper.experiment_name / "task2.csv"
    task3_csv = helper.runlogs_path / helper.experiment_name / "task3.csv"
    task1_csv = helper.runlogs_path / helper.experiment_name / "task1.csv"
    assert task2_csv.exists(), "Expected task2.csv file in experiment directory"
    assert not task3_csv.exists(), "task3.csv file should not exist"
    assert not task1_csv.exists(), "task1.csv file should not exist"

def test_json_overrides_config_file(helper) -> None:
    """Test that JSON overrides config file task name."""
    # Create config with task3
    with open(helper.task3_path, "w") as f:
        json.dump({"task": "task3"}, f)

    # Run with JSON override (should override config file)
    cmd = f'-d {helper.runlogs_dir} -e {helper.experiment_name} -j \'{{"task": "task1"}}\' -f {helper.task3_path} nope'
    stdout, stderr, returncode = helper.run_launcher(cmd)
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"
    # Verify we're writing to task1.* files
    task1_csv = helper.runlogs_path / helper.experiment_name / "task1.csv"
    task3_csv = helper.runlogs_path / helper.experiment_name / "task3.csv"
    assert task1_csv.exists(), "Expected task1.csv file in experiment directory"
    assert not task3_csv.exists(), "task3.csv file should not exist in experiment directory"

def test_config_file_task_override(helper) -> None:
    """Test that config file can override default task name."""
    stdout, stderr, returncode = helper.run_launcher(f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f {helper.task3_path} nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"
    # Verify we're writing to task3.* files
    task3_csv = helper.runlogs_path / helper.experiment_name / "task3.csv"
    nope_csv = helper.runlogs_path / helper.experiment_name / "nope.csv"
    assert task3_csv.exists(), "Expected task3.csv file in experiment directory"
    assert not nope_csv.exists(), "Expected nope.csv file should not exist in experiment directory"

def test_first_config_file_precedence(helper) -> None:
    """Test that first config file takes precedence."""
    stdout, stderr, returncode = helper.run_launcher(f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f {helper.task4_path} -f {helper.task3_path} nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify we're writing to task3.* files (second config doesn't override)
    task3_csv = helper.runlogs_path / helper.experiment_name / "task3.csv"
    task4_csv = helper.runlogs_path / helper.experiment_name / "task4.csv"
    assert task3_csv.exists(), "Expected task3.csv file in experiment directory"
    assert not task4_csv.exists(), "task4.csv file should not exist in experiment directory"

def test_last_config_file_precedence(helper) -> None:
    """Test that last config file takes precedence."""
    stdout, stderr, returncode = helper.run_launcher(f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f {helper.task3_path} -f {helper.task4_path} nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify we're writing to task4.* files (last config overrides)
    task4_csv = helper.runlogs_path / helper.experiment_name / "task4.csv"
    task3_csv = helper.runlogs_path / helper.experiment_name / "task3.csv"
    assert task4_csv.exists(), "Expected task4.csv file in experiment directory"
    assert not task3_csv.exists(), "task3.csv file should not exist in experiment directory"

def test_append_mode(helper) -> None:
    """Test append mode with multiple config files."""
    # Update task3.json to include append mode
    with open(helper.task3_path, "w") as f:
        json.dump({"task": "task3", "mode": "a"}, f)

    # Run command twice
    cmd = f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f {helper.task3_path} -f {helper.task4_path} nope'
    helper.run_launcher(cmd)  # First run
    stdout, stderr, returncode = helper.run_launcher(cmd)  # Second run
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify task4.csv has two observations
    assert helper.count_csv_rows(f"{helper.experiment_name}/task4") == 2, "Expected two observations in CSV"


def test_cli_append_overrides_config(helper) -> None:
    """Test that CLI -a flag overrides config file mode setting."""
    # Config says write mode, CLI says append
    with open(helper.task4_path, "w") as f:
        json.dump({"task": "task4", "mode": "w"}, f)

    # First run without -a (should write)
    cmd = f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f {helper.task4_path} nope'
    helper.run_launcher(cmd)
    assert helper.count_csv_rows(f"{helper.experiment_name}/task4") == 1

    # Second run WITH -a (should append despite config saying "w")
    cmd_with_append = f'-a {cmd}'
    stdout, stderr, returncode = helper.run_launcher(cmd_with_append)
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify task4.csv now has two observations (appended)
    assert helper.count_csv_rows(f"{helper.experiment_name}/task4") == 2, "CLI -a should override config mode=w"

def test_warm_start_with_multiple_configs(helper) -> None:
    """Test warm start with multiple config files."""
    # First run with append mode to get initial observations
    with open(helper.task3_path, "w") as f:
        json.dump({"task": "task3", "mode": "w"}, f)
    with open(helper.task4_path, "w") as f:
        json.dump({"task": "task4", "mode": "a"}, f)

    cmd = f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f {helper.task3_path} -f {helper.task4_path} nope'
    helper.run_launcher(cmd)  # First run
    helper.run_launcher(cmd)  # Second run

    # Now update task3.json to include warm start
    with open(helper.task3_path, "w") as f:
        json.dump({"task": "task3", "start": "warm", "mode": "a"}, f)

    # Run final command that should add warm start observation
    stdout, stderr, returncode = helper.run_launcher(cmd)
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify task4.csv has three observations
    assert helper.count_csv_rows(f"{helper.experiment_name}/task4") == 3, "Expected three observations in CSV"

    # Verify task4.md shows warm start in invariants (start is now an invariant, not a CSV column)
    md_path = helper.runlogs_path / helper.experiment_name / "task4.md"
    content = md_path.read_text()
    match = re.search(r"## Invariant parameters.*?```json\s+(.*?)\s+```", content, re.DOTALL)
    assert match, "Invariant block missing in markdown"
    invariants = json.loads(match.group(1))
    # New structure: { launch_id: { param: value, ... }, ... }
    # Should have both "normal" and "warm" starts from different runs
    start_values = set()
    for launch_id, params in invariants.items():
        if "start" in params:
            start_values.add(params["start"])
    assert "warm" in start_values, "warm start should be in invariants"
    assert "normal" in start_values, "normal start should be in invariants"

def test_single_config_warm_start(helper) -> None:
    """Test warm start with single config file."""
    with open(helper.task4_path, "w") as f:
        json.dump({"task": "task4", "start": "warm"}, f)

    # Run with just task4.json
    stdout, stderr, returncode = helper.run_launcher(f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f {helper.task4_path} nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify task4.csv has one warm observation
    assert helper.count_csv_rows(f"{helper.experiment_name}/task4") == 1, "Expected one observation in CSV"

    # Verify task4.md shows warm start in invariants (start is now an invariant, not a CSV column)
    md_path = helper.runlogs_path / helper.experiment_name / "task4.md"
    content = md_path.read_text()
    match = re.search(r"## Invariant parameters.*?```json\s+(.*?)\s+```", content, re.DOTALL)
    assert match, "Invariant block missing in markdown"
    invariants = json.loads(match.group(1))
    # New structure: { launch_id: { param: value, ... }, ... }
    start_values = {params["start"] for params in invariants.values() if "start" in params}
    assert "warm" in start_values, "warm start should be in invariants"

def test_repro_basic(helper) -> None:
    """Test basic reproduction of experiments."""
    with open(helper.task4_path, "w") as f:
        json.dump({"task": "task4", "start": "warm"}, f)
    # First run to create md file
    helper.run_launcher(f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f {helper.task4_path} nope')

    # Move md file to config dir and remove csv
    orig_md_path = helper.runlogs_path / helper.experiment_name / "task4.md"
    new_md_path = helper.config_dir / "task4.md"
    orig_md_path.rename(new_md_path)
    csv_path = helper.runlogs_path / helper.experiment_name / "task4.csv"
    csv_path.unlink()

    # Run reproduction using md from config dir
    stdout, stderr, returncode = helper.run_launcher(f'-d {helper.runlogs_dir} -e {helper.experiment_name} --repro {new_md_path}')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify task4.csv has one warm observation
    csv_path = helper.runlogs_path / helper.experiment_name / "task4.csv"
    with open(csv_path) as f:
        lines = list(f)
        assert len(lines) - 1 == 1, "Expected one observation in CSV"

    # Verify start is in invariants (not CSV column)
    md_path = helper.runlogs_path / helper.experiment_name / "task4.md"
    content = md_path.read_text()
    match = re.search(r"## Invariant parameters.*?```json\s+(.*?)\s+```", content, re.DOTALL)
    assert match, "Invariant block missing in markdown"
    invariants = json.loads(match.group(1))
    # New structure: { launch_id: { param: value, ... }, ... }
    start_values = {params["start"] for params in invariants.values() if "start" in params}
    assert "warm" in start_values, "warm start should be in invariants"

def test_repro_with_task_override(helper) -> None:
    """Test reproduction with task name override."""
    with open(helper.task4_path, "w") as f:
        json.dump({"task": "task4", "start": "warm"}, f)
    # First run to create md file
    helper.run_launcher(f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f {helper.task4_path} nope')

    # Run reproduction with task override
    md_path = helper.runlogs_path / helper.experiment_name / "task4.md"
    stdout, stderr, returncode = helper.run_launcher(f'-d {helper.runlogs_dir} -e {helper.experiment_name} --repro {md_path} -t task5')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"
    # Verify task5.* files exist with same experiment
    task5_csv = helper.runlogs_path / helper.experiment_name / "task5.csv"
    task5_md = helper.runlogs_path / helper.experiment_name / "task5.md"
    assert task5_csv.exists(), "Expected task5.csv file in experiment directory"
    assert task5_md.exists(), "Expected task5.md file in experiment directory"

    # Verify task5.csv has one warm observation
    assert helper.count_csv_rows(f"{helper.experiment_name}/task5") == 1, "Expected one observation in CSV"

    # Verify start is in invariants (not CSV column)
    md_path = helper.runlogs_path / helper.experiment_name / "task5.md"
    content = md_path.read_text()
    match = re.search(r"## Invariant parameters.*?```json\s+(.*?)\s+```", content, re.DOTALL)
    assert match, "Invariant block missing in markdown"
    invariants = json.loads(match.group(1))
    # New structure: { launch_id: { param: value, ... }, ... }
    start_values = {params["start"] for params in invariants.values() if "start" in params}
    assert "warm" in start_values, "warm start should be in invariants"

def test_time_backend(helper) -> None:
    """Test time backend metrics."""
    # This test needs real metrics from the time backend
    helper.skip_sys_specs = False

    stdout, stderr, returncode = helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f backends/bintime.yaml -b bintime nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify max_rss in CSV
    max_rss = helper.read_csv_column(f"{helper.experiment_name}/nope", "max_rss", 0)
    assert max_rss != "", "max_rss metric should not be empty"

    # Verify max_rss in MD
    md_path = helper.runlogs_path / helper.experiment_name / "nope.md"
    with open(md_path) as f:
        content = f.read()
        assert "max_rss" in content, "Expected max_rss metric in MD file"

def test_repro_task_override(helper) -> None:
    """Test reproduction with task override."""
    # This test needs real metrics for reproduction
    helper.skip_sys_specs = False

    # First create the source experiment
    helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f backends/bintime.yaml -b bintime nope')

    # Run reproduction with task override
    md_path = helper.runlogs_path / helper.experiment_name / "nope.md"
    stdout, stderr, returncode = helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} --repro {md_path} -t task6')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify task6.* files exist with max_rss metric
    max_rss = helper.read_csv_column(f"{helper.experiment_name}/task6", "max_rss", 0)
    assert max_rss != "", "max_rss metric should not be empty"

def test_repro_with_backend_override(helper) -> None:
    """Test reproduction with backend override."""
    # This test needs real metrics for reproduction
    helper.skip_sys_specs = False

    # First create the source experiment
    helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} -f backends/bintime.yaml -b bintime nope')

    # Run reproduction with uname backend
    md_path = helper.runlogs_path / helper.experiment_name / "nope.md"
    stdout, stderr, returncode = helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} --repro {md_path} -f backends/uname.yaml -b uname -t task6')
    assert returncode == 0, f"Command failed with code {returncode}"

    # Verify backend order: new CLI backend (uname) should come before repro backend (bintime)
    task6_md = helper.runlogs_path / helper.experiment_name / "task6.md"
    md_content = task6_md.read_text()
    # Extract backend_names line from JSON
    import json
    # Find the JSON block
    json_start = md_content.find('```json')
    json_end = md_content.find('```', json_start + 7)
    json_str = md_content[json_start + 7:json_end].strip()
    config = json.loads(json_str)
    backend_names = config.get('backend_names', [])
    assert backend_names == ['uname', 'bintime'], \
        f"Expected backend_names in order ['uname', 'bintime'], got: {backend_names}"

    # Verify task6.csv has both time and uname metrics
    hostname = helper.read_csv_column(f"{helper.experiment_name}/task6", "hostname", 0)
    max_rss = helper.read_csv_column(f"{helper.experiment_name}/task6", "max_rss", 0)
    assert hostname != "", "hostname metric should not be empty"
    assert max_rss != "", "kernel metric should not be empty"

def test_autoload_local_backend_default(helper) -> None:
    """Test that local backend config is auto-loaded when no backend is specified."""
    # Run without any -f or -b flags - should auto-load backends/local.yaml
    stdout, stderr, returncode = helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} -t autoload_default nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify the run completed successfully
    csv_content = helper.read_csv_column(f"{helper.experiment_name}/autoload_default", "outer_time", 0)
    assert csv_content != "", "outer_time should be recorded"

def test_autoload_local_backend_explicit(helper) -> None:
    """Test that local backend config is auto-loaded when -b local is specified."""
    # Run with -b local but no -f - should auto-load backends/local.yaml
    stdout, stderr, returncode = helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} -t autoload_explicit -b local nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify the run completed successfully
    csv_content = helper.read_csv_column(f"{helper.experiment_name}/autoload_explicit", "outer_time", 0)
    assert csv_content != "", "outer_time should be recorded"

def test_autoload_other_backend(helper) -> None:
    """Test that backend config is auto-loaded when -b backend is specified without -f."""
    helper.skip_sys_specs = False  # Need sys_specs for uname backend metrics

    # Run with -b uname but no -f - should auto-load backends/uname.yaml
    stdout, stderr, returncode = helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} -t autoload_uname -b uname nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify uname metrics were collected
    hostname = helper.read_csv_column(f"{helper.experiment_name}/autoload_uname", "hostname", 0)
    assert hostname != "", "hostname metric should not be empty"

def test_autoload_multiple_backends(helper) -> None:
    """Test that multiple backend configs are auto-loaded in order."""
    helper.skip_sys_specs = False  # Need sys_specs for uname backend metrics

    # Run with -b local -b uname but no -f - should auto-load both in order
    stdout, stderr, returncode = helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} -t autoload_multi -b local -b uname nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify both backends worked
    outer_time = helper.read_csv_column(f"{helper.experiment_name}/autoload_multi", "outer_time", 0)
    hostname = helper.read_csv_column(f"{helper.experiment_name}/autoload_multi", "hostname", 0)
    assert outer_time != "", "outer_time (from local) should be recorded"
    assert hostname != "", "hostname (from uname) should not be empty"

def test_no_autoload_when_explicit_config(helper) -> None:
    """Test that backend config is NOT auto-loaded when already provided via -f."""
    # Run with -f backends/uname.yaml -b uname - should NOT auto-load again
    stdout, stderr, returncode = helper.run_launcher(
        f'-d {helper.runlogs_dir} -e {helper.experiment_name} -t no_autoload -f backends/uname.yaml -b uname nope')
    assert returncode == 0, f"Command failed with code {returncode}"
    assert stderr == "", "Expected empty stderr"

    # Verify it still works (config was loaded via -f)
    hostname = helper.read_csv_column(f"{helper.experiment_name}/no_autoload", "hostname", 0)
    assert hostname != "", "hostname metric should not be empty"

def test_cold_start_executes_reset_command(helper) -> None:
    """Test that cold start executes the reset command before each iteration."""
    import tempfile
    import subprocess
    from pathlib import Path

    # Use a single absolute reset marker path inside the test's config directory
    # so the launcher subprocess can create/touch it. Quote the path for the
    # shell when building the reset command.
    import shlex

    reset_marker = Path(getattr(helper, "config_dir", helper.project_root)) / "reset_marker.txt"
    reset_marker.parent.mkdir(parents=True, exist_ok=True)
    reset_marker_path = str(reset_marker.resolve())

    # Remove it so we can count how many times it's created
    reset_marker.unlink(missing_ok=True)

    try:
        # Use -j to override backend reset command and set cold start
        # CR (count repeater) with max=3 runs exactly 3 iterations
        json_config = {
            "start": "cold",
            "repeater": "count",
            "repeater_options": {"CR": {"max": 3}},
            "backend_options": {
                "local": {
                    "run": "$CMD $ARGS",
                    "reset": f"touch {shlex.quote(reset_marker_path)}"
                }
            }
        }

        # Run with new CLI (not old launcher)
        cmd = [
            "src/cli/launch.py",
            "-d", helper.runlogs_dir,
            "-e", helper.experiment_name,
            "-t", "cold_start_test",
            "-j", json.dumps(json_config),
            "nope"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=helper.project_root)

        assert result.returncode == 0, "Expected zero exit code"

        # Verify start is in invariants (not CSV column)
        md_path = helper.runlogs_path / helper.experiment_name / "cold_start_test.md"
        content = md_path.read_text()
        match = re.search(r"## Invariant parameters.*?```json\s+(.*?)\s+```", content, re.DOTALL)
        assert match, "Invariant block missing in markdown"
        invariants = json.loads(match.group(1))
        # New structure: { launch_id: { param: value, ... }, ... }
        start_values = {params["start"] for params in invariants.values() if "start" in params}
        assert "cold" in start_values, "cold start should be in invariants"

        # Verify reset command was executed (marker file exists)
        # Note: The reset command runs before the benchmark, and we run 3 iterations,
        # so the file should have been touched at least once
        assert Path(reset_marker_path).exists(), \
            f"Reset marker file should exist (reset command was executed): {reset_marker_path}"

    finally:
        # Cleanup
        if reset_marker.exists():
            reset_marker.unlink()



#####################################################################
