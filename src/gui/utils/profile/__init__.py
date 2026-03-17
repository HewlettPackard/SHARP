"""
Profile tab utilities.

This package contains modular utilities for the profiling workflow.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

# Re-export commonly used functions for convenience
from .tree import (
    compute_tree,
    select_tree_predictors,
    render_tree_plot,
    summarize_tree,
    search_for_cutoff,
    select_complete_rows,
)

from .cutoff import (
    suggest_cutoff,
    compute_cutoff_from_data,
)

from .metrics import (
    compute_predictor_stats,
    create_predictor_exclusion_ui,
    build_predictor_exclusion_modal,
    apply_exclusions,
    DEFAULT_EXCLUDED_PREDICTORS,
)

from .files import (
    check_prof_file_exists,
    get_markdown_path,
    validate_markdown,
    extract_run_time_from_md,
    extract_backends_from_md,
    get_file_paths,
    detect_file_state,
)

from .modals import (
    build_choose_source_modal,
    build_configure_modal,
    build_invalid_backend_modal,
    build_profiling_error_modal,
)

from .execution import (
    determine_task_name_for_profiling,
    build_orchestrator_options,
    ProfilingExecutor,
    load_profiling_data,
)

__all__ = [
    # Tree functions
    "compute_tree",
    "select_tree_predictors",
    "render_tree_plot",
    "summarize_tree",
    "search_for_cutoff",
    "select_complete_rows",
    # Metric functions
    "suggest_cutoff",
    "compute_cutoff_from_data",
    "compute_predictor_stats",
    "create_predictor_exclusion_ui",
    "build_predictor_exclusion_modal",
    "apply_exclusions",
    "DEFAULT_EXCLUDED_PREDICTORS",
    # File functions
    "check_prof_file_exists",
    "get_markdown_path",
    "validate_markdown",
    "extract_run_time_from_md",
    "extract_backends_from_md",
    "get_file_paths",
    "detect_file_state",
    # Modal functions
    "build_choose_source_modal",
    "build_configure_modal",
    "build_invalid_backend_modal",
    "build_profiling_error_modal",
    # Execution functions
    "determine_task_name_for_profiling",
    "build_orchestrator_options",
    "ProfilingExecutor",
    "load_profiling_data",
]

