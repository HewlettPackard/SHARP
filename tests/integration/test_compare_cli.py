"""
Integration tests for the compare CLI tool.

Tests the complete comparison workflow using real benchmark runs.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def test_data_dir():
    """Path to test comparison data."""
    return Path(__file__).parent.parent.parent / 'runlogs' / 'test_compare'


def test_compare_help():
    """Test that compare --help works."""
    result = subprocess.run(
        ['uv', 'run', 'compare', '--help'],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert 'Compare two benchmark runs' in result.stdout
    assert '--metrics' in result.stdout
    assert '--format' in result.stdout


def test_compare_with_experiment_flag(test_data_dir):
    """Test comparing two runs using -e experiment flag."""
    if not test_data_dir.exists():
        pytest.skip("Test data not available")

    result = subprocess.run(
        ['uv', 'run', 'compare', '-e', 'test_compare', 'sleep_fast.csv', 'sleep_slow.csv'],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert 'Statistical Comparison' in result.stdout
    assert 'inner_time' in result.stdout
    assert 'Metadata Comparison' in result.stdout


def test_compare_with_full_paths(test_data_dir):
    """Test comparing two runs using full paths."""
    if not test_data_dir.exists():
        pytest.skip("Test data not available")

    fast_path = test_data_dir / 'sleep_fast.csv'
    slow_path = test_data_dir / 'sleep_slow.csv'

    result = subprocess.run(
        ['uv', 'run', 'compare', str(fast_path), str(slow_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert 'Statistical Comparison' in result.stdout
    assert 'inner_time' in result.stdout


def test_compare_csv_format(test_data_dir):
    """Test CSV output format."""
    if not test_data_dir.exists():
        pytest.skip("Test data not available")

    result = subprocess.run(
        ['uv', 'run', 'compare', '-e', 'test_compare', '--format', 'csv',
         'sleep_fast.csv', 'sleep_slow.csv'],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert 'metric,baseline_n,baseline_median' in result.stdout
    assert 'inner_time' in result.stdout
    # Should not have markdown formatting
    assert '|' not in result.stdout


def test_compare_plaintext_format(test_data_dir):
    """Test plaintext output format."""
    if not test_data_dir.exists():
        pytest.skip("Test data not available")

    result = subprocess.run(
        ['uv', 'run', 'compare', '-e', 'test_compare', '--format', 'plaintext',
         'sleep_fast.csv', 'sleep_slow.csv'],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert 'Statistical Comparison' in result.stdout
    assert 'inner_time' in result.stdout
    # Should not have markdown formatting
    assert '|' not in result.stdout


def test_compare_multiple_metrics(test_data_dir):
    """Test comparing multiple metrics."""
    if not test_data_dir.exists():
        pytest.skip("Test data not available")

    result = subprocess.run(
        ['uv', 'run', 'compare', '-e', 'test_compare', '-m', 'inner_time,outer_time',
         'sleep_fast.csv', 'sleep_slow.csv'],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert 'inner_time' in result.stdout
    assert 'outer_time' in result.stdout


def test_compare_show_all_metadata(test_data_dir):
    """Test --show-all flag for metadata."""
    if not test_data_dir.exists():
        pytest.skip("Test data not available")

    # Without --show-all
    result_default = subprocess.run(
        ['uv', 'run', 'compare', '-e', 'test_compare',
         'sleep_fast.csv', 'sleep_slow.csv'],
        capture_output=True,
        text=True,
    )

    # With --show-all
    result_all = subprocess.run(
        ['uv', 'run', 'compare', '-e', 'test_compare', '--show-all',
         'sleep_fast.csv', 'sleep_slow.csv'],
        capture_output=True,
        text=True,
    )

    assert result_default.returncode == 0
    assert result_all.returncode == 0

    # --show-all should have more metadata rows
    # (This is a heuristic check since exact content depends on data)
    assert len(result_all.stdout) >= len(result_default.stdout)


def test_compare_nonexistent_file():
    """Test error handling for nonexistent files."""
    result = subprocess.run(
        ['uv', 'run', 'compare', 'nonexistent1.csv', 'nonexistent2.csv'],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert 'Error' in result.stderr


def test_compare_missing_metric(test_data_dir):
    """Test error handling when requested metric doesn't exist."""
    if not test_data_dir.exists():
        pytest.skip("Test data not available")

    result = subprocess.run(
        ['uv', 'run', 'compare', '-e', 'test_compare', '-m', 'nonexistent_metric',
         'sleep_fast.csv', 'sleep_slow.csv'],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert 'Error' in result.stderr or 'not found' in result.stderr


def test_compare_different_benchmarks(test_data_dir):
    """Test comparing different benchmarks (should work but show more differences)."""
    if not test_data_dir.exists():
        pytest.skip("Test data not available")

    result = subprocess.run(
        ['uv', 'run', 'compare', '-e', 'test_compare',
         'sleep_fast.csv', 'nope_test.csv'],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert 'Statistical Comparison' in result.stdout
    assert 'Metadata Comparison' in result.stdout
    # Should show runtime option differences (args, entry_point, task)
    assert 'args' in result.stdout
    assert 'entry_point' in result.stdout


def test_compare_metadata_parsing(test_data_dir):
    """Test that metadata sections are correctly parsed from v4 .md files."""
    if not test_data_dir.exists():
        pytest.skip("Test data not available")

    from src.core.runlogs.metadata_compare import load_metadata

    md_file = test_data_dir / 'sleep_fast.md'
    if not md_file.exists():
        pytest.skip("Metadata file not available")

    sections = load_metadata(md_file)

    # Check expected sections exist
    assert 'Initial runtime options' in sections
    assert 'Initial system configuration' in sections
    assert 'Invariant parameters' in sections

    # Check structure of runtime options
    runtime = sections['Initial runtime options']
    assert 'backend_names' in runtime
    assert 'metrics' in runtime
    assert 'task' in runtime

    # Check structure of system configuration
    sys_config = sections['Initial system configuration']
    assert 'cpu' in sys_config
    assert 'memory' in sys_config
    assert 'load_average' in sys_config


def test_compare_metadata_flattening(test_data_dir):
    """Test that nested metadata is flattened for comparison."""
    if not test_data_dir.exists():
        pytest.skip("Test data not available")

    from src.core.runlogs.metadata_compare import load_metadata, flatten_dict

    md_file = test_data_dir / 'sleep_fast.md'
    if not md_file.exists():
        pytest.skip("Metadata file not available")

    sections = load_metadata(md_file)
    sys_config = sections['Initial system configuration']
    flat = flatten_dict(sys_config)

    # Check that nested fields are flattened with dot notation
    assert 'cpu.processor_count' in flat
    assert 'memory.total_memory_kb' in flat
    assert 'load_average.one_minute' in flat


def test_compare_significance_filtering():
    """Test that insignificant differences are filtered out."""
    from src.core.runlogs.metadata_compare import is_significant_difference

    # Uptime should not be significant (always different)
    assert not is_significant_difference('System', 'uptime_seconds', 1000, 1100)

    # Running processes should not be significant (noise)
    assert not is_significant_difference('System', 'running_processes', 100, 105)

    # Small memory difference (<1%) should not be significant
    assert not is_significant_difference('System', 'memory.available_memory_kb',
                                        1024243772, 1023983576)

    # Small load average (<threshold) should not be significant with 128 cores
    assert not is_significant_difference('System', 'load_average.one_minute', 3.06, 2.36,
                                        core_count=128)

    # Large CPU freq difference (>5%) should be significant
    assert is_significant_difference('System', 'cpu.scaling_cur_freq_khz', 1500547, 1690514)

    # Different task names should be significant
    assert is_significant_difference('Runtime', 'task', 'sleep_fast', 'nope_test')

    # Different args should be significant
    assert is_significant_difference('Runtime', 'args', ['0.1'], ['0.2'])


def test_core_count_extraction(test_data_dir):
    """Test that core count is correctly extracted from metadata."""
    if not test_data_dir.exists():
        pytest.skip("Test data not available")

    from src.core.runlogs.metadata_compare import load_metadata, extract_core_count

    md_file = test_data_dir / 'sleep_fast.md'
    if not md_file.exists():
        pytest.skip("Metadata file not available")

    metadata = load_metadata(md_file)
    core_count = extract_core_count(metadata)

    # Should extract the processor_count from the metadata
    assert core_count is not None
    assert core_count == 128  # Based on the test system
