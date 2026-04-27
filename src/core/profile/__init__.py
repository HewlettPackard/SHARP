"""
Profile module for performance classification and factor analysis.

This module provides a modular framework for:
1. ClassSelector: Classifying performance data into categories (e.g., fast/slow)
2. ClassifierTrainer: Training classification models on performance data
3. FactorAnalyzer: Analyzing which factors influence performance class membership

Each component has an abstract interface allowing different implementations.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from .base import ClassSelector, ClassifierTrainer, FactorAnalyzer
from .base import ClassificationResult, TrainedModel, FactorImportance, ModelSummary
from .cutoff import (
    CutoffClassSelector,
    suggest_cutoff,
    suggest_cutoff_from_data,
    validate_cutoff_range,
    search_optimal_cutoff,
)
from .decision_tree import DecisionTreeTrainer, TreeFactorAnalyzer

__all__ = [
    # Abstract interfaces
    "ClassSelector",
    "ClassifierTrainer",
    "FactorAnalyzer",
    # Data classes
    "ClassificationResult",
    "TrainedModel",
    "FactorImportance",
    "ModelSummary",
    # Concrete implementations
    "CutoffClassSelector",
    "DecisionTreeTrainer",
    "TreeFactorAnalyzer",
    # Cutoff utilities
    "suggest_cutoff",
    "suggest_cutoff_from_data",
    "validate_cutoff_range",
    "search_optimal_cutoff",
]
