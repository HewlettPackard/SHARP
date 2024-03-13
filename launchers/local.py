#!/usr/bin/env python3
"""
An implementation of launcher that runs tasks on the local machine.

See launcher.py for API documentation.

© Copyright 2022--2024 Hewlett Packard Enterprise Development LP
"""
from launcher import Launcher
import os
import subprocess
from typing import *


class LocalLauncher(Launcher):
    """Launch program/function on local host."""

    ###################
    def __init__(self, backend: str, options: Dict[str, Any]) -> None:
        """Initialize launcher."""
        super().__init__(backend, options)

    ###################
    def reset(self) -> None:
        """Flush filesystem cache to ensure cold run."""
        super().reset()
        print("Flushing all filesystem caches...")
        try:
            cmd = ["sudo", "sh", "-c", "/usr/bin/sync; /sbin/sysctl vm.drop_caches=3"]
            subprocess.run(cmd)
        except PermissionError:
            print("Can't reset caches. Consider adding this line to /etc/sudoers:")
            print(f"{os.getlogin()}\tALL=NOPASSWD:\t/sbin/sysctl vm.drop_caches=3")
            raise

    ###################
    def run_commands(self, copies: int, nested: str = "") -> List[str]:
        """Return execution string from current and nested commands."""
        cmd: str = nested
        if not nested:
            cmd = self._find_exec(self._func)
            cmd += f" {self._args}"

        return [cmd] * copies
