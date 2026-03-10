"""
Integration tests for build hooks (pre_build and post_build).

Tests that build hooks execute correctly and can modify the build environment
in both Docker and AppImage builders.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from src.core.config.loader import load_benchmark_config
from src.core.config.schema import (
    BenchmarkBuild,
    BenchmarkConfig,
    BenchmarkEntry,
)
from src.core.packaging.appimage import AppImageBuilder
from src.core.packaging.docker import DockerBuilder


@pytest.fixture
def temp_benchmark_dir():
    """Create temporary benchmark directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def benchmark_with_hooks(temp_benchmark_dir: Path) -> tuple[BenchmarkConfig, Path]:
    """Create a benchmark configuration with pre_build and post_build hooks.

    Creates a simple Python benchmark that writes files during hooks
    to verify hook execution.
    """
    # Create a simple Python script that outputs hook marker files
    script_content = """#!/usr/bin/env python3
import sys
from pathlib import Path

# Check that hook files exist
pre_hook = Path('pre_hook_ran.txt')
post_hook = Path('post_hook_ran.txt')

if not pre_hook.exists():
    print('ERROR: pre_build hook did not run', file=sys.stderr)
    sys.exit(1)

if not post_hook.exists():
    print('ERROR: post_build hook did not run', file=sys.stderr)
    sys.exit(1)

print('SUCCESS: Both hooks executed')
"""

    script_path = temp_benchmark_dir / 'test_hook.py'
    script_path.write_text(script_content)
    script_path.chmod(0o755)

    # Create benchmark config with hooks
    build = BenchmarkBuild(
        pre_build='echo "pre_build executed" > pre_hook_ran.txt',
        post_build='echo "post_build executed" > post_hook_ran.txt',
        requirements=[],
        system_deps=[],
        build_commands=[],
    )

    entry = BenchmarkEntry(
        entry_point='test_hook.py',
        args=[],
        build=build,
    )

    config = BenchmarkConfig(
        benchmarks={'test_hook': entry},
        tags=['test'],
        metrics={},
    )

    # Store config path for source resolution
    config._config_path = str(temp_benchmark_dir / 'benchmark.yaml')

    return config, temp_benchmark_dir


