#!/usr/bin/env python3
"""
Tests to verify composable backend functionality in launcher.py.

This test suite verifies that multiple backends can be composed together
and that they correctly process system specifications and metrics.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

import os
import unittest
try:
    from tests.command_test_case import CommandTestCase  # type: ignore
except:
    from command_test_case import CommandTestCase  # type: ignore


class ComposableBackendsTests(CommandTestCase):
    """Tests for composable backend functionality."""

    def test_python_mock_without_sysspec(self) -> None:
        """Test PythonMockLauncherWithoutSysSpec backend with and without config."""
        backends = ["PythonMockLauncherWithoutSysSpec"]
        self._verify_md_content(
            config=False,
            backends=backends,
            expect_sys_config=False,
            expect_warning = True
        )
        self._verify_md_content(
            config=True,
            backends=backends,
            expect_sys_config=True,
        )

    def test_python_mock_with_sysspec(self) -> None:
        """Test PythonMockLauncherWithSysSpec backend with and without config."""
        backends = ["PythonMockLauncherWithSysSpec"]
        self._verify_md_content(
            config=False,
            backends=backends,
            expect_sys_config=False,
            expect_warning = True
        )
        self._verify_md_content(
            config=True,
            backends=backends,
            expect_sys_config=True,
            expected_content=["Python mock sysspec:"]
        )

    def test_yaml_mock_without_sysspec(self) -> None:
        """Test YAMLMockLauncherWithoutSysSpec backend without system specifications."""
        backends = ["YAMLMockLauncherWithoutSysSpec"]
        self._verify_md_content(
            config=False,
            backends=backends,
            expect_sys_config=False,
            expect_warning=True
        )
        self._verify_md_content(
            config=True,
            backends=backends,
            expect_sys_config=True
        )

    def test_yaml_mock_with_sysspec(self) -> None:
        """Test YAMLMockLauncherWithSysSpec backend with system specifications."""
        backends = ["YAMLMockLauncherWithSysSpec"]
        self._verify_md_content(
            config=False,
            backends=backends,
            expect_sys_config=False,
            expect_warning=True
        )
        self._verify_md_content(
            config=True,
            backends=backends,
            expect_sys_config=True,
            expected_content=["YAML mock sysspec:"]
        )

    def test_python_mock_without_sysspec_and_yaml_mock_without_sysspec(self) -> None:
        """Test PythonMockLauncherWithoutSysSpec + YAMLMockLauncherWithoutSysSpec combinations."""
        backends = ["PythonMockLauncherWithoutSysSpec", "YAMLMockLauncherWithoutSysSpec"]
        self._verify_md_content(
            config=False,
            backends=backends,
            expect_sys_config=False,
            expect_warning=True
        )
        self._verify_md_content(
            config=True,
            backends=backends,
            expect_sys_config=True
        )

    def test_python_mock_with_sysspec_and_yaml_mock_without_sysspec(self) -> None:
        """Test PythonMockLauncherWithSysSpec + YAMLMockLauncherWithoutSysSpec combinations."""
        backends = ["PythonMockLauncherWithSysSpec", "YAMLMockLauncherWithoutSysSpec"]
        self._verify_md_content(
            config=False,
            backends=backends,
            expect_sys_config=False,
            expect_warning=True
        )
        self._verify_md_content(
            config=True,
            backends=backends,
            expect_sys_config=True,
            expected_content=["PythonMockLauncherWithSysSpec"]
        )

    def test_python_mock_without_sysspec_and_yaml_mock_with_sysspec(self) -> None:
        """Test PythonMockLauncherWithoutSysSpec + YAMLMockLauncherWithSysSpec combinations."""
        backends = ["PythonMockLauncherWithoutSysSpec", "YAMLMockLauncherWithSysSpec"]
        self._verify_md_content(
            config=False,
            backends=backends,
            expect_sys_config=False,
            expect_warning=True
        )
        self._verify_md_content(
            config=True,
            backends=backends,
            expect_sys_config=True,
            expected_content=["PythonMockLauncherWithoutSysSpec", "YAML mock sysspec:"]
        )

    def test_python_mock_with_sysspec_and_yaml_mock_with_sysspec(self) -> None:
        """Test PythonMockLauncherWithSysSpec + YAMLMockLauncherWithSysSpec combinations."""
        backends = ["PythonMockLauncherWithSysSpec", "YAMLMockLauncherWithSysSpec"]
        self._verify_md_content(
            config=False,
            backends=backends,
            expect_sys_config=False,
            expect_warning=True
        )
        self._verify_md_content(
            config=True,
            backends=backends,
            expect_sys_config=True,
            expected_content=["PythonMockLauncherWithSysSpec", "YAML mock sysspec:"]
        )

    def test_yaml_mock_without_sysspec_and_python_mock_without_sysspec(self) -> None:
        """Test YAMLMockLauncherWithoutSysSpec + PythonMockLauncherWithoutSysSpec combinations."""
        backends = ["YAMLMockLauncherWithoutSysSpec", "PythonMockLauncherWithoutSysSpec"]
        self._verify_md_content(
            config=False,
            backends=backends,
            expect_sys_config=False,
            expect_warning=True
        )
        self._verify_md_content(
            config=True,
            backends=backends,
            expect_sys_config=True,
            expected_content=["YAMLMockLauncherWithoutSysSpec"]
        )

    def test_yaml_mock_with_sysspec_and_python_mock_without_sysspec(self) -> None:
        """Test YAMLMockLauncherWithSysSpec + PythonMockLauncherWithoutSysSpec combinations."""
        backends = ["YAMLMockLauncherWithSysSpec", "PythonMockLauncherWithoutSysSpec"]
        self._verify_md_content(
            config=False,
            backends=backends,
            expect_sys_config=False,
            expect_warning=True
        )
        self._verify_md_content(
            config=True,
            backends=backends,
            expect_sys_config=True,
            expected_content=["YAMLMockLauncherWithSysSpec"]
        )

    def test_yaml_mock_without_sysspec_and_python_mock_with_sysspec(self) -> None:
        """Test YAMLMockLauncherWithoutSysSpec + PythonMockLauncherWithSysSpec combinations."""
        backends = ["YAMLMockLauncherWithoutSysSpec", "PythonMockLauncherWithSysSpec"]
        self._verify_md_content(
            config=False,
            backends=backends,
            expect_sys_config=False,
            expect_warning=True
        )
        self._verify_md_content(
            config=True,
            backends=backends,
            expect_sys_config=True,
            expected_content=["YAMLMockLauncherWithoutSysSpec", "Python mock sysspec:"]
        )

    def test_yaml_mock_with_sysspec_and_python_mock_with_sysspec(self) -> None:
        """Test YAMLMockLauncherWithSysSpec + PythonMockLauncherWithSysSpec combinations."""
        backends = ["YAMLMockLauncherWithSysSpec", "PythonMockLauncherWithSysSpec"]
        self._verify_md_content(
            config=False,
            backends=backends,
            expect_sys_config=False,
            expect_warning=True
        )
        self._verify_md_content(
            config=True,
            backends=backends,
            expect_sys_config=True,
            expected_content=["YAMLMockLauncherWithSysSpec", "Python mock sysspec:"]
        )


#####################################################################
if __name__ == "__main__":
    unittest.main()
