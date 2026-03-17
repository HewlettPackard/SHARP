"""
Docker image builder.

Creates Docker images for benchmark executables. Docker images provide
isolated, reproducible environments for running benchmarks across
different systems.

Build Process:
1. Generate Dockerfile from benchmark configuration
2. Copy benchmark sources to build context
3. Build Docker image using docker build
4. Tag image with benchmark name and version

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any

from src.core.config.schema import BenchmarkConfig, BenchmarkBuild
from src.core.packaging.errors import BuildError
from src.core.packaging.base import BaseBuilder


class DockerBuilder(BaseBuilder):
    """
    Build Docker images from benchmark configurations.

    Creates containerized benchmark environments using Docker.
    The resulting images can be pushed to registries or used locally.

    Attributes:
        registry: Docker registry for pushing images (optional)
        tag_prefix: Prefix for image tags (default: 'sharp-')
        verbose: If True, stream build output to terminal
    """

    def __init__(self, registry: str | None = None,
                 tag_prefix: str = 'sharp-',
                 verbose: bool = False):
        """Initialize Docker builder.

        Args:
            registry: Docker registry URL (e.g., 'ghcr.io/username')
                      If None, images are built locally only
            tag_prefix: Prefix for image tags (default: 'sharp-')
            verbose: If True, stream build output to terminal
        """
        super().__init__(verbose)
        self._registry = registry
        self._tag_prefix = tag_prefix

    def build(self, benchmark: BenchmarkConfig, sources_dir: Path,
              benchmark_name: str) -> Path:
        """
        Build Docker image from benchmark configuration.

        Generates a Dockerfile, creates build context, and builds
        the Docker image.

        Args:
            benchmark: Benchmark configuration
            sources_dir: Path to prepared sources
            benchmark_name: Name of the benchmark

        Returns:
            Path to a manifest file containing image details

        Raises:
            BuildError: If build fails at any stage
        """
        entry, build_config, python_reqs, system_deps, docker_config = self._get_build_config(
            benchmark, benchmark_name, 'docker'
        )

        base_image = docker_config.get('base_image', 'python:3.10-slim')

        # Determine benchmark directory (where benchmark.yaml lives)
        benchmark_dir = self._get_benchmark_dir(benchmark)

        # Create build context directory
        from src.core.config.include_resolver import get_project_root
        build_dir = get_project_root() / 'build' / 'docker' / benchmark_name
        build_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Copy sources to build context
            self._copy_sources_to_dir(sources_dir, benchmark_dir, build_dir, entry)

            # Generate Dockerfile
            self._generate_dockerfile(
                build_dir,
                benchmark_name,
                entry,
                base_image,
                python_reqs,
                system_deps,
                build_config
            )

            # Build Docker image
            image_tag = self._build_image(build_dir, benchmark_name)

            # Create manifest file
            manifest_path = self._create_manifest(
                build_dir, benchmark_name, image_tag, base_image
            )

            return manifest_path

        except Exception as e:
            if isinstance(e, BuildError):
                raise
            raise BuildError(f"Docker build failed: {e}")

    def _generate_dockerfile(self, build_dir: Path, benchmark_name: str,
                             entry: Any, base_image: str,
                             python_reqs: list[str],
                             system_deps: list[str],
                             build_config: BenchmarkBuild) -> Path:
        """Generate Dockerfile from benchmark configuration."""
        dockerfile_path = build_dir / 'Dockerfile'
        docker_config = build_config.docker or {}

        lines = [f'FROM {base_image}', '']

        # Install system dependencies
        if system_deps:
            deps = ' '.join(system_deps)
            lines.extend([
                '# Install system dependencies',
                f'RUN apt-get update && apt-get install -y {deps} && rm -rf /var/lib/apt/lists/*',
                ''
            ])

        # Run docker-specific install commands (override declarative reqs)
        install_commands = docker_config.get('install_commands', [])
        if install_commands:
            lines.append('# Install commands')
            for cmd in install_commands:
                lines.append(f'RUN {cmd}')
            lines.append('')
        # Fall back to requirements list if no install_commands
        elif python_reqs:
            reqs = ' '.join(python_reqs)
            lines.extend([
                '# Install Python requirements',
                f'RUN pip install --no-cache-dir {reqs}',
                ''
            ])

        # Set working directory
        lines.extend([
            'WORKDIR /benchmarks',
            ''
        ])

        # Copy files
        lines.extend([
            '# Copy benchmark files',
            'COPY . .',
            ''
        ])

        # Run pre_build hook (after copy, before build commands)
        if build_config.pre_build:
            lines.extend([
                '# Pre-build hook',
                f'RUN {build_config.pre_build}',
                ''
            ])

        # Run build commands if specified
        if build_config.build_commands:
            lines.append('# Build commands')
            for cmd in build_config.build_commands:
                lines.append(f'RUN {cmd}')
            lines.append('')

        # Run Makefile if specified
        if build_config.makefile:
            lines.extend([
                '# Build with Makefile',
                f'RUN make -f {build_config.makefile}',
                ''
            ])

        # Run post_build hook (after build)
        if build_config.post_build:
            lines.extend([
                '# Post-build hook',
                f'RUN {build_config.post_build}',
                ''
            ])

        # Check for docker-specific entrypoint
        docker_entrypoint = docker_config.get('entrypoint')
        if docker_entrypoint:
            # Use explicit entrypoint from config
            entrypoint_json = ', '.join(f'"{arg}"' for arg in docker_entrypoint)
            lines.append(f'ENTRYPOINT [{entrypoint_json}]')
        else:
            # Generate ENTRYPOINT + CMD from entry_point
            # ENTRYPOINT = executable (python3 script.py or ./binary)
            # CMD = default args (replaceable when running container)
            entry_point = entry.entry_point.lstrip('./')
            if entry_point.endswith('.py'):
                entrypoint_parts = ['python3', entry_point]
            else:
                entrypoint_parts = [f'./{entry_point}']

            entrypoint_json = ', '.join(f'"{part}"' for part in entrypoint_parts)
            lines.append(f'ENTRYPOINT [{entrypoint_json}]')

            # Add default args as CMD (will be replaced by docker run args)
            if entry.args:
                cmd_json = ', '.join(f'"{arg}"' for arg in entry.args)
                lines.append(f'CMD [{cmd_json}]')

        dockerfile_path.write_text('\n'.join(lines))
        return dockerfile_path

    def _build_image(self, build_dir: Path, benchmark_name: str) -> str:
        """Build Docker image and return the image tag."""
        image_tag = f'{self._tag_prefix}{benchmark_name}:latest'

        # Check if docker is available
        if not shutil.which('docker'):
            raise BuildError(
                "Docker not found. Install Docker from https://docs.docker.com/get-docker/"
            )

        try:
            if self._verbose:
                print(f"  Running: docker build -t {image_tag} .")
                result = subprocess.run(
                    ['docker', 'build', '-t', image_tag, '.'],
                    cwd=str(build_dir),
                    text=True,
                    timeout=1800  # 30 minutes for large images
                )
            else:
                result = subprocess.run(
                    ['docker', 'build', '-t', image_tag, '.'],
                    cwd=str(build_dir),
                    capture_output=True,
                    text=True,
                    timeout=1800  # 30 minutes for large images
                )

            if result.returncode != 0:
                raise BuildError(f"docker build failed: {getattr(result, 'stderr', '')}")

            # Optionally push to registry
            if self._registry:
                registry_tag = f'{self._registry}/{image_tag}'
                subprocess.run(
                    ['docker', 'tag', image_tag, registry_tag],
                    check=True
                )
                if self._verbose:
                    print(f"  Running: docker push {registry_tag}")
                    push_result = subprocess.run(
                        ['docker', 'push', registry_tag],
                        text=True,
                        timeout=600
                    )
                else:
                    push_result = subprocess.run(
                        ['docker', 'push', registry_tag],
                        capture_output=True,
                        text=True,
                        timeout=600
                    )
                if push_result.returncode != 0:
                    raise BuildError(f"docker push failed: {getattr(push_result, 'stderr', '')}")
                image_tag = registry_tag

            return image_tag

        except subprocess.TimeoutExpired:
            raise BuildError("docker build timeout (30 minutes)")
        except subprocess.CalledProcessError as e:
            raise BuildError(f"docker command failed: {e}")

    def _create_manifest(self, build_dir: Path, benchmark_name: str,
                         image_tag: str, base_image: str) -> Path:
        """Create manifest file with build details."""
        import json
        from datetime import datetime

        manifest_path = build_dir / 'manifest.json'
        manifest = {
            'benchmark': benchmark_name,
            'image_tag': image_tag,
            'base_image': base_image,
            'build_timestamp': datetime.now().isoformat(),
            'build_dir': str(build_dir),
        }

        manifest_path.write_text(json.dumps(manifest, indent=2))
        return manifest_path


class DockerComposeBuilder:
    """
    Build Docker Compose configurations for multi-container benchmarks.

    Some benchmarks (e.g., distributed systems, client-server) require
    multiple containers. This builder generates docker-compose.yaml files.
    """

    def __init__(self) -> None:
        """Initialize Docker Compose builder."""
        pass

    def build(self, benchmark: BenchmarkConfig, sources_dir: Path,
              benchmark_name: str) -> Path:
        """Build Docker Compose configuration.

        Not yet implemented - placeholder for future multi-container support.
        """
        raise BuildError("Docker Compose builder not yet implemented")
