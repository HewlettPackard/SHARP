"""
Unit tests for system information collection (sysinfo.py).

Tests real command execution, error handling, and output processing.
Uses actual shell commands to catch real bugs in subprocess handling.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from src.core.logging.sysinfo import collect_sysinfo


def test_real_commands_execute_and_strip_whitespace():
    """Real shell commands execute correctly with whitespace stripped."""
    commands = {
        'test': {
            'echo': 'echo "  hello  "',
            'true': 'true',  # No output
            'printf': 'printf "world\\n\\n"',
        }
    }

    result = collect_sysinfo(commands)

    # Verify whitespace stripping and structure preservation
    assert result['test']['echo'] == 'hello', "Leading/trailing whitespace should be stripped"
    assert result['test']['true'] == '', "Commands with no output should return empty string"
    assert result['test']['printf'] == 'world', "Trailing newlines should be stripped"


def test_failed_commands_return_empty_not_exception():
    """Nonexistent or failing commands return empty string without raising exceptions."""
    commands = {
        'failures': {
            'nonexistent': '/nonexistent/command/xyz',
            'bad_exit': 'sh -c "exit 1"',
            'stderr_only': 'sh -c "echo error >&2; exit 1"',
        }
    }

    # Should not raise, should return empty strings
    result = collect_sysinfo(commands)

    assert result['failures']['nonexistent'] == '', "Nonexistent command should return empty"
    assert result['failures']['bad_exit'] == '', "Non-zero exit should return empty"
    assert result['failures']['stderr_only'] == '', "stderr output should not be captured"


def test_unicode_escape_sequences_decoded():
    """Literal backslash-n sequences are decoded to actual newlines."""
    commands = {
        'unicode': {
            # printf with \\n creates literal \n in output, not newline
            'escaped': r'printf "line1\\nline2\\ttab"',
        }
    }

    result = collect_sysinfo(commands)

    # The unicode_escape decode should turn \n into actual newline
    assert '\n' in result['unicode']['escaped'], "Literal \\n should be decoded to newline"
    assert '\t' in result['unicode']['escaped'], "Literal \\t should be decoded to tab"


def test_preserves_multiline_output():
    """Actual multiline command output is preserved correctly."""
    commands = {
        'multiline': {
            'lines': 'printf "line1\\nline2\\nline3"',
        }
    }

    result = collect_sysinfo(commands)

    # Should have real newlines from printf
    lines = result['multiline']['lines'].split('\n')
    assert len(lines) == 3, "Should preserve all three lines"
    assert lines[0] == 'line1'
    assert lines[1] == 'line2'
    assert lines[2] == 'line3'
