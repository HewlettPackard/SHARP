"""
Factor analysis rendering utilities for profile tab.

Provides functions to render factor information cards, scatter plots,
and comparison tables for selected performance factors.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""
import numpy as np
import polars as pl
import matplotlib.pyplot as plt
from shiny import ui
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import r2_score
from sklearn.preprocessing import StandardScaler

from src.core.metrics.factors import get_factor_info
from src.core.stats.narrative import format_sig_figs
from src.core.config.settings import Settings


def _create_error_figure(message: str, color: str = '#999') -> plt.Figure:
    """
    Create a simple error/message figure.

    Args:
        message: Message to display
        color: Text color

    Returns:
        Matplotlib figure with message
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.text(0.5, 0.5, message, ha='center', va='center', fontsize=12, color=color)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    return fig


def _prepare_plot_data(data: pl.DataFrame, factor_name: str, metric: str, cutoff: float):
    """
    Prepare and clean data for scatter plot.

    Args:
        data: DataFrame with factor and metric columns
        factor_name: Name of the factor column
        metric: Name of the performance metric column
        cutoff: Cutoff value for binary classification

    Returns:
        Tuple of (factor_clean, metric_clean, categories_clean) or None if insufficient data
    """
    # Create binary classification
    data_plot = data.with_columns([
        pl.when(pl.col(metric) > cutoff)
          .then(pl.lit('RIGHT'))
          .otherwise(pl.lit('LEFT'))
          .alias('category')
    ])

    # Extract data for plotting
    factor_values = data_plot[factor_name].to_numpy()
    metric_values = data_plot[metric].to_numpy()
    categories = data_plot['category'].to_numpy()

    # Remove NaN values
    valid_mask = ~(np.isnan(factor_values) | np.isnan(metric_values))
    factor_clean = factor_values[valid_mask]
    metric_clean = metric_values[valid_mask]
    cat_clean = categories[valid_mask]

    if len(factor_clean) < 2:
        return None

    return factor_clean, metric_clean, cat_clean


def _calculate_linear_r2(X: np.ndarray, y: np.ndarray) -> tuple[LinearRegression, float]:
    """
    Calculate R² for linear regression.

    Args:
        X: Factor values (n_samples, 1)
        y: Metric values (n_samples,)

    Returns:
        Tuple of (fitted model, r2_score)
    """
    model = LinearRegression()
    model.fit(X, y)
    y_pred = model.predict(X)
    r2 = r2_score(y, y_pred)
    return model, r2


def _calculate_mcfadden_r2(X: np.ndarray, y_binary: np.ndarray) -> float:
    """
    Calculate McFadden's pseudo R² for logistic regression.

    This matches R's regclass::rsquared() for glm binomial models.
    Uses StandardScaler to avoid numerical issues with large values.

    Args:
        X: Factor values (n_samples, 1)
        y_binary: Binary class labels (n_samples,)

    Returns:
        McFadden's pseudo R² value (0.0 if calculation fails)
    """
    if len(np.unique(y_binary)) <= 1:
        return 0.0

    # Scale X to avoid numerical issues with large values (R's glm does this internally)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    log_model = LogisticRegression(max_iter=1000, solver='lbfgs', penalty=None)
    log_model.fit(X_scaled, y_binary)

    # Compute McFadden's pseudo R²: 1 - (log L_fitted / log L_null)
    y_pred_proba = log_model.predict_proba(X_scaled)

    # Log-likelihood of fitted model: LL = sum(y_i * log(p_i) + (1-y_i) * log(1-p_i))
    eps = 1e-15
    p_class1 = np.clip(y_pred_proba[:, 1], eps, 1 - eps)
    ll_fitted = np.sum(y_binary * np.log(p_class1) + (1 - y_binary) * np.log(1 - p_class1))

    # Log-likelihood of null model (intercept only)
    p_null = np.clip(np.mean(y_binary), eps, 1 - eps)
    ll_null = np.sum(y_binary * np.log(p_null) + (1 - y_binary) * np.log(1 - p_null))

    # McFadden's pseudo R² (clamp to 0 if negative, matching R's behavior)
    return max(0.0, 1 - (ll_fitted / ll_null)) if ll_null != 0 else 0.0


