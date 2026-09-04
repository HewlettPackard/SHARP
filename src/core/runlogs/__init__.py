"""
Runlogs module - read/write experiment results and metadata.

Functions for scanning, loading, parsing, and writing experiment runlogs
(CSV data files and markdown metadata). Handles both reading completed results
and writing results during execution.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from .scanner import scan_runlogs, get_experiments, get_tasks_for_experiment
from .reader import load_runlog, load_table
from .profile_settings import (
    build_profile_settings_payload,
    extract_profile_settings_from_md,
    update_markdown_profile_settings,
)
from .parser import (
    parse_markdown_runtime_options,
    extract_runtime_options_from_markdown,
    parse_markdown_metadata,
)
from .writer import RunLogger
from .sysinfo import collect_sysinfo

__all__ = [
    "scan_runlogs",
    "get_experiments",
    "get_tasks_for_experiment",
    "load_table",
    "load_runlog",
    "build_profile_settings_payload",
    "parse_markdown_runtime_options",
    "extract_runtime_options_from_markdown",
    "parse_markdown_metadata",
    "extract_profile_settings_from_md",
    "update_markdown_profile_settings",
    "RunLogger",
    "collect_sysinfo",
]
