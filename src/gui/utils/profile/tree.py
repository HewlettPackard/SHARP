"""
Decision tree utilities for profile workflow.

Functions for training, rendering, and analyzing decision trees for
performance classification.

This module provides backward-compatible wrappers around the core profile
module, plus GUI-specific rendering functions. New code should use
src.core.profile directly for training and analysis.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any, Dict, List, Callable
from io import BytesIO
import os
import traceback
import numpy as np
import polars as pl
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from PIL import Image
from sklearn.tree import DecisionTreeClassifier

from src.core.config.settings import Settings
from src.core.profile.decision_tree import DecisionTreeTrainer
from src.core.profile.labeler import PerformanceLabeler, BinaryLabeler
from src.core.profile.cutoff import search_optimal_cutoff as _core_search_optimal_cutoff
from src.core.profile import predictor_selection


# Re-export from core for backward compatibility
def _encode_features(data: pl.DataFrame, feature_cols: list[str]) -> tuple[np.ndarray | None, list[str]]:
    """Encode features with one-hot encoding for categorical columns."""
    return predictor_selection.encode_features(data, feature_cols)


def _filter_predictors_by_variance(data: pl.DataFrame, exclude: list[str], metric: str) -> list[str]:
    """Filter columns to find potential predictors with variance."""
    numeric_cols, categorical_cols = predictor_selection._filter_by_variance(data, exclude, metric)
    return numeric_cols + categorical_cols


def _filter_and_select_top_predictors(correlations: Dict[str, float], max_predictors: int,
                                      max_correlation: float) -> list[str]:
    """Filter correlations by threshold and select top N predictors.

    Falls back to returning at least the best predictor if all are filtered out."""
    if not correlations:
        return []

    # Filter by correlation threshold
    filtered = {k: v for k, v in correlations.items() if abs(v) < max_correlation}

    # If nothing passes the threshold, fall back to the best predictor
    if not filtered:
        # Return the predictor with highest absolute correlation
        best = max(correlations.items(), key=lambda x: abs(x[1]))
        return [best[0]]

    # Sort by absolute correlation and select top N
    sorted_preds = sorted(filtered.items(), key=lambda x: abs(x[1]), reverse=True)
    return [name for name, _ in sorted_preds[:max_predictors]]


def select_tree_predictors(data: pl.DataFrame, metric: str, exclude: list[str] | None = None,
                          max_predictors: int = 100, max_correlation: float = 0.99) -> list[str]:
    """Select best predictors for decision tree using generalized correlation."""
    if exclude is None:
        exclude = []
    return predictor_selection.select_predictors(data, metric, exclude, max_predictors, max_correlation)


def select_complete_rows(
    data: pl.DataFrame,
    columns: list[str],
    target_rows: int | None = None,
    completeness_threshold: float | None = None
) -> pl.DataFrame:
    """
    Select rows from data that have high completeness in the specified columns.

    Uses an adaptive threshold approach: starts with the preferred completeness_threshold
    and progressively lowers it until enough rows are found.

    Args:
        data: DataFrame to select rows from
        columns: List of column names to check for completeness
        target_rows: Target number of rows to return
        completeness_threshold: Initial minimum fraction of non-null values

    Returns:
        DataFrame containing only the selected complete rows
    """
    if target_rows is None:
        target_rows = Settings().get("profiling.tree_training.target_rows", 1000)
    if completeness_threshold is None:
        completeness_threshold = Settings().get("profiling.tree_training.completeness_threshold", 0.95)

    try:
        subset = data.select(columns)
        non_null_counts = subset.select([
            pl.sum_horizontal([pl.col(c).is_not_null().cast(pl.Int32) for c in columns]).alias("non_null_count")
        ])
        total_cols = len(columns)
        completeness = (non_null_counts["non_null_count"] / total_cols)

        thresholds_to_try = [completeness_threshold, 0.75, 0.5, 0.25, 0.0]
        valid_indices = []

        for threshold in thresholds_to_try:
            valid_mask = completeness >= threshold
            valid_indices = [i for i, is_valid in enumerate(valid_mask.to_list()) if is_valid]
            if len(valid_indices) >= min(10, target_rows):
                break

        if len(valid_indices) > target_rows:
            valid_indices = valid_indices[:target_rows]

        if not valid_indices:
            return data.head(0)

        return data[valid_indices]

    except Exception:
        traceback.print_exc()
        return data.head(0)


def compute_tree(data: pl.DataFrame, metric: str, labeler: PerformanceLabeler,
                exclude: list[str] | None = None, max_predictors: int = 100,
                max_correlation: float = 0.99, predictors: list[str] | None = None) -> DecisionTreeClassifier | None:
    """
    Train decision tree classifier for performance classification.

    Args:
        data: Polars dataframe with features and metric
        metric: Target metric column name
        labeler: PerformanceLabeler instance for creating labels
        exclude: List of column names to exclude from features
        max_predictors: Maximum number of predictors
        max_correlation: Correlation threshold for filtering
        predictors: Pre-selected predictor list

    Returns:
        Fitted DecisionTreeClassifier, or None if unable to train
    """
    if data is None or data.is_empty():
        return None

    if exclude is None:
        exclude = []

    try:
        if not metric or metric.strip() == "":
            return None

        if metric not in data.columns:
            return None

        # Create labels using labeler
        valid_mask = data[metric].is_not_null()
        valid_data = data.filter(valid_mask)

        if len(valid_data) < 3:
            return None

        # Get metric values and classify them
        metric_values = valid_data[metric].to_numpy()
        labels = labeler.label(metric_values)

        # Convert string labels to numeric (0, 1, 2, ...)
        unique_labels = labeler.get_class_names()
        label_to_int = {label: i for i, label in enumerate(unique_labels)}
        numeric_labels = np.array([label_to_int[label] for label in labels])

        # Train using core module
        trainer = DecisionTreeTrainer()
        trained = trainer.train(
            valid_data, numeric_labels,
            exclude_cols=exclude,
            max_predictors=max_predictors,
            max_correlation=max_correlation,
            predictors=predictors
        )

        if trained is None:
            return None

        # Add attributes expected by GUI code for backward compatibility
        tree = trained.model
        tree.feature_names_ = trained.feature_names
        tree.original_predictors_ = trained.original_predictors
        tree.class_names_ = unique_labels  # Store class names for visualization

        return tree

    except Exception:
        traceback.print_exc()
        return None


def explain_tree_unavailable(data: pl.DataFrame | None, metric_col: str | None,
                             labeler: PerformanceLabeler | None) -> str:
    """Provide a user-friendly reason when a tree cannot be trained."""
    try:
        if labeler is None:
            return "No labeling strategy selected. Choose a cutoff/labeling option and try again."

        if data is None or data.is_empty():
            return "No data available to train a tree."

        if not metric_col or metric_col.strip() == "":
            return "No outcome metric selected."

        if metric_col not in data.columns:
            return f"Metric '{metric_col}' is not present in the dataset."

        valid = data[metric_col].drop_nulls()
        n_valid = len(valid)
        if n_valid < 3:
            return f"Only {n_valid} valid rows for metric '{metric_col}'. Need at least 3 samples to train a tree."

        metric_values = valid.to_numpy()
        labels = labeler.label(metric_values)
        unique_labels = np.unique(labels)
        if len(unique_labels) < 2:
            return (
                f"All samples map to a single class ({unique_labels[0]}). "
                "Adjust cutoffs or use a different labeling strategy to produce multiple classes."
            )

        return (
            "Tree training failed with the current data and cutoff configuration. "
            "Try adjusting exclusions, cutoffs, or ensuring more diverse samples."
        )
    except Exception:
        return "Tree could not be trained due to an unexpected error. Try adjusting cutoffs or exclusions and retry."


def _reconstruct_features(data: pl.DataFrame, feature_names: List[str]) -> np.ndarray:
    """
    Reconstruct feature matrix X from data to match the exact schema defined by feature_names.

    This ensures that the X matrix passed to visualization aligns perfectly with the
    encoded features expected by the trained tree, even if the current data subset
    is missing some categories or has different column ordering.
    """
    n_rows = len(data)
    n_features = len(feature_names)
    X = np.zeros((n_rows, n_features), dtype=np.float64)

    # Identify potential raw columns present in data
    available_cols = set(data.columns)

    for i, fname in enumerate(feature_names):
        # 1. Exact match (Numeric feature)
        if fname in available_cols:
            try:
                # Handle nulls by filling with 0 (safe default for viz)
                vals = data[fname].fill_null(0).to_numpy()
                X[:, i] = vals.astype(np.float64)
            except Exception:
                pass # Keep 0
            continue

        # 2. Key=Value match (One-Hot Encoded feature)
        # We look for a column 'col' such that fname == f"{col}={val}"

        # Find potential columns that are prefixes of the feature name
        candidates = [c for c in available_cols if fname.startswith(c + "=")]
        if not candidates:
            continue

        # Pick longest match to avoid ambiguity (e.g., "param" vs "param_full")
        col = max(candidates, key=len)
        val_str = fname[len(col)+1:]

        try:
             col_series = data[col]
             # Robust comparison requires casting to string
             if col_series.dtype == pl.Categorical:
                  match = (col_series.cast(pl.Utf8) == val_str)
             else:
                  match = (col_series.cast(pl.Utf8) == val_str)

             X[:, i] = match.fill_null(False).cast(np.float64).to_numpy()
        except Exception:
             pass

    return X


def _calculate_aic(y_true: np.ndarray, y_pred: np.ndarray, n_nodes: int) -> float | None:
    """Calculate AIC for a classification tree.

    AIC = 2k - 2*ln(L), where k=n_nodes (number of parameters) and L is likelihood.
    """
    from src.core.stats.aic import calculate_aic
    return calculate_aic(y_true, y_pred, n_nodes)


def summarize_tree(
    tree: DecisionTreeClassifier,
    data: pl.DataFrame,
    metric_col: str,
    cutoff: float,
    exclude: list[str] | None = None,
    lower_is_better: bool = True
) -> Dict[str, Any] | None:
    """
    Summarize decision tree statistics including AIC.

    Args:
        tree: Trained DecisionTreeClassifier
        data: Original data used to train the tree
        metric_col: Name of the metric column
        cutoff: Cutoff value used for classification
        exclude: List of column names to exclude
        lower_is_better: Whether lower metric values are better

    Returns:
        Dictionary with tree statistics or None if invalid
    """
    if tree is None:
        return None

    if exclude is None:
        exclude = []

    try:
        from src.core.profile.base import TrainedModel

        # Wrap sklearn tree in TrainedModel
        feature_names = getattr(tree, 'feature_names_', [])
        original_predictors = getattr(tree, 'original_predictors_', feature_names)

        trained_model = TrainedModel(
            model=tree,
            feature_names=feature_names,
            original_predictors=original_predictors,
            parameters={}
        )

        # Get labels for summary
        selector = CutoffClassSelector(cutoff, lower_is_better)
        labels = selector.classify_binary(data, metric_col)

        trainer = DecisionTreeTrainer()
        summary = trainer.summarize(trained_model, data, labels)

        if summary is None:
            return None

        return {
            'n_nodes': summary.n_nodes,
            'n_leaves': summary.n_leaves,
            'aic': summary.aic,
            'accuracy': summary.accuracy,
            'log_likelihood': summary.log_likelihood
        }

    except Exception:
        traceback.print_exc()
        return None


def search_for_cutoff(
    data: pl.DataFrame,
    metric_col: str,
    exclude: list[str],
    max_search_points: int = 100,
    progress_callback: Callable[..., Any] | None = None,
    lower_is_better: bool = True
) -> float | None:
    """
    Search for optimal cutoff point that minimizes decision tree AIC.

    Args:
        data: Polars DataFrame containing the data
        metric_col: Name of the metric column to use for classification
        exclude: List of predictor names to exclude from the tree
        max_search_points: Maximum number of cutoff points to search
        progress_callback: Optional callback function
        lower_is_better: Whether lower metric values are better

    Returns:
        Optimal cutoff value, or None if no valid trees found
    """
    trainer = DecisionTreeTrainer()

    def labeler_factory(cutoff: float) -> BinaryLabeler:
        return BinaryLabeler.with_cutoff(cutoff, lower_is_better)

    # Use the core search function with labeler factory
    from src.core.profile.cutoff import search_optimal_cutoff_with_classifier

    return search_optimal_cutoff_with_classifier(
        data=data,
        metric_col=metric_col,
        trainer=trainer,
        labeler_factory=labeler_factory,
        exclusions=exclude,
        max_search_points=max_search_points,
        progress_callback=progress_callback
    )


def search_optimal_manual_cutoffs(
    data: pl.DataFrame,
    metric_col: str,
    exclude: list[str],
    progress_callback: Callable[..., Any] | None = None,
    lower_is_better: bool = True,
    max_cutoffs: int = 9
) -> list[float] | None:
    """
    Search for optimal number and values of cutoffs for Manual labeler.

    Uses Jenks natural breaks to find candidate cutoff configurations (1-9 cutoffs),
    then evaluates each using decision tree AIC. Returns configuration with minimum AIC.

    Args:
        data: Polars DataFrame containing the data
        metric_col: Name of the metric column to use for classification
        exclude: List of predictor names to exclude from the tree
        progress_callback: Optional callback function for progress updates
        lower_is_better: Whether lower metric values are better
        max_cutoffs: Maximum number of cutoffs to try (default: 9)

    Returns:
        List of optimal cutoff values, or None if no valid configuration found
    """
    from src.core.stats.jenks_breaks import jenks_breaks
    from src.core.profile.labeler import ManualLabeler

    trainer = DecisionTreeTrainer()
    values = data[metric_col].drop_nulls().to_numpy()

    if len(values) < 10:
        return None

    best_aic = float('inf')
    best_cutoffs = None

    # Try different numbers of cutoffs (1 to max_cutoffs)
    for num_cutoffs in range(1, min(max_cutoffs + 1, 10)):
        if progress_callback:
            progress = num_cutoffs / max_cutoffs
            progress_callback(progress, f"Trying {num_cutoffs} cutoffs...")

        try:
            # Use Jenks to find optimal cutoff locations for this number of classes
            # jenks_breaks returns n_classes-1 cutoffs for n_classes classes
            cutoffs = jenks_breaks(values, n_classes=num_cutoffs + 1)

            if not cutoffs or len(cutoffs) != num_cutoffs:
                continue

            # Create labeler with these cutoffs
            labeler = ManualLabeler.with_cutoffs(cutoffs, lower_is_better)

            # Get labels for this labeler
            labels = labeler.label(values)

            # Compute tree for this labeler
            tree_model = compute_tree(
                data=data,
                metric=metric_col,
                labeler=labeler,
                exclude=exclude
            )

            if tree_model is None:
                continue

            # Compute AIC
            try:
                from src.core.profile.base import TrainedModel

                # Get feature names from tree
                feature_names = getattr(tree_model, 'feature_names_', [])
                original_predictors = getattr(tree_model, 'original_predictors_', feature_names)

                trained_model = TrainedModel(
                    model=tree_model,
                    feature_names=feature_names,
                    original_predictors=original_predictors,
                    parameters={}
                )

                trainer = DecisionTreeTrainer()
                summary = trainer.summarize(trained_model, data, labels)

                if summary is None or summary.aic is None:
                    continue

                aic = summary.aic

                # Check if this is better than current best
                if aic < best_aic:
                    best_aic = aic
                    best_cutoffs = cutoffs

            except Exception:
                continue

        except Exception:
            # Skip this configuration if it fails
            continue

    if progress_callback:
        progress_callback(1.0, "Search complete")

    return best_cutoffs


# ============================================================================
# GUI Rendering Functions (not moved to core - matplotlib/graphviz specific)
# ============================================================================

def _format_threshold(threshold: float) -> str:
    """Format tree threshold value for display."""
    if abs(threshold) >= 1000 or (abs(threshold) < 0.01 and threshold != 0):
        return f"{threshold:.1e}"
    else:
        return f"{threshold:.2f}"


def _create_dot_node(node_id: int, tree: Any, feature_names: List[str],
                     class_colors: List[str], class_names: List[str] | None = None,
                     classes: np.ndarray | None = None) -> str:
    """Create DOT graph node specification for a tree node."""
    if tree.feature[node_id] == -2:  # Leaf node
        values = tree.value[node_id][0]
        class_idx = np.argmax(values)

        # Map internal index to actual class label if classes provided
        # This handles cases where tree.classes_ is a subset (e.g. [1] only)
        if classes is not None:
            real_class_idx = int(classes[class_idx])
        else:
            real_class_idx = class_idx

        # Get color for this class (with bounds check)
        color = class_colors[real_class_idx] if real_class_idx < len(class_colors) else class_colors[0]
        n_samples = tree.n_node_samples[node_id]

        label = f"{n_samples}"
        if class_names is not None and len(class_names) > real_class_idx:
            label = f"{class_names[real_class_idx]}\\n{n_samples}"

        return f'{node_id} [label="{label}", fillcolor="{color}"] ;'
    else:  # Internal node
        feature_name = feature_names[tree.feature[node_id]]
        return f'{node_id} [label="{feature_name}", fillcolor="#f0f0f0"] ;'


def _create_dot_edges(node_id: int, tree: Any) -> List[str]:
    """Create DOT graph edge specifications for a tree node's children."""
    edges = []
    left_child = tree.children_left[node_id]
    right_child = tree.children_right[node_id]

    if left_child != -1:
        threshold = tree.threshold[node_id]
        threshold_str = _format_threshold(threshold)
        edges.append(f'{node_id} -> {left_child} [label=" ≤ {threshold_str}"] ;')
        edges.append(f'{node_id} -> {right_child} [label=" > {threshold_str}"] ;')

    return edges


