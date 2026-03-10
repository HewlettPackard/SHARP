"""
Subprocess execution and management.

Handles running shell commands with timeout, capturing output,
and collecting metrics from subprocess results.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

import subprocess
import tempfile
import time
import warnings
from typing import List, Optional, Tuple


class Runner:
    """
    Executes commands and manages subprocess lifecycle.

    Handles:
    - Parallel command execution
    - Timeout management
    - Output capture to temporary files
    - Return code and error handling
    """

    def __init__(self, timeout: Optional[int] = None, verbose: bool = False,
                 stdin_fd: int = -1) -> None:
        """
        Initialize runner.

        Args:
            timeout: Global timeout in seconds (default: 24 hours)
            verbose: Print command lines before execution
            stdin_fd: File descriptor for stdin (default: closed)
        """
        self.timeout = timeout or (60 * 60 * 24)  # Default: 24 hours
        self.verbose = verbose
        self.stdin_fd = stdin_fd if stdin_fd >= 0 else None

    def run_commands(self, commands: List[str], env: Optional[dict[str, str]] = None) -> Tuple[bool, List[tempfile._TemporaryFileWrapper[bytes]], float]:
        """
        Execute commands in parallel and wait for completion.

        Creates temporary files for stdout+stderr of each command,
        launches commands as Popen objects, and waits for all to complete
        or timeout.

        Args:
            commands: List of shell commands to execute in parallel
            env: Environment variables to set for subprocess (default: inherit parent)

        Returns:
            Tuple of (success: bool, output_files: List[TemporaryFile], elapsed_time: float)
            - success: True if all commands completed within timeout (even with non-zero exit)
            - output_files: List of temporary files with command outputs
                (caller responsible for reading and cleanup)
            - elapsed_time: Wall-clock time in seconds for command execution

        Raises:
            RuntimeError: If command fails catastrophically (not found, segfault, etc.)
        """
        t0 = time.perf_counter()
        popens, output_files = self._launch_commands(commands, env)
        success = self._wait_for_commands(popens, commands, t0)
        elapsed_time = time.perf_counter() - t0
        return success, output_files, elapsed_time

    def _launch_commands(self, commands: List[str], env: Optional[dict[str, str]] = None) -> Tuple[List[subprocess.Popen], List[tempfile._TemporaryFileWrapper[bytes]]]:
        """
        Launch all commands in parallel.

        Args:
            commands: List of shell commands to execute
            env: Environment variables to set for subprocess (default: inherit parent)

        Returns:
            Tuple of (popens, output_files)
        """
        popens = []
        output_files = []

        for i, cmd in enumerate(commands):
            output_file = tempfile.NamedTemporaryFile(suffix=f"_{i}", delete=False)
            output_files.append(output_file)

            if self.verbose:
                print(f"Running: {cmd}")

            popen = subprocess.Popen(
                cmd,
                stdout=output_file,
                stdin=self.stdin_fd,
                stderr=subprocess.STDOUT,
                text=True,
                shell=True,
                env=env,
            )
            popens.append(popen)

        return popens, output_files

    def _wait_for_commands(self, popens: List[subprocess.Popen], commands: List[str], start_time: float) -> bool:
        """
        Wait for all commands to complete, checking for catastrophic failures.

        Args:
            popens: List of Popen objects for running commands
            commands: Original command strings (for error messages)
            start_time: Time when commands were launched (for timeout calculation)

        Returns:
            True if all commands completed within timeout, False if timeout occurred

        Raises:
            RuntimeError: If command fails catastrophically (not found, segfault, etc.)
        """
        completed_commands = []

        while popens and (time.perf_counter() - start_time) < self.timeout:
            for i, popen in enumerate(popens):
                returncode = popen.poll()
                if returncode is not None:
                    # Command completed - check for catastrophic failures
                    cmd_index = len(completed_commands)
                    completed_commands.append((cmd_index, returncode))

                    match returncode:
                        case 0:
                            # Success - no action needed
                            pass
                        case 127:
                            # Command not found
                            raise RuntimeError(
                                f"Command not found (exit code 127): {commands[cmd_index]}"
                            )
                        case 126:
                            # Command not executable
                            raise RuntimeError(
                                f"Command not executable (exit code 126): {commands[cmd_index]}"
                            )
                        case n if n < 0:
                            # Killed by signal (negative return code means signal)
                            signal_num = -n
                            raise RuntimeError(
                                f"Command killed by signal {signal_num}: {commands[cmd_index]}"
                            )
                        case _:
                            # Non-zero but not catastrophic - just warn
                            warnings.warn(
                                f"Command {cmd_index} exited with code {returncode}: {commands[cmd_index]}"
                            )

                    popens.pop(i)
                    break
            else:
                # No command completed this iteration, sleep a bit
                time.sleep(0.01)

        if popens:
            # Timeout exceeded
            warnings.warn(
                f"Timeout exceeded ({self.timeout}s): {len(popens)} command(s) still running"
            )
            for popen in popens:
                popen.terminate()
            return False

        return True
