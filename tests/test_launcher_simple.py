#!/usr/bin/env python3
"""
Tests to ensure launcher.py handles command-line operations correctly.

This test suite verifies that the launcher script processes command-line inputs
appropriately, including handling missing arguments, displaying help messages,
executing basic commands, and managing error cases.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

import unittest
import os
try:
    from tests.command_test_case import CommandTestCase  # type: ignore
except:
    from command_test_case import CommandTestCase  # type: ignore


class SimpleLauncherTests(CommandTestCase):
    """Tests to ensure launcher.py handles command-line operations correctly."""

    def setUp(self) -> None:
        """Set up test with sys_specs disabled for faster testing."""
        super().setUp()
        self._skip_sys_specs = True  # Skip sys_specs for faster simple tests

    def test_launcher_no_arguments(self) -> None:
        """Test launcher.py without arguments, expecting an error."""
        stdout, stderr, returncode = self.run_launcher("")
        self.assert_command_failure(stdout, returncode)
        self.assertNotEqual(stderr, "", "Expected runtime error of missing argument")

    def test_launcher_help_message(self) -> None:
        """Test launcher.py with -h, expecting a help message."""
        stdout, stderr, returncode = self.run_launcher("-h")
        self.assert_command_success(stdout, returncode, expect_output=True)
        self.assertEqual(stderr, "", "Expected empty stderr")

    def test_launcher_silent_run_nope(self) -> None:
        """Test silent run of nope, check for output files."""
        task_name = self.get_task_name()
        stdout, stderr, returncode = self.run_launcher(f"-d {self._runlogs} -e {self._expname} -t {task_name} {self._nope_fun}")
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")
        self.assertTrue(os.path.isfile(os.path.join(self._runlogs_path, self._expname, f"{task_name}.csv")),
                        "Expected CSV output file to exist")
        self.assertTrue(os.path.isfile(os.path.join(self._runlogs_path, self._expname, f"{task_name}.md")),
                        "Expected MD output file to exist")

    def test_launcher_verbose_run_nope(self) -> None:
        """Test verbose run of nope, expecting output and log files."""
        task_name = self.get_task_name()
        stdout, stderr, returncode = self.run_launcher(f"-d {self._runlogs} -e {self._expname} -t {task_name} -v {self._nope_fun}")
        self.assert_command_success(stdout, returncode, expect_output=True)
        self.assertEqual(stderr, "", "Expected empty stderr")
        self.assertTrue(os.path.isfile(os.path.join(self._runlogs_path, self._expname, f"{task_name}.csv")),
                        "Expected CSV file to exist in tests directory")
        self.assertTrue(os.path.isfile(os.path.join(self._runlogs_path, self._expname, f"{task_name}.md")),
                        "Expected MD output file to exist")

    def test_non_existent_command(self) -> None:
        """Test execution with a non-existent command, expecting an error."""
        task_name = self.get_task_name()
        stdout, stderr, returncode = self.run_launcher(f"-d {self._runlogs} -e {self._expname} -t {task_name} -v foo")
        self.assert_command_failure(stdout, returncode)
        self.assertNotEqual(stderr, "", "Expected runtime error for foo indicating no such file or directory")

    def test_sleep_command(self) -> None:
        """Test execution with the sleep command, checking exit code and inner time."""
        task_name = self.get_task_name()
        stdout, stderr, returncode = self.run_launcher(f"-d {self._runlogs} -f backends/inner_time.yaml -e {self._expname} -t {task_name} -v sleep 1")

        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")

        # Read inner time from CSV
        inner_time = float(self.read_csv_column(f"{self._expname}/{task_name}", "inner_time", 0))

        self.assertGreaterEqual(inner_time, 1.0, "Inner time should be at least 1 second")
        self.assertLess(inner_time, 1.1, "Inner time should be less than 1.1 seconds")


    def test_auto_metrics(self) -> None:
        """Test generation of metrics from an 'auto' directive."""
        task_name = self.get_task_name()
        # First create the source experiment
        self.run_launcher(
            f'-d {self._runlogs} -e {self._expname} -t {task_name} -f backends/strace.yaml -b strace inc 10000')

        # Even nope should be calling these system calls:
        expected_syscalls = ['execve', 'read', 'write', 'mmap']
        for scall in expected_syscalls:
            time = float(self.read_csv_column(f"{self._expname}/{task_name}", scall))
            self.assertTrue(time >= 0,
                  f"Any program should call {scall}.")

    def test_arg_repetition(self) -> None:
        """Test two local backends to ensure the argument doesn't get repeated."""
        task_name = self.get_task_name()
        stdout, stderr, returncode = self.run_launcher(f"-b local -b local -d {self._runlogs} -e {self._expname} -t {task_name} -v echo test")
        self.assertNotIn("test test", stdout, "Expected single print of the argument 'test'")

#####################################################################
if __name__ == "__main__":
    unittest.main()
