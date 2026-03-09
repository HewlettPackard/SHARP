"""
Tests for feature importance calculation.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""
import pytest
import numpy as np
from sklearn.tree import DecisionTreeClassifier
from sklearn.datasets import make_classification

from src.core.stats.feature_importance import (
    TreeFeatureImportance,
    get_feature_importance,
    get_ranked_features,
)


class TestTreeFeatureImportance:
    """Test TreeFeatureImportance calculator."""

    @pytest.fixture
    def trained_tree(self):
        """Create a simple trained decision tree."""
        # Create synthetic data
        X, y = make_classification(
            n_samples=100,
            n_features=5,
            n_informative=3,
            n_redundant=0,
            random_state=42
        )

        # Train tree
        tree = DecisionTreeClassifier(max_depth=3, random_state=42)
        tree.fit(X, y)

        # Add feature names
        tree.feature_names_ = [f'feature_{i}' for i in range(5)]

        return tree

    def test_compute_importance_returns_dict(self, trained_tree):
        """compute_importance should return a dictionary."""
        calculator = TreeFeatureImportance()
        importance = calculator.compute_importance(trained_tree)

        assert isinstance(importance, dict)
        assert len(importance) == 5

    def test_importance_scores_sum_to_one(self, trained_tree):
        """Importance scores should sum to approximately 1.0."""
        calculator = TreeFeatureImportance()
        importance = calculator.compute_importance(trained_tree)

        total = sum(importance.values())
        assert abs(total - 1.0) < 0.01  # Allow small floating point error

    def test_importance_scores_non_negative(self, trained_tree):
        """All importance scores should be non-negative."""
        calculator = TreeFeatureImportance()
        importance = calculator.compute_importance(trained_tree)

        for score in importance.values():
            assert score >= 0.0

    def test_get_ranked_features_returns_sorted_list(self, trained_tree):
        """get_ranked_features should return features sorted by importance."""
        calculator = TreeFeatureImportance()
        ranked = calculator.get_ranked_features(trained_tree)

        assert isinstance(ranked, list)
        assert len(ranked) == 5

        # Check it's sorted descending
        for i in range(len(ranked) - 1):
            assert ranked[i][1] >= ranked[i + 1][1]

    def test_get_ranked_features_structure(self, trained_tree):
        """Each ranked item should be (name, score) tuple."""
        calculator = TreeFeatureImportance()
        ranked = calculator.get_ranked_features(trained_tree)

        for item in ranked:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], str)
            assert isinstance(item[1], float)

    def test_raises_for_non_tree_model(self):
        """Should raise ValueError for non-tree models."""
        calculator = TreeFeatureImportance()

        class FakeModel:
            pass

        with pytest.raises(ValueError, match="Expected DecisionTreeClassifier"):
            calculator.compute_importance(FakeModel())

    def test_raises_for_tree_without_feature_names(self):
        """Should raise ValueError if tree lacks feature_names_."""
        calculator = TreeFeatureImportance()

        # Create tree without feature_names_
        X = np.array([[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]])
        y = np.array([0, 0, 1, 1, 1])
        tree = DecisionTreeClassifier(max_depth=2, random_state=42)
        tree.fit(X, y)
        # Don't add feature_names_

        with pytest.raises(ValueError, match="must have feature_names_"):
            calculator.compute_importance(tree)


class TestTopLevelFunctions:
    """Test top-level convenience functions."""

    @pytest.fixture
    def trained_tree(self):
        """Create a simple trained decision tree."""
        X, y = make_classification(
            n_samples=100,
            n_features=5,
            n_informative=3,
            n_redundant=0,
            random_state=42
        )

        tree = DecisionTreeClassifier(max_depth=3, random_state=42)
        tree.fit(X, y)
        tree.feature_names_ = [f'feature_{i}' for i in range(5)]

        return tree

    def test_get_feature_importance_with_tree(self, trained_tree):
        """get_feature_importance should work with trees."""
        importance = get_feature_importance(trained_tree)

        assert isinstance(importance, dict)
        assert len(importance) == 5

    def test_get_ranked_features_with_tree(self, trained_tree):
        """get_ranked_features should work with trees."""
        ranked = get_ranked_features(trained_tree)

        assert isinstance(ranked, list)
        assert len(ranked) == 5

        # Check sorted descending
        for i in range(len(ranked) - 1):
            assert ranked[i][1] >= ranked[i + 1][1]

    def test_unsupported_model_raises(self):
        """Should raise ValueError for unsupported model types."""
        class UnsupportedModel:
            pass

        model = UnsupportedModel()

        with pytest.raises(ValueError, match="Unsupported model type"):
            get_feature_importance(model)

        with pytest.raises(ValueError, match="Unsupported model type"):
            get_ranked_features(model)