def _build_tree_dot_graph(tree: DecisionTreeClassifier, feature_names: List[str],
                         class_colors: List[str]) -> str:
    """Build DOT graph representation of a decision tree."""
    dot_lines = ['digraph Tree {']
    dot_lines.append('node [shape=box, style="filled, rounded", fontname=helvetica] ;')
    dot_lines.append('edge [fontname=helvetica] ;')

    # Use class_names_ if available (set by compute_tree), otherwise use classes_ from sklearn
    class_names = getattr(tree, "class_names_", getattr(tree, "classes_", ["Class 0", "Class 1"]))
    classes = getattr(tree, "classes_", None)

    for i in range(tree.tree_.node_count):
        dot_lines.append(_create_dot_node(i, tree.tree_, feature_names, class_colors, class_names, classes))

    for i in range(tree.tree_.node_count):
        dot_lines.extend(_create_dot_edges(i, tree.tree_))

    dot_lines.append('}')
    return '\n'.join(dot_lines)


def _render_dot_to_matplotlib(dot_data: str, figsize: tuple[int, int] = (14, 10)) -> Figure:
    """Render DOT graph to matplotlib figure."""
    # Lazy import to avoid hard dependency at module import time
    import graphviz
    graph = graphviz.Source(dot_data)
    png_bytes = graph.pipe(format='png')

    img = Image.open(BytesIO(png_bytes))
    fig, ax = plt.subplots(figsize=figsize)
    ax.imshow(img)
    ax.axis('off')
    plt.tight_layout()
    return fig


