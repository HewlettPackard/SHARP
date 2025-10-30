"""
Abstract base class for all repeater strategies.

A repeater decides when to stop repeating an experiment based on statistical
criteria applied to collected performance metrics.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from src.core.rundata import RunData

__all__ = ['Repeater', 'RunData']


class Repeater(ABC):
    """Base class for all repeater strategies."""

    def __init__(self, options: Dict[str, Any]):
        """Initialize repeater from options dictionary.

        Args:
            options: Dictionary containing 'repeater_options' with strategy-specific settings
        """
        self._count: int = 0
        self._verbose = options.get("repeater_options", {}).get("verbose", False)

    @abstractmethod
    def __call__(self, pdata: RunData) -> bool:
        """Decide whether to repeat the experiment.

        Args:
            pdata: Performance data from latest run

        Returns:
            True if another repetition should occur, False otherwise
        """
        self._count += 1
        return False

    def get_count(self) -> int:
        """Return total number of runs to date."""
        return self._count
