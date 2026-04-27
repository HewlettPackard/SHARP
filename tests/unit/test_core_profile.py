"""
Tests for core profile utilities.

Tests the core logic in src/core/profile/ independent of the GUI.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import numpy as np
import polars as pl
from sklearn.tree import DecisionTreeClassifier

from src.core.profile.base import TrainedModel, ClassificationResult, ClassifierTrainer
from src.core.profile.decision_tree import DecisionTreeTrainer, TreeFactorAnalyzer
from src.core.profile.cutoff import CutoffClassSelector


class TestDecisionTreeTrainer:
    """Tests for DecisionTreeTrainer class."""

    @pytest.fixture
    def simple_data(self):
        """Create simple dataset for training."""
        return pl.DataFrame({
            "feature1": [1.0, 2.0, 3.0, 4.0, 5.0],
            "feature2": ["A", "A", "B", "B", "A"],
            "metric": [10, 20, 80, 90, 15],
        })

    @pytest.fixture
    def binary_labels(self):
        """Create binary labels corresponding to simple_data."""
        # 0 for low metric (fast), 1 for high metric (slow)
        return np.array([0, 0, 1, 1, 0])

    def test_train_returns_trained_model(self, simple_data, binary_labels):
        """Test that train returns a TrainedModel instance."""
        trainer = DecisionTreeTrainer(max_depth=3)
        model = trainer.train(simple_data, binary_labels, exclude_cols=["metric"])

        assert isinstance(model, TrainedModel)
        assert isinstance(model.model, DecisionTreeClassifier)
        assert model.n_features > 0
        assert "feature1" in model.original_predictors
        assert "feature2" in model.original_predictors

    def test_train_handles_categorical_features(self, simple_data, binary_labels):
        """Test that categorical features are encoded."""
        trainer = DecisionTreeTrainer()
        model = trainer.train(simple_data, binary_labels, exclude_cols=["metric"])

        # feature2 is categorical, should be one-hot encoded
        feature_names = model.feature_names
        assert any("feature2" in name for name in feature_names)
        assert "feature1" in feature_names

    def test_train_respects_exclusions(self, simple_data, binary_labels):
        """Test that excluded columns are not used."""
        trainer = DecisionTreeTrainer()
        model = trainer.train(simple_data, binary_labels, exclude_cols=["metric", "feature1"])

        assert "feature1" not in model.original_predictors
        assert "feature1" not in model.feature_names
        # Only feature2 should be used
        assert all("feature2" in name for name in model.feature_names)

    def test_summarize_returns_summary(self, simple_data, binary_labels):
        """Test that summarize returns a ModelSummary."""
        trainer = DecisionTreeTrainer()
        model = trainer.train(simple_data, binary_labels, exclude_cols=["metric"])

        summary = trainer.summarize(model, simple_data, binary_labels)

        assert summary is not None
        assert summary.n_nodes > 0
        assert summary.n_leaves > 0
        assert summary.accuracy >= 0.0
        assert summary.accuracy <= 1.0
        assert summary.aic is not None

    def test_summarize_handles_mismatched_data(self, simple_data, binary_labels):
        """Test summarize with data length mismatch."""
        trainer = DecisionTreeTrainer()
        model = trainer.train(simple_data, binary_labels, exclude_cols=["metric"])

        # Pass fewer labels than data rows
        short_labels = binary_labels[:-1]
        summary = trainer.summarize(model, simple_data, short_labels)

        assert summary is None


    def test_train_handles_imbalanced_data(self):
        """
        Test that training handles imbalanced data correctly using class weights.

        This reproduces a bug where a small minority class (e.g. 1% Slow) was
        ignored by the tree visualization because the leaf node was dominated
        by the majority class in raw counts, even if the tree isolated the
        minority samples.
        """
        # Create imbalanced data: 100 samples, 98 Fast (0), 2 Slow (1)
        # Feature 'x' perfectly separates them: x > 0.9 is Slow
        n_samples = 100
        x = np.random.uniform(0, 0.8, n_samples)
        x[-2:] = 1.0  # Last 2 are Slow

        data = pl.DataFrame({"x": x})
        labels = np.zeros(n_samples, dtype=int)
        labels[-2:] = 1

        trainer = DecisionTreeTrainer(max_depth=2, min_samples_leaf=1)
        model = trainer.train(data, labels)

        assert model is not None
        tree = model.model

        # Check if class_weight is set to balanced
        assert tree.class_weight == 'balanced'

        # Find the leaf node for the Slow samples
        # We can use the apply method to find which leaf the Slow samples land in
        # We need to encode the data first (though here it's just 'x')
        X_slow = np.array([[1.0], [1.0]])
        leaf_indices = tree.apply(X_slow)

        # Both slow samples should be in the same leaf
        assert leaf_indices[0] == leaf_indices[1]
        leaf_idx = leaf_indices[0]

        # The predicted class for this leaf should be 1 (Slow)
        # We check this by looking at the value array for this node
        # value shape is (n_nodes, 1, n_classes)
        node_value = tree.tree_.value[leaf_idx][0]
        predicted_class = np.argmax(node_value)

        assert predicted_class == 1, f"Leaf for minority class should predict class 1, got {predicted_class}. Node value: {node_value}"


class TestTreeFactorAnalyzer:
    """Tests for TreeFactorAnalyzer class."""

    def test_analyze_returns_factors(self):
        """Test that analyze returns sorted factors."""
        # Create a dummy trained model with known importances
        clf = DecisionTreeClassifier(random_state=42)

        # Col 0: perfect predictor (0,0,1,1) matches y (0,0,1,1)
        # Col 1: noise (0,1,0,1)
        X = np.array([
            [0, 0],
            [0, 1],
            [1, 0],
            [1, 1]
        ])
        y = np.array([0, 0, 1, 1])
        clf.fit(X, y)

        model = TrainedModel(
            model=clf,
            feature_names=["important", "unimportant"],
            original_predictors=["important", "unimportant"],
            parameters={}
        )

        analyzer = TreeFactorAnalyzer()
        factors = analyzer.analyze(model)

        assert len(factors) == 2
        assert factors[0].name == "important"
        assert factors[0].importance > factors[1].importance

    def test_analyze_handles_empty_model(self):
        """Test analyze with None model."""
        analyzer = TreeFactorAnalyzer()
        factors = analyzer.analyze(None)
        assert factors == []

    def test_analyze_handles_untrained_model(self):
        """Test analyze with model lacking feature_importances_."""
        clf = DecisionTreeClassifier() # Not fitted
        model = TrainedModel(
            model=clf,
            feature_names=["a", "b"],
            original_predictors=["a", "b"],
            parameters={}
        )

        analyzer = TreeFactorAnalyzer()
        factors = analyzer.analyze(model)
        assert factors == []

class TestClassifierTrainerAIC:
    """Tests for _calculate_aic method in ClassifierTrainer."""

    class ConcreteTrainer(ClassifierTrainer):
        """Concrete implementation for testing."""
        def train(self, *args, **kwargs): return None
        def summarize(self, *args, **kwargs): return None
        def select_predictors(self, *args, **kwargs): return []

    @pytest.fixture
    def trainer(self):
        return self.ConcreteTrainer()

    def test_perfect_accuracy(self, trainer):
        """Test AIC calculation with perfect accuracy."""
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 1, 0, 1])
        # Accuracy = 1.0. Log likelihood = 4 * ln(1) = 0.
        # AIC = 2*k - 2*0 = 2*k
        aic = trainer._calculate_aic(y_true, y_pred, n_parameters=3)
        assert aic == 6.0

    def test_zero_accuracy_handling(self, trainer):
        """Test that zero accuracy is handled gracefully (clamped)."""
        y_true = np.array([0, 0])
        y_pred = np.array([1, 1])
        # Accuracy = 0. log(1e-10).
        aic = trainer._calculate_aic(y_true, y_pred, n_parameters=2)
        assert aic is not None
        # Should be large positive number
        expected_ll = 2 * np.log(1e-10)
        expected_aic = 4 - 2 * expected_ll
        assert np.isclose(aic, expected_aic)

    def test_empty_input(self, trainer):
        """Test handling of empty input arrays."""
        aic = trainer._calculate_aic(np.array([]), np.array([]), n_parameters=1)
        assert aic is None

    def test_parameter_penalty(self, trainer):
        """Test that more parameters increase AIC."""
        y_true = np.array([0, 1])
        y_pred = np.array([0, 1])
        aic_low_k = trainer._calculate_aic(y_true, y_pred, n_parameters=2)
        aic_high_k = trainer._calculate_aic(y_true, y_pred, n_parameters=10)

        assert aic_high_k > aic_low_k
        assert np.isclose(aic_high_k - aic_low_k, 2 * (10 - 2))

    def test_mismatched_lengths(self, trainer):
        """Test handling of mismatched array lengths (should probably fail or warn, but check current behavior)."""
        # Current implementation relies on numpy broadcasting or element-wise comparison
        # If lengths differ, (y_true == y_pred) might raise DeprecationWarning or return False
        # or raise ValueError depending on shapes.
        # Let's see what happens with current implementation.
        y_true = np.array([0, 1, 0])
        y_pred = np.array([0, 1])

        # This usually raises a DeprecationWarning in numpy for elementwise comparison failure
        # or False.
        # The implementation wraps in try/except, so it should return None.
        aic = trainer._calculate_aic(y_true, y_pred, n_parameters=2)
        assert aic is None
