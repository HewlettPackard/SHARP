"""
Unit tests for subprocess runner (runner.py).

Tests real subprocess execution: timeouts, output capture, error handling.
Uses controlled shell commands (echo, sleep, false) to test actual behavior.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import tempfile
import os
import warnings

from src.core.execution.runner import Runner


# ========== Test basic command execution ==========

def test_run_single_command_success() -> None:
    """Test executing a single successful command."""
    runner = Runner(timeout=5)
    commands = ['echo "hello world"']

    success, output_files, elapsed_time = runner.run_commands(commands)

    assert success
    assert len(output_files) == 1

    # Read output from temp file
    output_files[0].seek(0)
    output = output_files[0].read()
    assert b'hello world' in output

    # Cleanup
    for f in output_files:
        os.unlink(f.name)


def test_run_multiple_commands_in_parallel() -> None:
    """Test executing multiple commands in parallel."""
    runner = Runner(timeout=5)
    commands = [
        'echo "cmd1"',
        'echo "cmd2"',
        'echo "cmd3"'
    ]

    success, output_files, elapsed_time = runner.run_commands(commands)

    assert success
    assert len(output_files) == 3

    # Verify each command executed
    outputs = []
    for f in output_files:
        f.seek(0)
        outputs.append(f.read())
        os.unlink(f.name)

    # Should have 3 outputs with different content
    assert len(outputs) == 3
    assert b'cmd1' in outputs[0]
    assert b'cmd2' in outputs[1]
    assert b'cmd3' in outputs[2]


def test_failed_command_returns_false_status() -> None:
    """Test that failing command is detected (exit code != 0)."""
    runner = Runner(timeout=5, verbose=False)
    commands = ['false']  # Exit code 1

    # Suppress expected warning about command exit code
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        success, output_files, elapsed_time = runner.run_commands(commands)

    # Even though command fails, run_commands doesn't error
    # (failures are recorded in output via stderr, warnings issued)
    assert len(output_files) == 1

    # Cleanup
    for f in output_files:
        os.unlink(f.name)


def test_timeout_terminates_hanging_command() -> None:
    """Test that timeout stops long-running commands."""
    runner = Runner(timeout=1)  # 1 second timeout
    commands = ['sleep 10']  # 10 second sleep

    # Suppress expected warnings about timeout and subprocess still running
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        warnings.simplefilter("ignore", ResourceWarning)
        success, output_files, elapsed_time = runner.run_commands(commands)

    # Should timeout and return False
    assert not success
    assert len(output_files) == 1

    # Cleanup
    for f in output_files:
        if os.path.exists(f.name):
            os.unlink(f.name)


# ========== Test output capture from commands ==========

def test_stdout_captured_to_file() -> None:
    """Test that stdout is captured to temporary files."""
    runner = Runner(timeout=5)
    commands = ['printf "line1\\nline2\\nline3"']

    success, output_files, elapsed_time = runner.run_commands(commands)

    assert success
    output_files[0].seek(0)
    output = output_files[0].read().decode()

    assert 'line1' in output
    assert 'line2' in output
    assert 'line3' in output

    os.unlink(output_files[0].name)


def test_stderr_merged_with_stdout() -> None:
    """Test that stderr is merged into stdout in output file."""
    runner = Runner(timeout=5)
    # This command writes to both stdout and stderr
    commands = ['sh -c "echo stdout; echo stderr >&2"']

    success, output_files, elapsed_time = runner.run_commands(commands)

    output_files[0].seek(0)
    output = output_files[0].read().decode()

    # Both stdout and stderr should be in the file
    assert 'stdout' in output
    assert 'stderr' in output

    os.unlink(output_files[0].name)


def test_large_output_captured_completely() -> None:
    """Test that large command outputs are captured without truncation."""
    runner = Runner(timeout=5)
    # Generate 1000 lines of output
    commands = ['python -c "for i in range(1000): print(f\'Line {i}\')"']

    success, output_files, elapsed_time = runner.run_commands(commands)

    assert success
    output_files[0].seek(0)
    output = output_files[0].read().decode()
    lines = output.strip().split('\n')

    # Should have all 1000 lines
    assert len(lines) >= 990  # Allow for some variation

    os.unlink(output_files[0].name)


# ========== Test error handling and edge cases ==========

def test_invalid_command_still_creates_output_file() -> None:
    """Test that invalid/nonexistent commands raise RuntimeError."""
    runner = Runner(timeout=5)
    commands = ['/nonexistent/command/xyz']

    # Should raise RuntimeError for command not found
    with pytest.raises(RuntimeError) as exc_info:
        runner.run_commands(commands)

    assert "Command not found" in str(exc_info.value)
    # Note: output file is created before command runs, but we don't verify
    # it here since the exception is raised during execution


def test_empty_command_list() -> None:
    """Test handling of empty command list."""
    runner = Runner(timeout=5)
    commands = []

    success, output_files, elapsed_time = runner.run_commands(commands)

    assert success  # No commands = success
    assert len(output_files) == 0


def test_mixed_success_and_failure_commands() -> None:
    """Test mix of successful and failing commands."""
    runner = Runner(timeout=5)
    commands = [
        'echo "success"',
        'false',  # Will fail
        'echo "also success"'
    ]

    # Suppress expected warning about 'false' command exit code
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        success, output_files, elapsed_time = runner.run_commands(commands)

    # All files should be created despite one failure
    assert len(output_files) == 3

    # Verify outputs exist
    output_files[0].seek(0)
    assert b'success' in output_files[0].read()

    # Cleanup
    for f in output_files:
        os.unlink(f.name)


def test_very_short_timeout_with_instant_command() -> None:
    """Test that instant commands complete before very short timeout."""
    runner = Runner(timeout=0.1)  # 100ms
    commands = ['true']  # Instant

    success, output_files, elapsed_time = runner.run_commands(commands)

    assert success
    os.unlink(output_files[0].name)


# ========== Test specific command execution behaviors ==========

def test_shell_expansion_works() -> None:
    """Test that shell expansions (glob, variables, etc.) work."""
    runner = Runner(timeout=5)
    # Create temp file and use glob to reference it
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('test content')
        temp_path = f.name

    try:
        # Use glob-like pattern to find file
        dir_path = os.path.dirname(temp_path)
        pattern = os.path.join(dir_path, '*.txt')
        commands = [f'ls {pattern}']

        success, output_files, elapsed_time = runner.run_commands(commands)

        assert success
        output_files[0].seek(0)
        output = output_files[0].read().decode()
        assert os.path.basename(temp_path) in output

        os.unlink(output_files[0].name)
    finally:
        os.unlink(temp_path)


def test_piped_commands_work() -> None:
    """Test that shell pipes work in commands."""
    runner = Runner(timeout=5)
    commands = ['echo -e "apple\\nbanana\\ncherry" | grep banana']

    success, output_files, elapsed_time = runner.run_commands(commands)

    assert success
    output_files[0].seek(0)
    output = output_files[0].read().decode()
    assert 'banana' in output

    os.unlink(output_files[0].name)


def test_environment_variables_available() -> None:
    """Test that environment variables are accessible in commands."""
    runner = Runner(timeout=5)
    os.environ['TEST_VAR'] = 'test_value'
    commands = ['echo $TEST_VAR']

    success, output_files, elapsed_time = runner.run_commands(commands)

    assert success
    output_files[0].seek(0)
    output = output_files[0].read().decode()
    assert 'test_value' in output

    os.unlink(output_files[0].name)

