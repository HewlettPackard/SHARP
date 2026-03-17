"""
SHARP 4.0 Parameter Space Exploration

Provides strategies for exploring parameter spaces:
- Cartesian product (full sweep)
- Future: Random sampling, gradient descent, genetic algorithms, etc.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import copy
import itertools
import uuid
import warnings
from abc import ABC, abstractmethod
from typing import Any

from src.core.config.schema import ExperimentConfig, SweepConfig


# =============================================================================
# Utilities
# =============================================================================

def generate_launch_id(prefix: str = "sweep", sequence: int | None = None, session_id: str | None = None) -> str:
    """
    Generate a unique launch identifier.

    Args:
        prefix: Prefix for the ID (default: "sweep")
        sequence: Optional sequence number for ordering
        session_id: Optional session ID for grouping related runs

    Returns:
        Launch ID string (e.g., "sweep_0001_abc123" or "abc123")
    """
    if session_id is None:
        session_id = uuid.uuid4().hex[:6]

    if sequence is not None:
        return f"{prefix}_{sequence:04d}_{session_id}"
    return session_id


def cartesian_product_dict(param_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Expand a dictionary with scalar or list values into all combinations.

    Scalar values are treated as single-element lists.
    List values are expanded via Cartesian product.

    Example:
        {'a': [1, 2], 'b': 'x', 'c': [10, 20]}
        → [{'a': 1, 'b': 'x', 'c': 10},
           {'a': 1, 'b': 'x', 'c': 20},
           {'a': 2, 'b': 'x', 'c': 10},
           {'a': 2, 'b': 'x', 'c': 20}]

    Args:
        param_dict: Dictionary with scalar or list values

    Returns:
        List of dictionaries with all parameter combinations
    """
    if not param_dict:
        return [{}]

    keys = list(param_dict.keys())
    # Expand scalars to single-element lists
    value_lists = [
        v if isinstance(v, list) else [v]
        for v in [param_dict[k] for k in keys]
    ]

    # Compute Cartesian product
    return [dict(zip(keys, combo)) for combo in itertools.product(*value_lists)]


# =============================================================================
# Parameter Space Exploration Strategy (Abstract Base)
# =============================================================================

class ParameterSpaceStrategy(ABC):
    """
    Abstract base class for parameter space exploration strategies.

    This provides a common interface for different exploration methods:
    - Full sweep (Cartesian product)
    - Random sampling
    - Gradient-based optimization
    - Genetic algorithms
    - Bayesian optimization
    - etc.
    """

    def __init__(self, base_config: ExperimentConfig):
        """
        Initialize strategy with base configuration.

        Args:
            base_config: Base experiment configuration to vary
        """
        self.base_config = base_config

    @abstractmethod
    def generate_configurations(self) -> list[tuple[str, ExperimentConfig, dict[str, Any]]]:
        """
        Generate configurations to explore.

        Returns:
            List of (launch_id, config, parameters) tuples where:
            - launch_id: Unique identifier for this configuration
            - config: Complete ExperimentConfig for this run
            - parameters: Dict of parameters that varied (for logging)
        """
        pass

    @abstractmethod
    def get_parameter_ranges(self) -> dict[str, Any]:
        """
        Get the parameter space definition (for documentation).

        Returns:
            Dictionary describing the parameter space being explored
        """
        pass


# =============================================================================
# Cartesian Product Strategy (Full Sweep)
# =============================================================================

