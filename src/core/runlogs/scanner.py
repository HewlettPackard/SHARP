"""
Runlogs directory scanning and metadata extraction.

Functions for scanning the runlogs directory to discover completed experiments
and extract metadata from their markdown files.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from pathlib import Path
from datetime import datetime
from typing import Any

from src.core.config.settings import Settings
from .parser import parse_markdown_metadata


def scan_runlogs(runlogs_dir: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    """
    Scan runlogs directory for experiment results.

    Scans markdown files only (much faster than CSV scanning).
    Markdown files contain all metadata: benchmark, backends, start/end times.

    Args:
        runlogs_dir: Path to runlogs directory (defaults to settings.sharp.runlogs_dir)
        limit: Maximum number of runs to return. If None, returns all runs.
               If specified, returns the most recent N runs.

    Returns:
        List of run metadata dicts, sorted by timestamp (newest first).
        Each dict contains: {
            'experiment': str,
            'task': str,
            'md_path': Path,
            'csv_path': Path | None,
            'timestamp': datetime | None,
            'benchmark': str | None,
            'backends': list[str] | None,
            'duration': float | None,
            'rows': int | None,  # Number of data rows (V4 only)
        }
    """
    if runlogs_dir is None:
        runlogs_dir = Settings().get("sharp.runlogs_dir", "runlogs")

    runlogs_path = Path(runlogs_dir)

    if not runlogs_path.exists():
        return []

    runs = []

    # Scan for markdown files only (much faster than scanning CSVs)
    for md_file in runlogs_path.rglob("*.md"):
        # Extract experiment and task from path
        # Expected structure: runlogs/<experiment>/<task>.md
        relative_path = md_file.relative_to(runlogs_path)
        parts = relative_path.parts

        if len(parts) < 2:
            continue

        experiment = parts[0]
        task = md_file.stem

        # Parse metadata from markdown, gracefully handling errors
        try:
            metadata = parse_markdown_metadata(md_file)
        except Exception:
            # Skip experiments with damaged/unparseable markdown
            continue

        timestamp = metadata.get("timestamp")
        benchmark = metadata.get("benchmark")
        backends = metadata.get("backends")
        duration = metadata.get("duration")
        rows = metadata.get("rows")  # Will be None for pre-V4 files

        # If no timestamp from metadata, use file modification time
        if timestamp is None:
            timestamp = datetime.fromtimestamp(md_file.stat().st_mtime)

        # Look for corresponding CSV file
        csv_file = md_file.with_suffix(".csv")
        csv_exists = csv_file.exists()

        runs.append({
            "experiment": experiment,
            "task": task,
            "md_path": md_file,
            "csv_path": csv_file if csv_exists else None,
            "timestamp": timestamp,
            "benchmark": benchmark,
            "backends": backends,
            "duration": duration,
            "rows": rows,
        })

    # Sort by timestamp (newest first)
    runs.sort(key=lambda r: r["timestamp"], reverse=True)

    # Limit results if requested
    if limit is not None and len(runs) > limit:
        runs = runs[:limit]

    return runs


def get_experiments() -> dict[str, str]:
    """
    Get list of unique experiments from runlogs.

    Returns:
        Dict mapping experiment name to itself (for Shiny select widget)
    """
    runs = scan_runlogs(limit=None)
    experiments = sorted(set(r["experiment"] for r in runs))
    return {exp: exp for exp in experiments}


def get_tasks_for_experiment(experiment: str) -> dict[str, str]:
    """
    Get list of tasks for a given experiment with CSV paths.

    Returns dict mapping full CSV path to task display name.
    Shiny will return the key (path) when selected.

    Args:
        experiment: Name of the experiment

    Returns:
        Dict mapping CSV path to task name
    """
    runs = scan_runlogs(limit=None)
    tasks = {}
    for r in runs:
        if r["experiment"] == experiment and r["csv_path"] is not None:
            # Use CSV path as key, task name as value (Shiny returns key on selection)
            tasks[str(r["csv_path"])] = r["task"]
    return tasks

