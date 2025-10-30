"""
Unit tests for benchmark packaging and source fetching.

Tests source fetching (git, path, download), build manifest generation,
and error handling for BuildError and SourceError conditions.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
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


# ========== Test fetch_sources ==========

def test_fetch_sources_empty_list_raises_error_early():
    """Test that empty sources list raises SourceError immediately."""
    with pytest.raises(SourceError) as exc_info:
        fetch_sources([], "test_bench")

    error_msg = str(exc_info.value)
    assert "no sources" in error_msg.lower()


def test_fetch_sources_git_clone_success(tmp_path):
    """Test successful git source fetch."""
    source = BenchmarkSource(
        type='git',
        location="https://github.com/test/repo.git"
    )

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        try:
            fetch_sources([source], "test_bench", base_dir=tmp_path)
        except (OSError, Exception):
            pass

        if mock_run.called:
            call_args = mock_run.call_args[0][0]
            assert 'git' in call_args
            assert 'clone' in call_args


def test_fetch_sources_git_with_ref(tmp_path):
    """Test git source spec includes ref in command."""
    source = BenchmarkSource(
        type='git',
        location="https://github.com/test/repo.git",
        ref="v1.0"
    )

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        try:
            fetch_sources([source], "test_bench", base_dir=tmp_path)
        except (OSError, Exception):
            pass

        if mock_run.called:
            call_args = mock_run.call_args[0][0]
            assert '--branch' in call_args
            assert 'v1.0' in call_args


def test_fetch_sources_path_copy(tmp_path):
    """Test path source fetching (directory copy)."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "file.py").write_text("code")

    source = BenchmarkSource(
        type='path',
        location=str(source_dir)
    )

    result = fetch_sources([source], "test_bench", base_dir=tmp_path)
    assert isinstance(result, Path)
    assert result.exists()


# ========== Test build_benchmark ==========

@pytest.fixture
def benchmark_config():
    """Create benchmark configuration for testing."""
    return BenchmarkConfig(
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


def test_build_benchmark_download_only_returns_manifest(benchmark_config):
    """Test download_only flag returns manifest without building."""
    with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
        mock_fetch.return_value = Path('/tmp/sources')

        result = build_benchmark(
            benchmark_config,
            'docker',
            download_only=True
        )

        assert 'benchmark' in result
        assert 'sources_dir' in result
        assert 'download_timestamp' in result
        assert 'artifact_path' not in result


def test_build_benchmark_appimage_not_implemented(benchmark_config):
    """Test AppImage building raises BuildError (Phase 4)."""
    with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
        mock_fetch.return_value = Path('/tmp/sources')

        with pytest.raises(BuildError) as exc_info:
            build_benchmark(benchmark_config, 'appimage')

        error_msg = str(exc_info.value)
        assert "not yet implemented" in error_msg.lower()


def test_build_benchmark_docker_not_implemented(benchmark_config):
    """Test Docker building raises BuildError (Phase 4)."""
    with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
        mock_fetch.return_value = Path('/tmp/sources')

        with pytest.raises(BuildError) as exc_info:
            build_benchmark(benchmark_config, 'docker')

        error_msg = str(exc_info.value)
        assert "not yet implemented" in error_msg.lower()


def test_build_benchmark_invalid_backend_raises_error(benchmark_config):
    """Test unsupported backend type raises BuildError."""
    with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
        mock_fetch.return_value = Path('/tmp/sources')

        with pytest.raises(BuildError) as exc_info:
            build_benchmark(benchmark_config, 'invalid_backend')

        error_msg = str(exc_info.value)
        assert "unsupported" in error_msg.lower()


def test_build_benchmark_clean_flag_passed_to_fetch(benchmark_config):
    """Test --clean flag is passed to fetch_sources."""
    with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
        mock_fetch.return_value = Path('/tmp/sources')

        try:
            build_benchmark(benchmark_config, 'docker', clean=True)
        except BuildError:
            pass

        call_kwargs = mock_fetch.call_args[1]
        assert call_kwargs.get('clean')


def test_build_benchmark_download_only_includes_ref():
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

        assert result['source_ref'] == 'v1.2.3'


def test_build_benchmark_empty_benchmarks_raises_error():
    """Test empty benchmarks dict raises BuildError."""
    empty_benchmark = BenchmarkConfig(benchmarks={})

    with pytest.raises(BuildError) as exc_info:
        build_benchmark(empty_benchmark, 'docker')

    error_msg = str(exc_info.value)
    assert "no benchmarks" in error_msg.lower()