def _create_error_figure(message: str, color: str = '#666') -> Figure:
    """Create a matplotlib figure with an error or info message."""
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.text(0.5, 0.5, message, ha='center', va='center', fontsize=10, color=color)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    return fig


def render_tree_plot(tree: DecisionTreeClassifier, class_colors: List[str]) -> Figure:
    """
    Render decision tree visualization using graphviz and matplotlib.

    Args:
        tree: Trained DecisionTreeClassifier with feature_names_ attribute
        class_colors: List of hex colors for each class (ordered by class index)

    Returns:
        Matplotlib figure with tree visualization
    """
    if tree is None:
        return _create_error_figure("No tree available. Train a tree by selecting a metric and cutoff.")

    feature_names = getattr(tree, 'feature_names_', None)
    if feature_names is None:
        feature_names = [f"Feature_{i}" for i in range(tree.n_features_in_)]

    try:
        dot_data = _build_tree_dot_graph(tree, feature_names, class_colors)
        return _render_dot_to_matplotlib(dot_data)

    except (ExecutableNotFound, FileNotFoundError) as e:
        error_msg = (
            "Graphviz 'dot' executable not found.\n\n"
            "Install Graphviz system package:\n"
            "• Ubuntu/Debian: sudo apt-get install graphviz\n"
            "• RedHat/CentOS: sudo yum install graphviz\n"
            "• macOS: brew install graphviz"
        )
        return _create_error_figure(error_msg, color='#dc3545')

    except Exception as e:
        traceback.print_exc()
        return _create_error_figure(f"Error rendering tree:\n{str(e)}", color='#dc3545')


