"""
Factor and mitigation metadata management.

Loads performance factor descriptions and mitigation strategies from YAML
configuration files. Used by both GUI profile tab and future CLI profiling tools.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""
from pathlib import Path
from typing import Any
import yaml


_FACTORS_PATH = Path(__file__).parent / 'factors.yaml'
_MITIGATIONS_PATH = Path(__file__).parent / 'mitigations.yaml'


def load_factors() -> dict[str, Any]:
    """Load profiling factor definitions from factors.yaml.

    Returns:
        Dictionary mapping factor names to their metadata (description,
        references, mitigations list). Empty dict if file not found or invalid.
    """
    try:
        with open(_FACTORS_PATH) as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, yaml.YAMLError):
        return {}


def load_mitigations() -> dict[str, Any]:
    """Load mitigation strategy definitions from mitigations.yaml.

    Returns:
        Dictionary mapping mitigation names to their metadata (description,
        references). May include 'backend_options' key with executable
        mitigation backends. Empty dict if file not found or invalid.
    """
    try:
        with open(_MITIGATIONS_PATH) as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, yaml.YAMLError):
        return {}


def get_factor_info(factor_name: str) -> dict[str, Any] | None:
    """Get information for a specific performance factor.

    Args:
        factor_name: Factor identifier (e.g., 'dTLB_misses', 'cache_misses')

    Returns:
        Dictionary with 'description', 'references', 'mitigations' keys,
        or None if factor not found.
    """
    factors = load_factors()
    return factors.get(factor_name)


def get_mitigation_info(mitigation_name: str) -> dict[str, Any] | None:
    """Get information for a specific mitigation strategy.

    Args:
        mitigation_name: Mitigation identifier (e.g., 'huge_pages', 'mem_allocator_je')

    Returns:
        Dictionary with 'description' and optionally 'references' keys,
        or None if mitigation not found.
    """
    mitigations = load_mitigations()
    # Filter out backend_options key which is not a mitigation entry
    if mitigation_name == 'backend_options':
        return None
    return mitigations.get(mitigation_name)


def get_mitigation_backend(mitigation_name: str) -> dict[str, Any] | None:
    """Get backend configuration for executable mitigation.

    Args:
        mitigation_name: Mitigation identifier

    Returns:
        Dictionary with 'run' command template and other backend config,
        or None if no backend exists for this mitigation.
    """
    mitigations = load_mitigations()
    backend_options = mitigations.get('backend_options', {})
    result = backend_options.get(mitigation_name)
    if isinstance(result, dict):
        return result
    return None


def list_factors() -> list[str]:
    """Get list of all available factor names.

    Returns:
        Sorted list of factor identifiers.
    """
    return sorted(load_factors().keys())


def list_mitigations() -> list[str]:
    """Get list of all available mitigation names.

    Returns:
        Sorted list of mitigation identifiers, excluding 'backend_options'.
    """
    mitigations = load_mitigations()
    return sorted(k for k in mitigations.keys() if k != 'backend_options')
