"""
Unit tests for configuration loader.

Tests load_config function with various schemas, error handling,
and integration with include resolution.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import tempfile
from pathlib import Path

from src.core.config.errors import ConfigError
from src.core.config.loader import load_config, discover_benchmarks, discover_backends
from src.core.config.schema import (
    BackendConfig,
    BenchmarkConfig,
)


@pytest.fixture
def config_temp_dir(tmp_path):
    """Create temporary directory for test files."""
    return tmp_path


def test_load_config_without_schema_returns_dict(config_temp_dir):
    """Test loading config without schema returns raw dict."""
    config_file = config_temp_dir / "config.yaml"
    config_file.write_text("key1: value1\nkey2: value2\nlist: [1, 2, 3]")

    result = load_config(str(config_file))

    assert isinstance(result, dict)
    assert result['key1'] == 'value1'
    assert result['key2'] == 'value2'
    assert result['list'] == [1, 2, 3]


def test_load_config_with_backend_schema(config_temp_dir):
    """Test loading backend config with schema validation."""
    backend_file = config_temp_dir / "backend.yaml"
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

    assert isinstance(result, BackendConfig)
    assert 'local' in result.backend_options
    assert result.backend_options['local'].command_template == "$CMD $ARGS"
    assert 'cycles' in result.metrics


def test_load_config_with_benchmark_schema(config_temp_dir):
    """Test loading benchmark config with schema validation."""
    benchmark_file = config_temp_dir / "benchmark.yaml"
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

    assert isinstance(result, BenchmarkConfig)
    assert 'test_bench' in result.benchmarks
    assert result.benchmarks['test_bench'].entry_point == 'python3'


def test_load_config_with_includes_merges_correctly(config_temp_dir):
    """Test config with includes merges data correctly."""
    # Create base config
    base_file = config_temp_dir / "base.yaml"
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
    main_file = config_temp_dir / "main.yaml"
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
    assert 'local' in result.backend_options
    assert 'perf' in result.backend_options
    # Should have both metrics
    assert 'base_metric' in result.metrics
    assert 'perf_metric' in result.metrics


def test_load_config_validation_error_raises_config_error(config_temp_dir):
    """Test schema validation failure raises ConfigError."""
    bad_backend = config_temp_dir / "bad.yaml"
    bad_backend.write_text("""
backend_options:
  broken:
    command_template: "missing placeholders"
""")

    with pytest.raises(ConfigError) as context:
        load_config(str(bad_backend), BackendConfig)

    error_msg = str(context.value)
    assert "Validation failed" in error_msg
    assert "BackendConfig" in error_msg


def test_load_config_missing_file_raises_error(config_temp_dir):
    """Test loading nonexistent file raises ConfigError."""
    with pytest.raises(ConfigError) as context:
        load_config(str(config_temp_dir / "nonexistent.yaml"))

    error_msg = str(context.value)
    assert "not found" in error_msg.lower()


def test_load_config_invalid_yaml_raises_error(config_temp_dir):
    """Test invalid YAML raises ConfigError."""
    bad_file = config_temp_dir / "bad.yaml"
    # Actually invalid YAML - unterminated quote
    bad_file.write_text("key: 'unterminated string\nother: value")

    with pytest.raises(ConfigError):
        load_config(str(bad_file))


def test_load_config_resolves_relative_path(config_temp_dir):
    """Test loader resolves relative paths correctly."""
    config_file = config_temp_dir / "config.yaml"
    config_file.write_text("key: value")

    # Change to temp dir and use relative path
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(config_temp_dir)
        result = load_config("config.yaml")
        assert result['key'] == 'value'
    finally:
        os.chdir(original_cwd)


def test_load_config_type_hints_work_correctly(config_temp_dir):
    """Test type hints allow proper IDE autocomplete."""
    backend_file = config_temp_dir / "backend.yaml"
    backend_file.write_text("""
backend_options:
  local:
    command_template: "$CMD $ARGS"
