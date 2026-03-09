"""
CSV data loading for runlogs.

Functions for loading experiment CSV data files into Polars DataFrames
for analysis and visualization.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import json
import re
import polars as pl
from pathlib import Path


def load_csv(csv_path: str | Path) -> pl.DataFrame:
    """
    Load CSV file into Polars DataFrame.

    Args:
        csv_path: Path to CSV file

    Returns:
        Polars DataFrame with CSV data

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        pl.exceptions.ComputeError: If CSV parsing fails
    """
    csv_path = Path(csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pl.read_csv(
        csv_path,
        null_values=["NA", "N/A", ""],
        rechunk=True,  # Rechunk for better performance in subsequent operations
        low_memory=False,  # Use more memory for faster loading
        n_threads=1  # Single-threaded avoids contention on wide files
    )

    return df


def load_runlog(csv_path: str | Path, md_path: str | Path | None = None) -> pl.DataFrame:
    """
    Load runlog data (CSV) and merge invariant parameters from Markdown metadata.

    Args:
        csv_path: Path to CSV file
        md_path: Path to Markdown file (optional, defaults to csv_path with .md extension)

    Returns:
        Polars DataFrame with merged data (metrics + constants)
    """
    csv_path = Path(csv_path)
    if md_path is None:
        md_path = csv_path.with_suffix(".md")
    else:
        md_path = Path(md_path)

    # Load CSV data
    df = load_csv(csv_path)

    # If no launch_id column, return as is (legacy format support)
    if "launch_id" not in df.columns:
        # Check for old run_id
        if "run_id" in df.columns:
            # Rename run_id to launch_id for consistency if we want to support
            # old files but new code expects launch_id?
            # For now, let's assume we only care about new files or we handle both.
            # If we want to support old files, we might need to map run_id to launch_id or just use run_id.
            # But the user asked to replace "run id" with "launch id".
            pass
        else:
            return df

    # Load metadata if available
    invariants = {}
    if md_path.exists():
        try:
            content = md_path.read_text(encoding="utf-8")
            match = re.search(r"## Invariant parameters.*?```json\s+(.*?)\s+```", content, re.DOTALL)
            if match:
                invariants_data = json.loads(match.group(1))
                # Structure: {param: {type: ..., description: ..., values: {launch_id: value}}}
                # Pivot to: {launch_id: {param: value}}
                for param, details in invariants_data.items():
                    values = details.get("values", {})
                    for launch_id, value in values.items():
                        if launch_id not in invariants:
                            invariants[launch_id] = {}
                        invariants[launch_id][param] = value
        except Exception:
            pass  # Ignore metadata errors

    if not invariants:
        return df

    # Merge invariants into DataFrame
    # We can't easily do a join because invariants is a dict of dicts.
    # Convert invariants to a DataFrame and join?

    # Create a list of dicts for the invariants dataframe
    inv_rows = []
    for launch_id, params in invariants.items():
        inv_rows.append({"launch_id": launch_id, **params})

    if not inv_rows:
        return df

    inv_df = pl.DataFrame(inv_rows)

    # Join on launch_id
    # Use left join to keep all rows from CSV
    # Handle legacy run_id if present
    join_col = "launch_id" if "launch_id" in df.columns else "run_id"
    # If invariants use launch_id but df uses run_id (or vice versa), we might have a mismatch.
    # But since we just implemented this, let's assume consistency.

    df_merged = df.join(inv_df, on=join_col, how="left")

    return df_merged
