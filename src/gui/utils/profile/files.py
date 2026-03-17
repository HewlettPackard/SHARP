"""
File and metadata utilities for profile workflow.

Handles markdown path derivation, validation, metadata extraction,
and file state detection for profiling workflow.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from pathlib import Path
from typing import Dict, Tuple
import polars as pl

from src.core.runlogs import parse_markdown_runtime_options, parse_markdown_metadata, load_csv
from src.core.config.settings import Settings


def check_prof_file_exists(csv_path: str) -> str | None:
    """
    Check if a profiling variant of the CSV file exists.

    Args:
        csv_path: Path to the original CSV file

    Returns:
        Path to profiling CSV file if it exists, None otherwise
    """
    csv_path_obj = Path(csv_path)
    prof_suffix = Settings().get("profile.prof_suffix", "-prof")
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


def get_file_paths(csv_path: str) -> Dict[str, Path]:
    """
    Derive all related file paths from a CSV path.

    Args:
        csv_path: Path to the CSV file

    Returns:
        Dict with keys: csv, md, prof_csv, prof_md
    """
    csv_obj = Path(csv_path)
    prof_suffix = Settings().get("profile.prof_suffix", "-prof")
    return {
        "csv": csv_obj,
        "md": csv_obj.with_suffix(".md"),
        "prof_csv": csv_obj.parent / f"{csv_obj.stem}{prof_suffix}.csv",
        "prof_md": csv_obj.parent / f"{csv_obj.stem}{prof_suffix}.md",
    }


def detect_file_state(csv_path: str) -> tuple[str, Dict[str, Path]]:
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
    prof_suffix = Settings().get("profile.prof_suffix", "-prof")

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
    prof_csv = check_prof_file_exists(csv_path)
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
        df = load_csv(csv_path)
        if df is None or df.is_empty():
            return None, f"CSV file is empty: {csv_path}"
        return df, None
    except Exception as e:
        return None, f"Error loading CSV: {str(e)}"
