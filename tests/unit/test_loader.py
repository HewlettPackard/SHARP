"""
Unit tests for configuration loader.

Tests load_config function with various schemas, error handling,
and integration with include resolution.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.core.config.errors import ConfigError
from src.core.config.loader import load_config, discover_benchmarks, discover_backends
from src.core.config.schema import (
    BackendConfig,
    BackendOptionConfig,
    BenchmarkConfig,
    BenchmarkSource,
    BenchmarkBuild,
    BenchmarkEntry,
    MetricDefinition,
)


class TestLoadConfig(unittest.TestCase):
    """Test load_config function."""

    def setUp(self):
        """Create temporary directory for test files."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up temporary files."""
        for file in self.temp_dir.rglob("*"):
            if file.is_file():
                file.unlink()
        for dir in sorted(self.temp_dir.rglob("*"), reverse=True):
            if dir.is_dir():
                dir.rmdir()
        self.temp_dir.rmdir()

    def test_load_config_without_schema_returns_dict(self):
        """Test loading config without schema returns raw dict."""
        config_file = self.temp_dir / "config.yaml"
        config_file.write_text("key1: value1\nkey2: value2\nlist: [1, 2, 3]")

        result = load_config(str(config_file))

        self.assertIsInstance(result, dict)
        self.assertEqual(result['key1'], 'value1')
        self.assertEqual(result['key2'], 'value2')
        self.assertEqual(result['list'], [1, 2, 3])

    def test_load_config_with_backend_schema(self):
        """Test loading backend config with schema validation."""
        backend_file = self.temp_dir / "backend.yaml"
        backend_file.write_text("""
backend_options:
  local:
    profiling: false
    composable: true
    command_template: "$CMD $ARGS"
metrics:
  cycles:
    description: "CPU cycles"
    extract: "grep cycles"
""")

        result = load_config(str(backend_file), BackendConfig)

        self.assertIsInstance(result, BackendConfig)
        self.assertIn('local', result.backend_options)
        self.assertEqual(result.backend_options['local'].command_template, "$CMD $ARGS")
        self.assertIn('cycles', result.metrics)

    def test_load_config_with_benchmark_schema(self):
        """Test loading benchmark config with schema validation."""
        benchmark_file = self.temp_dir / "benchmark.yaml"
        benchmark_file.write_text("""
benchmarks:
  test_bench:
    sources:
      - type: path
        location: "./test.py"
    build:
      requirements: []
    entry_point: "python3"
    args: ["test.py"]
    tags: ["test"]
metrics: {}
""")

        result = load_config(str(benchmark_file), BenchmarkConfig)

        self.assertIsInstance(result, BenchmarkConfig)
        self.assertIn('test_bench', result.benchmarks)
        self.assertEqual(result.benchmarks['test_bench'].entry_point, 'python3')

    def test_load_config_with_includes_merges_correctly(self):
        """Test config with includes merges data correctly."""
        # Create base config
        base_file = self.temp_dir / "base.yaml"
        base_file.write_text("""
backend_options:
  local:
    command_template: "$CMD $ARGS"
metrics:
  base_metric:
    description: "Base metric"
    extract: "echo base"
""")

        # Create main config that includes base
        main_file = self.temp_dir / "main.yaml"
        main_file.write_text("""
include:
  - base.yaml
backend_options:
  perf:
    profiling: true
    command_template: "perf stat -- $CMD $ARGS"
metrics:
  perf_metric:
    description: "Perf metric"
    extract: "grep perf"
""")

        result = load_config(str(main_file), BackendConfig)

        # Should have both backends
        self.assertIn('local', result.backend_options)
        self.assertIn('perf', result.backend_options)
        # Should have both metrics
        self.assertIn('base_metric', result.metrics)
        self.assertIn('perf_metric', result.metrics)

    def test_load_config_validation_error_raises_config_error(self):
        """Test schema validation failure raises ConfigError."""
        bad_backend = self.temp_dir / "bad.yaml"
        bad_backend.write_text("""
backend_options:
  broken:
    command_template: "missing placeholders"
""")

        with self.assertRaises(ConfigError) as context:
            load_config(str(bad_backend), BackendConfig)

        error_msg = str(context.exception)
        self.assertIn("Validation failed", error_msg)
        self.assertIn("BackendConfig", error_msg)

    def test_load_config_missing_file_raises_error(self):
        """Test loading nonexistent file raises ConfigError."""
        with self.assertRaises(ConfigError) as context:
            load_config(str(self.temp_dir / "nonexistent.yaml"))

        error_msg = str(context.exception)
        self.assertIn("not found", error_msg.lower())

    def test_load_config_invalid_yaml_raises_error(self):
        """Test invalid YAML raises ConfigError."""
        bad_file = self.temp_dir / "bad.yaml"
        # Actually invalid YAML - unterminated quote
        bad_file.write_text("key: 'unterminated string\nother: value")

        with self.assertRaises(ConfigError):
            load_config(str(bad_file))

    def test_load_config_resolves_relative_path(self):
        """Test loader resolves relative paths correctly."""
        config_file = self.temp_dir / "config.yaml"
        config_file.write_text("key: value")

        # Change to temp dir and use relative path
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(self.temp_dir)
            result = load_config("config.yaml")
            self.assertEqual(result['key'], 'value')
        finally:
            os.chdir(original_cwd)

    def test_load_config_type_hints_work_correctly(self):
        """Test type hints allow proper IDE autocomplete."""
        backend_file = self.temp_dir / "backend.yaml"
        backend_file.write_text("""
backend_options:
  local:
    command_template: "$CMD $ARGS"
metrics: {}
""")

        # With schema, should return typed object
        typed_result = load_config(str(backend_file), BackendConfig)
        self.assertIsInstance(typed_result, BackendConfig)
        # IDE should know this has backend_options attribute
        self.assertTrue(hasattr(typed_result, 'backend_options'))

        # Without schema, should return dict
        untyped_result = load_config(str(backend_file))
        self.assertIsInstance(untyped_result, dict)


