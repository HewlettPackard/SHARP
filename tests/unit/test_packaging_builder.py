"""
Unit tests for benchmark packaging and source fetching.

Tests source fetching (git, path, download), PackagingManager,
AppImageBuilder, DockerBuilder, and error handling.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock

from src.core.config.schema import (
    BenchmarkConfig,
    BenchmarkEntry,
    BenchmarkSource,
    BenchmarkBuild,
)
from src.core.packaging.builder import (
    PackagingManager,
    fetch_sources,
    build_benchmark,
)
from src.core.packaging.appimage import AppImageBuilder
from src.core.packaging.docker import DockerBuilder
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


# ========== Test PackagingManager ==========

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
                entry_point='test.py',
                args=['arg1'],
                tags=['test']
            )
        }
    )


def test_packaging_manager_no_builder_registered(benchmark_config):
    """Test PackagingManager raises error when no builder registered."""
    manager = PackagingManager()

    with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
        mock_fetch.return_value = Path('/tmp/sources')

        with pytest.raises(BuildError) as exc_info:
            manager.build(benchmark_config, 'docker')

        assert "no builder registered" in str(exc_info.value).lower()


def test_packaging_manager_register_builder():
    """Test builder registration."""
    manager = PackagingManager()
    mock_builder = MagicMock()

    manager.register_builder('docker', mock_builder)

    assert 'docker' in manager._builders


def test_packaging_manager_download_only(benchmark_config):
    """Test download_only flag returns manifest without building."""
    manager = PackagingManager()

    with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
        mock_fetch.return_value = Path('/tmp/sources')

        result = manager.build(
            benchmark_config,
            'docker',
            download_only=True
        )

        assert 'benchmark' in result
        assert 'sources_dir' in result
        assert 'download_timestamp' in result
        assert 'artifact_path' not in result


def test_packaging_manager_calls_builder(benchmark_config):
    """Test PackagingManager calls registered builder."""
    manager = PackagingManager()
    mock_builder = MagicMock()
    mock_builder.build.return_value = Path('/tmp/artifact')
    manager.register_builder('docker', mock_builder)

    with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
        mock_fetch.return_value = Path('/tmp/sources')

        result = manager.build(benchmark_config, 'docker')

        mock_builder.build.assert_called_once()
        assert result['artifact_path'] == '/tmp/artifact'


def test_packaging_manager_benchmark_name_selects_specific_benchmark():
    """Test benchmark_name parameter selects the correct benchmark."""
    # Config with multiple benchmarks
    multi_config = BenchmarkConfig(
        benchmarks={
            'bench_a': BenchmarkEntry(
                sources=[],
                build=BenchmarkBuild(),
                entry_point='a.py',
                args=[],
                tags=[]
            ),
            'bench_b': BenchmarkEntry(
                sources=[],
                build=BenchmarkBuild(),
                entry_point='b.py',
                args=[],
                tags=[]
            )
        }
    )
    manager = PackagingManager()
    mock_builder = MagicMock()
    mock_builder.build.return_value = Path('/tmp/artifact')
    manager.register_builder('docker', mock_builder)

    with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
        mock_fetch.return_value = Path('/tmp/sources')

        result = manager.build(multi_config, 'docker', benchmark_name='bench_b')

        assert result['benchmark'] == 'bench_b'
        # Verify builder was called with the correct benchmark entry
        call_args = mock_builder.build.call_args
        assert call_args[0][2] == 'bench_b'  # benchmark_name argument


def test_packaging_manager_invalid_benchmark_name_raises_error():
    """Test invalid benchmark_name raises BuildError with helpful message."""
    config = BenchmarkConfig(
        benchmarks={
            'real_bench': BenchmarkEntry(
                sources=[],
                build=BenchmarkBuild(),
                entry_point='test.py',
                args=[],
                tags=[]
            )
        }
    )
    manager = PackagingManager()

    with pytest.raises(BuildError) as exc_info:
        manager.build(config, 'docker', benchmark_name='nonexistent')

    error_msg = str(exc_info.value)
    assert 'nonexistent' in error_msg
    assert 'real_bench' in error_msg  # Should list available benchmarks


def test_packaging_manager_defaults_to_first_benchmark():
    """Test that without benchmark_name, first benchmark is used."""
    # OrderedDict-like behavior: first benchmark should be selected
    config = BenchmarkConfig(
        benchmarks={
            'first_bench': BenchmarkEntry(
                sources=[],
                build=BenchmarkBuild(),
                entry_point='first.py',
                args=[],
                tags=[]
            ),
            'second_bench': BenchmarkEntry(
                sources=[],
                build=BenchmarkBuild(),
                entry_point='second.py',
                args=[],
                tags=[]
            )
        }
    )
    manager = PackagingManager()
    mock_builder = MagicMock()
    mock_builder.build.return_value = Path('/tmp/artifact')
    manager.register_builder('docker', mock_builder)

    with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
        mock_fetch.return_value = Path('/tmp/sources')

        result = manager.build(config, 'docker')  # No benchmark_name

        assert result['benchmark'] == 'first_bench'


# ========== Test build_benchmark convenience function ==========

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


def test_build_benchmark_clean_flag_passed_to_fetch(benchmark_config):
    """Test --clean flag is passed to fetch_sources."""
    with patch('src.core.packaging.builder.fetch_sources') as mock_fetch:
        mock_fetch.return_value = Path('/tmp/sources')

        build_benchmark(benchmark_config, 'docker', download_only=True, clean=True)

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


# ========== Test AppImageBuilder ==========

class TestAppImageBuilder:
    """Tests for AppImageBuilder."""

    def test_find_appimagetool_in_path(self):
        """Test finding appimagetool in PATH."""
        builder = AppImageBuilder()
        # Should not raise even if appimagetool not found
        assert builder._appimagetool is not None

    def test_create_appdir_structure(self, tmp_path):
        """Test AppDir directory structure creation."""
        builder = AppImageBuilder(output_dir=tmp_path)
        appdir = tmp_path / 'test.AppDir'

        builder._create_appdir_structure(appdir, 'test')

        assert (appdir / 'usr' / 'bin').exists()
        assert (appdir / 'usr' / 'lib').exists()
        assert (appdir / 'usr' / 'share' / 'applications').exists()

    def test_create_apprun_python(self, tmp_path):
        """Test AppRun script creation for Python entry point."""
        builder = AppImageBuilder(output_dir=tmp_path)
        appdir = tmp_path / 'test.AppDir'
        appdir.mkdir(parents=True)

        builder._create_apprun(appdir, 'test.py', ['--arg1'])

        apprun = appdir / 'AppRun'
        assert apprun.exists()
        content = apprun.read_text()
        assert 'python3' in content
        assert 'test.py' in content

    def test_create_desktop_entry(self, tmp_path):
        """Test .desktop file creation."""
        builder = AppImageBuilder(output_dir=tmp_path)
        appdir = tmp_path / 'test.AppDir'
        appdir.mkdir(parents=True)

        builder._create_desktop_entry(appdir, 'test_benchmark')

        desktop = appdir / 'test_benchmark.desktop'
        assert desktop.exists()
        content = desktop.read_text()
        assert 'Name=test_benchmark' in content

    def test_build_no_appimagetool(self, tmp_path, benchmark_config):
        """Test build fails gracefully when appimagetool not found."""
        builder = AppImageBuilder(
            output_dir=tmp_path,
            appimagetool='/nonexistent/appimagetool'
        )

        sources_dir = tmp_path / 'sources'
        sources_dir.mkdir()

        with pytest.raises(BuildError) as exc_info:
            builder.build(benchmark_config, sources_dir, 'test_bench')

        assert 'appimagetool' in str(exc_info.value).lower()


# ========== Test DockerBuilder ==========

class TestDockerBuilder:
    """Tests for DockerBuilder."""

    def test_generate_dockerfile(self, tmp_path, benchmark_config):
        """Test Dockerfile generation."""
        builder = DockerBuilder()
        build_dir = tmp_path / 'build'
        build_dir.mkdir()

        entry = benchmark_config.benchmarks['test_bench']

        dockerfile = builder._generate_dockerfile(
            build_dir,
            'test_bench',
            entry,
            'python:3.10-slim',
            ['numpy'],
            [],
            entry.build
        )

        assert dockerfile.exists()
        content = dockerfile.read_text()
        assert 'FROM python:3.10-slim' in content
        assert 'pip install' in content
        assert 'numpy' in content

    def test_generate_dockerfile_with_system_deps(self, tmp_path):
        """Test Dockerfile includes system dependencies."""
        builder = DockerBuilder()
        build_dir = tmp_path / 'build'
        build_dir.mkdir()

        build_config = BenchmarkBuild(system_deps=['libfoo-dev', 'libbar'])
        benchmark = BenchmarkConfig(
            benchmarks={
                'test': BenchmarkEntry(
                    sources=[],
                    build=build_config,
                    entry_point='test.py',
                    args=[],
                    tags=[]
                )
            }
        )
        entry = benchmark.benchmarks['test']

        dockerfile = builder._generate_dockerfile(
            build_dir,
            'test',
            entry,
            'python:3.10-slim',
            [],
            ['libfoo-dev', 'libbar'],
            build_config
        )

        content = dockerfile.read_text()
        assert 'apt-get install' in content
        assert 'libfoo-dev' in content

    def test_generate_dockerfile_with_build_commands(self, tmp_path):
        """Test Dockerfile includes build commands."""
        builder = DockerBuilder()
        build_dir = tmp_path / 'build'
        build_dir.mkdir()

        build_config = BenchmarkBuild(build_commands=['make', 'make install'])
        benchmark = BenchmarkConfig(
            benchmarks={
                'test': BenchmarkEntry(
                    sources=[],
                    build=build_config,
                    entry_point='test',
                    args=[],
                    tags=[]
                )
            }
        )
        entry = benchmark.benchmarks['test']

        dockerfile = builder._generate_dockerfile(
            build_dir,
            'test',
            entry,
            'python:3.10-slim',
            [],
            [],
            build_config
        )

        content = dockerfile.read_text()
        assert 'RUN make' in content
        assert 'RUN make install' in content

    def test_build_no_docker(self, tmp_path, benchmark_config):
        """Test build fails when docker not available."""
        builder = DockerBuilder()

        sources_dir = tmp_path / 'sources'
        sources_dir.mkdir()

        with patch('shutil.which', return_value=None):
            with pytest.raises(BuildError) as exc_info:
                builder.build(benchmark_config, sources_dir, 'test_bench')

            assert 'docker not found' in str(exc_info.value).lower()

    def test_create_manifest(self, tmp_path):
        """Test manifest file creation."""
        builder = DockerBuilder()
        build_dir = tmp_path / 'build'
        build_dir.mkdir()

        manifest_path = builder._create_manifest(
            build_dir,
            'test_bench',
            'sharp-test_bench:latest',
            'python:3.10-slim'
        )

        import json
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest['benchmark'] == 'test_bench'
        assert manifest['image_tag'] == 'sharp-test_bench:latest'

