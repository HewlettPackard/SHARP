"""
File and metadata utilities for profile workflow.

Handles markdown path derivation, validation, metadata extraction,
and file state detection for profiling workflow.

© Copyright 2025--2026 Hewlett Packard Enterprise Development LP
"""

import hashlib
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple
import polars as pl

from src.core.runlogs import (
    parse_markdown_runtime_options,
    parse_markdown_metadata,
    load_table,
)


def load_and_merge_tasks(
    task_csv_pairs: list[tuple[str, str]],
) -> tuple[pl.DataFrame, str]:
    """Load and merge multiple task CSV files into a single DataFrame.

    For a single task returns ``(df, csv_path)`` with no changes.

    For multiple tasks each CSV is loaded, assigned a ``task`` column (taken
    from the CSV itself when already present, otherwise set to the task name
    from *task_csv_pairs*), then concatenated via an outer union that fills
    missing columns with ``null``.  The merged DataFrame is written to a
    deterministic temp file (keyed on the sorted pair list) so that downstream
    routes can load it with a plain ``load_table`` call. If the file already
    exists, it is reused (avoiding redundant merge + save operations).

    The ``task`` column is always placed first.

    Args:
        task_csv_pairs: Non-empty list of ``(task_name, csv_path)`` tuples.

    Returns:
        ``(merged_df, path)`` where *path* is the original CSV path for a
        single task, or the temp merged CSV path for multiple tasks.
    """
    if not task_csv_pairs:
        raise ValueError("task_csv_pairs must not be empty")

    if len(task_csv_pairs) == 1:
        _, csv_path = task_csv_pairs[0]
        return load_table(csv_path), csv_path

    key = hashlib.sha256(
        str(sorted(task_csv_pairs)).encode()
    ).hexdigest()[:16]
    temp_path = Path(tempfile.gettempdir()) / f"sharp_merged_{key}.csv"

    # If merged file already exists, load and return it
    if temp_path.exists():
        return load_table(str(temp_path)), str(temp_path)

    # Merge all CSVs
    frames: list[pl.DataFrame] = []
    for task_name, csv_path in task_csv_pairs:
        df = load_table(csv_path)
        if "task" not in df.columns:
            df = df.with_columns(pl.lit(task_name).alias("task"))
        # Prepend task column when it isn't already first
        if df.columns[0] != "task":
            df = df.select(["task"] + [c for c in df.columns if c != "task"])
        frames.append(df)

    merged = pl.concat(frames, how="diagonal_relaxed")
    merged.write_csv(temp_path)

    return merged, str(temp_path)


def combined_profile_md_path(task_csv_pairs: list[tuple[str, str]]) -> Path:
    """Return a canonical, order-independent markdown path for a combined profile.

    Combined-profile settings must not live in any single task's markdown, since
    that is order-dependent (which task is "first") and pollutes the individual
    run.  Instead they are persisted to a dedicated file whose name is derived
    from the *sorted set* of task names, so the same combination of tasks always
    maps to the same file regardless of the order they were selected in.

    The file lives in a hidden ``.profile-combined`` directory inside the
    experiment folder (the parent of the task CSVs) so the runlog scanner does
    not surface it as a task.

    Args:
        task_csv_pairs: Non-empty list of ``(task_name, csv_path)`` tuples, all
            from the same experiment.

    Returns:
        Absolute-or-relative :class:`Path` to the combined-profile markdown file.
    """
    exp_dir = Path(task_csv_pairs[0][1]).parent
    tasks = sorted({task_name for task_name, _ in task_csv_pairs})
    key = hashlib.sha256("\x00".join(tasks).encode()).hexdigest()[:16]
    return exp_dir / ".profile-combined" / f"{key}.md"
from src.core.config.settings import Settings


def check_prof_file_exists(csv_path: str, settings: Any | None = None) -> str | None:
    """
    Check if a profiling variant of the CSV file exists.

    Args:
        csv_path: Path to the original CSV file

    Returns:
        Path to profiling CSV file if it exists, None otherwise
    """
    csv_path_obj = Path(csv_path)
    if settings is None:
        settings = Settings()
    prof_suffix = settings.get("profile.prof_suffix", "-prof")
    prof_path = csv_path_obj.parent / f"{csv_path_obj.stem}{prof_suffix}.csv"
    return str(prof_path) if prof_path.exists() else None


def get_markdown_path(csv_path: str) -> str:
    """
    Derive markdown filename from CSV path.

    Replaces .csv extension with .md.

    Args:
        csv_path: Path to CSV file (e.g., /path/task.csv or /path/task-prof.csv)

    Returns:
        Path to corresponding markdown file (e.g., /path/task.md or /path/task-prof.md)
    """
    csv_path_obj = Path(csv_path)
    return str(csv_path_obj.with_suffix(".md"))


def validate_markdown(md_path: str) -> tuple[bool, str]:
    """
    Validate markdown file for required fields.

    Uses the actual metadata parser to check if markdown can be
    successfully parsed, which is more reliable than string search.

    Args:
        md_path: Path to markdown file

    Returns:
        Tuple of (is_valid, error_message)
    """
    path = Path(md_path)
    if not path.exists():
        return False, f"Markdown file not found: {md_path}"

    try:
        # Use the actual metadata parser to validate
        # This handles both v4 and pre-v4 formats correctly
        metadata = parse_markdown_metadata(path)

        # Check if we got any metadata (indicates successful parse)
        if not metadata:
            return False, "Markdown file could not be parsed"

        return True, ""
    except Exception as e:
        return False, f"Error reading markdown: {str(e)}"


