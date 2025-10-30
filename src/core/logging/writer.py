"""
Experiment logging to CSV and Markdown formats.

Records experiment metadata and run results to:
- CSV file: columnar data (shared metadata + per-run metrics)
- Markdown file: human-readable metadata, field descriptions, system specs

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import csv
import json
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class RunLogger:
    """Records experiment data to CSV and Markdown files."""

    def __init__(self, topdir: str, experiment: str, task: str, options: Dict[str, Any]) -> None:
        """
        Initialize logger for a single task/benchmark run.

        Args:
            topdir: Top-level directory for all logs (e.g., 'runlogs')
            experiment: Experiment subdirectory name (e.g., 'matmul_perf')
            task: Base filename for CSV/MD files (e.g., 'matmul', not 'path/to/matmul')
            options: Experiment options dict (for preamble, excludes sys_spec_commands)

        Raises:
            ValueError: If topdir does not exist or cannot create experiment directory
        """
        self.clear_rows()
        self._columns: Dict[str, str] = {}
        self._metadata: Dict[str, Dict[str, str]] = {}
        self._task: str = task
        self._start_time: float = time.perf_counter()

        # Create experiment directory if needed
        exp_dir = Path(topdir) / experiment
        exp_dir.mkdir(parents=True, exist_ok=True)

        # Base filename (without extension)
        self._base_path: str = str(exp_dir / task.split("/")[-1])

        if options.get("verbose", False):
            print(f"Logging runs to: {self._base_path} starting at {self._start_time}")

        # Generate markdown preamble
        self._preamble = self._generate_preamble(task, options)

    def _generate_preamble(self, task: str, options: Dict[str, Any]) -> str:
        """
        Generate markdown preamble with metadata and runtime options.

        Args:
            task: Task/benchmark name
            options: Experiment options dict

        Returns:
            Preamble text for markdown file
        """
        # Try to get git hash for reproducibility
        git_hash = ""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                git_hash = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # git not available or timed out

        now = datetime.now(timezone.utc)
        preamble = f"This file describes the fields in the file {task}.csv. "
        preamble += f"The measurements were run on {platform.node()}, starting at {now} (UTC).\n"

        if git_hash:
            preamble += f"The source code version used was from git hash: {git_hash}\n"

        preamble += "\n## Runtime options\n\n```json\n"

        # Exclude sys_spec_commands from output (shown in System configuration section)
        options_filtered = {k: v for k, v in options.items() if k != "sys_spec_commands"}
        preamble += json.dumps(options_filtered, indent=2)
        preamble += "\n```"

        return preamble

    def clear_rows(self) -> None:
        """
        Clear all row data (but keep column definitions).

        Can be used to reset row data between experiment phases.
        """
        self._rows: List[Dict[str, Any]] = []

    def get_csv_path(self) -> str:
        """
        Get the full path to the CSV output file.

        Returns:
            Full path to CSV file (with .csv extension)
        """
        return f"{self._base_path}.csv"

    def get_markdown_path(self) -> str:
        """
        Get the full path to the Markdown output file.

        Returns:
            Full path to Markdown file (with .md extension)
        """
        return f"{self._base_path}.md"

    def add_column(self, field: str, value: str, typ: str, desc: str) -> None:
        """
        Add a column field (shared across all rows).

        Args:
            field: Column name/key
            value: Column value (same for all rows)
            typ: Data type for documentation (e.g., 'string', 'float', 'int')
            desc: Human-readable description for markdown documentation
        """
        if field not in self._metadata:
            self._metadata[field] = {"type": typ, "desc": desc}
        self._columns[field] = value

    def add_row_data(
        self, field: str, value: Union[str, int, float], typ: str, desc: str
    ) -> None:
        """
        Add a field to the current row (per-run data).

        Creates new row if current row already has this field.
        All rows must have consistent fields.

        Args:
            field: Column name/key
            value: Value for this row
            typ: Data type for documentation
            desc: Human-readable description

        Raises:
            AssertionError: If field exists in earlier rows but not in most recent row
                (indicates inconsistent row structure)
        """
        if field not in self._metadata:
            self._metadata[field] = {"type": typ, "desc": desc}

        # Check consistency: if field existed in row before last, it should be in last row
        if len(self._rows) > 1:
            assert field in self._rows[-2], \
                f"Can't add new field '{field}' that isn't in previous row (inconsistent row structure)"

        # Create new row if this field already exists in current row
        if len(self._rows) == 0 or field in self._rows[-1]:
            self._rows.append({})

        self._rows[-1][field] = value

    def save_csv(self, mode: str = "w") -> None:
        """
        Write all rows to CSV file.

        Args:
            mode: File write mode - "w" (truncate) or "a" (append)

        Raises:
            AssertionError: If no rows to save
            IOError: If cannot write to CSV file
        """
        assert len(self._rows) > 0, "No row data to save"

        # Merge column and row data
        records = [{**self._columns, **r} for r in self._rows]
        fieldnames = list(self._columns.keys()) + list(self._rows[0].keys())

        csv_path = f"{self._base_path}.csv"

        with open(csv_path, mode, encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            # Write header if truncating or file is empty
            if mode == "w" or os.path.getsize(csv_path) == 0:
                writer.writeheader()

            writer.writerows(records)

    def save_md(self, mode: str = "w", sys_specs: Optional[Dict[str, Any]] = None) -> None:
        """
        Write metadata and field descriptions to Markdown file.

        In append mode, skips writing if file already exists (to avoid duplication).

        Args:
            mode: File write mode - "w" (truncate) or "a" (append)
            sys_specs: System specification dict (optional, for System configuration section)

        Raises:
            IOError: If cannot write to markdown file
        """
        md_path = f"{self._base_path}.md"

        # Skip writing in append mode if file exists (to avoid duplicate preambles)
        if mode == "a" and os.path.exists(md_path):
            return

        with open(md_path, mode, encoding="utf-8") as f:
            now = datetime.now(timezone.utc)
            elapsed = int(time.perf_counter() - self._start_time)

            f.write(f"Experiment completed at {now} (total experiment time: {elapsed}s).\n\n")
            f.write(self._preamble)
            f.write("\n\n## Field description\n\n")

            # Document all fields (both columns and row data)
            for field in self._metadata.keys():
                typ = self._metadata[field]["type"]
                desc = self._metadata[field]["desc"]
                f.write(f"  * `{field}` ({typ}): {desc}.\n")

            # Add system configuration section if provided
            if sys_specs:
                f.write("\n## System configuration\n\n")
                f.write("```json\n")
                f.write(json.dumps(sys_specs, indent=2))
                f.write("\n```\n")
