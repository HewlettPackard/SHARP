"""
Runlogs module - read/write experiment results and metadata.

Functions for scanning, loading, parsing, and writing experiment runlogs
(CSV data files and markdown metadata). Handles both reading completed results
and writing results during execution.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from .scanner import scan_runlogs, get_experiments, get_tasks_for_experiment
from .reader import load_csv, load_runlog
from .parser import parse_markdown_runtime_options, extract_runtime_options_from_markdown, parse_markdown_metadata
from .writer import RunLogger
from .sysinfo import collect_sysinfo

__all__ = [
    "scan_runlogs",
    "get_experiments",
    "get_tasks_for_experiment",
    "load_csv",
    "load_runlog",
    "parse_markdown_runtime_options",
    "extract_runtime_options_from_markdown",
    "parse_markdown_metadata",
    "RunLogger",
    "collect_sysinfo",
]
