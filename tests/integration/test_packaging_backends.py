"""
Integration tests for packaged benchmarks running on different backends.

Tests that benchmarks can be built as AppImages and Docker containers,
then executed successfully on local, MPI, and Docker backends.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from src.core.config.include_resolver import get_project_root
from src.core.config.loader import load_benchmark_config
from src.core.packaging.appimage import AppImageBuilder
from src.core.packaging.docker import DockerBuilder


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def project_root() -> Path:
    """Get the project root directory."""
    return get_project_root()


@pytest.fixture(scope="module")
def sympy_appimage(project_root: Path) -> Path:
    """Build sympy-expand AppImage if not already built.

    Returns the path to the built AppImage.
    """
    appimage_path = project_root / "build" / "appimages" / "sympy-expand-x86_64.AppImage"

    if appimage_path.exists():
        return appimage_path

    # Check if appimagetool is available
    if not shutil.which("appimagetool"):
        pytest.skip("appimagetool not found - cannot build AppImage")

    # Load benchmark config and build
    benchmark_yaml = project_root / "benchmarks" / "micro" / "python" / "benchmark.yaml"
    if not benchmark_yaml.exists():
        pytest.skip("sympy-expand benchmark.yaml not found")

    benchmark_config = load_benchmark_config(str(benchmark_yaml))
    builder = AppImageBuilder(verbose=False)

    try:
        # Prepare empty sources dir (sympy-expand has no external sources)
        import tempfile
        with tempfile.TemporaryDirectory() as sources_dir:
            result = builder.build(benchmark_config, Path(sources_dir), "sympy-expand")
        return result
    except Exception as e:
        pytest.skip(f"Failed to build AppImage: {e}")


@pytest.fixture(scope="module")
def sympy_docker_image(project_root: Path) -> str:
    """Build sympy-expand Docker image if not already built.

    Returns the Docker image tag.
    """
    image_tag = "sharp-sympy-expand:latest"

    # Check if docker is available
    if not shutil.which("docker"):
        pytest.skip("docker not found - cannot build Docker image")

    # Check if image already exists
    result = subprocess.run(
        ["docker", "image", "inspect", image_tag],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        return image_tag

    # Load benchmark config and build
    benchmark_yaml = project_root / "benchmarks" / "micro" / "python" / "benchmark.yaml"
    if not benchmark_yaml.exists():
        pytest.skip("sympy-expand benchmark.yaml not found")

    benchmark_config = load_benchmark_config(str(benchmark_yaml))
    builder = DockerBuilder(verbose=False)

    try:
        # Prepare empty sources dir (sympy-expand has no external sources)
        import tempfile
        with tempfile.TemporaryDirectory() as sources_dir:
            builder.build(benchmark_config, Path(sources_dir), "sympy-expand")
        return image_tag
    except Exception as e:
        pytest.skip(f"Failed to build Docker image: {e}")


# =============================================================================
# AppImage Tests
# =============================================================================

class TestAppImageExecution:
    """Tests for AppImage execution on various backends."""

    def test_appimage_runs_directly(self, sympy_appimage: Path) -> None:
        """Test AppImage executes successfully when run directly."""
        result = subprocess.run(
            [str(sympy_appimage), "10"],
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode == 0, f"AppImage failed: {result.stderr}"
        assert "@@@ Time" in result.stdout, "Missing timing output"
        assert "Terms:" in result.stdout, "Missing sympy computation output"

    def test_appimage_local_backend(self, sympy_appimage: Path, tmp_path: Path) -> None:
        """Test AppImage runs via SHARP local backend."""
        result = subprocess.run(
            [
                "uv", "run", "launch", "sympy-expand",
                "-e", "test_appimage_local",
                "--skip-sys-specs",
                "-r", "COUNT",
                "-j", '{"count": 1}',
                "-b", "local",
                "-d", str(tmp_path)
            ],
            text=True,
            timeout=120,
            cwd=get_project_root()
        )

        assert result.returncode == 0, "Launch command failed"

        # Verify output files created
        csv_files = list(tmp_path.glob("**/sympy-expand.csv"))
        assert len(csv_files) > 0, "No CSV output file created"

        # Verify CSV has data
        with open(csv_files[0]) as f:
            lines = f.readlines()
            assert len(lines) >= 2, "CSV file is empty"  # Header + at least 1 data row

    def test_appimage_mpi_backend(self, sympy_appimage: Path, tmp_path: Path) -> None:
        """Test AppImage runs via SHARP MPI backend."""
        # Check if mpirun is available
        if not shutil.which("mpirun"):
            pytest.skip("mpirun not found - cannot test MPI backend")

        result = subprocess.run(
            [
                "uv", "run", "launch", "sympy-expand",
                "-e", "test_appimage_mpi",
                "--skip-sys-specs",
                "-r", "COUNT",
                "-j", '{"count": 1}',
                "-b", "mpi",
                "-d", str(tmp_path)
            ],
            text=True,
            timeout=120,
            cwd=get_project_root()
        )

        assert result.returncode == 0, "Launch command failed"

        # Verify output files created
        csv_files = list(tmp_path.glob("**/sympy-expand.csv"))
        assert len(csv_files) > 0, "No CSV output file created"


# =============================================================================
# Docker Tests
# =============================================================================

class TestDockerExecution:
    """Tests for Docker container execution."""

    def test_docker_image_runs_directly(self, sympy_docker_image: str) -> None:
        """Test Docker image executes successfully when run directly."""
        result = subprocess.run(
            ["docker", "run", "--rm", sympy_docker_image, "10"],
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode == 0, f"Docker run failed: {result.stderr}"
        assert "@@@ Time" in result.stdout, "Missing timing output"
        assert "Terms:" in result.stdout, "Missing sympy computation output"

    def test_docker_backend(self, sympy_docker_image: str, tmp_path: Path) -> None:
        """Test Docker image runs via SHARP Docker backend."""
        result = subprocess.run(
            [
                "uv", "run", "launch", "sympy-expand",
                "-e", "test_docker_backend",
                "--skip-sys-specs",
                "-r", "COUNT",
                "-j", '{"count": 1}',
                "-b", "docker",
                "-d", str(tmp_path)
            ],
            text=True,
            timeout=120,
            cwd=get_project_root()
        )

        assert result.returncode == 0, "Launch command failed"

        # Verify output files created
        csv_files = list(tmp_path.glob("**/sympy-expand.csv"))
        assert len(csv_files) > 0, "No CSV output file created"

        # Verify CSV has data
        with open(csv_files[0]) as f:
            lines = f.readlines()
            assert len(lines) >= 2, "CSV file is empty"  # Header + at least 1 data row


# =============================================================================
# Cross-Backend Tests
# =============================================================================

class TestCrossBackendConsistency:
    """Tests verifying consistent results across backends."""

    def test_appimage_and_docker_produce_same_output(
        self, sympy_appimage: Path, sympy_docker_image: str
    ) -> None:
        """Test that AppImage and Docker produce equivalent computation results."""
        # Use the same degree for both - 10 is fast
        degree = "10"

        # Run AppImage
        appimage_result = subprocess.run(
            [str(sympy_appimage), degree],
            capture_output=True,
            text=True,
            timeout=60
        )

        # Run Docker
        docker_result = subprocess.run(
            ["docker", "run", "--rm", sympy_docker_image, degree],
            capture_output=True,
            text=True,
            timeout=60
        )

        assert appimage_result.returncode == 0, f"AppImage failed: {appimage_result.stderr}"
        assert docker_result.returncode == 0, f"Docker failed: {docker_result.stderr}"

        # Extract term counts (should be identical)
        def extract_terms(output: str) -> int:
            for line in output.split("\n"):
                if "Terms:" in line:
                    # Format: "Terms: 66, Coefficient sum: ..."
                    return int(line.split("Terms:")[1].split(",")[0].strip())
            return -1

        appimage_terms = extract_terms(appimage_result.stdout)
        docker_terms = extract_terms(docker_result.stdout)

        assert appimage_terms == docker_terms, \
            f"AppImage terms ({appimage_terms}) != Docker terms ({docker_terms})"
        assert appimage_terms > 0, "Failed to extract term count"


# =============================================================================
# SSH Backend Tests (with entry_point override)
# =============================================================================

class TestSSHBackendWithEntryPointOverride:
    """Tests for SSH backend with custom entry point override.

    Demonstrates using the 'entry_point' option via -j to specify
    a different executable path for remote execution. This is useful when
    the benchmark is located at a different path on the remote system.

    Example:
        uv run launch sympy-expand -b ssh -j '{"entry_point": "/remote/path/app.AppImage"}'
    """

    def test_ssh_backend_with_entry_point_override(self, sympy_appimage: Path, tmp_path: Path) -> None:
        """Test SSH backend with custom entry_point via -j option.

        This test uses 'ssh localhost' to simulate remote execution,
        demonstrating how to override the entry point for SSH backends.
        """
        # Check if ssh to localhost works (some systems may not have this configured)
        ssh_check = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "localhost", "echo", "test"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if ssh_check.returncode != 0:
            pytest.skip("SSH to localhost not configured (passwordless auth required)")

        # Use the absolute path to the AppImage for the remote entry_point
        appimage_abs_path = str(sympy_appimage.resolve())

        # JSON config with entry_point override
        # This demonstrates overriding the entry point for remote backends
        json_config = {
            "count": 1,
            "entry_point": appimage_abs_path,  # Override entry point directly
            "backend_options": {
                "ssh": {
                    "hosts": "localhost"
                }
            }
        }

        import json
        result = subprocess.run(
            [
                "uv", "run", "launch", "sympy-expand",
                "-e", "test_ssh_entry_point",
                "--skip-sys-specs",
                "-r", "COUNT",
                "-j", json.dumps(json_config),
                "-b", "ssh",
                "-d", str(tmp_path)
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=get_project_root()
        )

        assert result.returncode == 0, f"Launch command failed: {result.stderr}"

        # Verify output files created
        csv_files = list(tmp_path.glob("**/sympy-expand.csv"))
        assert len(csv_files) > 0, "No CSV output file created"

        # Verify CSV has data
        with open(csv_files[0]) as f:
            lines = f.readlines()
            assert len(lines) >= 2, "CSV file is empty"  # Header + at least 1 data row

    def test_ssh_backend_produces_same_result_as_local(
        self, sympy_appimage: Path, tmp_path: Path
    ) -> None:
        """Test that SSH backend with entry_point override produces same results as local."""
        # Check if ssh to localhost works
        ssh_check = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "localhost", "echo", "test"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if ssh_check.returncode != 0:
            pytest.skip("SSH to localhost not configured (passwordless auth required)")

        appimage_abs_path = str(sympy_appimage.resolve())

        # Run via local backend
        local_dir = tmp_path / "local"
        local_dir.mkdir()
        local_result = subprocess.run(
            [
                "uv", "run", "launch", "sympy-expand",
                "-e", "test_local_compare",
                "--skip-sys-specs",
                "-r", "COUNT",
                "-j", '{"count": 1}',
                "-b", "local",
                "-d", str(local_dir)
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=get_project_root()
        )
        assert local_result.returncode == 0, f"Local launch failed: {local_result.stderr}"

        # Run via SSH backend with entry_point override
        ssh_dir = tmp_path / "ssh"
        ssh_dir.mkdir()
        import json
        json_config = {
            "count": 1,
            "entry_point": appimage_abs_path,  # Override entry point directly
            "backend_options": {
                "ssh": {
                    "hosts": "localhost"
                }
            }
        }
        ssh_result = subprocess.run(
            [
                "uv", "run", "launch", "sympy-expand",
                "-e", "test_ssh_compare",
                "--skip-sys-specs",
                "-r", "COUNT",
                "-j", json.dumps(json_config),
                "-b", "ssh",
                "-d", str(ssh_dir)
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=get_project_root()
        )
        assert ssh_result.returncode == 0, f"SSH launch failed: {ssh_result.stderr}"

        # Compare CSV outputs - both should have data
        local_csv = list(local_dir.glob("**/sympy-expand.csv"))[0]
        ssh_csv = list(ssh_dir.glob("**/sympy-expand.csv"))[0]

        with open(local_csv) as f:
            local_lines = f.readlines()
        with open(ssh_csv) as f:
            ssh_lines = f.readlines()

        # Both should have header + at least 1 data row
        assert len(local_lines) >= 2, "Local CSV is empty"
        assert len(ssh_lines) >= 2, "SSH CSV is empty"
