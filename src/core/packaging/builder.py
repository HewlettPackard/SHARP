"""
Benchmark source fetching and building.

Handles downloading and preparing benchmark sources from git, local paths,
or URLs. Sources are stored in benchmarks/_sources/{benchmark_name}/ and
reused across benchmarks in suites via the subdir field.

PackagingManager orchestrates the full build process:
1. Validate benchmark configuration
2. Fetch/prepare sources
3. Build artifact (AppImage or Docker image)
4. Return build manifest

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from src.core.config.include_resolver import get_project_root
from src.core.config.schema import BenchmarkConfig, BenchmarkSource
from src.core.packaging.errors import BuildError, SourceError


class ArtifactBuilder(Protocol):
    """Protocol for artifact builders (AppImage, Docker)."""

    def build(self, benchmark: BenchmarkConfig, sources_dir: Path,
              benchmark_name: str) -> Path:
        """Build artifact from sources.

        Args:
            benchmark: Benchmark configuration
            sources_dir: Path to prepared sources
            benchmark_name: Name of the benchmark being built

        Returns:
            Path to built artifact (file or manifest)

        Raises:
            BuildError: If build fails
        """
        ...


class PackagingManager:
    """
    Orchestrates benchmark building and packaging.

    This class manages the complete build lifecycle:
    1. Validation of benchmark configuration
    2. Source fetching (git, local, download)
    3. Artifact building (AppImage or Docker)
    4. Manifest generation

    Usage:
        manager = PackagingManager()
        manifest = manager.build('matmul', backend_type='docker')
    """

    def __init__(self, base_dir: Path | None = None):
        """Initialize PackagingManager.

        Args:
            base_dir: Optional base directory for sources
                      (default: benchmarks/_sources)
        """
        self._base_dir = base_dir
        self._builders: dict[str, ArtifactBuilder] = {}

    def register_builder(self, backend_type: str, builder: ArtifactBuilder) -> None:
        """Register an artifact builder.

        Args:
            backend_type: Type identifier ('appimage', 'docker')
            builder: Builder instance implementing ArtifactBuilder protocol
        """
        self._builders[backend_type] = builder

    def build(self, benchmark: BenchmarkConfig,
              backend_type: str,
              benchmark_name: str | None = None,
              download_only: bool = False,
              clean: bool = False) -> dict[str, Any]:
        """
        Build benchmark artifact.

        Complete build workflow:
        1. Validate configuration
        2. Fetch sources (git clone, copy, or download)
        3. Build artifact (AppImage or Docker image)
        4. Return manifest with artifact location

        Args:
            benchmark: Benchmark configuration
            backend_type: 'appimage' or 'docker'
            benchmark_name: Specific benchmark to build. If None, builds first one.
            download_only: If True, download sources only (no build)
            clean: If True, remove existing sources before build

        Returns:
            Build manifest dict with:
            - benchmark: benchmark name
            - backend_type: 'appimage' or 'docker'
            - artifact_path: path to built artifact
            - sources_dir: path to sources directory
            - source_ref: git ref if applicable
            - build_timestamp: ISO format timestamp

        Raises:
            BuildError: If build fails
            SourceError: If source fetch fails
        """
        # Get benchmark entry by name or use first one
        benchmark_names = list(benchmark.benchmarks.keys())
        if not benchmark_names:
            raise BuildError("No benchmarks defined in config")

        if benchmark_name is None:
            benchmark_name = benchmark_names[0]
        elif benchmark_name not in benchmark.benchmarks:
            raise BuildError(
                f"Benchmark '{benchmark_name}' not found in config. "
                f"Available: {', '.join(benchmark_names)}"
            )

        entry = benchmark.benchmarks[benchmark_name]

        # Determine sources directory
        if entry.sources:
            # Fetch external sources
            sources_dir = fetch_sources(
                entry.sources,
                benchmark_name,
                clean=clean,
                base_dir=self._base_dir
            )
        else:
            # Local files - use benchmark YAML directory
            if hasattr(benchmark, '_config_path') and benchmark._config_path:
                sources_dir = Path(benchmark._config_path).parent
            else:
                # Fallback to empty sources dir
                project_root = get_project_root()
                sources_dir = project_root / "benchmarks" / "_sources" / benchmark_name
                sources_dir.mkdir(parents=True, exist_ok=True)

        # If --download-only, return early
        if download_only:
            return {
                'benchmark': benchmark_name,
                'sources_dir': str(sources_dir),
                'source_ref': entry.sources[0].ref if entry.sources else None,
                'download_timestamp': datetime.now().isoformat(),
            }

        # Build artifact using registered builder
        if backend_type not in self._builders:
            raise BuildError(
                f"No builder registered for backend type: {backend_type}. "
                f"Available: {list(self._builders.keys())}"
            )

        builder = self._builders[backend_type]
        artifact_path = builder.build(benchmark, sources_dir, benchmark_name)

        # Generate build manifest
        return {
            'benchmark': benchmark_name,
            'backend_type': backend_type,
            'artifact_path': str(artifact_path),
            'sources_dir': str(sources_dir),
            'source_ref': entry.sources[0].ref if entry.sources else None,
            'build_timestamp': datetime.now().isoformat(),
        }


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
    """Download from URL to destination, with mirror failover support."""
    import urllib.request

    # Build list of URLs to try: primary first, then mirrors
    urls_to_try = [source.location] + (source.mirrors or [])
    filename = Path(source.location).name or "source"
    dest_file = dest / filename

    errors = []
    for url in urls_to_try:
        try:
            urllib.request.urlretrieve(url, dest_file)
            return  # Success
        except Exception as e:
            errors.append(f"{url}: {e}")
            continue

    # All URLs failed
    raise SourceError(
        f"Download failed for {filename}. Tried {len(urls_to_try)} location(s):\n"
        + "\n".join(f"  - {err}" for err in errors)
    )


def build_benchmark(benchmark: BenchmarkConfig,
                    backend_type: str,
                    download_only: bool = False,
                    clean: bool = False,
                    base_dir: Path | None = None) -> dict[str, Any]:
    """
    Build benchmark artifact or prepare sources.

    Convenience function that uses PackagingManager internally.
    For more control, use PackagingManager directly.

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
    # Import builders lazily to avoid circular imports
    from src.core.packaging.appimage import AppImageBuilder
    from src.core.packaging.docker import DockerBuilder

    manager = PackagingManager(base_dir=base_dir)
    manager.register_builder('appimage', AppImageBuilder())
    manager.register_builder('docker', DockerBuilder())

    return manager.build(
        benchmark,
        backend_type,
        download_only=download_only,
        clean=clean
    )
