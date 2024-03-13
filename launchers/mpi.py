#!/usr/bin/env python3
"""
An implementation of Launcher that runs tasks using MPI.

Expects an additional 'mpiflags' option.
See launcher.py for API documentation.

© Copyright 2022--2024 Hewlett Packard Enterprise Development LP
"""
from launcher import Launcher
import shutil
from typing import *
import warnings

MPIRUN = shutil.which("mpirun")


class MPILauncher(Launcher):
    """Implementation of Launcher using mpirun."""

    ###################
    def __init__(self, backend: str, options: Dict[str, Any]) -> None:
        """Initialize launcher."""
        super().__init__(backend, options)

        if MPIRUN is None:
            raise ValueError(
                "mpirun not found on host system -- cannot execute mpi launcher"
            )
        self.__mpirun = MPIRUN

        self.__flags: str = (
            options.get("backend_options", {}).get("mpi", {}).get("flags", "")
        )
        if self.__flags == "":
            warnings.warn(f"Warning: missing MPI flags, will run on local host")

    ###################
    def reset(self) -> None:
        """Initiate cold-start, No-op for this Launcher."""
        super().reset()
        pass  # AFAIK, there's no way to reset MPI jobs

    ###################
    def run_commands(self, copies: int, nested: str = "") -> List[str]:
        """Return execution string from current and nested commands."""
        cmd: str = self.__mpirun
        cmd += f" -np {str(copies)} {self.__flags}"
        if nested:
            cmd += f" {nested}"
        else:
            cmd += f" {self._find_exec(self._func)}"
            cmd += f" {self._args}"

        return [cmd]

    ###################
    def sys_spec_commands(self) -> Dict[str, str]:
        """Compute a mapping from sys specs to commands to run to obtain system specifications."""
        return { spec: f"{self.__mpirun} -np 1 {cmd}" \
                for spec, cmd in self._sys_spec.items() }
