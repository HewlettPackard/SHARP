#!/usr/bin/env python3
"""
Tests to verify composable backend functionality in launcher.py.

This test suite verifies that multiple backends can be composed together
and that they correctly process system specifications and metrics.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
from typing import List, Optional
from pathlib import Path


# Mapping of backend names to their config files
# Use mock backends for speed - they execute instantly without real perf/ssh/mpi overhead
BACKEND_CONFIGS = {
    'mock_perf': 'tests/backends/mock_perf.yaml',
    'mock_mpi': 'tests/backends/mock_mpi.yaml',
    'mock_ssh': 'tests/backends/mock_ssh.yaml',
    'YAMLMockLauncherWithSysSpec': 'tests/backends/yaml_mock_with_sysspec.yaml',
    'YAMLMockLauncherWithoutSysSpec': 'tests/backends/yaml_mock_without_sysspec.yaml',
}


@pytest.fixture
def helper(launcher_helper, request):
    """Configure launcher helper for composable backend tests."""
    # Use minimal sys_spec subset for fast testing (no sensors, GPU, or network checks)
    # Only include fast commands that complete in <10ms each
    launcher_helper._minimal_sys_spec = (
        '{"sys_spec_commands": {'
        '"cpu": {"processor_count": "nproc", "architecture": "uname -m"}, '
        '"memory": {"total_memory_kb": "awk \\"/MemTotal/ {print \\\\$2}\\" /proc/meminfo"}, '
        '"kernel": {"version": "uname -r"}, '
        '"system": {"hostname": "hostname"}'
        '}}'
    )
    launcher_helper.task_name = request.node.name.replace("test_", "")
    yield launcher_helper



def _get_config_files(backends: List[str]) -> List[str]:
    """Get list of config files needed for the given backends.

    Args:
        backends: List of backend names

    Returns:
        List of config file paths
    """
    # sys_spec.yaml is auto-loaded, only need backend-specific configs
    config_files = []
    for backend in backends:
        if backend in BACKEND_CONFIGS:
            config_files.append(BACKEND_CONFIGS[backend])
    return config_files


def _build_command(helper, backends: List[str], config_files: List[str]) -> str:
    """Build launcher command with backends and config files.

    Args:
        helper: Launcher helper fixture
        backends: List of backend names
        config_files: List of config file paths

    Returns:
        Command string
    """
    cmd_parts = [
        f'-d {helper.runlogs_dir}',
        f'-e {helper.experiment_name}',
        f'-t {helper.task_name}',
        f"-j '{helper._minimal_sys_spec}'",  # Use minimal sys_spec for speed
    ]
    cmd_parts.extend(f'-f {config}' for config in config_files)
    cmd_parts.extend(f'-b {backend}' for backend in backends)
    cmd_parts.append('nope')
    return ' '.join(cmd_parts)


def _verify_markdown_output(helper, expected_content: Optional[List[str]] = None) -> None:
    """Verify markdown output contains expected content.

    Args:
        helper: Launcher helper fixture
        expected_content: Optional list of strings expected in the markdown output
    """
    md_path = helper.runlogs_path / helper.experiment_name / f"{helper.task_name}.md"
    assert md_path.exists(), f"Markdown file not found: {md_path}"

    with open(md_path, 'r') as f:
        content = f.read()

    # Always check for system configuration section
    assert "## Initial system configuration" in content, \
        "System configuration section not found in markdown output"

    # Check for additional expected content
    if expected_content:
        for expected in expected_content:
            assert expected in content, \
                f"Expected content not found in markdown: {expected}"


def _verify_backend_combination(helper, backends: List[str],
                                expected_content: Optional[List[str]] = None,
                                expect_warning: bool = False) -> None:
    """Helper method to verify backend combinations work correctly.

    Args:
        helper: Launcher helper fixture
        backends: List of backend names to combine
        expected_content: Optional list of strings expected in the markdown output
        expect_warning: Whether to expect warnings in stderr (e.g., for perf backend)
    """
    # Build and run command
    config_files = _get_config_files(backends)
    cmd = _build_command(helper, backends, config_files)
    stdout, stderr, returncode = helper.run_launcher(cmd)

    # Verify execution results
    assert returncode == 0, f"Expected zero exit code, got {returncode}\nstdout: {stdout}\nstderr: {stderr}"
    if expect_warning:
        assert stderr != "", "Expected warnings in stderr"
    else:
        assert stderr == "", f"Expected empty stderr, got: {stderr}"

    # Verify markdown output
    _verify_markdown_output(helper, expected_content)


# ========== Test Functions ==========

def test_yaml_mock_without_sysspec(helper) -> None:
    """Test YAMLMockLauncherWithoutSysSpec backend (no sys_spec overrides)."""
    backends = ["YAMLMockLauncherWithoutSysSpec"]
    # sys_spec.yaml is auto-loaded, this backend doesn't override sys_spec commands
    _verify_backend_combination(helper, backends=backends)


def test_yaml_mock_with_sysspec(helper) -> None:
    """Test YAMLMockLauncherWithSysSpec backend with sys_spec overrides."""
    backends = ["YAMLMockLauncherWithSysSpec"]
    # sys_spec.yaml is auto-loaded, this backend overrides some sys_spec commands
    _verify_backend_combination(
        helper,
        backends=backends,
        expected_content=["YAML mock sysspec:"]
    )


# Tests for single mock backends
def test_local_backend_only(helper):
    """Test single local backend with system specifications."""
    _verify_backend_combination(helper, ['local'])


def test_perf_backend_only(helper):
    """Test single mock_perf backend with system specifications."""
    _verify_backend_combination(helper, ['mock_perf'])


def test_ssh_backend_only(helper):
    """Test single mock_ssh backend with system specifications."""
    _verify_backend_combination(helper, ['mock_ssh'])


# Tests for dual backend combinations
def test_local_and_perf(helper):
    """Test local + mock_perf backend combination."""
    _verify_backend_combination(helper, ['local', 'mock_perf'])


def test_perf_and_local(helper):
    """Test mock_perf + local backend combination (reversed order)."""
    _verify_backend_combination(helper, ['mock_perf', 'local'])


def test_local_and_ssh(helper):
    """Test local + mock_ssh backend combination."""
    _verify_backend_combination(helper, ['local', 'mock_ssh'])


def test_ssh_and_perf(helper):
    """Test mock_ssh + mock_perf backend combination."""
    _verify_backend_combination(helper, ['mock_ssh', 'mock_perf'])


def test_ssh_and_local(helper):
    """Test mock_ssh + local backend combination (reversed order)."""
    _verify_backend_combination(helper, ['mock_ssh', 'local'])


# Test for MPI + perf - critical to verify each rank gets its own perf stats
def test_mpi_and_perf(helper):
    """Test mock_mpi + mock_perf backend combination to verify each rank gets its own perf stats.

    This is a critical test to ensure that when using MPI with perf, each MPI rank
    collects and reports its own performance statistics independently.
    """
    # Use mock backends for speed
    _verify_backend_combination(helper, ['mock_mpi', 'mock_perf'])


# Tests for mixing mock and real backends
def test_yaml_mock_and_local(helper):
    """Test YAMLMockLauncher + local backend combination."""
    _verify_backend_combination(helper, ['YAMLMockLauncherWithSysSpec', 'local'])


def test_local_and_yaml_mock(helper):
    """Test local + YAMLMockLauncher backend combination (reversed order)."""
    _verify_backend_combination(helper, ['local', 'YAMLMockLauncherWithSysSpec'])


def test_perf_and_yaml_mock(helper):
    """Test mock_perf + YAMLMockLauncher backend combination."""
    _verify_backend_combination(helper, ['mock_perf', 'YAMLMockLauncherWithSysSpec'])


# Test for triple backend combination
def test_local_perf_and_yaml_mock(helper):
    """Test three-backend combination: local + mock_perf + YAMLMockLauncher."""
    _verify_backend_combination(helper, ['local', 'mock_perf', 'YAMLMockLauncherWithSysSpec'])

