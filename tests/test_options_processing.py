#!/usr/bin/env python3
"""
Tests to verify command-line options processing in launcher.py.

This test suite verifies that the launcher correctly processes various combinations
of command-line options, configuration files, and JSON overrides.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

import json
import os
import unittest
import yaml  # type: ignore
try:
    from tests.command_test_case import CommandTestCase  # type: ignore
except:
    from command_test_case import CommandTestCase  # type: ignore


class OptionsProcessingTests(CommandTestCase):
    """Tests for command-line options processing in launcher.py."""

    def setUp(self) -> None:
        """Set up test fixtures, including temporary config files."""
        super().setUp()
        # Create temporary config files
        self.config_dir = os.path.join(self._runlogs_path, self._expname, "configs")
        os.makedirs(self.config_dir, exist_ok=True)

        # Create task3.json
        self.task3_path = os.path.join(self.config_dir, "task3.json")
        with open(self.task3_path, "w") as f:
            json.dump({"task": "task3"}, f)

        # Create task4.json
        self.task4_path = os.path.join(self.config_dir, "task4.json")
        with open(self.task4_path, "w") as f:
            json.dump({"task": "task4"}, f)

    def test_no_default_config(self) -> None:
        """Test launcher without default_config.yaml."""
        stdout, stderr, returncode = self.run_launcher(
            f'-d {self._runlogs} -e {self._expname} -j \'{{"task": "task1"}}\' -f {self.task3_path} {self._nope_fun}')
        self.assert_command_success(stdout, returncode)
        self.assertNotEqual(stderr, "", "Expected stderr to have warning regarding no system specifications.")

        # Verify md file exists and doesn't contain sys_spec_commands
        md_path = os.path.join(self._runlogs_path, self._expname, "task1.md")
        self.assertTrue(os.path.exists(md_path), "Expected MD file to exist")
        with open(md_path) as f:
            content = f.read()
            self.assertNotIn("sys_spec_commands", content,
                           "sys_spec_commands should not be present in configuration")

    def test_default_config(self) -> None:
        """Test launcher with default configuration."""
        stdout, stderr, returncode = self.run_launcher(f"-d {self._runlogs} -e {self._expname} {self._nope_fun}")
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")

        # Verify md file contents
        md_path = os.path.join(self._runlogs_path, self._expname, f"{self._nope_fun}.md")
        self.assertTrue(os.path.exists(md_path), "Expected MD file to exist")
        with open(md_path) as f:
            content = f.read()
            self.assertIn('"copies": 1', content, "Expected copies:1 in configuration")
            self.assertIn('"repeats": "1"', content, "Expected repeats:1 in configuration")
            self.assertIn(f'"experiment": "{self._expname}"', content,
                         f"Expected experiment:{self._expname} in configuration")
            self.assertIn('"timeout": 3600', content, "Expected timeout:3600 in configuration")
            self.assertIn('"backends": [\n    "local"\n  ]', content,
                         "Expected local backend in configuration")
            self.assertIn('"mode": "w"', content, "Expected write mode in configuration")
            self.assertIn('"start": "normal"', content, "Expected normal start in configuration")
            self.assertIn('"verbose": false', content, "Expected verbose:false in configuration")

    def test_json_override(self) -> None:
        """Test JSON override of task name."""
        stdout, stderr, returncode = self.run_launcher(
            f'-d {self._runlogs} -e {self._expname} -j \'{{"task": "task1"}}\' {self._nope_fun}')
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")
        self.assertTrue(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task1.csv")),
                       "Expected task1.csv file in experiment directory")

    def test_task_flag_override(self) -> None:
        """Test -t flag overriding JSON task name."""
        stdout, stderr, returncode = self.run_launcher(
            f'-d {self._runlogs} -e {self._expname} -t task2 -j \'{{"task": "task1"}}\' {self._nope_fun}')
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")
        self.assertTrue(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task2.csv")),
                       "Expected task2.csv file in experiment directory")

    def test_task_flag_overrides_all(self) -> None:
        """Test that -t flag overrides both JSON and config file task names."""
        cmd = (f'-d {self._runlogs} -e {self._expname} -t task2 -j \'{{"task": "task1"}}\' '
               f'-f launcher/default_config.yaml -f {self.task3_path} {self._nope_fun}')
        stdout, stderr, returncode = self.run_launcher(cmd)
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")

        # Verify we're writing to task2.* files
        self.assertTrue(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task2.csv")),
                       "Expected task2.csv file in experiment directory")
        self.assertFalse(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task3.csv")),
                        "task3.csv file should not exist")
        self.assertFalse(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task1.csv")),
                        "task1.csv file should not exist")

    def test_json_overrides_config_file(self) -> None:
        """Test that JSON overrides config file task name."""
        # Create config with task3
        with open(self.task3_path, "w") as f:
            json.dump({"task": "task3"}, f)

        # Run with JSON override (should override config file)
        cmd = f'-d {self._runlogs} -e {self._expname} -j \'{{"task": "task1"}}\' -f launcher/default_config.yaml -f {self.task3_path} {self._nope_fun}'
        stdout, stderr, returncode = self.run_launcher(cmd)
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")
        # Verify we're writing to task1.* files
        self.assertTrue(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task1.csv")),
                        "Expected task1.csv file in experiment directory")
        self.assertFalse(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task3.csv")),
                         "task3.csv file should not exist in experiment directory")

    def test_config_file_task_override(self) -> None:
        """Test that config file can override default task name."""
        stdout, stderr, returncode = self.run_launcher(f'-d {self._runlogs} -e {self._expname} -f launcher/default_config.yaml -f {self.task3_path} {self._nope_fun}')
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")
        # Verify we're writing to task3.* files
        self.assertTrue(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task3.csv")),
                        "Expected task3.csv file in experiment directory")
        self.assertFalse(os.path.exists(os.path.join(self._runlogs_path, self._expname, "{self._nope_fun}.csv")),
                         f"Expected {self._nope_fun}.csv file should not exist in experiment directory")

    def test_first_config_file_precedence(self) -> None:
        """Test that first config file takes precedence."""
        stdout, stderr, returncode = self.run_launcher(f'-d {self._runlogs} -e {self._expname} -f launcher/default_config.yaml -f {self.task4_path} -f {self.task3_path} {self._nope_fun}')
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")

        # Verify we're writing to task3.* files (second config doesn't override)
        self.assertTrue(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task3.csv")),
                        "Expected task3.csv file in experiment directory")
        self.assertFalse(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task4.csv")),
                         "task4.csv file should not exist in experiment directory")

    def test_last_config_file_precedence(self) -> None:
        """Test that last config file takes precedence."""
        stdout, stderr, returncode = self.run_launcher(f'-d {self._runlogs} -e {self._expname} -f launcher/default_config.yaml -f {self.task3_path} -f {self.task4_path} {self._nope_fun}')
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")

        # Verify we're writing to task4.* files (last config overrides)
        self.assertTrue(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task4.csv")),
                        "Expected task4.csv file in experiment directory")
        self.assertFalse(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task3.csv")),
                         "task3.csv file should not exist in experiment directory")

    def test_append_mode(self) -> None:
        """Test append mode with multiple config files."""
        # Update task3.json to include append mode
        with open(self.task3_path, "w") as f:
            json.dump({"task": "task3", "mode": "a"}, f)

        # Run command twice
        cmd = f'-d {self._runlogs} -e {self._expname} -f launcher/default_config.yaml -f {self.task3_path} -f {self.task4_path} {self._nope_fun}'
        self.run_launcher(cmd)  # First run
        stdout, stderr, returncode = self.run_launcher(cmd)  # Second run
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")

        # Verify task4.csv has two observations
        self.assertEqual(self.count_csv_rows(f"{self._expname}/task4"), 2, "Expected two observations in CSV")

    def test_warm_start_with_multiple_configs(self) -> None:
        """Test warm start with multiple config files."""
        # First run with append mode to get initial observations
        with open(self.task3_path, "w") as f:
            json.dump({"task": "task3", "mode": "w"}, f)
        with open(self.task4_path, "w") as f:
            json.dump({"task": "task4", "mode": "a"}, f)

        cmd = f'-d {self._runlogs} -e {self._expname} -f launcher/default_config.yaml -f {self.task3_path} -f {self.task4_path} {self._nope_fun}'
        self.run_launcher(cmd)  # First run
        self.run_launcher(cmd)  # Second run

        # Now update task3.json to include warm start
        with open(self.task3_path, "w") as f:
            json.dump({"task": "task3", "start": "warm", "mode": "a"}, f)

        # Run final command that should add warm start observation
        stdout, stderr, returncode = self.run_launcher(cmd)
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")

        # Verify task4.csv has three observations with last being warm
        self.assertEqual(self.count_csv_rows(f"{self._expname}/task4"), 3, "Expected three observations in CSV")
        self.assertEqual(self.read_csv_column(f"{self._expname}/task4", "start", 2), "warm")

        # Verify task4.md still shows normal start
        md_path = os.path.join(self._runlogs_path, self._expname, "task4.md")
        with open(md_path) as f:
            content = f.read()
            self.assertIn('"start": "normal"', content)

    def test_single_config_warm_start(self) -> None:
        """Test warm start with single config file."""
        with open(self.task4_path, "w") as f:
            json.dump({"task": "task4", "start": "warm"}, f)

        # Run with just task4.json
        stdout, stderr, returncode = self.run_launcher(f'-d {self._runlogs} -e {self._expname} -f launcher/default_config.yaml -f {self.task4_path} {self._nope_fun}')
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")

        # Verify task4.csv has one warm observation
        self.assertEqual(self.count_csv_rows(f"{self._expname}/task4"), 1, "Expected one observation in CSV")
        self.assertEqual(self.read_csv_column(f"{self._expname}/task4", "start", 0), "warm")

        # Verify task4.md shows warm start
        md_path = os.path.join(self._runlogs_path, self._expname, "task4.md")
        with open(md_path) as f:
            content = f.read()
            self.assertIn('"start": "warm"', content, "Expected warm start in MD file")

    def test_repro_basic(self) -> None:
        """Test basic reproduction of experiments."""
        with open(self.task4_path, "w") as f:
            json.dump({"task": "task4", "start": "warm"}, f)
        # First run to create md file
        self.run_launcher(f'-d {self._runlogs} -e {self._expname} -f launcher/default_config.yaml -f {self.task4_path} {self._nope_fun}')

        # Move md file to config dir and remove csv
        orig_md_path = os.path.join(self._runlogs_path, self._expname, "task4.md")
        new_md_path = os.path.join(self.config_dir, "task4.md")
        os.rename(orig_md_path, new_md_path)
        os.remove(os.path.join(self._runlogs_path, self._expname, "task4.csv"))

        # Run reproduction using md from config dir
        stdout, stderr, returncode = self.run_launcher(f'-d {self._runlogs} -e {self._expname} --repro {new_md_path}')
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")

        # Verify task4.csv has one warm observation
        csv_path = os.path.join(self._runlogs_path, self._expname, "task4.csv")
        with open(csv_path) as f:
            lines = list(f)
            self.assertEqual(len(lines) - 1, 1, "Expected one observation in CSV")
            self.assertEqual(self.read_csv_column(f"{self._expname}/task4", "start", 0), "warm")

    def test_repro_with_task_override(self) -> None:
        """Test reproduction with task name override."""
        with open(self.task4_path, "w") as f:
            json.dump({"task": "task4", "start": "warm"}, f)
        # First run to create md file
        self.run_launcher(f'-d {self._runlogs} -e {self._expname} -f launcher/default_config.yaml -f {self.task4_path} {self._nope_fun}')

        # Run reproduction with task override
        md_path = os.path.join(self._runlogs_path, self._expname, "task4.md")
        stdout, stderr, returncode = self.run_launcher(f'-d {self._runlogs} -e {self._expname} --repro {md_path} -t task5')
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")
        # Verify task5.* files exist with same experiment
        self.assertTrue(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task5.csv")),
                        "Expected task5.csv file in experiment directory")
        self.assertTrue(os.path.exists(os.path.join(self._runlogs_path, self._expname, "task5.md")),
                        "Expected task5.md file in experiment directory")

        # Verify task5.csv has one warm observation
        self.assertEqual(self.count_csv_rows(f"{self._expname}/task5"), 1, "Expected one observation in CSV")
        self.assertEqual(self.read_csv_column(f"{self._expname}/task5", "start", 0), "warm")

    def test_time_backend(self) -> None:
        """Test time backend metrics."""
        stdout, stderr, returncode = self.run_launcher(
            f'-d {self._runlogs} -e {self._expname} -f launcher/default_config.yaml -f backends/bintime.yaml -b time {self._nope_fun}')
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")

        # Verify max_rss in CSV
        self.assertNotEqual(self.read_csv_column(f"{self._expname}/{self._nope_fun}", "max_rss", 0), "",
                          "max_rss metric should not be empty")

        # Verify max_rss in MD
        md_path = os.path.join(self._runlogs_path, self._expname, f"{self._nope_fun}.md")
        with open(md_path) as f:
            content = f.read()
            self.assertIn("max_rss", content, "Expected max_rss metric in MD file")

    def test_repro_task_override(self) -> None:
        """Test reproduction with task override."""
        # First create the source experiment
        self.run_launcher(
            f'-d {self._runlogs} -e {self._expname} -f launcher/default_config.yaml -f backends/bintime.yaml -b time {self._nope_fun}')

        # Run reproduction with task override
        md_path = os.path.join(self._runlogs_path, self._expname, f"{self._nope_fun}.md")
        stdout, stderr, returncode = self.run_launcher(
            f'-d {self._runlogs} -e {self._expname} --repro {md_path} -t task6')
        self.assert_command_success(stdout, returncode)
        self.assertEqual(stderr, "", "Expected empty stderr")

        # Verify task6.* files exist with max_rss metric
        self.assertNotEqual(self.read_csv_column(f"{self._expname}/task6", "max_rss", 0), "",
                          "max_rss metric should not be empty")

    def test_repro_with_backend_override(self) -> None:
        """Test reproduction with backend override."""
        # First create the source experiment
        self.run_launcher(
            f'-d {self._runlogs} -e {self._expname} -f launcher/default_config.yaml -f backends/bintime.yaml -b time {self._nope_fun}')

        # Run reproduction with uname backend
        md_path = os.path.join(self._runlogs_path, self._expname, f"{self._nope_fun}.md")
        stdout, stderr, returncode = self.run_launcher(
            f'-d {self._runlogs} -e {self._expname} --repro {md_path} -f launcher/default_config.yaml -f backends/uname.yaml -b uname -t task6')
        self.assert_command_success(stdout, returncode)

        # Verify task6.csv has both time and uname metrics
        self.assertNotEqual(self.read_csv_column(f"{self._expname}/task6", "hostname", 0), "",
                          "hostname metric should not be empty")
        self.assertNotEqual(self.read_csv_column(f"{self._expname}/task6", "max_rss", 0), "",
                          "kernel metric should not be empty")



#####################################################################
if __name__ == "__main__":
    unittest.main()
