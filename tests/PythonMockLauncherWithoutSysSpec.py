#!/usr/bin/env python3
"""
Mock launcher implementations for testing.

This module provides mock launcher classes that can be used for testing
the launcher framework with different system specification configurations.

© Copyright 2024--2025 Hewlett Packard Enterprise Development LP
"""

from launcher import Launcher
from typing import *

class PythonMockLauncherWithoutSysSpec(Launcher):
    """A Mock launcher that has passthrough strings."""

    def __init__(self, backend: str, options: Dict[str, Any]) -> None:
        """Initialize mock launcher.

        Args:
            backend: identifier of current backend
            options: dictionary of all options
        """
        super().__init__(backend, options)

    def reset(self) -> None:
        """Initiate cold-start, No-op for this Launcher."""
        super().reset()

    def run_commands(self, copies: int, nested: str = "") -> List[str]:
        """Return execution string from current and nested commands.

        Args:
            copies: How many instances of the task to run
            nested: Nested commands to call instead of function, if defined

        Returns:
            List of command strings to execute
        """
        if not nested:
            nested = f"{self._find_exec(self._func)} {self._args}"

        cmd : str = f"/bin/echo {self.__class__.__name__}"
        cmds: List[str] = []
        for i in range(copies):
            cmds.append(f"{cmd}; {nested}")
        return cmds
