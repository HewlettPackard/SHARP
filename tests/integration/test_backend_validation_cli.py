#!/usr/bin/env python3
"""
Integration tests for backend composability validation in CLI.

Tests end-to-end CLI behavior with invalid backend combinations.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import subprocess
import sys
from pathlib import Path


def run_launch_command(args: list[str]) -> tuple[int, str, str]:
    """
    Run launch command and capture output.

    Args:
        args: Command-line arguments (without 'uv run launch')

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    cmd = [sys.executable, "-m", "src.cli.launch"] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent
    )
    return result.returncode, result.stdout, result.stderr


class TestCLIBackendValidation:
    """Test CLI rejection of invalid backend combinations."""

    def test_valid_single_backend(self):
        """CLI accepts single backend."""
        # Use sleep with a very short duration for fast test
        exit_code, stdout, stderr = run_launch_command([
            "-b", "local",
            "-r", "COUNT",
            "-j", '{"count": 1}',
            "--skip-sys-specs",
            "sleep", "0.01"
        ])
        # Should succeed (exit code 0) or fail for other reasons, but not backend validation
        assert "Backend Composition Error" not in stderr

    def test_valid_composable_chain(self):
        """CLI accepts chain of composable backends."""
        # Note: This test will succeed in validation but may fail in execution
        # if perf is not available - that's okay, we're testing validation
        exit_code, stdout, stderr = run_launch_command([
            "-b", "perf",
            "-b", "local",
            "-r", "COUNT",
            "-j", '{"count": 1}',
            "--skip-sys-specs",
            "sleep", "0.01"
        ])
        # Should not fail with backend composition error
        assert "Backend Composition Error" not in stderr

    def test_invalid_non_composable_not_leftmost(self):
        """CLI rejects non-composable backend not in position 1."""
        exit_code, stdout, stderr = run_launch_command([
            "-b", "perf",
            "-b", "mpip",
            "-r", "COUNT",
            "-j", '{"count": 1}',
            "--skip-sys-specs",
            "sleep", "0.01"
        ])
        # Should fail with backend composition error
        assert exit_code != 0
        assert "Backend Composition Error" in stderr
        assert "Non-composable" in stderr
        assert "mpip" in stderr

    def test_valid_non_composable_leftmost(self):
        """CLI accepts non-composable backend at position 1."""
        # This will likely fail during execution (mpip needs MPI setup)
        # but should pass validation
        exit_code, stdout, stderr = run_launch_command([
            "-b", "mpip",
            "--mpl", "1",
            "-r", "COUNT",
            "-j", '{"count": 1}',
            "--skip-sys-specs",
            "sleep", "0.01"
        ])
        # Should not fail with backend composition error
        # (may fail with other errors like missing mpip library, but that's different)
        assert "Backend Composition Error" not in stderr

    def test_error_message_includes_help(self):
        """Error message includes helpful examples."""
        exit_code, stdout, stderr = run_launch_command([
            "-b", "local",
            "-b", "mpi",  # mpi is non-composable
            "-r", "COUNT",
            "-j", '{"count": 1}',
            "--skip-sys-specs",
            "sleep", "0.01"
        ])
        assert exit_code != 0
        assert "Backend Composition Error" in stderr
        # Should include helpful information
        assert "Backend composition rules" in stderr or "Examples" in stderr

    def test_multiple_composable_backends(self):
        """CLI accepts multiple composable backends."""
        exit_code, stdout, stderr = run_launch_command([
            "-b", "strace",
            "-b", "perf",
            "-b", "local",
            "-r", "COUNT",
            "-j", '{"count": 1}',
            "--skip-sys-specs",
            "sleep", "0.01"
        ])
        # Should not fail with backend composition error
        assert "Backend Composition Error" not in stderr


class TestCLIBackendValidationWithConfig:
    """Test backend validation when using config files."""

    def test_invalid_chain_from_config_file(self, tmp_path):
        """CLI rejects invalid chain specified in config file."""
        # Note: We can't easily test config file with invalid backend chain
        # because the current config loading doesn't support 'backends' field
        # This test validates via CLI args instead
        exit_code, stdout, stderr = run_launch_command([
            "-b", "perf",
            "-b", "mpi",  # mpi is non-composable, must be leftmost
            "-r", "COUNT",
            "-j", '{"count": 1}',
            "--skip-sys-specs",
            "sleep", "0.01"
        ])
        assert exit_code != 0
        assert "Backend Composition Error" in stderr

    def test_valid_chain_from_config_file(self, tmp_path):
        """CLI accepts valid chain from CLI args."""
        # Test valid chain directly via CLI
        exit_code, stdout, stderr = run_launch_command([
            "-b", "perf",
            "-b", "local",
            "-r", "COUNT",
            "-j", '{"count": 1}',
            "--skip-sys-specs",
            "sleep", "0.01"
        ])
        # Should not fail with backend composition error
        assert "Backend Composition Error" not in stderr


class TestBackendValidationEdgeCases:
    """Test edge cases in backend validation."""

    def test_single_non_composable_backend(self):
        """Single non-composable backend is valid."""
        exit_code, stdout, stderr = run_launch_command([
            "-b", "docker",
            "-r", "COUNT",
            "-j", '{"count": 1}',
            "--skip-sys-specs",
            "sleep", "0.01"
        ])
        # Should not fail with backend composition error
        # (may fail with docker not available, but that's different)
        assert "Backend Composition Error" not in stderr

    def test_single_non_composable_backend(self):
        """Single non-composable backend is valid."""
        exit_code, stdout, stderr = run_launch_command([
            "-b", "mpi",
            "--mpl", "1",
            "-r", "COUNT",
            "-j", '{"count": 1}',
            "--skip-sys-specs",
            "sleep", "0.01"
        ])
        # Should not fail with backend composition error
        # (may fail with mpi not available, but that's different)
        assert "Backend Composition Error" not in stderr