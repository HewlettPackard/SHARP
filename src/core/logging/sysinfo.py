"""
System specification collection.

Executes shell commands to collect system information (CPU, memory, OS, etc.)
for inclusion in experiment metadata and markdown output.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

import subprocess
from typing import Any


def collect_sysinfo(
    sys_spec_commands: dict[str, dict[str, str]],
    backend_options: dict[str, Any] | None = None,
    backend_names: list[str] | None = None
) -> dict[str, dict[str, str]]:
    """
    Execute system specification commands and collect results.

    Runs shell commands organized in groups (e.g., 'cpu', 'memory', 'os')
    to gather system information. Commands that fail return empty strings
    rather than error messages.

    If backend_options and backend_names are provided, commands are run through
    the backend composition chain (e.g., through SSH to remote host). This ensures
    system specs reflect the actual execution environment.

    Args:
        sys_spec_commands: Two-level dict mapping group name to
            {spec_name: shell_command}. Example:
            {
                "cpu": {"model": "lscpu | grep 'Model name'"},
                "memory": {"total": "free -h | grep Mem"}
            }
        backend_options: Optional backend configuration for command composition.
            If None, commands run locally without backend wrapping.
        backend_names: Optional list of backend names to compose.
            If None, commands run locally without backend wrapping.

    Returns:
        Two-level dict with same structure as input, with commands
        replaced by their output (or empty string on failure).

    Example:
        >>> commands = {"cpu": {"count": "nproc"}}
        >>> result = collect_sysinfo(commands)
        >>> result
        {"cpu": {"count": "8"}}
    """
    if not sys_spec_commands:
        return {}

    # Import here to avoid circular dependency
    from src.core.execution.command_composer import CommandComposer

    result: dict[str, dict[str, str]] = {}

    # If backends are provided, create composer
    # For sys specs, we create a minimal benchmark_spec with the command as entry_point
    composer = None
    if backend_options is not None and backend_names is not None:
        composer = CommandComposer(backend_options, benchmark_spec=None)

    for group, commands in sys_spec_commands.items():
        result[group] = {}
        for key, command in commands.items():
            try:
                if composer and backend_names:
                    # Treat sys spec command like a regular command
                    # entry_point becomes the sys spec command, args is empty
                    temp_spec = {"entry_point": command, "args": "", "task": ""}
                    temp_composer = CommandComposer(backend_options, temp_spec)

                    # Use compose() with template_key="run_sys_spec" to use run_sys_spec template
                    composed = temp_composer.compose(backend_names, copies=1, template_key="run_sys_spec")
                    if not composed:
                        result[group][key] = ""
                        continue
                    full_cmd = composed[0]
                else:
                    # Run directly without backend wrapping
                    full_cmd = command

                # Execute command and capture output
                output = subprocess.run(
                    full_cmd,
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=10  # Prevent hanging
                ).stdout.strip()

                # Decode unicode escapes if present
                try:
                    output = output.encode().decode('unicode_escape')
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass  # Keep original if decoding fails

                result[group][key] = output

            except subprocess.TimeoutExpired:
                # Command took too long
                result[group][key] = ""
            except Exception:
                # Any other error (command not found, etc.)
                result[group][key] = ""

    return result
