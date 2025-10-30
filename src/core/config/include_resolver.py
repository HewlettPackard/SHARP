"""
Recursive YAML/JSON include resolution with cycle detection.

Resolves `include` directives in configuration files, merging included
content according to defined semantics. Supports relative paths, cycle
detection, and configurable depth limits.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import json
import os
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merge two dictionaries with specific semantics.

    Merge rules:
    - Primitive values: override wins
    - Lists: concatenate (base + override)
    - Dicts: recursive merge
    - Type mismatch: raise ConfigError

    Args:
        base: Base dictionary (lower precedence)
        override: Override dictionary (higher precedence)

    Returns:
        Merged dictionary

    Raises:
        ConfigError: If type mismatch occurs during merge
    """
    result = base.copy()

    for key, override_val in override.items():
        if key not in result:
            # Key only in override, just add it
            result[key] = override_val
        else:
            base_val = result[key]

            # Check for type mismatches
            if type(base_val) != type(override_val):
                raise ConfigError(
                    f"Type mismatch for key '{key}': "
                    f"{type(base_val).__name__} vs {type(override_val).__name__}"
                )

            # Handle different types
            if isinstance(override_val, dict):
                # Recursive merge for dicts
                result[key] = merge_dicts(base_val, override_val)  # type: ignore
            elif isinstance(override_val, list):
                # Concatenate lists (base + override)
                result[key] = base_val + override_val  # type: ignore
            else:
                # Primitive: override wins
                result[key] = override_val

    return result


def resolve_include_path(include_path: str, current_file: str) -> str:
    """
    Resolve include path relative to current file and standard directories.

    Resolution order:
    1. Relative to current file's directory
    2. Relative to benchmarks/
    3. Relative to backends/
    4. Relative to project root

    Args:
        include_path: Path from include directive
        current_file: Absolute path to file containing include

    Returns:
        Absolute path to included file

    Raises:
        ConfigError: If include path cannot be resolved
    """
    # Try relative to current file's directory first
    current_dir = Path(current_file).parent
    candidate = current_dir / include_path
    if candidate.exists():
        return str(candidate.resolve())

    # Determine project root (4 levels up from this file: src/core/config/include_resolver.py)
    project_root = Path(__file__).parent.parent.parent.parent

    # Try relative to benchmarks/
    candidate = project_root / "benchmarks" / include_path
    if candidate.exists():
        return str(candidate.resolve())

    # Try relative to backends/
    candidate = project_root / "backends" / include_path
    if candidate.exists():
        return str(candidate.resolve())

    # Try relative to project root
    candidate = project_root / include_path
    if candidate.exists():
        return str(candidate.resolve())

    # Could not resolve
    raise ConfigError(
        f"Cannot resolve include path '{include_path}' from {current_file}\n"
        f"Tried:\n"
        f"  - {current_dir / include_path}\n"
        f"  - {project_root / 'benchmarks' / include_path}\n"
        f"  - {project_root / 'backends' / include_path}\n"
        f"  - {project_root / include_path}"
    )


def _load_config_file(abs_path: str) -> dict[str, Any]:
    """
    Load and parse YAML or JSON configuration file.

    Args:
        abs_path: Absolute path to configuration file

    Returns:
        Parsed configuration dictionary

    Raises:
        ConfigError: If file cannot be read or parsed, or doesn't contain a dict
    """
    try:
        with open(abs_path, 'r') as f:
            if abs_path.endswith('.json'):
                data = json.load(f)
            else:
                data = yaml.safe_load(f) or {}
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        raise ConfigError(f"Failed to parse {abs_path}: {e}")
    except IOError as e:
        raise ConfigError(f"Failed to read {abs_path}: {e}")

    # Ensure we got a dict
    if not isinstance(data, dict):
        raise ConfigError(
            f"Configuration file must contain a dict/object, got {type(data).__name__} in {abs_path}"
        )

    return data


def _validate_guards(abs_path: str, visited: set[str], depth: int, max_depth: int) -> None:
    """
    Validate cycle detection and depth limit guards.

    Args:
        abs_path: Absolute path to check
        visited: Set of already-visited paths
        depth: Current recursion depth
        max_depth: Maximum allowed depth

    Raises:
        ConfigError: If cycle detected, depth exceeded, or file not found
    """
    # Cycle detection
    if abs_path in visited:
        raise ConfigError(f"Circular include detected: {abs_path}")

    # Depth limit
    if depth > max_depth:
        raise ConfigError(
            f"Include depth limit ({max_depth}) exceeded at {abs_path}"
        )

    # File existence
    if not Path(abs_path).exists():
        raise ConfigError(f"Configuration file not found: {abs_path}")


def _process_includes(
    includes: Any,
    abs_path: str,
    visited: set[str],
    depth: int,
    max_depth: int
) -> dict[str, Any]:
    """
    Process include directives and merge all included files.

    Args:
        includes: Include directive value from config file
        abs_path: Absolute path to file containing includes
        visited: Set of visited paths for cycle detection
        depth: Current recursion depth
        max_depth: Maximum recursion depth

    Returns:
        Merged data from all included files

    Raises:
        ConfigError: If include directive is invalid or inclusion fails
    """
    # Validate include directive is a list
    if not isinstance(includes, list):
        raise ConfigError(
            f"'include' directive must be a list, got {type(includes).__name__} in {abs_path}"
        )

    # Start with empty dict, merge all includes
    merged: dict[str, Any] = {}

    for include_path in includes:
        if not isinstance(include_path, str):
            raise ConfigError(
                f"Include paths must be strings, got {type(include_path).__name__} in {abs_path}"
            )

        # Resolve the include path
        resolved_path = resolve_include_path(include_path, abs_path)

        # Recursively resolve includes in the included file
        included_data = resolve_includes(
            resolved_path,
            visited.copy(),  # Use copy to allow parallel includes of same file
            depth + 1,
            max_depth
        )

        # Merge included data (earlier includes have lower precedence)
        merged = merge_dicts(merged, included_data)

    return merged


def resolve_includes(
    config_path: str,
    visited: set[str] | None = None,
    depth: int = 0,
    max_depth: int = 10
) -> dict[str, Any]:
    """
    Recursively resolve includes in YAML/JSON configuration file.

    Args:
        config_path: Path to configuration file
        visited: Set of already-visited absolute paths (for cycle detection)
        depth: Current recursion depth
        max_depth: Maximum recursion depth allowed

    Returns:
        Merged configuration dictionary with includes resolved

    Raises:
        ConfigError: If cycle detected, depth limit exceeded, or file not found
    """
    if visited is None:
        visited = set()

    # Resolve to absolute path for cycle detection
    abs_path = str(Path(config_path).resolve())

    # Validate guards (cycle detection, depth limit, file existence)
    _validate_guards(abs_path, visited, depth, max_depth)

    # Mark as visited
    visited.add(abs_path)

    # Load file content
    data = _load_config_file(abs_path)

    # Process includes if present
    if 'include' in data:
        # Merge all included files
        merged = _process_includes(data['include'], abs_path, visited, depth, max_depth)

        # Merge current file's data (higher precedence than includes)
        # Remove the include directive first
        current_data = {k: v for k, v in data.items() if k != 'include'}
        merged = merge_dicts(merged, current_data)

        return merged

    # No includes, return as-is
    return data
