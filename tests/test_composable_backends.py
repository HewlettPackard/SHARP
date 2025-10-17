#!/usr/bin/env python3
"""
Tests to verify composable backend functionality in launcher.py.

This test suite verifies that multiple backends can be composed together
and that they correctly process system specifications and metrics.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

import os
import unittest
from typing import List, Optional
try:
    from tests.command_test_case import CommandTestCase  # type: ignore
except:
    from command_test_case import CommandTestCase  # type: ignore


class ComposableBackendsTests(CommandTestCase):
    """Tests for composable backend functionality."""

    # Mapping of backend names to their config files
    BACKEND_CONFIGS = {
        'perf': 'backends/perf.yaml',
        'mpi': 'backends/mpi.yaml',
        'ssh': 'backends/ssh.yaml',
        'YAMLMockLauncherWithSysSpec': 'tests/backends/yaml_mock_with_sysspec.yaml',
        'YAMLMockLauncherWithoutSysSpec': 'tests/backends/yaml_mock_without_sysspec.yaml',
    }

    def _get_config_files(self, backends: List[str]) -> List[str]:
        """Get list of config files needed for the given backends.

        Args:
            backends: List of backend names

        Returns:
            List of config file paths
        """
        # sys_spec.yaml is auto-loaded, only need backend-specific configs
        config_files = []
        for backend in backends:
            if backend in self.BACKEND_CONFIGS:
                config_files.append(self.BACKEND_CONFIGS[backend])
        return config_files

    def _build_command(self, backends: List[str], config_files: List[str]) -> str:
        """Build launcher command with backends and config files.

        Args:
            backends: List of backend names
            config_files: List of config file paths

        Returns:
            Command string
        """
        task_name = self.get_task_name()
        cmd_parts = [
            f'-d {self._runlogs}',
            f'-e {self._expname}',
            f'-t {task_name}',
        ]
        cmd_parts.extend(f'-f {config}' for config in config_files)
        cmd_parts.extend(f'-b {backend}' for backend in backends)
        cmd_parts.append(self._nope_fun)
        return ' '.join(cmd_parts)

    def _verify_markdown_output(self, expected_content: Optional[List[str]] = None) -> None:
        """Verify markdown output contains expected content.

        Args:
            expected_content: Optional list of strings expected in the markdown output
        """
        task_name = self.get_task_name()
        md_path = os.path.join(self._runlogs_path, self._expname, f"{task_name}.md")
        self.assertTrue(os.path.exists(md_path), f"Markdown file not found: {md_path}")

        with open(md_path, 'r') as f:
            content = f.read()

        # Always check for system configuration section
        self.assertIn("## System configuration", content,
                     "System configuration section not found in markdown output")

        # Check for additional expected content
        if expected_content:
            for expected in expected_content:
                self.assertIn(expected, content,
                            f"Expected content not found in markdown: {expected}")

    def _verify_backend_combination(self, backends: List[str], expected_content: Optional[List[str]] = None,
                                    expect_warning: bool = False) -> None:
        """Helper method to verify backend combinations work correctly.

        Args:
            backends: List of backend names to combine
            expected_content: Optional list of strings expected in the markdown output
            expect_warning: Whether to expect warnings in stderr (e.g., for perf backend)
        """
        # Build and run command
        config_files = self._get_config_files(backends)
        cmd = self._build_command(backends, config_files)
        stdout, stderr, returncode = self.run_launcher(cmd)

        # Verify execution results
        self.assert_command_success(stdout, returncode)
        if expect_warning:
            self.assertNotEqual(stderr, "", "Expected warnings in stderr")
        else:
            self.assertEqual(stderr, "", "Expected empty stderr")

        # Verify markdown output
        self._verify_markdown_output(expected_content)

    def test_yaml_mock_without_sysspec(self) -> None:
        """Test YAMLMockLauncherWithoutSysSpec backend (no sys_spec overrides)."""
        backends = ["YAMLMockLauncherWithoutSysSpec"]
        # sys_spec.yaml is auto-loaded, this backend doesn't override sys_spec commands
        self._verify_md_content(backends=backends)

    def test_yaml_mock_with_sysspec(self) -> None:
        """Test YAMLMockLauncherWithSysSpec backend with sys_spec overrides."""
        backends = ["YAMLMockLauncherWithSysSpec"]
        # sys_spec.yaml is auto-loaded, this backend overrides some sys_spec commands
        self._verify_md_content(
            backends=backends,
            expected_content=["YAML mock sysspec:"]
        )

    # Tests for single real backends
    def test_local_backend_only(self):
        """Test single local backend with system specifications."""
        self._verify_backend_combination(['local'])

    def test_perf_backend_only(self):
        """Test single perf backend with system specifications."""
        self._verify_backend_combination(['perf'], expect_warning=True)

    def test_ssh_backend_only(self):
        """Test single ssh backend with system specifications."""
        self._verify_backend_combination(['ssh'], expect_warning=True)

    # Tests for dual backend combinations
    def test_local_and_perf(self):
        """Test local + perf backend combination."""
        self._verify_backend_combination(['local', 'perf'], expect_warning=True)

    def test_perf_and_local(self):
        """Test perf + local backend combination (reversed order)."""
        self._verify_backend_combination(['perf', 'local'], expect_warning=True)

    def test_local_and_ssh(self):
        """Test local + ssh backend combination."""
        self._verify_backend_combination(['local', 'ssh'], expect_warning=True)

    def test_ssh_and_perf(self):
        """Test ssh + perf backend combination."""
        self._verify_backend_combination(['ssh', 'perf'], expect_warning=True)

    def test_ssh_and_local(self):
        """Test ssh + local backend combination (reversed order)."""
        self._verify_backend_combination(['ssh', 'local'], expect_warning=True)

    # Test for MPI + perf - critical to verify each rank gets its own perf stats
    def test_mpi_and_perf(self):
        """Test MPI + perf backend combination to verify each rank gets its own perf stats.

        This is a critical test to ensure that when using MPI with perf, each MPI rank
        collects and reports its own performance statistics independently.
        """
        # Skip in fast mode (this test is slow)
        if os.environ.get('SKIP_SLOW_TESTS'):
            self.skipTest("Skipping slow test in fast mode")

        # Check if mpirun is available
        import shutil
        if shutil.which("mpirun") is None:
            self.skipTest("mpirun not found - skipping MPI test")

        # Run with 2 MPI ranks, each should get perf stats
        self._verify_backend_combination(['mpi', 'perf'],
                                        expected_content=['Rank:'],
                                        expect_warning=True)

    # Tests for mixing mock and real backends
    def test_yaml_mock_and_local(self):
        """Test YAMLMockLauncher + local backend combination."""
        self._verify_backend_combination(['YAMLMockLauncherWithSysSpec', 'local'])

    def test_local_and_yaml_mock(self):
        """Test local + YAMLMockLauncher backend combination (reversed order)."""
        self._verify_backend_combination(['local', 'YAMLMockLauncherWithSysSpec'])

    def test_perf_and_yaml_mock(self):
        """Test perf + YAMLMockLauncher backend combination."""
        self._verify_backend_combination(['perf', 'YAMLMockLauncherWithSysSpec'], expect_warning=True)

    # Test for triple backend combination
    def test_local_perf_and_yaml_mock(self):
        """Test three-backend combination: local + perf + YAMLMockLauncher."""
        self._verify_backend_combination(['local', 'perf', 'YAMLMockLauncherWithSysSpec'], expect_warning=True)


#####################################################################
if __name__ == "__main__":
    unittest.main()