def _prepare_tree_visualization_data(
    data: pl.DataFrame,
    metric_col: str,
    feature_names: List[str],
    predictors: List[str],
    labeler: PerformanceLabeler,
    class_names: List[str]
) -> tuple[np.ndarray, np.ndarray]:
    """
    Prepare X (features) and y (labels) arrays for tree visualization.

    Args:
        data: Original data
        metric_col: Metric column name
        feature_names: Encoded feature names from trained tree
        predictors: Original predictor column names
        labeler: Labeler to generate class labels
        class_names: Class names in order

    Returns:
        Tuple of (X, y) numpy arrays

    Raises:
        ValueError: If data preparation fails
    """
    try:
        valid_mask = data[metric_col].is_not_null()
        valid_data = data.filter(valid_mask)

        # Reconstruct features to match tree's expected schema
        if feature_names and not all(f.startswith("Feature_") for f in feature_names):
            X = _reconstruct_features(valid_data, feature_names)
        else:
            # Fallback encoding
            X, _ = _encode_features(valid_data.select(predictors), predictors)
            if X is None:
                raise ValueError("Feature encoding failed")

        # Generate labels
        metric_values = valid_data[metric_col].to_numpy()
        labels = labeler.label(metric_values)

        # Map labels to integers
        label_to_int = {label: i for i, label in enumerate(class_names)}
        y = np.array([label_to_int.get(l, 0) for l in labels])

        return X, y
    except Exception as e:
        raise ValueError(f"Failed to prepare visualization data: {e}")


