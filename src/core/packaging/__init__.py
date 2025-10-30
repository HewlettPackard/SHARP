"""
Benchmark packaging and source management.

Handles benchmark source fetching and preparation for building.
Sources are downloaded to benchmarks/_sources/{benchmark_name}/ and
reused across benchmarks in suites (e.g., Rodinia) via the subdir field.
"""

from src.core.packaging.errors import BuildError, SourceError
from src.core.packaging.builder import fetch_sources, build_benchmark

__all__ = [
    'BuildError',
    'SourceError',
    'fetch_sources',
    'build_benchmark',
]
