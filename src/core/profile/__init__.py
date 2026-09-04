"""
Profile module for performance classification and factor analysis.

This module provides a modular framework for:
1. ClassSelector: Classifying performance data into categories (e.g., fast/slow)
2. ClassifierTrainer: Training classification models on performance data
3. FactorAnalyzer: Analyzing which factors influence performance class membership

Each component has an abstract interface allowing different implementations.

© Copyright 2025--2026 Hewlett Packard Enterprise Development LP
"""

from .base import ClassSelector, ClassifierTrainer, FactorAnalyzer
from .base import (
    ClassificationResult,
    TrainedModel,
    FactorImportance,
    ModelSummary,
    CausalDirection,
    InfluenceFactor,
    InfluenceAnalyzer,
    AnalyzerVisualizer,
)
from .cutoff import (
    CutoffClassSelector,
    suggest_cutoff,
    suggest_cutoff_from_data,
    validate_cutoff_range,
    search_optimal_cutoff,
)
from .decision_tree import DecisionTreeTrainer, DecisionTreeRegressorTrainer, TreeFactorAnalyzer
from .data_model import DataModelInfo, detect_data_model
from .analyzers.registry import InfluenceAnalyzerRegistry, DataContext, create_analyzer_registry
from .analyzers import *
from .column_enrichment import (
    ColumnEnricher,
    AggregateEnricher,
    InteractionEnricher,
    TemporalEnricher,
    EnrichedInfluenceAnalyzer,
    create_enrichers_from_settings,
    is_enriched_column,
)
from .labeler import (
    PerformanceLabeler,
    RegressionLabeler,
    CutoffBasedLabeler,
    BinaryLabeler,
    TertileLabeler,
    QuartileLabeler,
    AutoLabeler,
    ManualLabeler,
)
from .lag_detection import auto_max_lag, max_lag_correlation, sparse_lag_screening
from .direction import DirectionResult, detect_direction
from .confounding import partial_correlation, prune_confounded, ci_pre_screening

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
    "CausalDirection",
    "InfluenceFactor",
    "InfluenceAnalyzer",
    "AnalyzerVisualizer",
    # Concrete implementations
    "CutoffClassSelector",
    "DecisionTreeTrainer",
    "TreeFactorAnalyzer",
    "TrainedModelInfluenceAnalyzer",
    "TreeInfluenceAnalyzer",
    "LaggedCCFInfluenceAnalyzer",
    "GrangerInfluenceAnalyzer",
    "auto_max_lag",
    "max_lag_correlation",
    "sparse_lag_screening",
    # Direction testing
    "DirectionResult",
    "detect_direction",
    # Confounding utilities
    "partial_correlation",
    "prune_confounded",
    "ci_pre_screening",
    # Registry
    "InfluenceAnalyzerRegistry",
    "create_analyzer_registry",
    # Cutoff utilities
    "suggest_cutoff",
    "suggest_cutoff_from_data",
    "validate_cutoff_range",
    "search_optimal_cutoff",
    # Data model
    "DataModelInfo",
    "detect_data_model",
    # Column enrichment (Phase 7)
    "ColumnEnricher",
    "AggregateEnricher",
    "InteractionEnricher",
    "TemporalEnricher",
    "EnrichedInfluenceAnalyzer",
    "create_enrichers_from_settings",
    "is_enriched_column",
    # Labelers
    "PerformanceLabeler",
    "CutoffBasedLabeler",
    "BinaryLabeler",
    "TertileLabeler",
    "QuartileLabeler",
    "AutoLabeler",
    "ManualLabeler",
]