def _generate_supertree_html(
    tree: DecisionTreeClassifier,
    X: np.ndarray,
    y: np.ndarray,
    feature_names: List[str],
    class_names: List[str]
) -> str | None:
    """
    Generate raw HTML from SuperTree library.

    Args:
        tree: Trained decision tree
        X: Feature matrix
        y: Label array
        feature_names: Feature names
        class_names: Class names

    Returns:
        Raw HTML string, or None if generation fails
    """
    try:
        from supertree import SuperTree  # type: ignore
        import tempfile
        import os

        # Try to instantiate with names
        try:
            st = SuperTree(tree, X, y, feature_names, class_names)
        except Exception:
            # Fallback without names
            st = SuperTree(tree, X, y)

        # Generate HTML via temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'tree')
            st.save_html(filename=output_path, which_tree=0)
            html_file = output_path + '.html'

            if os.path.exists(html_file):
                with open(html_file, 'r', encoding='utf-8') as f:
                    return f.read()

        return None
    except Exception:
        traceback.print_exc()
        return None


def render_supertree_html(tree: DecisionTreeClassifier,
                          feature_names: List[str] | None,
                          class_names: List[str] | None,
                          class_colors: List[str],
                          data: pl.DataFrame,
                          metric_col: str,
                          labeler: PerformanceLabeler) -> str:
    """
    Render DecisionTreeClassifier as interactive HTML using Supertree.

    Generates an interactive D3-based tree visualization with custom colors and branding removed.
    The output HTML is post-processed to ensure class colors are rendered natively by rewriting
    SuperTree's internal palette array, avoiding client-side color reapplication overhead.

    Args:
        tree: Trained DecisionTreeClassifier with feature_names_ and class_names_ attributes
        feature_names: List of predictor feature names
        class_names: List of class labels (e.g., ["FAST", "SLOW"])
        class_colors: List of hex colors for each class (e.g., ["#3366CC", "#DC3912"])
        data: Original training data (used for label validation)
        metric_col: Metric column name
        labeler: PerformanceLabeler used for classification

    Returns:
        HTML string ready for embedding in UI. If Supertree is unavailable or rendering fails,
        returns HTML-escaped error message.
    """
    if tree is None:
        import html
        reason = explain_tree_unavailable(data, metric_col, labeler)
        return (
            '<div style="padding:10px;color:#a00;">'
            'No decision tree could be trained with the current data/cutoffs.'
            f'<br/>{html.escape(reason)}'
            '</div>'
        )

    # Check if supertree is available
    try:
        import supertree  # type: ignore
    except Exception:
        return (
            '<div style="padding:10px;color:#a00;">'
            'Supertree is not installed. Please install it to enable interactive tree visualization.'
            '<br/><code>pip install supertree</code></div>'
        )

    # Fallbacks for missing metadata
    if feature_names is None:
        feature_names = [f"Feature_{i}" for i in range(getattr(tree, 'n_features_in_', 0))]
    if class_names is None:
        classes = getattr(tree, 'classes_', [])
        class_names = [str(c) for c in classes] if classes is not None else ["Class 0", "Class 1"]

    # Get predictors from tree
    predictors = getattr(tree, 'original_predictors_', feature_names or [])
    if not predictors:
        return (
            '<div style="padding:10px;color:#a00;">'
            'Cannot render interactive tree: no predictors found in model.'
            '</div>'
        )

    # Prepare visualization data
    try:
        X, y = _prepare_tree_visualization_data(
            data, metric_col, feature_names, predictors, labeler, class_names
        )
    except ValueError as e:
        return (
            '<div style="padding:10px;color:#a00;">'
            f'Failed to prepare data: {str(e)}'
            '</div>'
        )

    # Generate raw HTML
    html = _generate_supertree_html(tree, X, y, feature_names, class_names)

    if not html:
        return (
            '<div style="padding:10px;color:#a00;">'
            'Supertree is installed but could not render the tree with the current API.'
            '<br/>Please ensure the installed version supports HTML export and try again.'
            '</div>'
        )

    # Post-process HTML to customize appearance
    html = _customize_supertree_html(html, class_names, class_colors)
    return html


