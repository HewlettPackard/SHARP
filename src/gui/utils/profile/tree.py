"""
Decision tree utilities for profile workflow.

Functions for training, rendering, and analyzing decision trees for
performance classification.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Optional, Any, Dict, List
from io import BytesIO
import traceback
import numpy as np
import polars as pl
import matplotlib.pyplot as plt
from PIL import Image
import graphviz
from sklearn.tree import DecisionTreeClassifier

from src.core.stats.correlations import compute_generalized_correlation
from src.core.config.settings import Settings


def _encode_features(data: pl.DataFrame, feature_cols: list[str]) -> tuple[np.ndarray, list[str]]:
    """
    Encode features with one-hot encoding for categorical columns.
    Preserves NaN values for sklearn's missing value support.

    Args:
        data: Polars DataFrame
        feature_cols: List of column names to encode

    Returns:
        Tuple of (encoded numpy array, list of encoded feature names)
    """
    try:
        X_parts = []
        feature_names = []

        for i, col in enumerate(feature_cols):
            col_data = data[col]

            if col_data.dtype in [pl.Utf8, pl.Categorical]:
                # One-hot encode categorical column
                # Treat null as a separate category (encoded as all 0s)
                unique_cats = col_data.unique().drop_nulls().to_list()
                for cat in sorted(unique_cats):
                    indicator = (col_data == cat).cast(pl.Int32).to_numpy()
                    X_parts.append(indicator.reshape(-1, 1))
                    # Create feature name like "column_name=value"
                    feature_names.append(f"{col}={cat}")
            elif col_data.dtype in [pl.Float64, pl.Int64, pl.Int32, pl.Int16, pl.Int8]:
                # Keep numeric column as-is, preserving NaN for sklearn
                numeric_array = col_data.to_numpy().astype(np.float64)
                X_parts.append(numeric_array.reshape(-1, 1))
                # Keep original column name for numeric features
                feature_names.append(col)

        if not X_parts:
            return None, []

        result = np.hstack(X_parts) if len(X_parts) > 1 else X_parts[0]
        return result, feature_names

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, []


def _filter_predictors_by_variance(data: pl.DataFrame, exclude: list[str], metric: str) -> list[str]:
    """
    Filter columns to find potential predictors with variance.

    Args:
        data: Polars DataFrame
        exclude: List of column names to exclude
        metric: Target metric column name

    Returns:
        List of column names with at least 2 unique non-NA values
    """
    variance_check = []
    for col in data.columns:
        try:
            unique_count = len(data[col].drop_nulls().unique())
            variance_check.append(unique_count > 1)
        except Exception:
            variance_check.append(False)

    potential_predictors = [col for col, has_var in zip(data.columns, variance_check)
                           if has_var and col not in exclude and col != metric]
    return potential_predictors


def _compute_predictor_correlations(data: pl.DataFrame, metric: str, predictors: list[str],
                                   sample_size: int = 100) -> Dict[str, float]:
    """
    Compute correlations between predictors and metric.

    Args:
        data: Polars DataFrame
        metric: Target metric column name
        predictors: List of predictor names
        sample_size: Number of rows to sample for correlation computation

    Returns:
        Dictionary mapping predictor names to absolute correlation values
    """
    # Sample rows if dataset is large
    sample_rows = list(range(len(data)))
    if len(data) > sample_size:
        np.random.seed(42)
        sample_rows = sorted(np.random.choice(len(data), sample_size, replace=False))

    sampled_data = data[sample_rows] if len(sample_rows) < len(data) else data
    metric_values = sampled_data[metric].to_numpy()

    correlations = {}

    for pred in predictors:
        try:
            pred_values = sampled_data[pred].to_numpy()
            if len(pred_values) >= 3 and len(metric_values) >= 3:
                corr = np.abs(compute_generalized_correlation(pred_values, metric_values))
                if not np.isnan(corr):
                    correlations[pred] = corr
        except Exception:
            continue

    return correlations


def _filter_and_select_top_predictors(correlations: Dict[str, float], max_predictors: int,
                                      max_correlation: float) -> list[str]:
    """
    Filter correlations by threshold and select top N predictors.

    Args:
        correlations: Dictionary mapping predictor names to correlation values
        max_predictors: Maximum number of predictors to return
        max_correlation: Correlation threshold for filtering

    Returns:
        List of top predictor names
    """
    # Filter out correlations >= max_correlation
    filtered_correlations = {k: v for k, v in correlations.items() if v < max_correlation}

    # Fallback if all correlations are >= max_correlation
    if not filtered_correlations:
        filtered_correlations = {k: v for k, v in correlations.items() if v < 1.0}
    if not filtered_correlations:
        filtered_correlations = correlations  # Last resort

    # Select top predictors by correlation (descending)
    num_to_select = min(max_predictors, len(filtered_correlations))
    sorted_preds = sorted(filtered_correlations.keys(),
                         key=lambda p: filtered_correlations[p],
                         reverse=True)
    return sorted_preds[:num_to_select]


def select_tree_predictors(data: pl.DataFrame, metric: str, exclude: list[str] = None,
                          max_predictors: int = 100, max_correlation: float = 0.99) -> list[str]:
    """
    Select best predictors for decision tree, using generalized correlation.

    Filters out:
    - Columns with <=1 unique non-NA values
    - User-excluded columns
    - The metric column itself

    If too many predictors, selects top N by generalized correlation.
    Correlations computed on sampled rows for speed if dataset is large.

    Args:
        data: Polars dataframe
        metric: Target metric column name
        exclude: List of column names to exclude
        max_predictors: Maximum number of predictors to return
        max_correlation: Correlation threshold for filtering

    Returns:
        List of predictor column names
    """
    if exclude is None:
        exclude = []

    try:
        # Step 1: Filter by variance
        potential_predictors = _filter_predictors_by_variance(data, exclude, metric)

        # Step 2: If too many predictors, compute correlations and select top N
        if len(potential_predictors) > max_predictors:
            correlations = _compute_predictor_correlations(data, metric, potential_predictors, sample_size=100)

            # Step 3: Filter and select top predictors
            return _filter_and_select_top_predictors(correlations, max_predictors, max_correlation)

        # If few enough predictors, return all
        return potential_predictors

    except Exception as e:
        import traceback
        traceback.print_exc()
        return []


def select_complete_rows(
    data: pl.DataFrame,
    columns: list[str],
    target_rows: int = None,
    completeness_threshold: float = None
) -> pl.DataFrame:
    """
    Select rows from data that have high completeness in the specified columns.

    Uses an adaptive threshold approach: starts with the preferred completeness_threshold
    and progressively lowers it until enough rows are found. For highly sparse datasets,
    this ensures tree training can proceed even if no rows meet the initial threshold.

    Args:
        data: DataFrame to select rows from
        columns: List of column names to check for completeness
        target_rows: Target number of rows to return. If None, uses settings
        completeness_threshold: Initial minimum fraction of non-null values. If None, uses settings

    Returns:
        DataFrame containing only the selected complete rows
    """
    # Load defaults from settings if not provided
    if target_rows is None:
        target_rows = Settings().get("profiling.tree_training.target_rows", 1000)
    if completeness_threshold is None:
        completeness_threshold = Settings().get("profiling.tree_training.completeness_threshold", 0.95)


    # Calculate completeness for each row (fraction of non-null values)
    try:
        # Create a DataFrame with just the columns we care about
        subset = data.select(columns)

        # Count non-null values per row
        non_null_counts = subset.select([
            pl.sum_horizontal([pl.col(c).is_not_null().cast(pl.Int32) for c in columns]).alias("non_null_count")
        ])

        # Calculate completeness fraction
        total_cols = len(columns)
        completeness = (non_null_counts["non_null_count"] / total_cols)

        # Adaptive threshold: try progressively lower thresholds until we get enough rows
        # This handles highly sparse datasets where no rows meet high completeness
        thresholds_to_try = [completeness_threshold, 0.75, 0.5, 0.25, 0.0]
        valid_indices = []

        for threshold in thresholds_to_try:
            valid_mask = completeness >= threshold
            valid_indices = [i for i, is_valid in enumerate(valid_mask.to_list()) if is_valid]

            # If we have enough rows, use this threshold
            if len(valid_indices) >= min(10, target_rows):
                break

        # Take up to target_rows
        if len(valid_indices) > target_rows:
            valid_indices = valid_indices[:target_rows]

        # Return the filtered data
        if not valid_indices:
            return data.head(0)  # Return empty DataFrame with same schema

        result = data[valid_indices]
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return data.head(0)


def compute_tree(data: pl.DataFrame, metric: str, cutoff: float,
                exclude: list[str] = None, max_predictors: int = 100,
                max_correlation: float = 0.99, predictors: list[str] = None) -> Optional[DecisionTreeClassifier]:
    """
    Train decision tree classifier for performance classification.

    Creates binary target: Fast (y=0) if metric <= cutoff, Slow (y=1) if metric > cutoff.
    Includes categorical variables via one-hot encoding.

    Args:
        data: Polars dataframe with features and metric
        metric: Target metric column name
        cutoff: Threshold for binary classification
        exclude: List of column names to exclude from features
        max_predictors: Maximum number of predictors
        max_correlation: Correlation threshold for filtering
        predictors: Pre-selected predictor list (if None, will compute from data)

    Returns:
        Fitted DecisionTreeClassifier, or None if unable to train
    """
    if data is None or data.is_empty():
        return None

    if exclude is None:
        exclude = []

    try:

        # Validate metric column
        if not metric or metric.strip() == "":
            return None

        if metric not in data.columns:
            return None

        # Select predictors (or use provided ones)
        if predictors is None:
            predictors = select_tree_predictors(data, metric, exclude, max_predictors, max_correlation)

        if not predictors:
            return None


        # Prepare feature matrix and target from ALL rows (like R version)
        # R version uses na.rpart to handle missing values, we'll drop nulls in target but keep all feature rows
        try:
            # Create binary target for all rows
            y_data = (data[metric] > cutoff).cast(pl.Int32)

            # Remove rows where target (metric) is null - can't train on those
            valid_mask = data[metric].is_not_null()
            valid_data = data.filter(valid_mask)

            if len(valid_data) < 3:
                return None


            # Prepare features and target
            X_data = valid_data.select(predictors)
            y = (valid_data[metric] > cutoff).cast(pl.Int32).to_numpy()


        except Exception as prep_err:
            import traceback
            traceback.print_exc()
            return None

        # Encode features (one-hot for categoricals, as-is for numeric)
        X, encoded_feature_names = _encode_features(X_data, predictors)
        if X is None:
            return None


        # Train tree
        tree = DecisionTreeClassifier(
            max_depth=5,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42
        )
        tree.fit(X, y)

        # Store BOTH the original predictor names AND encoded feature names
        # feature_names_ is used for tree visualization (must match encoded features)
        # original_predictors_ is used for summarize_tree to re-encode from original data
        tree.feature_names_ = encoded_feature_names
        tree.original_predictors_ = predictors

        return tree

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None



def _format_threshold(threshold: float) -> str:
    """
    Format tree threshold value for display.

    Uses scientific notation for very large/small numbers.

    Args:
        threshold: Threshold value to format

    Returns:
        Formatted threshold string
    """
    if abs(threshold) >= 1000 or (abs(threshold) < 0.01 and threshold != 0):
        return f"{threshold:.1e}"
    else:
        return f"{threshold:.2f}"


def _create_dot_node(node_id: int, tree, feature_names: List[str],
                     left_color: str, right_color: str) -> str:
    """
    Create DOT graph node specification for a tree node.

    Args:
        node_id: Index of the node in the tree
        tree: Sklearn tree object
        feature_names: List of feature names
        left_color: Hex color for class 0 (Better)
        right_color: Hex color for class 1 (Worse)

    Returns:
        DOT specification string for the node
    """
    if tree.feature[node_id] == -2:  # Leaf node
        # Determine class for color
        values = tree.value[node_id][0]
        class_idx = np.argmax(values)
        color = left_color if class_idx == 0 else right_color
        # Show total number of samples in leaf
        n_samples = tree.n_node_samples[node_id]
        return f'{node_id} [label="{n_samples}", fillcolor="{color}"] ;'
    else:  # Internal node
        feature_name = feature_names[tree.feature[node_id]]
        return f'{node_id} [label="{feature_name}", fillcolor="#f0f0f0"] ;'


def _create_dot_edges(node_id: int, tree) -> List[str]:
    """
    Create DOT graph edge specifications for a tree node's children.

    Args:
        node_id: Index of the node in the tree
        tree: Sklearn tree object

    Returns:
        List of DOT edge specification strings
    """
    edges = []
    left_child = tree.children_left[node_id]
    right_child = tree.children_right[node_id]

    if left_child != -1:  # Has children
        threshold = tree.threshold[node_id]
        threshold_str = _format_threshold(threshold)

        # Left edge (<=)
        edges.append(f'{node_id} -> {left_child} [label=" ≤ {threshold_str}"] ;')
        # Right edge (>)
        edges.append(f'{node_id} -> {right_child} [label=" > {threshold_str}"] ;')

    return edges


def _build_tree_dot_graph(tree: DecisionTreeClassifier, feature_names: List[str],
                         left_color: str, right_color: str) -> str:
    """
    Build DOT graph representation of a decision tree.

    Args:
        tree: Trained DecisionTreeClassifier
        feature_names: List of feature names for display
        left_color: Hex color for class 0 leaves
        right_color: Hex color for class 1 leaves

    Returns:
        DOT graph as a string
    """
    dot_lines = ['digraph Tree {']
    dot_lines.append('node [shape=box, style="filled, rounded", fontname=helvetica] ;')
    dot_lines.append('edge [fontname=helvetica] ;')

    # Create nodes
    for i in range(tree.tree_.node_count):
        dot_lines.append(_create_dot_node(i, tree.tree_, feature_names, left_color, right_color))

    # Create edges
    for i in range(tree.tree_.node_count):
        dot_lines.extend(_create_dot_edges(i, tree.tree_))

    dot_lines.append('}')
    return '\n'.join(dot_lines)


def _render_dot_to_matplotlib(dot_data: str, figsize: tuple = (14, 10)):
    """
    Render DOT graph to matplotlib figure.

    Args:
        dot_data: DOT graph specification string
        figsize: Figure size tuple (width, height)

    Returns:
        Matplotlib figure with rendered tree
    """
    # Render using graphviz
    graph = graphviz.Source(dot_data)
    png_bytes = graph.pipe(format='png')

    # Display in matplotlib
    img = Image.open(BytesIO(png_bytes))
    fig, ax = plt.subplots(figsize=figsize)
    ax.imshow(img)
    ax.axis('off')
    plt.tight_layout()
    return fig


def _create_error_figure(message: str, color: str = '#666') -> Any:
    """
    Create a matplotlib figure with an error or info message.

    Args:
        message: Message to display
        color: Text color (default: gray)

    Returns:
        Matplotlib figure with centered text
    """
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.text(0.5, 0.5, message, ha='center', va='center', fontsize=10, color=color)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    return fig


def render_tree_plot(tree: DecisionTreeClassifier, left_color: str, right_color: str) -> Any:
    """
    Render decision tree visualization using graphviz and matplotlib.

    Args:
        tree: Trained DecisionTreeClassifier with feature_names_ attribute
        left_color: Hex color for "Better" class (leaf nodes)
        right_color: Hex color for "Worse" class (leaf nodes)

    Returns:
        Matplotlib figure with tree visualization
    """
    if tree is None:
        return _create_error_figure("No tree available. Train a tree by selecting a metric and cutoff.")

    try:
        # Get feature names from tree
        feature_names = getattr(tree, 'feature_names_', None)
        if feature_names is None:
            feature_names = [f"Feature_{i}" for i in range(tree.n_features_in_)]

        # Build DOT graph representation
        dot_data = _build_tree_dot_graph(tree, feature_names, left_color, right_color)

        # Render to matplotlib
        return _render_dot_to_matplotlib(dot_data)

    except Exception as e:
        traceback.print_exc()
        return _create_error_figure(f"Error rendering tree:\n{str(e)}", color='#dc3545')



def _calculate_aic(y_true: np.ndarray, y_pred: np.ndarray, n_nodes: int) -> Optional[float]:
    """
    Calculate AIC for a classification tree.

    Args:
        y_true: True labels
        y_pred: Predicted labels
        n_nodes: Number of nodes in the tree

    Returns:
        AIC value, or None if invalid
    """
    correct = (y_true == y_pred).sum()
    n = len(y_true)

    if n == 0 or correct == 0:
        return None

    # Log-likelihood: n * log(p) where p is accuracy
    accuracy = correct / n
    log_likelihood = n * np.log(max(accuracy, 1e-10))  # Avoid log(0)

    # AIC = 2k - 2ln(L)
    aic = 2 * n_nodes - 2 * log_likelihood

    return aic


def summarize_tree(
    tree: DecisionTreeClassifier,
    data: pl.DataFrame,
    metric_col: str,
    cutoff: float,
    exclude: list[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Summarize decision tree statistics including AIC.

    Includes categorical variables via one-hot encoding and respects the exclude list.

    Args:
        tree: Trained DecisionTreeClassifier
        data: Original data used to train the tree
        metric_col: Name of the metric column
        cutoff: Cutoff value used for classification
        exclude: List of column names to exclude (for consistency with tree training)

    Returns:
        Dictionary with tree statistics (n_nodes, n_leaves, aic, etc.) or None if invalid
    """
    if tree is None:
        return None

    if exclude is None:
        exclude = []

    try:
        # Get number of nodes and leaves
        n_nodes = tree.tree_.node_count
        n_leaves = tree.tree_.n_leaves

        # Use the original predictor names to select from data
        # (feature_names_ contains encoded names which won't match data columns)
        if not hasattr(tree, 'original_predictors_'):
            # Fallback for old trees without this attribute
            if not hasattr(tree, 'feature_names_'):
                return None
            feature_cols = tree.feature_names_
        else:
            feature_cols = tree.original_predictors_

        # Prepare data: select features and handle categorical encoding
        selected_data = data.select(feature_cols).drop_nulls().clone()

        # Encode features (one-hot for categoricals, as-is for numeric)
        X, _ = _encode_features(selected_data, feature_cols)
        if X is None:
            return None

        # Drop any rows with NaN
        mask = ~np.isnan(X).any(axis=1)
        X = X[mask]

        if len(X) == 0:
            return None

        # Create binary classification target (must match rows in X after dropping NaNs)
        y_data = data[metric_col].to_numpy()
        y_true = (y_data > cutoff).astype(int)

        # Align with X's row count
        if len(y_true) > len(X):
            y_true = y_true[:len(X)]
        elif len(y_true) < len(X):
            X = X[:len(y_true)]

        # Compute predictions
        y_pred = tree.predict(X)

        # Calculate AIC
        aic = _calculate_aic(y_true, y_pred, n_nodes)
        if aic is None:
            return None

        # Calculate accuracy for reporting
        accuracy = (y_true == y_pred).sum() / len(y_true)
        log_likelihood = len(y_true) * np.log(max(accuracy, 1e-10))

        return {
            'n_nodes': n_nodes,
            'n_leaves': n_leaves,
            'aic': aic,
            'accuracy': accuracy,
            'log_likelihood': log_likelihood
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None


def search_for_cutoff(
    data: pl.DataFrame,
    metric_col: str,
    exclude: list[str],
    max_search_points: int = 100,
    progress_callback: Optional[callable] = None
) -> Optional[float]:
    """
    Search for optimal cutoff point that minimizes decision tree AIC.

    Searches across the range of metric values to find the cutoff point that
    produces a decision tree with the lowest AIC (Akaike Information Criterion).
    Only considers trees with more than one node (non-trivial trees).

    PERFORMANCE: Selects predictors ONCE and reuses them for all cutoff points.

    Args:
        data: Polars DataFrame containing the data
        metric_col: Name of the metric column to use for classification
        exclude: List of predictor names to exclude from the tree
        max_search_points: Maximum number of cutoff points to search (default: 100)
        progress_callback: Optional callback function(progress_pct: float, detail: str)

    Returns:
        Optimal cutoff value, or None if no valid trees found
    """
    try:

        perf = data[metric_col].drop_nulls().to_numpy()

        if len(perf) == 0:
            return None

        # PERFORMANCE OPTIMIZATION: Select predictors ONCE for all cutoff points
        predictors = select_tree_predictors(data, metric_col, exclude, max_predictors=100, max_correlation=0.99)
        if not predictors:
            return None

        min_aic = float('inf')
        best_cutoff = perf[0]

        # Create search points across the range
        max_points = min(max_search_points, len(perf))
        search_points = np.linspace(perf.min(), perf.max(), max_points)

        valid_trees = 0
        for i, cutoff_candidate in enumerate(search_points):
            # Compute tree for this cutoff using pre-selected predictors
            tree = compute_tree(data, metric_col, float(cutoff_candidate), exclude=exclude, predictors=predictors)

            # Only consider valid trees with more than one node
            if tree is not None:
                tree_summary = summarize_tree(tree, data, metric_col, float(cutoff_candidate), exclude=exclude)
                if tree_summary is not None and tree_summary.get('n_nodes', 0) > 1:
                    valid_trees += 1
                    aic = tree_summary.get('aic')
                    if aic is not None and aic < min_aic:
                        min_aic = aic
                        best_cutoff = cutoff_candidate

            # Call progress callback if provided
            if progress_callback:
                progress_pct = (i + 1) / max_points
                progress_callback(progress_pct, f"Point {i+1} of {max_points}")

        return float(best_cutoff) if best_cutoff is not None else None

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None
