"""
Integration tests for the compare CLI tool.

Tests the complete comparison workflow using real benchmark runs.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DATA_DIR = PROJECT_ROOT / 'tests' / 'fixtures' / 'compare_cli'


@pytest.fixture
def test_data_dir():
    """Path to test comparison data."""
    return FIXTURE_DATA_DIR


@pytest.fixture
def experiment_name(test_data_dir):
    """Create a temporary experiment directory under runlogs for -e tests."""
    runlogs_dir = PROJECT_ROOT / 'runlogs'
    runlogs_dir.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix='compare_cli_', dir=runlogs_dir))

    try:
        for source_path in test_data_dir.iterdir():
            shutil.copy2(source_path, temp_dir / source_path.name)
        yield temp_dir.name
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_compare(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the compare CLI from the project root."""
    return subprocess.run(
        ['uv', 'run', 'compare', *args],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


def test_compare_help():
    """Test that compare --help works."""
    result = run_compare('--help')
    assert result.returncode == 0
    assert 'Compare two benchmark runs' in result.stdout
    assert '--metrics' in result.stdout
    assert '--format' in result.stdout


def test_compare_with_experiment_flag(experiment_name):
    """Test comparing two runs using -e experiment flag."""
    result = run_compare('-e', experiment_name, 'sleep_fast.csv', 'sleep_slow.csv')

    assert result.returncode == 0
    assert 'Statistical Comparison' in result.stdout
    assert 'inner_time' in result.stdout
    assert 'Metadata Comparison' in result.stdout


def test_compare_with_full_paths(test_data_dir):
    """Test comparing two runs using full paths."""
    fast_path = test_data_dir / 'sleep_fast.csv'
    slow_path = test_data_dir / 'sleep_slow.csv'

    result = run_compare(str(fast_path), str(slow_path))

    assert result.returncode == 0
    assert 'Statistical Comparison' in result.stdout
    assert 'inner_time' in result.stdout


def test_compare_csv_format(experiment_name):
    """Test CSV output format."""
    result = run_compare('-e', experiment_name, '--format', 'csv', 'sleep_fast.csv', 'sleep_slow.csv')

    assert result.returncode == 0
    assert 'metric,baseline_n,baseline_median' in result.stdout
    assert 'inner_time' in result.stdout
    # Should not have markdown formatting
    assert '|' not in result.stdout


def test_compare_plaintext_format(experiment_name):
    """Test plaintext output format."""
    result = run_compare('-e', experiment_name, '--format', 'plaintext', 'sleep_fast.csv', 'sleep_slow.csv')

    assert result.returncode == 0
    assert 'Statistical Comparison' in result.stdout
    assert 'inner_time' in result.stdout
    # Should not have markdown formatting
    assert '|' not in result.stdout


def test_compare_multiple_metrics(experiment_name):
    """Test comparing multiple metrics."""
    result = run_compare(
        '-e', experiment_name, '-m', 'inner_time,outer_time', 'sleep_fast.csv', 'sleep_slow.csv'
    )

    assert result.returncode == 0
    assert 'inner_time' in result.stdout
    assert 'outer_time' in result.stdout


def test_compare_show_all_metadata(experiment_name):
    """Test --show-all flag for metadata."""
    # Without --show-all
    result_default = run_compare('-e', experiment_name, 'sleep_fast.csv', 'sleep_slow.csv')

    # With --show-all
    result_all = run_compare('-e', experiment_name, '--show-all', 'sleep_fast.csv', 'sleep_slow.csv')

    assert result_default.returncode == 0
    assert result_all.returncode == 0

    # --show-all should have more metadata rows
    # (This is a heuristic check since exact content depends on data)
    assert len(result_all.stdout) >= len(result_default.stdout)


def test_compare_nonexistent_file():
    """Test error handling for nonexistent files."""
    result = run_compare('nonexistent1.csv', 'nonexistent2.csv')

    assert result.returncode == 1
    assert 'Error' in result.stderr


def test_compare_missing_metric(experiment_name):
    """Test error handling when requested metric doesn't exist."""
    result = run_compare('-e', experiment_name, '-m', 'nonexistent_metric', 'sleep_fast.csv', 'sleep_slow.csv')

    assert result.returncode == 1
    assert 'Error' in result.stderr or 'not found' in result.stderr


def test_compare_different_benchmarks(experiment_name):
    """Test comparing different benchmarks (should work but show more differences)."""
    result = run_compare('-e', experiment_name, 'sleep_fast.csv', 'nope_test.csv')

    assert result.returncode == 0
    assert 'Statistical Comparison' in result.stdout
    assert 'Metadata Comparison' in result.stdout
    # Should show runtime option differences (args, entry_point, task)
    assert 'args' in result.stdout
    assert 'entry_point' in result.stdout


def test_compare_metadata_parsing(test_data_dir):
    """Test that metadata sections are correctly parsed from v4 .md files."""
    from src.core.runlogs.metadata_compare import load_metadata

    md_file = test_data_dir / 'sleep_fast.md'

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
    from src.core.runlogs.metadata_compare import load_metadata, flatten_dict

    md_file = test_data_dir / 'sleep_fast.md'

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
    from src.core.runlogs.metadata_compare import load_metadata, extract_core_count

    md_file = test_data_dir / 'sleep_fast.md'

    metadata = load_metadata(md_file)
    core_count = extract_core_count(metadata)

    # Should extract the processor_count from the metadata
    assert core_count is not None
    assert core_count == 128  # Based on the test system