def render_tree_for_ui(
    tree: DecisionTreeClassifier | None,
    data: pl.DataFrame | None,
    metric_col: str | None,
    labeler: PerformanceLabeler | None
) -> str:
    """
    High-level wrapper for rendering tree visualization in UI context.

    Automatically extracts metadata from tree and labeler, computes colors,
    and handles error cases with informative messages.

    Args:
        tree: Trained decision tree (or None if training failed)
        data: Current dataset
        metric_col: Metric column name
        labeler: Performance labeler

    Returns:
        HTML string ready for ui.HTML() wrapping
    """
    import html as html_module

    # Validate inputs
    if labeler is None or not metric_col:
        return (
            '<div style="padding:10px;color:#999;text-align:center;">'
            'Select an outcome metric and labeling strategy to train a tree.'
            '</div>'
        )

    if tree is None:
        reason = explain_tree_unavailable(data, metric_col, labeler)
        return (
            '<div style="padding:10px;color:#a00;">'
            '<p style="margin:0;">No decision tree could be trained with the current data/cutoffs.</p>'
            f'<p style="margin:5px 0 0 0;font-size:0.9em;">{html_module.escape(reason)}</p>'
            '</div>'
        )

    # Extract metadata from tree and labeler
    feature_names = getattr(tree, 'feature_names_', None)
    class_names = labeler.get_class_names()

    # Compute colors from class names
    from src.gui.utils.profile.distribution import get_class_colors
    class_colors = get_class_colors(class_names)

    # Render using full API
    return render_supertree_html(
        tree, feature_names, class_names, class_colors,
        data, metric_col, labeler
    )


