#!/usr/bin/env python3
"""
SHARP run comparison tool (stub - not yet implemented).

This tool will compare two experimental runs and generate statistical analysis.
Planned for Phase 4 of the SHARP modernization.

Usage:
  compare CURRENT PREVIOUS [options]
  compare -e EXPERIMENT CURRENT_NAME PREVIOUS_NAME [options]

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import sys


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for the compare command.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (1 for not implemented)
    """
    print("Error: 'compare' command not yet implemented")
    print("This feature is planned for Phase 4 of the SHARP modernization.")
    print()
    print("Planned functionality:")
    print("  - Statistical comparison of two runs")
    print("  - Generate comparison narratives")
    print("  - Visualize performance differences")
    print()
    print("See DESIGN.md for implementation roadmap.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
