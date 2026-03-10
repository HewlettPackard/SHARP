"""
GUI modules: summary, measure, profile, compare, explore tabs.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from .summary import summary_ui, summary_server
from .measure import measure_ui, measure_server
from .profile import profile_ui, profile_server
from .explore import explore_ui, explore_server
from .compare import compare_ui, compare_server

__all__ = [
    "summary_ui", "summary_server",
    "measure_ui", "measure_server",
    "profile_ui", "profile_server",
    "explore_ui", "explore_server",
    "compare_ui", "compare_server"
]
