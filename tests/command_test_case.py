#!/usr/bin/env python3
"""
Base test case class for command execution testing.

This module provides a base test case class with helper methods for executing
commands and verifying their results, including success/failure assertions and
output validation.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

import csv
import os
import shutil
import subprocess
from typing import List, Optional, Tuple
import unittest


class CommandTestCase(unittest.TestCase):
    """Base test case class to handle command execution."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        super().setUp()
        self._runlogs = "runlogs/tests"  # Default directory for test logs
        self._expname = "tests"      # Default experiment name for tests
        self._nope_fun = "nope"      # Default function for the tests
        self._skip_sys_specs = False  # By default, collect sys_specs (tests can override)

        # Get absolute paths based on test file location
        mydir, _ = os.path.split(os.path.abspath(__file__))
        self.__project_root, _ = os.path.split(mydir)
        self._launcher_path = os.path.join(self.__project_root, "launcher", "launch.py")
        self._runlogs_path = os.path.join(self.__project_root, self._runlogs)
        self._fns_dir = os.path.join(self.__project_root, "fns")

    def get_task_name(self) -> str:
        """Generate unique task name from current test method name.

        Returns:
            Task name derived from test method (e.g., 'test_foo' -> 'test_foo')
        """
        # Get the current test method name
        test_method = self._testMethodName
        return test_method

    def tearDown(self) -> None:
        """Clean up after each test."""
        super().tearDown()
        if os.path.exists(self._runlogs_path):
            shutil.rmtree(self._runlogs_path)

    def run_command(self, command: str) -> Tuple[str, str, int]:
        """Run a command and return output, error and exit status."""
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
        )
        stdout, stderr = process.communicate()
        return stdout.decode(), stderr.decode(), process.returncode

    def run_launcher(self, args: str) -> Tuple[str, str, int]:
        """Run the launcher with given arguments and return results.

        Args:
            args: String containing launcher arguments
        """
        # Prepend --skip-sys-specs if enabled (for faster testing)
        if self._skip_sys_specs and "--skip-sys-specs" not in args:
            args = f"--skip-sys-specs {args}"
        command = f"{self._launcher_path} {args}"
        return self.run_command(command)

    def assert_command_success(self, stdout: str, returncode: int, expect_output: bool = False) -> None:
        """Assert that a command executed successfully.

        Args:
            stdout: Standard output from command
            returncode: Return code from command
            expect_output: If True, verify stdout is not empty
        """
        self.assertEqual(returncode, 0, "Expected zero exit code")
        #self.assertEqual(stderr, "", "Expected empty stderr") #Assert this individually case by case
        if expect_output:
            self.assertNotEqual(stdout, "", "Expected output in stdout")

    def assert_command_failure(self, stdout: str, returncode: int) -> None:
        """Assert that a command failed as expected.

        Args:
            stdout: Standard output from command
            returncode: Return code from command
        """
        self.assertNotEqual(returncode, 0, "Expected non-zero exit code")

    def read_csv_column(self, experiment_name: str, column_name: str, line_number: int = 0) -> str:
        """Read a specific column from a CSV results file.

        Args:
            experiment_name: Name of the experiment (used in CSV filename)
            column_name: Name of the column to read
            line_number: Which line to read (0-based, excluding header). Default is first line.

        Returns:
            The value from the specified column and line as a string

        Raises:
            FileNotFoundError: If the CSV file doesn't exist
            KeyError: If the column doesn't exist in the CSV
            IndexError: If line_number is out of range
        """
        csv_path = os.path.join(self._runlogs_path, f"{experiment_name}.csv")
        with open(csv_path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
            return rows[line_number][column_name]

    def count_csv_rows(self, experiment_name: str) -> int:
        """Count the number of data rows in a CSV file (excluding header).

        Args:
            experiment_name: Path to CSV file relative to runlogs directory

        Returns:
            Number of data rows in the CSV

        Raises:
            FileNotFoundError: If the CSV file doesn't exist
        """
        csv_path = os.path.join(self._runlogs_path, f"{experiment_name}.csv")
        with open(csv_path, newline='') as csvfile:
            return sum(1 for _ in csv.DictReader(csvfile))

    def _verify_md_content(self, backends: List[str], expected_content: Optional[List[str]] = None) -> None:
        """Helper method to verify markdown content for different test scenarios.

        Args:
            backends: List of backends to test
            expected_content: Optional list of strings expected in the content

        Note:
            sys_spec.yaml is always auto-loaded, so system configuration is always present.
        """
        try:
            # Construct command
            cmd = f'-d {self._runlogs} -e {self._expname}'

            # Add mock launcher backend configs
            for backend in backends:
                if backend == 'YAMLMockLauncherWithSysSpec':
                    cmd += ' -f tests/backends/yaml_mock_with_sysspec.yaml'
                elif backend == 'YAMLMockLauncherWithoutSysSpec':
                    cmd += ' -f tests/backends/yaml_mock_without_sysspec.yaml'

            for backend in backends:
                cmd += f' -b {backend}'
            cmd += f' {self._nope_fun}'

            # Run command and verify results
            stdout, stderr, returncode = self.run_launcher(cmd)
            self.assert_command_success(stdout, returncode)
            self.assertEqual(stderr, "", "Expected empty stderr")

            # Verify markdown content
            md_path = os.path.join(self._runlogs_path, self._expname, f"{self._nope_fun}.md")
            with open(md_path) as f:
                content = f.read()
                # sys_spec.yaml is always auto-loaded, so system config is always present
                self.assertIn("## System configuration", content, "Expected system specifications")

                if expected_content:
                    for expected in expected_content:
                        self.assertIn(expected, content, f"Expected '{expected}' in content")
        finally:
            # Clean up after verification
            self.tearDown()
