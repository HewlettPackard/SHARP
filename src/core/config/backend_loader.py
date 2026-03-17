#!/usr/bin/env python3
"""
Backend configuration loading and validation utilities.

Handles loading backend YAML configurations, merging them into config,
and validating backend chains for composability constraints.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import yaml
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.core.config.include_resolver import get_project_root


class BackendChainError(Exception):
    """Raised when backend chain violates composability constraints."""
    pass


def merge_config(base: Dict[str, Any], updates: Dict[str, Any]) -> None:
    """
    Merge updates into base configuration (in-place).

    Performs a recursive merge, updating nested dictionaries rather than replacing them.

    Args:
        base: Base configuration dictionary (modified in-place)
        updates: Updates to merge into base
    """
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            merge_config(base[key], value)
        else:
            base[key] = value


def resolve_backend_paths(
    backend_names: list[str],
    backends_dir: Path | None = None
) -> list[Path]:
    """
    Resolve backend names to file paths in the standard backends directory.

    Args:
        backend_names: List of backend names (without .yaml extension)
        backends_dir: Directory containing backend YAML files (default: project_root/backends)

    Returns:
        List of Path objects for existing backend files
    """
    if backends_dir is None:
        backends_dir = get_project_root() / "backends"

    paths = []
    for name in backend_names:
        backend_file = backends_dir / f"{name}.yaml"
        if backend_file.exists():
            paths.append(backend_file)
    return paths


def load_backend_configs(
    config_files: list[Path],
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Load backend configurations from YAML files and merge into config.

    Args:
        config_files: List of YAML file paths to load (in order)
        config: Base configuration dictionary (modified in-place)

    Returns:
        Backend options dictionary from config
    """
    if "backend_options" not in config:
        config["backend_options"] = {}

    for config_file in config_files:
        if config_file.exists():
            with open(config_file, 'r') as f:
                file_config = yaml.safe_load(f) or {}
            merge_config(config, file_config)

    options = config.get("backend_options", {})
    if isinstance(options, dict):
        return options
    return {}


def validate_backend_chain(
    backend_names: List[str],
    backend_configs: Dict[str, Dict[str, Any]]
) -> Tuple[bool, str]:
    """
    Validate a backend chain for composability constraints.

    Rules:
    1. At most one non-composable backend allowed
    2. Non-composable backends must be at position 0 (leftmost/outermost)
    3. All other backends must be composable

    Args:
        backend_names: List of backend names to validate (left=outermost, right=innermost)
        backend_configs: Dict mapping backend name to config dict with 'composable' field
                        (from discover_backends() or backend_options)

    Returns:
        Tuple of (is_valid, error_message)
        - (True, "") if valid
        - (False, error_msg) if invalid

    Examples:
        >>> # Valid chains
        >>> validate_backend_chain(['local'], {})  # Single backend
        (True, '')
        >>> validate_backend_chain(['perf'], {'perf': {'composable': True}})
        (True, '')
        >>> validate_backend_chain(['local', 'perf'], {
        ...     'local': {'composable': True},
        ...     'perf': {'composable': True}
        ... })
        (True, '')

        >>> # Invalid chains
        >>> validate_backend_chain(['perf', 'mpip'], {
        ...     'perf': {'composable': True},
        ...     'mpip': {'composable': False}
        ... })
        (False, "Non-composable backends can only be in position 1 (leftmost). Found at position 2 (mpip).")
    """
    if not backend_names:
        return True, ""

    non_composable_positions = []

    for idx, backend_name in enumerate(backend_names):
        # Get backend config - handle both BackendConfig objects and plain dicts
        backend_config = backend_configs.get(backend_name)
        if not backend_config:
            # Unknown backend - skip validation for this one
            # (will be caught elsewhere during execution)
            continue

        # Extract composable flag - handle both nested (BackendConfig) and flat dicts
        composable = True  # Default if not specified
        if isinstance(backend_config, dict):
            # Direct backend_options dict
            if "composable" in backend_config:
                composable = backend_config["composable"]
            # Or nested backend_options.{backend_name}.composable
            elif "backend_options" in backend_config:
                backend_opts = backend_config["backend_options"]
                if backend_name in backend_opts:
                    composable = backend_opts[backend_name].get("composable", True)
        else:
            # BackendConfig object (from discover_backends)
            if hasattr(backend_config, "backend_options"):
                backend_opts = backend_config.backend_options
                if backend_name in backend_opts:
                    backend_option = backend_opts[backend_name]
                    if hasattr(backend_option, "composable"):
                        composable = backend_option.composable

        # Track non-composable backends and their positions
        if not composable and idx > 0:
            non_composable_positions.append((idx + 1, backend_name))

    # Generate error if non-composable backends found in wrong positions
    if non_composable_positions:
        positions = ", ".join([f"position {pos} ({name})" for pos, name in non_composable_positions])
        error_msg = (
            f"Non-composable backends can only be in position 1 (leftmost). "
            f"Found at {positions}."
        )
        return False, error_msg

    return True, ""