metrics: {}
""")

    # With schema, should return typed object
    typed_result = load_config(str(backend_file), BackendConfig)
    assert isinstance(typed_result, BackendConfig)
    # IDE should know this has backend_options attribute
    assert hasattr(typed_result, 'backend_options')

    # Without schema, should return dict
    untyped_result = load_config(str(backend_file))
    assert isinstance(untyped_result, dict)


@pytest.fixture
def benchmarks_temp_dir(tmp_path):
    """Create temporary directory for test benchmarks."""
    benchmarks_dir = tmp_path / "benchmarks"
    benchmarks_dir.mkdir()
    return tmp_path, benchmarks_dir


def test_discover_benchmarks_empty_directory(benchmarks_temp_dir):
    """Test discovering benchmarks in empty directory returns empty dict."""
    temp_dir, benchmarks_dir = benchmarks_temp_dir
    result = discover_benchmarks(benchmarks_dir)
    assert result == {}


def test_discover_benchmarks_single_benchmark(benchmarks_temp_dir):
    """Test discovering single benchmark in directory."""
    temp_dir, benchmarks_dir = benchmarks_temp_dir
    # Create a benchmark directory with benchmark.yaml
    bench_dir = benchmarks_dir / "sleep"
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

    result = discover_benchmarks(benchmarks_dir)

    assert len(result) == 1
    assert 'sleep' in result
    config_path, bench_name = result['sleep']
    assert config_path == config_file
    assert bench_name == 'sleep'


def test_discover_benchmarks_multiple_benchmarks_per_file(benchmarks_temp_dir):
    """Test discovering multiple benchmarks from single file."""
    temp_dir, benchmarks_dir = benchmarks_temp_dir
    # Create one directory with multiple benchmarks
    bench_dir = benchmarks_dir / "suite"
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

    result = discover_benchmarks(benchmarks_dir)

    assert len(result) == 3
    assert 'bench1' in result
    assert 'bench2' in result
    assert 'bench3' in result

    # All should point to same config file
    for bench_name in ['bench1', 'bench2', 'bench3']:
        config_path, name = result[bench_name]
        assert config_path == config_file
        assert name == bench_name


def test_discover_benchmarks_nested_directories(benchmarks_temp_dir):
    """Test discovering benchmarks in nested directory structure."""
    temp_dir, benchmarks_dir = benchmarks_temp_dir
    # Create nested structure
    sleep_dir = benchmarks_dir / "microbenchmarks" / "sleep"
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

    matmul_dir = benchmarks_dir / "microbenchmarks" / "matmul"
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

    result = discover_benchmarks(benchmarks_dir)

    assert len(result) == 2
    assert 'sleep' in result
    assert 'matmul' in result


def test_discover_benchmarks_nonexistent_directory(benchmarks_temp_dir):
    """Test discovering benchmarks in nonexistent directory returns empty."""
    temp_dir, benchmarks_dir = benchmarks_temp_dir
    nonexistent = temp_dir / "does_not_exist"
    result = discover_benchmarks(nonexistent)
    assert result == {}


def test_discover_benchmarks_invalid_yaml_raises_error(benchmarks_temp_dir):
    """Test invalid benchmark.yaml raises ConfigError."""
    temp_dir, benchmarks_dir = benchmarks_temp_dir
    bench_dir = benchmarks_dir / "broken"
    bench_dir.mkdir()
    config_file = bench_dir / "benchmark.yaml"
    # Missing required 'benchmarks' key
    config_file.write_text("metrics: {}")

    with pytest.raises(ConfigError) as context:
        discover_benchmarks(benchmarks_dir)

    error_msg = str(context.value)
    assert "Failed to load benchmark config" in error_msg


@pytest.fixture
def backends_temp_dir(tmp_path):
    """Create temporary directory for test backends."""
    backends_dir = tmp_path / "backends"
    backends_dir.mkdir()
    return tmp_path, backends_dir


def test_discover_backends_empty_directory(backends_temp_dir):
    """Test discovering backends in empty directory returns empty dict."""
    temp_dir, backends_dir = backends_temp_dir
    result = discover_backends([str(backends_dir)])
    assert result == {}


def test_discover_backends_single_backend(backends_temp_dir):
    """Test discovering single backend."""
    temp_dir, backends_dir = backends_temp_dir
    local_file = backends_dir / "local.yaml"
    local_file.write_text("""
