"""
Benchmark packaging and source management.

Provides tools for building benchmark artifacts:
- PackagingManager: Orchestrates the build process
- AppImageBuilder: Creates portable AppImage bundles
- DockerBuilder: Creates Docker container images

Sources are downloaded to benchmarks/_sources/{benchmark_name}/ and
reused across benchmarks in suites (e.g., Rodinia) via the subdir field.
"""

from src.core.packaging.errors import BuildError, SourceError
from src.core.packaging.builder import (
    PackagingManager,
    fetch_sources,
    build_benchmark,
)
from src.core.packaging.appimage import AppImageBuilder
from src.core.packaging.docker import DockerBuilder

__all__ = [
    'BuildError',
    'SourceError',
    'PackagingManager',
    'fetch_sources',
    'build_benchmark',
    'AppImageBuilder',
    'DockerBuilder',
]
