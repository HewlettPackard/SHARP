"""
Statistical utilities: distribution analysis, comparisons, narrative generation
(shared by CLI and GUI).

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from .distribution import (
    compute_summary,
    detect_change_points,
    detect_temporal_phases,
    estimate_acf_lag,
    characterize_distribution
)
from .comparisons import (
    mann_whitney_test,
    ecdf_comparison,
    density_comparison,
    comparison_table
)
from .narrative import (
    describe_changepoints,
    format_p_value,
    report_test
)
from .jenks_breaks import (
    jenks_breaks,
    goodness_of_variance_fit,
    optimal_jenks_classes
)

__all__ = [
    # Distribution analysis
    'compute_summary',
    'detect_change_points',
    'detect_temporal_phases',
    'estimate_acf_lag',
    'characterize_distribution',
    # Comparisons
    'mann_whitney_test',
    'ecdf_comparison',
    'density_comparison',
    'comparison_table',
    # Narrative generation
    'describe_changepoints',
    'format_p_value',
    'report_test',
    # Clustering
    'jenks_breaks',
    'goodness_of_variance_fit',
    'optimal_jenks_classes',
]
