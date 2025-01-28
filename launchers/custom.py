#!/usr/bin/env python3
"""
An implementation of catch-all launcher.

This launcher can be customized from the options dictionary, with some macro substitutions.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

from launcher import Launcher
import subprocess
from typing import *


class CustomLauncher(Launcher):
    """Flexible launcher based on command-line options."""

    ###################
    def __init__(self, backend: str, options: Dict[str, Any]) -> None:
        """
        Lookup reset and run commands for custom backend in options.

        Args:
            backend (str): identifier of current backend
            options (dictionary): all launcher options
        """
        super().__init__(backend, options)

        bopts: Dict[str, Any] = options.get("backend_options", {})
        assert (
            backend in bopts
        ), f"Can't have a custom backend {backend} without an options section for it"
        assert (
            "run" in bopts[backend]
        ), f"Can't have a custom backend {backend} without a run command"

        self.__reset_cmd = bopts[backend].get("reset", "")
        self.__run_cmd = bopts[backend]["run"]
        self.__spec_run_cmd = bopts[backend].get("run_sys_spec", "$SPEC_COMMAND")

    ###################
    def __expand_macros(self, src: str) -> str:
        """
        Replace special-meaning macros in a string with values from the Launcher.

        Currently supported macros are:
            $TASK: The name of the task
            $FN: The name of the function
            $ARGS: A string of space-separated arguments to the command/function
        In addition, $CMD and $MPL are substitited at `commands` for the actual
        command to run (possibly nested) and actual concurrency.
        """
        return (
            src.replace("$TASK", self._task)
            .replace("$FN", self._func)
            .replace("$ARGS", self._args)
        )

    ###################
    def reset(self) -> None:
        """Perform any reset activities to ensure cold start."""
        super().reset()
        if self.__reset_cmd:
            cmd = self.__expand_macros(self.__reset_cmd)
            subprocess.Popen(cmd, shell=True)

    ###################
    def run_commands(self, copies: int, nested: str = "") -> List[str]:
        """
        Compute a list of commands that would launch a task with a given number of copies.

        Args:
            copies (int): How many instances of the task to run
            nested (str): Nested commands to call instead of function, if defined

        Returns:
            list: Each sublists is a sequence of strings to issue
                  at the command line to run a single copy of the task.

        Replaces any instances of the `$MPL` macro with copies.
        """
        cmd: str = ""
        if nested:
            cmd = self.__run_cmd.replace("$CMD", nested)
        else:
            cmd = self.__run_cmd
            cmd = cmd.replace("$CMD", self._find_exec(self._func))
            cmd = cmd.replace("$MPL", str(copies))
            if "$ARGS" not in self.__run_cmd:
                cmd += " " + self._args
        cmd = self.__expand_macros(cmd)

        return [cmd] * copies

    ###################
    def sys_spec_commands(self) -> Dict[str, str]:
        """Compute a mapping from sys specs to commands to run to obtain system specifications."""
        ret: Dict[str, str] = {}

        for spec, scmd in self._sys_spec.items():
            cmd: str = self.__spec_run_cmd.replace("$SPEC_COMMAND", scmd)
            cmd = self.__expand_macros(cmd)
            ret[spec] = cmd

        return ret