def test_docker_hooks_execute(benchmark_with_hooks):
    """Test that pre_build and post_build hooks execute in Docker builds."""
    if not shutil.which('docker'):
        pytest.skip('docker not found')

    config, sources_dir = benchmark_with_hooks
    builder = DockerBuilder(verbose=False)

    try:
        # Build the Docker image
        manifest_path = builder.build(config, sources_dir, 'test_hook')

        # Verify manifest was created
        assert manifest_path.exists()

        # Extract image tag from manifest
        import json
        manifest = json.loads(manifest_path.read_text())
        image_tag = manifest['image_tag']

        # Run the container to verify hooks executed
        result = subprocess.run(
            ['docker', 'run', '--rm', image_tag],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Check that the script succeeded (hooks created marker files)
        assert result.returncode == 0, f"Container failed: {result.stderr}"
        assert 'SUCCESS: Both hooks executed' in result.stdout

        # Cleanup: Remove the image
        subprocess.run(['docker', 'rmi', '-f', image_tag], capture_output=True)

    except Exception as e:
        pytest.fail(f"Docker hook test failed: {e}")


def test_docker_hook_order(benchmark_with_hooks):
    """Test that hooks run in correct order (system_deps → pre_build → build_commands → post_build)."""
    if not shutil.which('docker'):
        pytest.skip('docker not found')

    config, sources_dir = benchmark_with_hooks

    # Modify hooks to verify order
    config.benchmarks['test_hook'].build.pre_build = (
        'echo "PRE_BUILD_MARKER" && touch /tmp/pre_marker.txt'
    )
    config.benchmarks['test_hook'].build.post_build = (
        'echo "POST_BUILD_MARKER" && touch /tmp/post_marker.txt'
    )
    config.benchmarks['test_hook'].build.system_deps = ['curl']  # Add a system dep
    config.benchmarks['test_hook'].build.build_commands = ['echo "BUILD_MARKER"']

    builder = DockerBuilder(verbose=False)

    try:
        manifest_path = builder.build(config, sources_dir, 'test_hook')

        # Read the generated Dockerfile to verify order
        from src.core.config.include_resolver import get_project_root
        dockerfile_path = (
            get_project_root() / 'build' / 'docker' / 'test_hook' / 'Dockerfile'
        )

        if dockerfile_path.exists():
            dockerfile_content = dockerfile_path.read_text()

            # Verify system deps come first
            deps_idx = dockerfile_content.find('apt-get install')
            assert deps_idx > 0, "system deps not found in Dockerfile"

            # Verify pre_build comes after COPY (so it can patch files)
            copy_idx = dockerfile_content.find('COPY . .')
            pre_idx = dockerfile_content.find('PRE_BUILD_MARKER')
            assert copy_idx > 0, "COPY not found in Dockerfile"
            assert pre_idx > 0, "pre_build hook not found in Dockerfile"
            assert copy_idx < pre_idx, "pre_build should run after COPY"

            # Verify pre_build runs before build commands
            build_idx = dockerfile_content.find('BUILD_MARKER')
            assert build_idx > 0, "build commands not found in Dockerfile"
            assert pre_idx < build_idx, "pre_build should run before build commands"

            # Verify post_build appears after build commands
            post_idx = dockerfile_content.find('POST_BUILD_MARKER')
            assert post_idx > 0, "post_build hook not found in Dockerfile"
            assert build_idx < post_idx, "post_build should run after build commands"

        # Cleanup
        manifest = eval(manifest_path.read_text())  # noqa: S307
        subprocess.run(
            ['docker', 'rmi', '-f', manifest['image_tag']], capture_output=True
        )

    except Exception as e:
        pytest.fail(f"Docker hook order test failed: {e}")


def test_appimage_hooks_execute(benchmark_with_hooks):
    """Test that pre_build and post_build hooks execute in AppImage builds."""
    if not shutil.which('appimagetool'):
        pytest.skip('appimagetool not found')

    config, sources_dir = benchmark_with_hooks
    builder = AppImageBuilder(verbose=False)

    try:
        # Build the AppImage
        appimage_path = builder.build(config, sources_dir, 'test_hook')

        # Verify AppImage was created
        assert appimage_path.exists()
        assert appimage_path.name.endswith('.AppImage')

        # Make it executable
        appimage_path.chmod(0o755)

        # Run the AppImage to verify hooks executed
        result = subprocess.run(
            [str(appimage_path)],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Check that the script succeeded (hooks created marker files)
        assert result.returncode == 0, f"AppImage failed: {result.stderr}"
        assert 'SUCCESS: Both hooks executed' in result.stdout

        # Cleanup: Remove the AppImage
        appimage_path.unlink()

    except Exception as e:
        pytest.fail(f"AppImage hook test failed: {e}")


def test_appimage_hook_modifies_environment(temp_benchmark_dir: Path):
    """Test that pre_build hook can modify the build environment."""
    if not shutil.which('appimagetool'):
        pytest.skip('appimagetool not found')

    # Create a C program that reads a value patched by pre_build
    c_source = """#include <stdio.h>
#include "version.h"

int main() {
    printf("VERSION=%d\\n", PATCH_VERSION);
    return 0;
}
"""
    (temp_benchmark_dir / 'version.c').write_text(c_source)

    # Create a header file that will be patched by pre_build
    header_template = """#define PATCH_VERSION 0
"""
    (temp_benchmark_dir / 'version.h').write_text(header_template)

    # Create Makefile
    makefile = """version: version.c version.h
\tgcc -o version version.c -I.
"""
    (temp_benchmark_dir / 'Makefile').write_text(makefile)

    # Build config with pre_build hook that patches the version
    build = BenchmarkBuild(
        pre_build='sed -i "s/PATCH_VERSION 0/PATCH_VERSION 42/" version.h',
        makefile='Makefile',
        requirements=[],
        system_deps=['gcc'],
        build_commands=[],
    )

    entry = BenchmarkEntry(
        entry_point='version',
        args=[],
        build=build,
    )

    config = BenchmarkConfig(
        benchmarks={'version_test': entry},
        tags=['test'],
        metrics={},
    )
    config._config_path = str(temp_benchmark_dir / 'benchmark.yaml')

    builder = AppImageBuilder(verbose=False)

    try:
        # Build the AppImage
        appimage_path = builder.build(config, temp_benchmark_dir, 'version_test')

        # Verify AppImage was created
        assert appimage_path.exists()
        appimage_path.chmod(0o755)

        # Run and check that the patched version is used
        result = subprocess.run(
            [str(appimage_path)],
            capture_output=True,
            text=True,
            timeout=10
        )

        assert result.returncode == 0, f"AppImage failed: {result.stderr}"
        assert 'VERSION=42' in result.stdout, "pre_build hook did not patch version"

        # Cleanup
        appimage_path.unlink()

    except Exception as e:
        pytest.fail(f"AppImage environment modification test failed: {e}")


def test_hook_failure_stops_build(benchmark_with_hooks):
    """Test that a failing hook stops the build process."""
    if not shutil.which('docker'):
        pytest.skip('docker not found')

    config, sources_dir = benchmark_with_hooks

    # Make pre_build hook fail
    config.benchmarks['test_hook'].build.pre_build = 'exit 1'

    builder = DockerBuilder(verbose=False)

    # Build should raise BuildError
    from src.core.packaging.errors import BuildError
    with pytest.raises(BuildError, match='build failed'):
        builder.build(config, sources_dir, 'test_hook')
