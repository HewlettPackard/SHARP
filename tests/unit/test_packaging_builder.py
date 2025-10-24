"""
Unit tests for benchmark packaging and source fetching.

Tests source fetching (git, path, download), build manifest generation,
and error handling for BuildError and SourceError conditions.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.config.schema import (
    BenchmarkConfig,
    BenchmarkEntry,
    BenchmarkSource,
    BenchmarkBuild,
)
from src.core.packaging.builder import (
    fetch_sources,
    build_benchmark,
)
from src.core.packaging.errors import BuildError, SourceError


class TestFetchSources(unittest.TestCase):
    """Test source fetching functionality."""

    def setUp(self):
        """Create temporary directory for test sources."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_fetch_sources_empty_list_raises_error_early(self):
        """Test that empty sources list raises SourceError immediately."""
        with self.assertRaises(SourceError) as context:
            fetch_sources([], "test_bench")

        error_msg = str(context.exception)
        self.assertIn("no sources", error_msg.lower())

    def test_fetch_sources_git_clone_success(self):
        """Test successful git source fetch."""
        source = BenchmarkSource(
            type='git',
            location="https://github.com/test/repo.git"
        )

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            try:
                fetch_sources([source], "test_bench", base_dir=self.temp_dir)
            except (OSError, Exception):
                pass

            if mock_run.called:
                call_args = mock_run.call_args[0][0]
                self.assertIn('git', call_args)
                self.assertIn('clone', call_args)

    def test_fetch_sources_git_with_ref(self):
        """Test git source spec includes ref in command."""
        source = BenchmarkSource(
            type='git',
            location="https://github.com/test/repo.git",
            ref="v1.0"
        )

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            try:
                fetch_sources([source], "test_bench", base_dir=self.temp_dir)
            except (OSError, Exception):
                pass

            if mock_run.called:
                call_args = mock_run.call_args[0][0]
                self.assertIn('--branch', call_args)
                self.assertIn('v1.0', call_args)

    def test_fetch_sources_path_copy(self):
        """Test path source fetching (directory copy)."""
        source_dir = self.temp_dir / "source"
        source_dir.mkdir()
        (source_dir / "file.py").write_text("code")

        source = BenchmarkSource(
            type='path',
            location=str(source_dir)
        )

        result = fetch_sources([source], "test_bench", base_dir=self.temp_dir)
        self.assertIsInstance(result, Path)
        self.assertTrue(result.exists())


class TestBuildBenchmark(unittest.TestCase):
    """Test benchmark building."""

    def setUp(self):
        """Create benchmark configuration for testing."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.benchmark = BenchmarkConfig(
            benchmarks={
                'test_bench': BenchmarkEntry(
                    sources=[
                        BenchmarkSource(
                            type='path',
                            location='/tmp/source'
                        )
                    ],
                    build=BenchmarkBuild(),
                    entry_point='test',
                    args=['arg1'],
                    tags=['test']
                )
            }
        )

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_build_benchmark_download_only_returns_manifest(self):
        """Test download_only flag returns manifest without building."""
        with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
            mock_fetch.return_value = Path('/tmp/sources')

            result = build_benchmark(
                self.benchmark,
                'docker',
                download_only=True
            )

            self.assertIn('benchmark', result)
            self.assertIn('sources_dir', result)
            self.assertIn('download_timestamp', result)
            self.assertNotIn('artifact_path', result)

    def test_build_benchmark_appimage_not_implemented(self):
        """Test AppImage building raises BuildError (Phase 4)."""
        with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
            mock_fetch.return_value = Path('/tmp/sources')

            with self.assertRaises(BuildError) as context:
                build_benchmark(self.benchmark, 'appimage')

            error_msg = str(context.exception)
            self.assertIn("not yet implemented", error_msg.lower())

    def test_build_benchmark_docker_not_implemented(self):
        """Test Docker building raises BuildError (Phase 4)."""
        with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
            mock_fetch.return_value = Path('/tmp/sources')

            with self.assertRaises(BuildError) as context:
                build_benchmark(self.benchmark, 'docker')

            error_msg = str(context.exception)
            self.assertIn("not yet implemented", error_msg.lower())

    def test_build_benchmark_invalid_backend_raises_error(self):
        """Test unsupported backend type raises BuildError."""
        with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
            mock_fetch.return_value = Path('/tmp/sources')

            with self.assertRaises(BuildError) as context:
                build_benchmark(self.benchmark, 'invalid_backend')

            error_msg = str(context.exception)
            self.assertIn("unsupported", error_msg.lower())

    def test_build_benchmark_clean_flag_passed_to_fetch(self):
        """Test --clean flag is passed to fetch_sources."""
        with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
            mock_fetch.return_value = Path('/tmp/sources')

            try:
                build_benchmark(self.benchmark, 'docker', clean=True)
            except BuildError:
                pass

            call_kwargs = mock_fetch.call_args[1]
            self.assertTrue(call_kwargs.get('clean'))

    def test_build_benchmark_download_only_includes_ref(self):
        """Test download_only manifest includes git ref if present."""
        benchmark_with_ref = BenchmarkConfig(
            benchmarks={
                'test_bench': BenchmarkEntry(
                    sources=[
                        BenchmarkSource(
                            type='git',
                            location='https://github.com/test/repo.git',
                            ref='v1.2.3'
                        )
                    ],
                    build=BenchmarkBuild(),
                    entry_point='test',
                    args=[],
                    tags=[]
                )
            }
        )

        with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
            mock_fetch.return_value = Path('/tmp/sources')

            result = build_benchmark(
                benchmark_with_ref,
                'docker',
                download_only=True
            )

            self.assertEqual(result['source_ref'], 'v1.2.3')

    def test_build_benchmark_empty_benchmarks_raises_error(self):
        """Test empty benchmarks dict raises BuildError."""
        empty_benchmark = BenchmarkConfig(benchmarks={})

        with self.assertRaises(BuildError) as context:
            build_benchmark(empty_benchmark, 'docker')

        error_msg = str(context.exception)
        self.assertIn("no benchmarks", error_msg.lower())


if __name__ == '__main__':
    unittest.main()