def _customize_supertree_html(html: str, class_names: List[str], class_colors: List[str]) -> str:
    """
    Post-process Supertree HTML to customize colors and hide branding.

    SuperTree uses D3.js to render tree visualizations client-side with a hardcoded palette.
    This function customizes the output by:

    1. **Palette Rewriting**: Rewrites the embedded 'const M=[...]' array to inject custom
       colors. SuperTree uses M[i] for fill colors on nodes, so replacing these entries
       ensures custom class colors are rendered natively without client-side recoloring.

    2. **Branding Removal**: Scrubs the setTimeout() injection that adds mljar logo elements,
       and injects aggressive CSS rules to hide any remaining branding.

    Args:
        html: Original HTML from Supertree
        class_names: List of class names in order
        class_colors: List of hex colors corresponding to each class

    Returns:
        Modified HTML with custom colors and hidden branding
    """
    import re

    # Build class name to color mapping
    class_color_map = {str(name): class_colors[i % len(class_colors)]
                      for i, name in enumerate(class_names)}

    # FORCE-OVERRIDE: Rewrite the embedded palette array (const M=[...])
    # SuperTree uses this array by index (M[e]) for fill colors.
    # We replace the first N entries with our configured class colors.
    m_match = re.search(r'const\s+M\s*=\s*\[(.*?)\]', html, re.DOTALL)
    if m_match:
        content = m_match.group(1)
        # Find all string literals in the array (e.g. "#FEFEBB")
        existing_items = re.findall(r'["\'][^"\']*["\']', content)

        # Replace the first N items with our class colors
        was_rewritten = False
        for i, color in enumerate(class_colors):
            new_item = f'"{color}"'
            if i < len(existing_items):
                if existing_items[i] != new_item:
                    existing_items[i] = new_item
                    was_rewritten = True
            else:
                existing_items.append(new_item)
                was_rewritten = True

        if was_rewritten:
            # Reconstruct the array content
            new_content = ",".join(existing_items)

            # Replace in html
            html = html[:m_match.start(1)] + new_content + html[m_match.end(1):]

    # Remove mljar logo injection code
    # Matches the setTimeout block that injects the logo
    html = re.sub(
        r'setTimeout\(\(function\(\)\{logoURL=["\'].*?mljar.*?["\'];.*?\}\),\s*\d+\);',
        '',
        html,
        flags=re.DOTALL
    )

    # Build CSS color variables for each class
    color_css_vars = '\n'.join([
        f'        --class-color-{name}: {color};'
        for name, color in class_color_map.items()
    ])

    # CSS overrides for Supertree
    custom_css = f"""
    <style>
        /* Hide mljar logo button - Ultra Aggressive */
        .st-logo-button,
        button.st-logo-button,
        div.st-logo-button,
        a.st-logo-button,
        [class*="logo"],
        [class*="Logo"],
        a[href*="mljar"],
        a[href*="MLJAR"],
        svg[class*="logo"] {{
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            width: 0 !important;
            height: 0 !important;
            pointer-events: none !important;
            position: absolute !important;
            left: -9999px !important;
        }}

        /* Hide color palette/layout pickers */
        .st-dropdown,
        .st-color-picker,
        input[type="color"],
        [class*="palette"],
        [id*="palette"] {{
            display: none !important;
            visibility: hidden !important;
        }}

        /* Hide specific toolbar items */
        .st-body-toolbar-div > *:not(button):not(.st-option-button) {{
             display: none !important;
        }}

        /* Custom class colors via CSS variables */
        :root {{
{color_css_vars}
        }}

        /* Reduce toolbar height and spacing */
        .st-toolbar, .st-body-toolbar-div {{
            padding: 2px 4px !important;
            min-height: 30px !important;
            gap: 5px !important;
        }}

        .st-option-button {{
            height: 24px !important;
            width: 24px !important;
            line-height: 24px !important;
        }}

        .st-option-button svg {{
            width: 14px !important;
            height: 14px !important;
        }}

        /* Constrain height to match distribution plot */
        .st-svg {{
            max-height: 400px !important;
            margin-top: 0 !important;
        }}

        .st-container {{
            gap: 0 !important;
            max-height: 400px !important;
        }}
    </style>
    """

    # JavaScript to apply custom colors based on class names
    # Create a mapping of class names to colors
    class_color_js = ', '.join(f'"{name}": "{color}"' for name, color in class_color_map.items())

    # Minimal JS to ensuring branding is hidden if regex fails
    # and to support simple class-based coloring if data attributes are present
    custom_js = f"""
    <script>
    (function() {{
        // Direct class name to color mapping
        const classColorMap = {{{class_color_js}}};

        function hideBranding() {{
            document.querySelectorAll('a[href*="mljar"], button[title*="mljar"], [class*="logo"], img[src*="mljar"]').forEach(el => {{
                // If it's an image, also hide its parent button
                if (el.tagName === 'IMG') {{
                   const btn = el.closest('button');
                   if (btn) {{
                       btn.style.display = 'none';
                       btn.style.visibility = 'hidden';
                   }}
                }}
                if (el.style.display !== 'none' || el.style.visibility !== 'hidden') {{
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                }}
            }});
        }}

        // Run once on load
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', hideBranding);
        }} else {{
            hideBranding();
        }}

        // And a few times shortly after
        setTimeout(hideBranding, 100);
        setTimeout(hideBranding, 500);
        setTimeout(hideBranding, 1000);
    }})();
    </script>
    """

    # Inject CSS into <head> or at start
    if '<head>' in html:
        html = html.replace('<head>', '<head>' + custom_css, 1)
    elif '<html>' in html:
        html = html.replace('<html>', '<html><head>' + custom_css + '</head>', 1)
    else:
        html = custom_css + html

    # Inject JS before </body> or at end
    if '</body>' in html:
        html = html.replace('</body>', custom_js + '</body>', 1)
    else:
        html += custom_js

    return html
