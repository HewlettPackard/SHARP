"""
GUI utilities: runlog loaders, formatters, input validators.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from src.core.runlogs import scan_runlogs, load_csv, parse_markdown_runtime_options
from src.core.stats.correlations import compute_generalized_correlation, safe_correlation
from .filters import create_filter_ui, apply_filter, get_filterable_columns, is_full_range_filter
from .profile.cutoff import (
    suggest_cutoff,
    compute_cutoff_from_data,
)
from .profile.files import (
    check_prof_file_exists,
    get_markdown_path,
    validate_markdown,
    extract_run_time_from_md,
    extract_backends_from_md,
)
from .profile.tree import (
    select_tree_predictors,
    compute_tree,
    render_tree_plot,
    search_for_cutoff,
    summarize_tree,
)

__all__ = [
    "scan_runlogs",
    "load_csv",
    "parse_markdown_runtime_options",
    "compute_generalized_correlation",
    "safe_correlation",
    "create_filter_ui",
    "apply_filter",
    "get_filterable_columns",
    "is_full_range_filter",
    "check_prof_file_exists",
    "get_markdown_path",
    "validate_markdown",
    "extract_run_time_from_md",
    "extract_backends_from_md",
    "suggest_cutoff",
    "compute_cutoff_from_data",
    "select_tree_predictors",
    "compute_tree",
    "render_tree_plot",
    "search_for_cutoff",
    "summarize_tree",
]