backend_options:
  local:
    profiling: false
    composable: false
    command_template: "$CMD $ARGS"
metrics: {}
""")

    result = discover_backends([str(backends_dir)])

    assert len(result) == 1
    assert 'local' in result
    assert isinstance(result['local'], BackendConfig)


def test_discover_backends_multiple_backends(backends_temp_dir):
    """Test discovering multiple backends."""
    temp_dir, backends_dir = backends_temp_dir
    # Create execution backend
    (backends_dir / "local.yaml").write_text("""
backend_options:
  local:
    profiling: false
    command_template: "$CMD $ARGS"
metrics: {}
""")

    # Create profiling backend
    (backends_dir / "perf.yaml").write_text("""
backend_options:
  perf:
    profiling: true
    command_template: "perf stat -- $CMD $ARGS"
metrics:
  cycles:
    description: "CPU cycles"
    extract: "grep cycles"
""")

    result = discover_backends([str(backends_dir)])

    assert len(result) == 2
    assert 'local' in result
    assert 'perf' in result


def test_discover_backends_filter_profiling_only(backends_temp_dir):
    """Test filtering to profiling backends only."""
    temp_dir, backends_dir = backends_temp_dir
    # Create execution backend
    (backends_dir / "local.yaml").write_text("""
backend_options:
  local:
    profiling: false
    command_template: "$CMD $ARGS"
metrics: {}
""")

    # Create profiling backends
    (backends_dir / "perf.yaml").write_text("""
backend_options:
  perf:
    profiling: true
    command_template: "perf stat -- $CMD $ARGS"
metrics: {}
""")

    (backends_dir / "strace.yaml").write_text("""
backend_options:
  strace:
    profiling: true
    command_template: "strace -c $CMD $ARGS"
metrics: {}
""")

    result = discover_backends([str(backends_dir)], profiling=True)

    assert len(result) == 2
    assert 'perf' in result
    assert 'strace' in result
    assert 'local' not in result


def test_discover_backends_filter_execution_only(backends_temp_dir):
    """Test filtering to execution backends only."""
    temp_dir, backends_dir = backends_temp_dir
    # Create execution backends
    (backends_dir / "local.yaml").write_text("""
backend_options:
  local:
    profiling: false
    command_template: "$CMD $ARGS"
metrics: {}
""")

    (backends_dir / "ssh.yaml").write_text("""
backend_options:
  ssh:
    profiling: false
    command_template: "ssh host $CMD $ARGS"
metrics: {}
""")

    # Create profiling backend
    (backends_dir / "perf.yaml").write_text("""
backend_options:
  perf:
    profiling: true
    command_template: "perf stat -- $CMD $ARGS"
metrics: {}
""")

    result = discover_backends([str(backends_dir)], profiling=False)

    assert len(result) == 2
    assert 'local' in result
    assert 'ssh' in result
    assert 'perf' not in result


def test_discover_backends_multiple_search_paths(backends_temp_dir):
    """Test discovering backends from multiple search paths."""
    temp_dir, backends_dir = backends_temp_dir
    # Create second backend directory
    backends_dir2 = temp_dir / "custom_backends"
    backends_dir2.mkdir()

    (backends_dir / "local.yaml").write_text("""
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

    result = discover_backends([str(backends_dir), str(backends_dir2)])

    assert len(result) == 2
    assert 'local' in result
    assert 'custom' in result


def test_discover_backends_nonexistent_directory(backends_temp_dir):
    """Test discovering backends in nonexistent directory returns empty."""
    temp_dir, backends_dir = backends_temp_dir
    nonexistent = str(temp_dir / "does_not_exist")
    result = discover_backends([nonexistent])
    assert result == {}


def test_discover_backends_invalid_yaml_raises_error(backends_temp_dir):
    """Test invalid backend.yaml raises ConfigError."""
    temp_dir, backends_dir = backends_temp_dir
    bad_file = backends_dir / "broken.yaml"
    # Missing command template placeholders
    bad_file.write_text("""
backend_options:
  broken:
    command_template: "missing placeholders"
""")

    with pytest.raises(ConfigError) as context:
        discover_backends([str(backends_dir)])

    error_msg = str(context.value)
    assert "Failed to load backend config" in error_msg
