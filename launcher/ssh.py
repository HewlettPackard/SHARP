#!/usr/bin/env python3
"""
An implementation of launcher that runs tasks remotely using ssh.

This launcher *assumes* that the remote hosts are running the same OS or filesystem
as the localhost doing the launching, AND that all the runnable programs (functions/scripts)
are in the same path locations on all the remote machines as in the local host.
See launcher.py for API documentation.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

from launcher import Launcher
import platform
import shutil
from typing import *
import warnings


SSHCMD = shutil.which("ssh")


class SSHLauncher(Launcher):
    """Launch a program/function using ssh."""

    ###################
    def __init__(self, backend: str, options: Dict[str, Any]) -> None:
        """Initialize launcher."""
        super().__init__(backend, options)

        if SSHCMD is None:
            raise ValueError(
                "ssh not found on host system -- cannot execute ssh launcher"
            )
        self.__sshcmd = SSHCMD

        ssh_opts: Dict[str, Any] = options.get("backend_options", {}).get(backend, {})
        self.__hosts: List[str] = self.__get_host_list(ssh_opts)

    ###################
    def reset(self) -> None:
        """Initiate cold-start, No-op for this Launcher."""
        super().reset()
        pass  # Can't really reset remote machines

    ###################
    def __get_host_list(self, options: Dict[str, Any]) -> List[str]:
        """Get a list of hosts to run on, from options."""
        if options.get("hosts", "") != "":
            return str(options["hosts"]).split(",")
        elif options.get("hostfile", "") != "":
            return [fn.strip() for fn in open(options["hostfile"], "r")]
        else:
            warnings.warn(f"Warning: no host data means sshing to localhost only")
            return [platform.node()]

    ###################
    def run_commands(self, copies: int, nested: str = "") -> List[str]:
        """Return execution string from current and nested commands."""
        basecmd: str = self.__sshcmd
        funcmd: str = nested
        if not nested:
            funcmd = self._find_exec(self._func)
            funcmd += " " + self._args

        cmds: List[str] = []
        for i in range(copies):
            # Pick host round-robin from hosts:
            host: str = self.__hosts[i % len(self.__hosts)]
            cmd: str = f"{basecmd} {host} \"{funcmd}\""
            cmds.append(cmd)

        return cmds

    ###################
    def sys_spec_commands(self) -> Dict[str, str]:
        """Compute a mapping from sys specs to commands to run to obtain system specifications."""
        return { spec: f"{self.__sshcmd} {self.__hosts[0]} \"{cmd}\"" \
                for spec, cmd in self._sys_spec.items() }