class TestDiscoverBenchmarks(unittest.TestCase):
    """Test discover_benchmarks function."""

    def setUp(self):
        """Create temporary directory for test benchmarks."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.benchmarks_dir = self.temp_dir / "benchmarks"
        self.benchmarks_dir.mkdir()

    def tearDown(self):
        """Clean up temporary files."""
        for file in self.temp_dir.rglob("*"):
            if file.is_file():
                file.unlink()
        for dir in sorted(self.temp_dir.rglob("*"), reverse=True):
            if dir.is_dir():
                dir.rmdir()
        self.temp_dir.rmdir()

    def test_discover_benchmarks_empty_directory(self):
        """Test discovering benchmarks in empty directory returns empty dict."""
        result = discover_benchmarks(self.benchmarks_dir)
        self.assertEqual(result, {})

    def test_discover_benchmarks_single_benchmark(self):
        """Test discovering single benchmark in directory."""
        # Create a benchmark directory with benchmark.yaml
        bench_dir = self.benchmarks_dir / "sleep"
        bench_dir.mkdir()
        config_file = bench_dir / "benchmark.yaml"
        config_file.write_text("""
benchmarks:
  sleep:
    sources:
      - type: path
        location: "sleep.py"
    build:
      requirements: []
    entry_point: "python3"
    args: ["sleep.py"]
    tags: ["microbenchmark"]
metrics: {}
""")

        result = discover_benchmarks(self.benchmarks_dir)

        self.assertEqual(len(result), 1)
        self.assertIn('sleep', result)
        config_path, bench_name = result['sleep']
        self.assertEqual(config_path, config_file)
        self.assertEqual(bench_name, 'sleep')

    def test_discover_benchmarks_multiple_benchmarks_per_file(self):
        """Test discovering multiple benchmarks from single file."""
        # Create one directory with multiple benchmarks
        bench_dir = self.benchmarks_dir / "suite"
        bench_dir.mkdir()
        config_file = bench_dir / "benchmark.yaml"
        config_file.write_text("""
