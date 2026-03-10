"""
Unit tests for profiling utilities.

Tests build_orchestrator_options to ensure profiling backends are correctly
prepended to the backend chain and that backend configs include all keys
from the YAML files (e.g., 'run', 'run_sys_spec').

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import tempfile
from pathlib import Path

from src.gui.utils.profile.execution import build_orchestrator_options


@pytest.fixture
def sample_v4_markdown(tmp_path):
    """Create a sample V4 markdown file with YAML frontmatter."""
    md_file = tmp_path / "test.md"
    content = """---
benchmark_spec:
  entry_point: /bin/echo
  args: ["hello"]
  task: test_task
backend_options:
  local:
    profiling: false
    composable: true
    run: $CMD $ARGS
repeats: MAX
repeater_options:
  MAX:
    max: 10
timeout: 3600
directory: runlogs
---

# Test Experiment

Experiment completed.
"""
    md_file.write_text(content)
    return str(md_file)


def test_backend_names_prepended(sample_v4_markdown):
    """Test that profiling backends are prepended using a sample V4 markdown fixture."""
    md = Path(sample_v4_markdown)
    opts = build_orchestrator_options(str(md), ['perf'], task_name='inc-prof')
    backend_names = opts.get('backend_names')
    assert backend_names[0] == 'perf', f"Expected 'perf' as first backend, got {backend_names}"
    assert backend_names.count('perf') == 1, f"Profiling backend duplicated: {backend_names}"
    assert len(backend_names) > 0, "backend_names should not be empty"


def test_profiling_backends_prepended_v4(sample_v4_markdown):
    """Test that profiling backends are prepended to original backends (V4 format)."""
    options = build_orchestrator_options(sample_v4_markdown, ['perf'], task_name='test-prof')

    assert 'backend_names' in options
    backend_names = options['backend_names']
    assert isinstance(backend_names, list)
    assert len(backend_names) >= 2
    assert backend_names[0] == 'perf', f"Expected 'perf' first, got {backend_names}"
    assert 'local' in backend_names, f"Expected 'local' in backend chain, got {backend_names}"

    assert 'backend_options' in options
    backend_opts = options['backend_options']
    assert 'perf' in backend_opts, f"Expected 'perf' in backend_options, got {list(backend_opts.keys())}"
    assert 'local' in backend_opts, f"Expected 'local' in backend_options, got {list(backend_opts.keys())}"


def test_perf_backend_config_includes_run_key(sample_v4_markdown):
    """Test that perf backend config includes 'run' key from YAML file."""
    options = build_orchestrator_options(sample_v4_markdown, ['perf'], task_name='test-prof')

    backend_opts = options.get('backend_options', {})
    perf_opts = backend_opts.get('perf')

    assert perf_opts is not None, "perf backend options should be present"
    assert isinstance(perf_opts, dict), f"perf opts should be dict, got {type(perf_opts)}"

    # Verify 'run' key is present (critical test that would fail with model_dump())
    assert 'run' in perf_opts, f"Expected 'run' key in perf options, got keys: {list(perf_opts.keys())}"

    # Verify run command includes perf stat
    run_cmd = perf_opts['run']
    assert 'perf stat' in run_cmd, f"Expected 'perf stat' in run command, got: {run_cmd}"
    assert '$CMD' in run_cmd, f"Expected '$CMD' placeholder in run command, got: {run_cmd}"


def test_multiple_profiling_backends(sample_v4_markdown):
    """Test prepending multiple profiling backends in order."""
    options = build_orchestrator_options(sample_v4_markdown, ['strace', 'perf'], task_name='test-prof')

    backend_names = options['backend_names']
    assert len(backend_names) >= 3
    assert backend_names[0] == 'strace', f"Expected 'strace' first, got {backend_names}"
    assert backend_names[1] == 'perf', f"Expected 'perf' second, got {backend_names}"
    assert 'local' in backend_names, f"Expected 'local' in backend chain, got {backend_names}"


def test_task_name_override(sample_v4_markdown):
    """Test that task name is correctly overridden."""
    options = build_orchestrator_options(sample_v4_markdown, ['perf'], task_name='custom-prof')

    assert options.get('task') == 'custom-prof', f"Expected task='custom-prof', got {options.get('task')}"


def test_no_original_backends(tmp_path):
    """Test profiling when original markdown has no backends specified."""
    md_file = tmp_path / "no_backends.md"
    content = """---
benchmark_spec:
  entry_point: /bin/echo
  args: []
  task: test_task
repeats: MAX
repeater_options:
  MAX:
    max: 5
---

# Test
"""
    md_file.write_text(content)

    options = build_orchestrator_options(str(md_file), ['perf'], task_name='test-prof')

    backend_names = options['backend_names']
    # Should have only perf since no original backends
    assert backend_names == ['perf'], f"Expected only ['perf'], got {backend_names}"
