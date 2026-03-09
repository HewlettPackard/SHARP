"""
Benchmark source fetching and building.

Handles downloading and preparing benchmark sources from git, local paths,
or URLs. Sources are stored in benchmarks/_sources/{benchmark_name}/ and
reused across benchmarks in suites via the subdir field.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.config.include_resolver import get_project_root
from src.core.config.schema import BenchmarkConfig, BenchmarkSource
from src.core.packaging.errors import BuildError, SourceError


def fetch_sources(sources: list[BenchmarkSource],
                  benchmark_name: str,
                  clean: bool = False,
                  base_dir: Path | None = None) -> Path:
    """
    Fetch and prepare benchmark sources.

    Downloads sources from git, local filesystem, or URL to a shared
    directory within benchmarks/_sources/{benchmark_name}/ (or base_dir if specified).

    For benchmark suites (e.g., Rodinia), multiple benchmarks reference
    the same sources location, so they share the same download.

    Args:
        sources: List of source specifications (BenchmarkSource objects)
        benchmark_name: Benchmark name (used for directory path)
        clean: If True, remove existing sources before fetching
        base_dir: Optional base directory for sources (default: benchmarks/_sources)

    Returns:
        Path to sources directory

    Raises:
        SourceError: If fetch fails or sources invalid
    """
    # Validate inputs first
    if not sources:
        raise SourceError("No sources specified in benchmark config")

    # Determine sources directory
    if base_dir is None:
        project_root = get_project_root()
        base_dir = project_root / "benchmarks" / "_sources"

    sources_dir = base_dir / benchmark_name
    sources_dir.mkdir(parents=True, exist_ok=True)

    # Handle --clean flag: remove existing sources
    if clean and sources_dir.exists():
        try:
            shutil.rmtree(sources_dir)
            sources_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise SourceError(f"Failed to clean sources directory: {e}")

    # Skip if sources already exist and non-empty
    if sources_dir.exists() and any(sources_dir.iterdir()):
        return sources_dir

    # Fetch each source
    for source in sources:
        try:
            _fetch_single_source(source, sources_dir)
        except Exception as e:
            if isinstance(e, SourceError):
                raise
            raise SourceError(f"Failed to fetch {source.type} source: {e}")

    return sources_dir


def _fetch_single_source(source: BenchmarkSource, dest: Path) -> None:
    """
    Fetch a single source to destination directory.

    Args:
        source: Source specification
        dest: Destination directory

    Raises:
        SourceError: If fetch fails
    """
    if source.type == 'git':
        _fetch_git(source, dest)
    elif source.type == 'path':
        _fetch_path(source, dest)
    elif source.type == 'download':
        _fetch_download(source, dest)
    else:
        raise SourceError(f"Unknown source type: {source.type}")


def _fetch_git(source: BenchmarkSource, dest: Path) -> None:
    """Clone git repository to destination."""
    cmd = ['git', 'clone']
    if source.ref:
        cmd.extend(['--branch', source.ref])
    cmd.extend([source.location, str(dest)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode != 0:
            raise SourceError(f"Git clone failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        raise SourceError(f"Git clone timeout for {source.location}")


def _fetch_path(source: BenchmarkSource, dest: Path) -> None:
    """Copy filesystem path to destination."""
    src_path = Path(source.location).expanduser()
    if not src_path.exists():
        raise SourceError(f"Source path not found: {source.location}")

    if src_path.is_file():
        shutil.copy2(src_path, dest / src_path.name)
    else:
        # Copy directory tree
        for item in src_path.iterdir():
            target = dest / item.name
            if item.is_file():
                shutil.copy2(item, target)
            elif item.is_dir():
                shutil.copytree(item, target)


def _fetch_download(source: BenchmarkSource, dest: Path) -> None:
    """Download from URL to destination."""
    import urllib.request

    try:
        filename = Path(source.location).name or "source"
        dest_file = dest / filename
        urllib.request.urlretrieve(source.location, dest_file)
    except Exception as e:
        raise SourceError(f"Download failed for {source.location}: {e}")


def build_benchmark(benchmark: BenchmarkConfig,
                    backend_type: str,
                    download_only: bool = False,
                    clean: bool = False,
                    base_dir: Path | None = None) -> dict[str, Any]:
    """
    Build benchmark artifact or prepare sources.

    Downloads/prepares sources, optionally builds artifact for target backend.

    Args:
        benchmark: Benchmark configuration
        backend_type: 'appimage' or 'docker'
        download_only: If True, download sources and return (no build)
        clean: If True, remove existing sources before build
        base_dir: Optional base directory for sources (default: benchmarks/_sources)

    Returns:
        Build manifest dict with:
        - benchmark: benchmark name
        - sources_dir: path to sources directory
        - source_ref: git ref if applicable
        - artifact_path: path to built artifact (if not download_only)
        - build_timestamp: ISO format timestamp

    Raises:
        SourceError: If source retrieval fails
        BuildError: If build fails
    """
    # Get first benchmark entry (for single-benchmark YAML files)
    benchmark_names = list(benchmark.benchmarks.keys())
    if not benchmark_names:
        raise BuildError("No benchmarks defined in config")

    benchmark_name = benchmark_names[0]
    entry = benchmark.benchmarks[benchmark_name]

    # Fetch/prepare sources
    sources_dir = fetch_sources(
        entry.sources,
        benchmark_name,
        clean=clean,
        base_dir=base_dir
    )

    # If --download-only, return early with manifest
    if download_only:
        return {
            'benchmark': benchmark_name,
            'sources_dir': str(sources_dir),
            'source_ref': entry.sources[0].ref if entry.sources else None,
            'download_timestamp': datetime.now().isoformat(),
        }

    # Build artifact (compile + package)
    if backend_type == 'appimage':
        artifact_path = _build_appimage(benchmark, sources_dir)
    elif backend_type == 'docker':
        artifact_path = _build_docker(benchmark, sources_dir)
    else:
        raise BuildError(f"Unsupported backend type: {backend_type}")

    # Generate build manifest
    manifest = {
        'benchmark': benchmark_name,
        'backend_type': backend_type,
        'artifact_path': str(artifact_path),
        'sources_dir': str(sources_dir),
        'source_ref': entry.sources[0].ref if entry.sources else None,
        'build_timestamp': datetime.now().isoformat(),
    }

    return manifest


def _build_appimage(benchmark: BenchmarkConfig, sources_dir: Path) -> Path:
    """
    Build AppImage artifact.

    Placeholder implementation - actual AppImage building delegated to
    packaging/appimage.py module (Phase 4).

    Args:
        benchmark: Benchmark configuration
        sources_dir: Path to prepared sources

    Returns:
        Path to built AppImage artifact

    Raises:
        BuildError: If build fails
    """
    # TODO: Phase 4 - implement actual AppImage builder
    raise BuildError("AppImage building not yet implemented (Phase 4)")


def _build_docker(benchmark: BenchmarkConfig, sources_dir: Path) -> Path:
    """
    Build Docker image.

    Placeholder implementation - actual Docker building delegated to
    packaging/docker.py module (Phase 4).

    Args:
        benchmark: Benchmark configuration
        sources_dir: Path to prepared sources

    Returns:
        Path to Docker image reference/manifest

    Raises:
        BuildError: If build fails
    """
    # TODO: Phase 4 - implement actual Docker builder
    raise BuildError("Docker building not yet implemented (Phase 4)")