def _plot_scatter_with_regression(ax: plt.Axes, factor_clean: np.ndarray, metric_clean: np.ndarray,
                                   cat_clean: np.ndarray, model: LinearRegression,
                                   factor_name: str, metric: str):
    """
    Plot scatter points with regression line.

    Args:
        ax: Matplotlib axes to plot on
        factor_clean: Clean factor values
        metric_clean: Clean metric values
        cat_clean: Category labels
        model: Fitted linear regression model
        factor_name: Factor column name
        metric: Metric column name
    """
    # Get colors from settings
    settings = Settings()
    dist_colors = settings.get("gui.distribution", {})
    left_color = dist_colors.get("left_color", "#2ca02c")
    right_color = dist_colors.get("right_color", "#ff7f0e")

    # Plot scatter points by category
    for category, color in [('LEFT', left_color), ('RIGHT', right_color)]:
        mask = cat_clean == category
        ax.scatter(factor_clean[mask], metric_clean[mask],
                  c=color, label=category, alpha=0.6, s=50)

    # Add regression line
    x_line = np.linspace(factor_clean.min(), factor_clean.max(), 100)
    y_line = model.predict(x_line.reshape(-1, 1))
    ax.plot(x_line, y_line, 'k--', alpha=0.5, linewidth=2)

    ax.set_xlabel(factor_name, fontsize=12)
    ax.set_ylabel(metric, fontsize=12)
    ax.legend()
    ax.grid(True, alpha=0.3)


def render_factor_info_card(factor_name: str):
    """
    Render information card for a performance factor.

    Args:
        factor_name: Name of the factor

    Returns:
        Shiny UI card with factor description, references, and mitigations
    """
    factor_info = get_factor_info(factor_name)
    if not factor_info:
        return ui.p(f'Factor "{factor_name}" not found in factor database.',
                   style='color: #999; font-style: italic;')

    description = factor_info.get('description', 'No description available')
    references = factor_info.get('references', {})

    # Build references HTML
    ref_links = []
    for name, url in references.items():
        ref_links.append(ui.tags.a(name, href=url, target='_blank'))
    refs_content = ui.tags.span(*[
        item for pair in zip(ref_links, [ui.tags.span(' | ')] * len(ref_links))
        for item in pair
    ][:-1]) if ref_links else ui.tags.span('No references available', style='color: #999;')

    return ui.card(
        ui.card_header(f'Factor: {factor_name}'),
        ui.tags.div(
            ui.markdown(description),
            style='margin-bottom: 15px;'
        ),
        ui.tags.div(
            ui.tags.strong('References: '),
            refs_content,
            style='margin-bottom: 10px; font-size: 0.9em;'
        )
    )


def render_factor_scatter_plot(data: pl.DataFrame, factor_name: str, metric: str, cutoff: float):
    """
    Render scatter plot of factor vs performance metric with classification.

    Args:
        data: DataFrame with factor and metric columns
        factor_name: Name of the factor column
        metric: Name of the performance metric column
        cutoff: Cutoff value for binary classification

    Returns:
        Matplotlib figure or None if error
    """
    # Validate input data
    if data is None or data.is_empty():
        return _create_error_figure('No data available')

    if factor_name not in data.columns or metric not in data.columns:
        return _create_error_figure(f'Factor "{factor_name}" or metric "{metric}" not in data', color='red')

    # Prepare and clean data
    plot_data = _prepare_plot_data(data, factor_name, metric, cutoff)
    if plot_data is None:
        return _create_error_figure('Insufficient data points for plotting')

    factor_clean, metric_clean, cat_clean = plot_data

    # Calculate statistics
    X = factor_clean.reshape(-1, 1)
    y = metric_clean
    y_binary = (cat_clean == 'RIGHT').astype(int)

    model, r2_continuous = _calculate_linear_r2(X, y)
    log_r2 = _calculate_mcfadden_r2(X, y_binary)

    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))
    _plot_scatter_with_regression(ax, factor_clean, metric_clean, cat_clean, model, factor_name, metric)

    ax.set_title(f'{factor_name} explains {r2_continuous*100:.2f}% of variation in {metric}\n'
                f'and {log_r2*100:.2f}% of variation in performance classes',
                fontsize=12, fontweight='bold')

    plt.tight_layout(pad=1.0)
    fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.15)

    return fig


