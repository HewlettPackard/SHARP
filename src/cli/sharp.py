#!/usr/bin/env python3
"""
SHARP unified CLI entry point with git-style subcommand dispatching.

Supports subcommands:
  - launch: Run benchmarking experiments
  - build: Build benchmark artifacts
  - compare: Compare experimental results

Usage:
  sharp <subcommand> [args...]
  sharp --version
  sharp help [subcommand]

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import sys


def print_version() -> None:
    """Print SHARP version information."""
    # Import here to avoid circular dependencies
    try:
        from importlib.metadata import version
        sharp_version = version("sharp")
    except Exception:
        sharp_version = "4.0.0"

    print(f"SHARP version {sharp_version}")


def print_usage() -> None:
    """Print main usage information."""
    print("""
SHARP - Serverless and HPC Application Runtime Profiler

Usage:
  sharp <subcommand> [args...]
  sharp --version
  sharp help [subcommand]

Available subcommands:
  launch     Run benchmarking experiments
  build      Build benchmark artifacts (future)
  compare    Compare experimental results (future)
  registry   Manage benchmark registry (future)
  report     Generate reports (future)

Use 'sharp help <subcommand>' for more information on a specific command.

Examples:
  sharp launch --help
  sharp launch -b local matmul 1000
  sharp --version
""".strip())


def print_subcommand_help(subcommand: str) -> int:
    """
    Print help for a specific subcommand.

    Args:
        subcommand: Name of the subcommand

    Returns:
        Exit code (0 for success, 1 for unknown subcommand)
    """
    if subcommand == "launch":
        # Import and invoke launch's help
        try:
            from src.cli.launch import main as launch_main
            return launch_main(["--help"])
        except ImportError:
            print(f"Error: 'launch' subcommand not yet implemented")
            return 1
    elif subcommand in ("build", "compare", "registry", "report"):
        print(f"Error: '{subcommand}' subcommand not yet implemented")
        return 1
    else:
        print(f"Error: Unknown subcommand '{subcommand}'")
        print("Run 'sharp help' for available subcommands")
        return 1


def dispatch_subcommand(subcommand: str, args: list[str]) -> int:
    """
    Dispatch to the appropriate subcommand handler.

    Args:
        subcommand: Name of the subcommand
        args: Arguments to pass to the subcommand

    Returns:
        Exit code from the subcommand
    """
    if subcommand == "launch":
        try:
            from src.cli.launch import main as launch_main
            return launch_main(args)
        except ImportError as e:
            print(f"Error: Could not import launch subcommand: {e}")
            return 1

    elif subcommand == "build":
        try:
            from src.cli.build import main as build_main
            return build_main(args)
        except ImportError as e:
            print(f"Error: Could not import build subcommand: {e}")
            return 1

    elif subcommand == "compare":
        try:
            from src.cli.compare import main as compare_main
            return compare_main(args)
        except ImportError as e:
            print(f"Error: Could not import compare subcommand: {e}")
            return 1

    elif subcommand == "registry":
        print("Error: 'registry' subcommand not yet implemented")
        print("This feature is planned for a future release.")
        return 1

    elif subcommand == "report":
        print("Error: 'report' subcommand not yet implemented")
        print("This feature is planned for a future release.")
        return 1

    else:
        print(f"Error: Unknown subcommand '{subcommand}'")
        print("Run 'sharp help' for available subcommands")
        return 1


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for the SHARP CLI.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    if argv is None:
        argv = sys.argv[1:]

    # Handle no arguments
    if not argv:
        print_usage()
        return 0

    # Handle --version flag
    if argv[0] in ("--version", "-v"):
        print_version()
        return 0

    # Handle help command
    if argv[0] in ("help", "--help", "-h"):
        if len(argv) > 1:
            return print_subcommand_help(argv[1])
        else:
            print_usage()
            return 0

    # Dispatch to subcommand
    subcommand = argv[0]
    subcommand_args = argv[1:]
    return dispatch_subcommand(subcommand, subcommand_args)


if __name__ == "__main__":
    sys.exit(main())