def extract_run_time_from_md(md_path: str) -> float | None:
    """
    Extract run duration from markdown YAML frontmatter.

    Uses the parser module's metadata extraction to get duration
    from both v4 and pre-v4 markdown formats.

    Args:
        md_path: Path to markdown file

    Returns:
        Duration in seconds if found, None otherwise
    """
    try:
        metadata = parse_markdown_metadata(Path(md_path))
        return metadata.get("duration")
    except Exception:
        return None


def extract_backends_from_md(md_path: str) -> list[str]:
    """
    Extract backend list from markdown YAML frontmatter.

    Reuses parser module's markdown metadata parser to extract the
    list of backend names used in the original experiment.

    Args:
        md_path: Path to markdown file

    Returns:
        List of backend names (empty list if none found or error)
    """
    try:
        metadata = parse_markdown_metadata(Path(md_path))
        return list(metadata.get("backends", []))
    except Exception:
        return []


def extract_repeater_max_from_md(md_path: str) -> int | None:
    """
    Extract the number of iterations from markdown file.

    Prefers 'total rows' count from V4 markdown files, falls back to
    'max' value from repeater_options for pre-V4 files.

    This value indicates how many iterations were in the original run,
    which is useful for creating progress bars during reprofile.

    Args:
        md_path: Path to markdown file

    Returns:
        Number of iterations if found, None otherwise
    """
    try:
        # First try to get row count from V4 format (most accurate)
        metadata = parse_markdown_metadata(Path(md_path))
        if metadata.get("rows") is not None:
            return int(metadata["rows"])

        # Fall back to repeater_options for pre-V4 files
        runtime_opts = parse_markdown_runtime_options(Path(md_path))

        if 'repeater_options' in runtime_opts:
            # Find the max value from any repeater
            for repeater_key, repeater_opts in runtime_opts['repeater_options'].items():
                if 'max' in repeater_opts:
                    return int(repeater_opts['max'])

        return None
    except Exception:
        return None


def get_file_paths(csv_path: str, settings: Any | None = None) -> Dict[str, Path]:
    """
    Derive all related file paths from a CSV path.

    Args:
        csv_path: Path to the CSV file

    Returns:
        Dict with keys: csv, md, prof_csv, prof_md
    """
    csv_obj = Path(csv_path)
    if settings is None:
        settings = Settings()
    prof_suffix = settings.get("profile.prof_suffix", "-prof")
    return {
        "csv": csv_obj,
        "md": csv_obj.with_suffix(".md"),
        "prof_csv": csv_obj.parent / f"{csv_obj.stem}{prof_suffix}.csv",
        "prof_md": csv_obj.parent / f"{csv_obj.stem}{prof_suffix}.md",
    }


def detect_file_state(csv_path: str, settings: Any | None = None) -> tuple[str, Dict[str, Path]]:
    """
    Detect the state of files for the profiling workflow.

    States:
    - state1: Both original CSV and profiling CSV exist
    - state2: Original CSV exists, profiling CSV does not exist
    - state3: Cannot determine state or files missing

    Args:
        csv_path: Path to original CSV file

    Returns:
        Tuple of (state_name, paths_dict)
        - paths_dict contains: csv, md, prof_csv (if exists), prof_md (if exists)
    """
    csv_path_obj = Path(csv_path)
    paths = {"csv": csv_path_obj}
    if settings is None:
        settings = Settings()
    prof_suffix = settings.get("profile.prof_suffix", "-prof")

    # If the provided CSV is already a profiling file, treat it specially
    if csv_path_obj.stem.endswith(prof_suffix):
        # prof_csv is the selected path itself
        paths["prof_csv"] = csv_path_obj
        # prof markdown derives from selected prof CSV
        paths["prof_md"] = Path(get_markdown_path(str(csv_path_obj)))

        # Derive the original csv/md by removing the prof suffix
        suffix_len = len(prof_suffix)
        original_stem = csv_path_obj.stem[:-suffix_len]
        original_csv = csv_path_obj.parent / f"{original_stem}.csv"
        paths["csv"] = original_csv
        paths["md"] = Path(get_markdown_path(str(original_csv)))

        # If the prof CSV exists, it's state1 (profiling data exists)
        return "state1", paths

    # Derive markdown path for non-prof CSV
    md_path = get_markdown_path(csv_path)
    paths["md"] = Path(md_path)

    # Check for profiling CSV variant (original -> original-prof.csv)
    prof_csv = check_prof_file_exists(csv_path, settings=settings)
    if prof_csv:
        paths["prof_csv"] = Path(prof_csv)
        # Derive profiling markdown path
        prof_md = get_markdown_path(prof_csv)
        paths["prof_md"] = Path(prof_md)

    # Determine state
    if prof_csv:
        return "state1", paths
    elif Path(md_path).exists():
        return "state2", paths
    else:
        return "state3", paths


def load_csv_with_validation(csv_path: str, md_path: str | None = None) -> Tuple[pl.DataFrame | None, str | None]:
    """
    Load CSV and optionally validate its markdown file.

    Args:
        csv_path: Path to CSV file
        md_path: Optional path to corresponding markdown file for validation

    Returns:
        Tuple of (dataframe, error_message)
        - If successful: (dataframe, None)
        - If failed: (None, error_message)
    """
    # Validate markdown first if provided
    if md_path:
        is_valid, error = validate_markdown(md_path)
        if not is_valid:
            return None, error

    # Load CSV
    try:
        df = load_table(csv_path)
        if df is None or df.is_empty():
            return None, f"CSV file is empty: {csv_path}"
        return df, None
    except Exception as e:
        return None, f"Error loading CSV: {str(e)}"