benchmarks:
  bench1:
    sources:
      - type: path
        location: "bench1.py"
    build:
      requirements: []
    entry_point: "python3"
    args: ["bench1.py"]
    tags: ["test"]
  bench2:
    sources:
      - type: path
        location: "bench2.py"
    build:
      requirements: []
    entry_point: "python3"
    args: ["bench2.py"]
    tags: ["test"]
  bench3:
    sources:
      - type: path
        location: "bench3.py"
    build:
      requirements: []
    entry_point: "python3"
    args: ["bench3.py"]
    tags: ["test"]
metrics: {}
""")

        result = discover_benchmarks(self.benchmarks_dir)

        self.assertEqual(len(result), 3)
        self.assertIn('bench1', result)
        self.assertIn('bench2', result)
        self.assertIn('bench3', result)

        # All should point to same config file
        for bench_name in ['bench1', 'bench2', 'bench3']:
            config_path, name = result[bench_name]
            self.assertEqual(config_path, config_file)
            self.assertEqual(name, bench_name)

    def test_discover_benchmarks_nested_directories(self):
        """Test discovering benchmarks in nested directory structure."""
        # Create nested structure
        sleep_dir = self.benchmarks_dir / "microbenchmarks" / "sleep"
        sleep_dir.mkdir(parents=True)
        (sleep_dir / "benchmark.yaml").write_text("""
benchmarks:
  sleep:
    sources:
      - type: path
        location: "sleep.py"
    build: {}
    entry_point: "python3"
    args: ["sleep.py"]
    tags: []
metrics: {}
""")

        matmul_dir = self.benchmarks_dir / "microbenchmarks" / "matmul"
        matmul_dir.mkdir(parents=True)
        (matmul_dir / "benchmark.yaml").write_text("""
benchmarks:
  matmul:
    sources:
      - type: path
        location: "matmul.py"
    build: {}
    entry_point: "python3"
    args: ["matmul.py"]
    tags: []
