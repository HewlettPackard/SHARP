#!/usr/bin/env python3
"""
SHARP benchmark build tool.

Builds benchmark artifacts (AppImage, Docker images) from benchmark
configurations. When given a benchmark.yaml file or directory, builds
ALL benchmarks defined in that file.

Usage:
  build [OPTIONS] [BENCHMARK]

Examples:
  # Build all benchmarks in a suite as AppImages
  build -t appimage benchmarks/micro/cpu

  # Build all benchmarks in a directory
  build -t appimage benchmarks/micro/python

  # Build a specific benchmark by name
  build -t docker sleep

  # List all available benchmarks
  build --list-benchmarks

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import argparse
import sys
from pathlib import Path

from typing import Any
from src.cli import discovery
from src.core.config.loader import load_benchmark_config
from src.core.config.schema import BenchmarkConfig
from src.core.packaging.builder import ArtifactBuilder
from src.core.packaging import (
    PackagingManager,
    AppImageBuilder,
    DockerBuilder,
    BuildError,
    SourceError,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="build",
        description="Build benchmark artifacts (AppImage or Docker)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all available benchmarks
  build --list-benchmarks

  # Build all benchmarks in a suite as AppImages
  build -t appimage benchmarks/micro/cpu

  # Build Docker image for matmul benchmark
  build -t docker matmul

  # Build AppImage for sleep benchmark
  build -t appimage sleep

  # Download sources only (no build)
  build --download-only matmul

  # Clean rebuild (remove cached sources)
  build --clean -t docker matmul
""",
    )

    parser.add_argument(
        "--list-benchmarks",
        action="store_true",
        help="List all available benchmarks",
    )

    parser.add_argument(
        "-t", "--type",
        choices=["docker", "appimage"],
        default="appimage",
        help="Build type: docker or appimage (default: appimage)",
    )

    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Download sources only, don't build artifact",
    )

    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove cached sources before building",
    )

    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output directory for built artifacts",
    )

    parser.add_argument(
        "--registry",
        type=str,
        help="Docker registry for pushing images (Docker only)",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )

    parser.add_argument(
        "benchmark",
        nargs="?",
        help="Benchmark to build (name, path to benchmark.yaml, or directory)",
    )

    return parser.parse_args(argv)


def build_single_benchmark(
    benchmark_config: BenchmarkConfig,
    benchmark_name: str,
    args: argparse.Namespace,
    manager: PackagingManager,
) -> dict[str, Any]:
    """Build a single benchmark and return manifest."""
    manifest = manager.build(
        benchmark_config,
        args.type,
        benchmark_name=benchmark_name,
        download_only=args.download_only,
        clean=args.clean,
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for the build command.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args(argv)

    # Handle discovery command
    if args.list_benchmarks:
        return discovery.list_benchmarks()

    # Require benchmark name for build operations
    if not args.benchmark:
        print("Error: benchmark name or path required")
        print("Use --list-benchmarks to see available benchmarks")
        return 1

    try:
        # Load benchmark configuration
        benchmark_config = load_benchmark_config(args.benchmark)

        # Create PackagingManager with appropriate builder
        output_dir = Path(args.output) if args.output else None
        manager = PackagingManager(base_dir=output_dir)

        # Register builders
        builder: ArtifactBuilder
        if args.type == 'appimage':
            builder = AppImageBuilder(output_dir=output_dir, verbose=args.verbose)
        else:  # docker
            builder = DockerBuilder(registry=args.registry, verbose=args.verbose)

        manager.register_builder(args.type, builder)

        # Get all benchmark names from config
        benchmark_names = list(benchmark_config.benchmarks.keys())

        if args.verbose:
            print(f"Building {len(benchmark_names)} benchmark(s) as {args.type}...")
            for name in benchmark_names:
                print(f"  - {name}")

        # Build all benchmarks in the config
        manifests = []
        for benchmark_name in benchmark_names:
            if args.verbose:
                print(f"\n{'='*60}")
                print(f"Building: {benchmark_name}")
                print(f"{'='*60}")

            manifest = build_single_benchmark(
                benchmark_config,
                benchmark_name,
                args,
                manager,
            )
            manifests.append(manifest)

            # Print result for this benchmark
            if args.download_only:
                print(f"Sources downloaded to: {manifest['sources_dir']}")
            else:
                print(f"Built: {manifest['artifact_path']}")

        # Print summary
        print(f"\nBuild summary: {len(manifests)} benchmark(s)")
        for manifest in manifests:
            name = manifest.get('benchmark', 'unknown')
            if args.download_only:
                print(f"  [downloaded] {name}")
            else:
                print(f"  [built] {name}: {manifest.get('artifact_path', 'N/A')}")

        return 0

    except (BuildError, SourceError) as e:
        print(f"Build error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"File not found: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