def render_factor_comparison_table(data: pl.DataFrame, factor_name: str, metric: str, cutoff: float):
    """
    Render comparison table showing factor statistics for LEFT vs RIGHT groups.

    Args:
        data: DataFrame with factor and metric columns
        factor_name: Name of the factor column
        metric: Name of the performance metric column
        cutoff: Cutoff value for binary classification

    Returns:
        Shiny UI table with group statistics
    """
    if data is None or data.is_empty():
        return ui.p('No data available', style='color: #999; font-style: italic;')

    if factor_name not in data.columns or metric not in data.columns:
        return ui.p(f'Factor "{factor_name}" or metric "{metric}" not in data',
                   style='color: red;')

    # Create binary classification
    data_groups = data.with_columns([
        pl.when(pl.col(metric) > cutoff)
          .then(pl.lit('RIGHT'))
          .otherwise(pl.lit('LEFT'))
          .alias('category')
    ])

    # Compute statistics per group
    try:
        grouped = data_groups.group_by('category').agg([
            pl.col(factor_name).count().alias('n'),
            pl.col(factor_name).mean().alias('mean'),
            pl.col(factor_name).median().alias('median'),
            pl.col(factor_name).std().alias('std')
        ])

        # Convert to dict for easy access
        stats_dict = {}
        for row in grouped.iter_rows(named=True):
            stats_dict[row['category']] = {
                'n': row['n'],
                'mean': row['mean'],
                'median': row['median'],
                'std': row['std']
            }

        # Get colors from settings
        settings = Settings()
        dist_colors = settings.get("gui.distribution", {})
        left_color = dist_colors.get("left_color", "#2ca02c")
        right_color = dist_colors.get("right_color", "#ff7f0e")

        # Create color map with transparency
        group_colors = {
            'LEFT': left_color + '66',  # 40% opacity
            'RIGHT': right_color + '66'
        }

        return ui.tags.div(
            ui.tags.h4(f'{factor_name} Statistics by Group', style='margin-bottom: 10px;'),
            ui.tags.table(
                ui.tags.thead(
                    ui.tags.tr(
                        ui.tags.th('Group', style='padding: 8px; text-align: left;'),
                        ui.tags.th('N', style='padding: 8px; text-align: right;'),
                        ui.tags.th('Mean', style='padding: 8px; text-align: right;'),
                        ui.tags.th('Median', style='padding: 8px; text-align: right;'),
                        ui.tags.th('Std Dev', style='padding: 8px; text-align: right;'),
                    )
                ),
                ui.tags.tbody(
                    *[
                        ui.tags.tr(
                            ui.tags.td(group, style='padding: 8px; font-weight: bold;'),
                            ui.tags.td(f"{stats_dict[group]['n']}", style='padding: 8px; text-align: right;'),
                            ui.tags.td(format_sig_figs(stats_dict[group]['mean'], sig_figs=3),
                                     style='padding: 8px; text-align: right;'),
                            ui.tags.td(format_sig_figs(stats_dict[group]['median'], sig_figs=3),
                                     style='padding: 8px; text-align: right;'),
                            ui.tags.td(format_sig_figs(stats_dict[group]['std'], sig_figs=3),
                                     style='padding: 8px; text-align: right;'),
                            style=f"background-color: {group_colors[group]};"
                        )
                        for group in ['LEFT', 'RIGHT'] if group in stats_dict
                    ]
                ),
                style='width: 100%; border-collapse: collapse; font-size: 0.9em;'
            )
        )

    except Exception as e:
        return ui.p(f'Error computing statistics: {str(e)}', style='color: red; font-size: 0.9em;')