metrics: {}
""")

        result = discover_benchmarks(self.benchmarks_dir)

        self.assertEqual(len(result), 2)
        self.assertIn('sleep', result)
        self.assertIn('matmul', result)

    def test_discover_benchmarks_nonexistent_directory(self):
        """Test discovering benchmarks in nonexistent directory returns empty."""
        nonexistent = self.temp_dir / "does_not_exist"
        result = discover_benchmarks(nonexistent)
        self.assertEqual(result, {})

    def test_discover_benchmarks_invalid_yaml_raises_error(self):
        """Test invalid benchmark.yaml raises ConfigError."""
        bench_dir = self.benchmarks_dir / "broken"
        bench_dir.mkdir()
        config_file = bench_dir / "benchmark.yaml"
        # Missing required 'benchmarks' key
        config_file.write_text("metrics: {}")

        with self.assertRaises(ConfigError) as context:
            discover_benchmarks(self.benchmarks_dir)

        error_msg = str(context.exception)
        self.assertIn("Failed to load benchmark config", error_msg)


class TestDiscoverBackends(unittest.TestCase):
    """Test discover_backends function."""

    def setUp(self):
        """Create temporary directory for test backends."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.backends_dir = self.temp_dir / "backends"
        self.backends_dir.mkdir()

    def tearDown(self):
        """Clean up temporary files."""
        for file in self.temp_dir.rglob("*"):
            if file.is_file():
                file.unlink()
        for dir in sorted(self.temp_dir.rglob("*"), reverse=True):
            if dir.is_dir():
                dir.rmdir()
        self.temp_dir.rmdir()

    def test_discover_backends_empty_directory(self):
        """Test discovering backends in empty directory returns empty dict."""
        result = discover_backends([str(self.backends_dir)])
        self.assertEqual(result, {})

    def test_discover_backends_single_backend(self):
        """Test discovering single backend."""
        local_file = self.backends_dir / "local.yaml"
        local_file.write_text("""
backend_options:
  local:
    profiling: false
    composable: false
    command_template: "$CMD $ARGS"
metrics: {}
""")

        result = discover_backends([str(self.backends_dir)])

        self.assertEqual(len(result), 1)
        self.assertIn('local', result)
        self.assertIsInstance(result['local'], BackendConfig)

    def test_discover_backends_multiple_backends(self):
        """Test discovering multiple backends."""
        # Create execution backend
        (self.backends_dir / "local.yaml").write_text("""
backend_options:
  local:
    profiling: false
    command_template: "$CMD $ARGS"
metrics: {}
""")

        # Create profiling backend
        (self.backends_dir / "perf.yaml").write_text("""
backend_options:
  perf:
    profiling: true
    command_template: "perf stat -- $CMD $ARGS"
metrics:
  cycles:
    description: "CPU cycles"
    extract: "grep cycles"
""")

        result = discover_backends([str(self.backends_dir)])

        self.assertEqual(len(result), 2)
        self.assertIn('local', result)
        self.assertIn('perf', result)

    def test_discover_backends_filter_profiling_only(self):
        """Test filtering to profiling backends only."""
        # Create execution backend
        (self.backends_dir / "local.yaml").write_text("""
backend_options:
  local:
    profiling: false
    command_template: "$CMD $ARGS"
metrics: {}
""")

        # Create profiling backends
        (self.backends_dir / "perf.yaml").write_text("""
backend_options:
  perf:
    profiling: true
    command_template: "perf stat -- $CMD $ARGS"
metrics: {}
""")

        (self.backends_dir / "strace.yaml").write_text("""
backend_options:
  strace:
    profiling: true
    command_template: "strace -c $CMD $ARGS"
metrics: {}
""")

        result = discover_backends([str(self.backends_dir)], profiling=True)

        self.assertEqual(len(result), 2)
        self.assertIn('perf', result)
        self.assertIn('strace', result)
        self.assertNotIn('local', result)

    def test_discover_backends_filter_execution_only(self):
        """Test filtering to execution backends only."""
        # Create execution backends
        (self.backends_dir / "local.yaml").write_text("""
backend_options:
  local:
    profiling: false
    command_template: "$CMD $ARGS"
metrics: {}
""")

        (self.backends_dir / "ssh.yaml").write_text("""
backend_options:
  ssh:
    profiling: false
    command_template: "ssh host $CMD $ARGS"
metrics: {}
""")

        # Create profiling backend
        (self.backends_dir / "perf.yaml").write_text("""
backend_options:
  perf:
    profiling: true
    command_template: "perf stat -- $CMD $ARGS"
metrics: {}
""")

        result = discover_backends([str(self.backends_dir)], profiling=False)

        self.assertEqual(len(result), 2)
        self.assertIn('local', result)
        self.assertIn('ssh', result)
        self.assertNotIn('perf', result)

    def test_discover_backends_multiple_search_paths(self):
        """Test discovering backends from multiple search paths."""
        # Create second backend directory
        backends_dir2 = self.temp_dir / "custom_backends"
        backends_dir2.mkdir()

        (self.backends_dir / "local.yaml").write_text("""
backend_options:
  local:
    profiling: false
    command_template: "$CMD $ARGS"
metrics: {}
""")

        (backends_dir2 / "custom.yaml").write_text("""
backend_options:
  custom:
    profiling: false
    command_template: "custom $CMD $ARGS"
metrics: {}
""")

        result = discover_backends([str(self.backends_dir), str(backends_dir2)])

        self.assertEqual(len(result), 2)
        self.assertIn('local', result)
        self.assertIn('custom', result)

    def test_discover_backends_nonexistent_directory(self):
        """Test discovering backends in nonexistent directory returns empty."""
        nonexistent = str(self.temp_dir / "does_not_exist")
        result = discover_backends([nonexistent])
        self.assertEqual(result, {})

    def test_discover_backends_invalid_yaml_raises_error(self):
        """Test invalid backend.yaml raises ConfigError."""
        bad_file = self.backends_dir / "broken.yaml"
        # Missing command template placeholders
        bad_file.write_text("""
backend_options:
  broken:
    command_template: "missing placeholders"
""")

        with self.assertRaises(ConfigError) as context:
            discover_backends([str(self.backends_dir)])

        error_msg = str(context.exception)
        self.assertIn("Failed to load backend config", error_msg)


if __name__ == '__main__':
    unittest.main()
