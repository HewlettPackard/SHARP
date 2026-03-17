"""
Repeater strategies for intelligent experiment termination (adaptive stopping rules).

Provides modular repeater implementations with a factory function for instantiation.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from typing import Any, Dict

from .base import Repeater
from .bb import BBRepeater
from .ci import CIRepeater
from .count import CountRepeater
from .decision import DecisionRepeater
from .gmm import GaussianMixtureRepeater
from .hdi import HDIRepeater
from .ks import KSRepeater
from .rse import RSERepeater

__all__ = [
    "Repeater",
    "CountRepeater",
    "RSERepeater",
    "CIRepeater",
    "HDIRepeater",
    "BBRepeater",
    "GaussianMixtureRepeater",
    "KSRepeater",
    "DecisionRepeater",
    "repeater_factory",
    "REPEATER_REGISTRY",
]


def _extract_summary(docstring: str | None) -> str:
    """Extract the first line (summary) from a docstring.

    Args:
        docstring: The docstring to extract from

    Returns:
        First non-empty line of docstring, or 'No description' if empty
    """
    if not docstring:
        return "No description available"
    lines = docstring.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line:
            return line
    return "No description available"


# Centralized repeater registry with metadata
REPEATER_REGISTRY: Dict[str, Dict[str, Any]] = {
    "COUNT": {
        "class": CountRepeater,
        "description": _extract_summary(CountRepeater.__doc__),
        "defaults": CountRepeater._DEFAULT_VALUES,
        "aliases": ["MAX"],
    },
    "RSE": {
        "class": RSERepeater,
        "description": _extract_summary(RSERepeater.__doc__),
        "defaults": RSERepeater._DEFAULT_VALUES,
    },
    "CI": {
        "class": CIRepeater,
        "description": _extract_summary(CIRepeater.__doc__),
        "defaults": CIRepeater._DEFAULT_VALUES,
    },
    "HDI": {
        "class": HDIRepeater,
        "description": _extract_summary(HDIRepeater.__doc__),
        "defaults": HDIRepeater._DEFAULT_VALUES,
    },
    "BB": {
        "class": BBRepeater,
        "description": _extract_summary(BBRepeater.__doc__),
        "defaults": BBRepeater._DEFAULT_VALUES,
    },
    "GMM": {
        "class": GaussianMixtureRepeater,
        "description": _extract_summary(GaussianMixtureRepeater.__doc__),
        "defaults": GaussianMixtureRepeater._DEFAULT_VALUES,
    },
    "KS": {
        "class": KSRepeater,
        "description": _extract_summary(KSRepeater.__doc__),
        "defaults": KSRepeater._DEFAULT_VALUES,
    },
    "DC": {
        "class": DecisionRepeater,
        "description": _extract_summary(DecisionRepeater.__doc__),
        "defaults": DecisionRepeater._DEFAULT_VALUES,
    },
}


def repeater_factory(options: Dict[str, Any]) -> Repeater:
    """Return a fully-constructed Repeater object based on options.

    Args:
        options: Configuration dictionary with 'repeats' key specifying repeater type

    Returns:
        Instantiated Repeater subclass

    Raises:
        Exception: If repeater type is unrecognized
    """
    opt = options.get("repeats", "MAX")

    if "repeater_options" not in options:
        options["repeater_options"] = {}

    # First, handle count repeater, whose argument is an integer:
    if type(opt) is int:
        options["repeater_options"]["max"] = opt
        return CountRepeater(options)

    # Handle string-based repeater types
    assert type(opt) is str

    if opt.isdigit():
        options["repeater_options"]["max"] = int(opt)
        return CountRepeater(options)

    # Pattern match on repeater type
    match opt:
        case "MAX" | "COUNT":
            return CountRepeater(options)
        case "RSE":
            return RSERepeater(options)
        case "CI":
            return CIRepeater(options)
        case "HDI":
            return HDIRepeater(options)
        case "BB":
            return BBRepeater(options)
        case "GMM":
            return GaussianMixtureRepeater(options)
        case "DC":
            return DecisionRepeater(options)
        case "KS":
            return KSRepeater(options)
        case _:
            raise Exception(f"Unrecognized repeater {opt}")