class CartesianSweepStrategy(ParameterSpaceStrategy):
    """
    Explores parameter space via full Cartesian product.

    This is the traditional "parameter sweep" that tries all combinations
    of specified parameter values.
    """

    def __init__(self, base_config: ExperimentConfig, sweep_config: SweepConfig):
        """
        Initialize Cartesian sweep strategy.

        Args:
            base_config: Base experiment configuration
            sweep_config: Sweep configuration defining parameter space
        """
        super().__init__(base_config)
        self.sweep_config = sweep_config
        self._session_id = uuid.uuid4().hex[:6]

    def generate_configurations(self) -> list[tuple[str, ExperimentConfig, dict[str, Any]]]:
        """
        Generate all combinations via Cartesian product.

        Returns:
            List of (launch_id, config, parameters) tuples
        """
        configs = []

        # Build a unified parameter space dictionary
        # Args are special: each entry is already a complete args list
        param_space: dict[str, Any] = {}

        if self.sweep_config.args:
            param_space['__args__'] = self.sweep_config.args

        if self.sweep_config.env:
            for key, value in self.sweep_config.env.items():
                param_space[f'env.{key}'] = value

        if self.sweep_config.options:
            for key, value in self.sweep_config.options.items():
                param_space[f'opt.{key}'] = value

        # Generate all combinations using cartesian_product_dict
        all_combinations = cartesian_product_dict(param_space)

        # Create a config for each combination
        for sequence, combo in enumerate(all_combinations, start=1):
            launch_id = generate_launch_id(prefix="sweep", sequence=sequence, session_id=self._session_id)

            config = copy.deepcopy(self.base_config)
            parameters = {}

            # Apply each parameter from the combination
            for key, value in combo.items():
                if key == '__args__':
                    config.options['args'] = value
                    parameters['args'] = value
                elif key.startswith('env.'):
                    env_key = key[4:]  # Remove 'env.' prefix
                    if env_key in config.environment and config.environment[env_key] != value:
                        warnings.warn(
                            f"Sweep overriding environment variable '{env_key}': "
                            f"{config.environment[env_key]} → {value}"
                        )
                    config.environment[env_key] = value
                    parameters[key] = value
                elif key.startswith('opt.'):
                    opt_key = key[4:]  # Remove 'opt.' prefix
                    if opt_key in config.options and config.options[opt_key] != value:
                        warnings.warn(
                            f"Sweep overriding option '{opt_key}': "
                            f"{config.options[opt_key]} → {value}"
                        )
                    config.options[opt_key] = value
                    parameters[opt_key] = value

            configs.append((launch_id, config, parameters))

        return configs

    def get_parameter_ranges(self) -> dict[str, Any]:
        """
        Get parameter ranges for documentation.

        Returns:
            Dictionary with parameter names and their ranges
        """
        ranges: dict[str, Any] = {}

        if self.sweep_config.args:
            ranges['args'] = f"{len(self.sweep_config.args)} combinations"

        if self.sweep_config.env:
            for key, value in self.sweep_config.env.items():
                ranges[f'env.{key}'] = value if isinstance(value, list) else [value]

        if self.sweep_config.options:
            for key, value in self.sweep_config.options.items():
                ranges[key] = value if isinstance(value, list) else [value]

        return ranges


# =============================================================================
# Factory Function
# =============================================================================

def create_parameter_space_strategy(
    base_config: ExperimentConfig,
    sweep_config: SweepConfig | None = None,
    strategy_type: str = "cartesian"
) -> ParameterSpaceStrategy:
    """
    Factory function to create parameter space exploration strategy.

    Args:
        base_config: Base experiment configuration
        sweep_config: Sweep configuration (required for cartesian)
        strategy_type: Type of strategy ("cartesian", future: "random", "gradient", etc.)

    Returns:
        Configured ParameterSpaceStrategy instance

    Raises:
        ValueError: If strategy_type is unknown or required config is missing
    """
    if strategy_type == "cartesian":
        if sweep_config is None:
            raise ValueError("cartesian strategy requires sweep_config")
        return CartesianSweepStrategy(base_config, sweep_config)

    # Future strategies will be added here:
    # elif strategy_type == "random":
    #     return RandomSamplingStrategy(base_config, ...)
    # elif strategy_type == "gradient":
    #     return GradientDescentStrategy(base_config, ...)

    raise ValueError(f"Unknown parameter space strategy: {strategy_type}")
