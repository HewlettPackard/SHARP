#!/usr/bin/env python3
"""
SHARP benchmark build tool (stub - not yet implemented).

This tool will build benchmark artifacts (AppImage, Docker images).
Planned for Phase 4 of the SHARP modernization.

Usage:
  build [options] BENCHMARK
  build --list-benchmarks

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import argparse
import sys

from src.cli import discovery


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="build",
        description="Build benchmark artifacts (not yet implemented)",
    )

    parser.add_argument(
        "--list-benchmarks",
        action="store_true",
        help="List all available benchmarks",
    )

    parser.add_argument(
        "benchmark",
        nargs="?",
        help="Benchmark to build",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for the build command.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (1 for not implemented, 0 for discovery commands)
    """
    args = parse_args(argv)

    # Handle discovery command
    if args.list_benchmarks:
        return discovery.list_benchmarks()

    # Stub implementation for actual build
    print("Error: 'build' command not yet implemented")
    print("This feature is planned for Phase 4 of the SHARP modernization.")
    print()
    print("Planned functionality:")
    print("  - Build benchmark artifacts (AppImage, Docker)")
    print("  - Download benchmark sources")
    print("  - Manage build cache")
    print()
    print("See DESIGN.md for implementation roadmap.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
