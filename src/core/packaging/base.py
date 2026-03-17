"""
Base class for packaging builders.

Common logic for AppImage, Docker, and other packaging strategies.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import shutil
import os
from pathlib import Path
from typing import Any, Tuple, List, Dict

from src.core.config.schema import BenchmarkConfig, BenchmarkBuild, BenchmarkEntry


class BaseBuilder:
    """
    Base class for benchmark packaging builders.

    Provides common utilities for:
    - Extracting configuration
    - Locating benchmark directories
    - Copying source files
    """

    def __init__(self, verbose: bool = False):
        """Initialize builder.

        Args:
            verbose: If True, stream build output to terminal
        """
        self._verbose = verbose

    def _get_build_config(self, benchmark: BenchmarkConfig, benchmark_name: str,
                          builder_config_key: str) -> Tuple[BenchmarkEntry, BenchmarkBuild, List[str], List[str], Dict[str, Any]]:
        """
        Extract build configuration and requirements.

        Args:
            benchmark: Benchmark configuration object
            benchmark_name: Name of the benchmark
            builder_config_key: Key for builder-specific config (e.g., 'docker', 'appimage')

        Returns:
            Tuple containing:
            - entry: BenchmarkEntry
            - build_config: BenchmarkBuild
            - python_reqs: List of Python requirements
            - system_deps: List of system dependencies
            - builder_config: Builder-specific configuration dictionary
        """
        entry = benchmark.benchmarks[benchmark_name]
        build_config = entry.build

        # Check for builder-specific config
        builder_config = getattr(build_config, builder_config_key, {}) or {}

        # Get requirements from unified 'requires' field or legacy fields
        requires = build_config.requires
        if requires:
            # Use unified declarative requirements
            python_reqs = requires.python
            system_deps = requires.system
        else:
            # Fall back to legacy fields or builder-specific overrides
            python_reqs = builder_config.get('requirements', []) or build_config.requirements
            system_deps = builder_config.get('system_deps', []) or build_config.system_deps

        return entry, build_config, python_reqs, system_deps, builder_config

    def _get_benchmark_dir(self, benchmark: BenchmarkConfig) -> Path | None:
        """Get the directory containing the benchmark YAML."""
        if hasattr(benchmark, '_config_path') and benchmark._config_path:
            return Path(benchmark._config_path).parent
        return None

    def _copy_sources_to_dir(self, sources_dir: Path, benchmark_dir: Path | None,
                             target_dir: Path, entry: BenchmarkEntry | None = None) -> None:
        """
        Copy source files to a target directory.

        Copies both external sources (downloaded/fetched) and local benchmark
        files (from the benchmark.yaml directory) to the target directory.

        Args:
            sources_dir: Directory containing fetched external sources
            benchmark_dir: Directory containing benchmark.yaml and local files
            target_dir: Directory to copy files into
            entry: Optional BenchmarkEntry (unused in base implementation but kept for compatibility)
        """
        # Helper to copy files/dirs
        def copy_item(item: Path, dest_dir: Path) -> None:
            # Skip hidden files, benchmark.yaml, and build directories
            if item.name.startswith('.'):
                return
            if item.name in ('benchmark.yaml', '__pycache__', 'build'):
                return

            target = dest_dir / item.name
            if item.is_file():
                shutil.copy2(item, target)
                # Preserve executable permission
                if os.access(item, os.X_OK):
                    target.chmod(target.stat().st_mode | 0o111)
            elif item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)

        # Copy external sources (downloaded tarballs, git repos, etc.)
        if sources_dir.exists() and sources_dir.is_dir():
            for item in sources_dir.iterdir():
                copy_item(item, target_dir)

        # Copy local benchmark files (C source, Makefile, Python scripts, etc.)
        if benchmark_dir and benchmark_dir.exists() and benchmark_dir.is_dir():
            for item in benchmark_dir.iterdir():
                copy_item(item, target_dir)
