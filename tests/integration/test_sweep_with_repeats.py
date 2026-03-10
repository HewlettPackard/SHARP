"""
Integration tests for parameter sweep with repeats.

Tests that sweep functionality works correctly when combined with the repeater.

© Copyright 2025 Hewlett Packard Enterprise Development LP
"""

import csv
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml


def find_output_file(pattern: str, search_dirs: list[Path]) -> Path | None:
    """
    Find output file matching pattern in multiple possible directories.

    Args:
        pattern: Glob pattern to search for
        search_dirs: List of directories to search

    Returns:
        Path to first matching file, or None if not found
    """
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        matches = list(search_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def test_sweep_with_repeats():
    """Test that parameter sweep works correctly with repeater (multiple iterations per config)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create benchmark script
        script = workspace / "demo.sh"
        script.write_text(
            "#!/bin/bash\n"
            "SIZE=$1\n"
            "THREADS=$2\n"
            "echo \"result $((SIZE * THREADS))\"\n"
        )
        script.chmod(0o755)

        # Create experiment config with sweep AND repeater
        config = {
            "version": "4.0",
            "name": "sweep-with-repeats",
            "entry_point": str(script),
            "args": ["100", "4"],  # Default args (will be overridden by sweep)
            "task": "demo",
            "metrics": {
                "result": {
                    "extract": "awk '/result/ {print $2}'",
                    "type": "numeric"
                }
            },
            "options": {
                "directory": str(workspace / "runlogs"),
                "skip_sys_specs": True
            },
            "repeater": "COUNT",
            "repeater_options": {
                "CR": {"max": 2}  # 2 iterations per sweep configuration
            },
            "sweep": {
                "args": [
                    ["50", "2"],  # Config 1: 50 * 2 = 100
                    ["100", "2"]  # Config 2: 100 * 2 = 200
                ]
            },
            "backend": "local"
        }

        config_file = workspace / "sweep_config.yaml"
        config_file.write_text(yaml.dump(config, sort_keys=False))

        # Execute
        result = subprocess.run(
            ["uv", "run", "src/cli/launch.py", "-f", str(config_file)],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0, f"Execution failed: {result.stderr}"

        # Find output files
        search_dirs = [
            workspace / "runlogs" / "sweep-with-repeats",
            Path.cwd() / "runlogs" / "sweep-with-repeats",
            workspace / "runlogs" / "misc",
            Path.cwd() / "runlogs" / "misc"
        ]

        csv_file = find_output_file("demo*.csv", search_dirs)
        assert csv_file, f"CSV file not found in {search_dirs}"

        md_file = find_output_file("demo*.md", search_dirs)
        assert md_file, f"Markdown file not found in {search_dirs}"

        # Verify CSV has correct number of rows
        # 2 sweep configs * 2 repeats = 4 total rows
        csv_content = csv_file.read_text()
        lines = csv_content.strip().split('\n')
        assert len(lines) == 5, f"Expected header + 4 data rows, got {len(lines)} lines"

        # Parse CSV
        with csv_file.open('r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Debug: print CSV content
        print(f"\n=== CSV Content ({len(rows)} rows) ===")
        for i, row in enumerate(rows):
            print(f"Row {i+1}: launch_id={row.get('launch_id')}, repeat={row.get('repeat')}, args={row.get('args', 'N/A')}")

        assert len(rows) == 4, f"Expected 4 rows (2 configs * 2 repeats), got {len(rows)}"

        # Verify launch_id and repeat columns exist
        assert 'launch_id' in rows[0], "launch_id column missing"
        assert 'repeat' in rows[0], "repeat column missing"

        # Group by launch_id
        launch_ids = {}
        for row in rows:
            lid = row['launch_id']
            if lid not in launch_ids:
                launch_ids[lid] = []
            launch_ids[lid].append(row)

        # Should have exactly 2 unique launch_ids (one per sweep config)
        assert len(launch_ids) == 2, f"Expected 2 launch_ids, got {len(launch_ids)}. Rows: {rows}"

        # Each launch_id should have exactly 2 repeats
        for lid, lid_rows in launch_ids.items():
            assert len(lid_rows) == 2, f"Launch ID {lid} should have 2 repeats, got {len(lid_rows)}. Rows: {lid_rows}"
            repeats = [row['repeat'] for row in lid_rows]
            assert repeats == ['1', '2'], f"Launch ID {lid} should have repeats 1,2, got {repeats}"

        # Verify markdown format
        md_content = md_file.read_text()

        # Should have runtime options section (may be "Initial" for first sweep config)
        assert ("## Runtime options" in md_content or "## Initial runtime options" in md_content)

        # Should have invariant parameters section with both launch_ids
        assert "## Invariant parameters" in md_content, "Invariant parameters section missing"

        # Should have both launch_ids in the parameters
        assert "sweep_0001" in md_content, "First sweep launch_id not found"
        assert "sweep_0002" in md_content, "Second sweep launch_id not found"

        # Each launch_id should show the sweep parameters
        # Config 1 has args: ["50", "2"]
        # Config 2 has args: ["100", "2"]
        assert "50, 2" in md_content, "First sweep config args (50, 2) not found in markdown"
        assert "100, 2" in md_content, "Second sweep config args (100, 2) not found in markdown"


def test_directory_option_respected():
    """Test that the directory option is respected and files are created in the right place."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        custom_dir = workspace / "my_custom_runlogs"

        # Create benchmark script
        script = workspace / "test.sh"
        script.write_text(
            "#!/bin/bash\n"
            "echo 'value 42'\n"
        )
        script.chmod(0o755)

        # Create experiment config with custom directory
        config = {
            "version": "4.0",
            "name": "custom-dir-test",
            "entry_point": str(script),
            "task": "test",
            "metrics": {
                "value": {
                    "extract": "awk '/value/ {print $2}'",
                    "type": "numeric"
                }
            },
            "options": {
                "directory": str(custom_dir),
                "skip_sys_specs": True
            },
            "repeater": "COUNT",
            "repeater_options": {
                "CR": {"max": 1}
            },
            "backend": "local"
        }

        config_file = workspace / "config.yaml"
        config_file.write_text(yaml.dump(config, sort_keys=False))

        # Execute
        result = subprocess.run(
            ["uv", "run", "src/cli/launch.py", "-f", str(config_file)],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0, f"Execution failed: {result.stderr}\nStdout: {result.stdout}"

        # Debug: find where files actually are in workspace
        find_result = subprocess.run(
            ["find", str(workspace), "-name", "*.csv", "-type", "f"],
            capture_output=True,
            text=True
        )
        actual_csv_files = find_result.stdout.strip().split('\n') if find_result.stdout.strip() else []

        # Also check current directory
        find_cwd = subprocess.run(
            ["find", str(Path.cwd() / "runlogs"), "-name", "*test.csv", "-type", "f", "-mmin", "-1"],
            capture_output=True,
            text=True
        )
        cwd_csv_files = find_cwd.stdout.strip().split('\n') if find_cwd.stdout.strip() else []

        # Verify files are in the custom directory
        expected_csv = custom_dir / "custom-dir-test" / "test.csv"
        expected_md = custom_dir / "custom-dir-test" / "test.md"

        assert expected_csv.exists(), \
            f"CSV not found at {expected_csv}.\nWorkspace CSV files: {actual_csv_files}\nCWD CSV files: {cwd_csv_files}\nStdout: {result.stdout}"
        assert expected_md.exists(), \
            f"Markdown not found at {expected_md}. Files may be in wrong location."

        # Verify CSV has data
        with expected_csv.open('r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
        assert rows[0]['value'] in ['42', '42.0'], f"Expected value=42, got {rows[0]['value']}"


def test_directory_option_with_cli_override():
    """Test that CLI --directory flag overrides config file directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        config_dir = workspace / "config_runlogs"
        cli_dir = workspace / "cli_runlogs"

        # Create benchmark script
        script = workspace / "test.sh"
        script.write_text(
            "#!/bin/bash\n"
            "echo 'value 99'\n"
        )
        script.chmod(0o755)

        # Create experiment config with directory in config
        config = {
            "version": "4.0",
            "name": "cli-override-test",
            "entry_point": str(script),
            "task": "test",
            "metrics": {
                "value": {
                    "extract": "awk '/value/ {print $2}'",
                    "type": "numeric"
                }
            },
            "options": {
                "directory": str(config_dir),  # This should be overridden
                "skip_sys_specs": True
            },
            "repeater": "COUNT",
            "repeater_options": {
                "CR": {"max": 1}
            },
            "backend": "local"
        }

        config_file = workspace / "config.yaml"
        config_file.write_text(yaml.dump(config, sort_keys=False))

        # Execute with CLI override
        result = subprocess.run(
            ["uv", "run", "src/cli/launch.py",
             "-f", str(config_file),
             "--directory", str(cli_dir)],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0, f"Execution failed: {result.stderr}"

        # Verify files are in the CLI-specified directory, NOT the config directory
        cli_csv = cli_dir / "cli-override-test" / "test.csv"
        cli_md = cli_dir / "cli-override-test" / "test.md"
        config_csv = config_dir / "cli-override-test" / "test.csv"

        assert cli_csv.exists(), \
            f"CSV not found at CLI directory {cli_csv}"
        assert cli_md.exists(), \
            f"Markdown not found at CLI directory {cli_md}"
        assert not config_csv.exists(), \
            f"CSV should NOT be in config directory {config_csv}, CLI flag should override"
