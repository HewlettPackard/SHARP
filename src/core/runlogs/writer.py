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
import re
import subprocess
import time
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from src.core.config.include_resolver import get_project_root
from src.core.config.settings import Settings


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
        self._constants: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, Dict[str, str]] = {}
        self._task: str = task
        self._start_time: float = time.perf_counter()
        self._launch_id: str = uuid.uuid4().hex[:8]

        # Create experiment directory if needed
        exp_dir = Path(topdir) / experiment
        exp_dir.mkdir(parents=True, exist_ok=True)

        # Base filename (without extension)
        self._base_path: str = str(exp_dir / task.split("/")[-1])

        if options.get("verbose", False):
            print(f"Logging runs to: {self._base_path} starting at {self._start_time}")

        # Generate markdown preamble
        self._preamble = self._generate_preamble(task, options)
        # Cache output precision from settings to avoid repeated lookups
        self._precision = Settings().get("sharp.output_precision", 4)

    def _truncate_values(self, row: dict) -> dict:
        """
        Truncate all float-like values in the row to output_precision decimal places.
        """
        out = {}
        for k, v in row.items():
            meta_type = None
            if k in self._metadata:
                meta_type = self._metadata[k].get("type")

            # Only attempt to truncate if metadata indicates float or value is already float
            if meta_type == "float" or isinstance(v, float):
                try:
                    out[k] = float(f"{{:.{self._precision}f}}".format(float(v)))
                except (TypeError, ValueError):
                    out[k] = v
            else:
                out[k] = v
        return out

    def _generate_preamble(self, task: str, options: Dict[str, Any]) -> str:
        """
        Generate markdown preamble with metadata and runtime options.

        Args:
            task: Task/benchmark name
            options: Experiment options dict

        Returns:
            Preamble text for markdown file
        """
        # Try to get SHARP version from pyproject.toml
        version = "unknown"
        try:
            # Find project root (assuming writer.py is in src/core/runlogs/)
            pyproject_path = get_project_root() / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, "rb") as f:
                    pyproject_data = tomllib.load(f)
                    version = pyproject_data.get("project", {}).get("version", "unknown")
        except Exception:
            pass  # Use "unknown" if can't read version

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

        preamble += f"SHARP version: {version}\n"
        if git_hash:
            preamble += f"The source code version used was from git hash: {git_hash}\n"

        preamble += "\n## Initial runtime options\n\n```json\n"

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

    def add_invariant(self, field: str, value: Any, typ: str, desc: str) -> None:
        """
        Add an invariant parameter (constant for this run).

        Args:
            field: Parameter name/key
            value: Parameter value
            typ: Data type for documentation (e.g., 'string', 'float', 'int')
            desc: Human-readable description for markdown documentation
        """
        if field not in self._metadata:
            self._metadata[field] = {"type": typ, "desc": desc}

        self._constants[field] = {
            "value": value,
            "type": typ,
            "description": desc
        }

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

        # Add launch_id to every row
        records = [{"launch_id": self._launch_id, **r} for r in self._rows]

        # Fieldnames: launch_id + keys from first row
        # Note: _constants are NOT included in CSV anymore
        fieldnames = ["launch_id"] + list(self._rows[0].keys())

        csv_path = f"{self._base_path}.csv"

        with open(csv_path, mode, encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            # Write header if truncating or file is empty
            if mode == "w" or os.path.getsize(csv_path) == 0:
                writer.writeheader()

            for r in records:
                writer.writerow(self._truncate_values(r))

    def save_md(self, mode: str = "w", sys_specs: Optional[Dict[str, Any]] = None) -> None:
        """
        Write metadata and field descriptions to Markdown file.

        Args:
            mode: File write mode - "w" (truncate) or "a" (append)
            sys_specs: System specification dict (optional, for System configuration section)

        Raises:
            IOError: If cannot write to markdown file
        """
        md_path = Path(f"{self._base_path}.md")

        invariants = {}
        if mode == "a" and md_path.exists():
            invariants = self._load_existing_invariants(md_path)

        invariants = self._merge_invariants(invariants)

        if mode == "a" and md_path.exists():
            self._update_existing_markdown(md_path, invariants, sys_specs)
            return

        now = datetime.now(timezone.utc)
        elapsed = int(time.perf_counter() - self._start_time)
        row_count = len(self._rows)
        self._write_new_markdown(md_path, invariants, sys_specs, now, elapsed, row_count)

    def _load_existing_invariants(self, md_path: Path) -> Dict[str, Any]:
        """Extract invariant parameters JSON block from existing markdown file."""
        try:
            content = md_path.read_text(encoding="utf-8")
            match = re.search(r"## Invariant parameters.*?```json\s+(.*?)\s+```", content, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        except Exception:
            pass
        return {}

    def _merge_invariants(self, base: Dict[str, Any]) -> Dict[str, Any]:
        """Merge current run's constants into existing invariants structure."""
        # Structure: { launch_id: { param_name: value, ... }, ... }
        launch_entry = base.setdefault(self._launch_id, {})
        for param, details in self._constants.items():
            launch_entry[param] = details["value"]
        return base

    def _render_invariants_block(self, invariants: Dict[str, Any]) -> str:
        """Render invariants dictionary as markdown section with JSON code block."""
        invariants_json = json.dumps(invariants, indent=2)
        return (
            "## Invariant field description\n\n"
            + self._render_invariant_field_descriptions()
            + "\n\n## Invariant parameters\n\n"
            "Values are keyed by launch ID.\n\n"
            "```json\n"
            f"{invariants_json}\n"
            "```"
        )

    def _render_invariant_field_descriptions(self) -> str:
        """Render invariant field descriptions in same format as CSV fields."""
        lines = []
        for field, details in self._constants.items():
            typ = details["type"]
            desc = details["description"]
            lines.append(f"  * `{field}` ({typ}): {desc}.")
        return "\n".join(lines)

    def _update_existing_markdown(self, md_path: Path, invariants: Dict[str, Any],
                                  sys_specs: Optional[Dict[str, Any]]) -> None:
        """Update existing markdown file in append mode by replacing invariants block."""
        content = md_path.read_text(encoding="utf-8")
        invariants_block = self._render_invariants_block(invariants)

        if "## Invariant parameters" in content:
            content = re.sub(
                r"## Invariant parameters.*?```json\s+.*?\s+```",
                invariants_block,
                content,
                flags=re.DOTALL
            )
        else:
            split_marker = None
            if "## Initial system configuration" in content:
                split_marker = "## Initial system configuration"
            elif "## Starting system configuration" in content:
                split_marker = "## Starting system configuration"
            elif "## System configuration" in content:
                split_marker = "## System configuration"

            if split_marker:
                parts = content.split(split_marker, 1)
                content = parts[0].rstrip() + "\n\n" + invariants_block + "\n\n" + split_marker + parts[1]
            else:
                content = content.rstrip() + "\n\n" + invariants_block

        if sys_specs and "## Initial system configuration" not in content and "## Starting system configuration" not in content and "## System configuration" not in content:
            content = content.rstrip() + "\n\n## Initial system configuration\n\n```json\n" + json.dumps(sys_specs, indent=2) + "\n```\n"

        md_path.write_text(content + ("\n" if not content.endswith("\n") else ""), encoding="utf-8")

    def _write_new_markdown(self, md_path: Path, invariants: Dict[str, Any],
                            sys_specs: Optional[Dict[str, Any]], now: datetime,
                            elapsed: int, row_count: int) -> None:
        """Write new markdown file with preamble, field descriptions, invariants, and system specs."""
        invariants_block = self._render_invariants_block(invariants)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(
                f"Experiment completed at {now} (total experiment time: {elapsed}s, total rows: {row_count}).\n\n"
            )
            f.write(self._preamble)
            f.write("\n\n## CSV field description\n\n")
            f.write("  * `launch_id` (string): Unique identifier for the launch (links to Invariant parameters).\n")

            for field in self._metadata.keys():
                if field not in self._constants:
                    typ = self._metadata[field]["type"]
                    desc = self._metadata[field]["desc"]
                    f.write(f"  * `{field}` ({typ}): {desc}.\n")

            f.write("\n\n")
            f.write(invariants_block)
            f.write("\n")

            if sys_specs:
                f.write("\n## Initial system configuration\n\n")
                f.write("```json\n")
                f.write(json.dumps(sys_specs, indent=2))
                f.write("\n```\n")
