"""
Base class for all launchers. Provides the basic Launcher API.

© Copyright 2022--2024 Hewlett Packard Enterprise Development LP
"""

import glob
import os
from rundata import RunData
import subprocess
import sys
import tempfile
import time
from typing import *
import warnings


class Launcher:
    """Base class for all launchers."""

    ###################
    def __init__(self, backend: str, options: Dict[str, Any]) -> None:
        """
        Initialize Launcher from options.

        Args:
            backend (str): identifier of current backend
            options (dictionary): dictionary of all options
        """
        _topdir, _ = os.path.split(os.path.abspath(__file__))

        self._fndir, _ = os.path.split(os.path.abspath(_topdir))
        self._fndir = os.path.join(self._fndir, "fns")
        self._input_fd = self.__get_input_fd(options)

        self._task = options["task"]
        self._func = options["function"]
        self._args = options["arguments"]
        self._mpl = options["copies"]
        self._verbose = options["verbose"]
        self._timeout = options.get("timeout", None)
        self._mopts = options.get("metrics", {})
        self._sys_spec: Dict[str, str] = options.get("sys_spec_commands", {})

    ###################
    def reset(self) -> None:
        """Reset all caches and stale data for function so that next launch is cold."""
        pass

    ###################
    def _find_exec(self, func: str) -> str:
        """
        Search an executable for a given function name `func`.

        First, try to find the the first file matching the name `func`[.ext] in
        the specified `fndir`. the [.ext] extension is optional.
        If none found, return the OS path to the given file, assuming an
        explicit full-path to a binary was passed.
        """
        fdir: str = os.path.join(self._fndir, self._func)
        for fn in glob.glob(os.path.join(fdir, f"{func}.*")):
            if os.path.isfile(fn) and os.access(fn, os.X_OK):
                return fn

        return os.path.join(fdir, func)

    ###################
    def __get_input_fd(self, options: Dict[str, Any]) -> int:
        """Get an open file descriptor for the input data file or standard input."""
        if "datafile" in options:
            return open(options["datafile"], "r").fileno()
        else:
            return sys.stdin.fileno()

    ###################
    def _wait_for_run(self, popen, fp, timeout: int) -> None: # type: ignore
        """
        Wait for a run described by a popen object to terminate.

        Waiting can be limited to a timeout, if specified in options.
        Args:
            popen (Popen object): an alredy-open subprocess
            fp (File object): an alredy-opened File object containing subprocess output
            timeout (int): timeout in seconds for function
        """
        if timeout is None:
            status = popen.wait()
        else:
            try:
                status = popen.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f"Error: timeout of {timeout}s exceeded!")
                popen.kill()
                return None

        if self._verbose:
            fp.seek(0)
            output = fp.read()
            print(output.decode("utf-8"), end="")

        if status == 127:   # bash's "No such file or directory"
            raise RuntimeError(f"Failed to execute {popen.args}: no such file or directory")

        if status != 0:
            warnings.warn(f"executing function return status {status}")
            return None

    ###################
    def _get_metrics(self, fp, mopts: Dict[str, Any]) -> List[Dict[str, Any]]: # type: ignore
        """
        Get application metrics after run completion.

        Given a file with the output of a run, return a dictionary with its
        metrics values, as extracted from its output.

        Args:
            fp (File object): an alredy-opened File object containing subprocess output
            mopts (dictionary): A dictionary with discretionary options for metrics

            Returns:
                list: dictionaries mapping from metrics to values
                (one dictionary per run).  if timeout exceeded or subprocess
                failed or extraction failed, returns None.
        """
        if not mopts:
            return [{}]

        metrics = {}
        for name, mdata in mopts.items():
            cmd = f"cat {fp.name} | " + mdata["extract"]
            result = subprocess.run(cmd, text=True, capture_output=True, shell=True)
            if (
                result.returncode != 0
                or len(result.stderr) > 0
                or len(result.stdout) == 0
            ):
                warnings.warn(
                    f"Failed to extract output for metric {name}. Did you include the correct backend and output the metric from your program?\nReturn code {result.returncode}, stderr: {result.stderr}"
                )
                metrics[name] = ["NA"]
            else:
                metrics[name] = result.stdout.split()

        if len(set(map(len, metrics.values()))) != 1:
          raise Exception(f"Some metrics have fewer rows than others. Inspect metrics for duplicated/missing rows:\n{metrics}")

        ret = []
        for i in range(len(next(iter(metrics.values())))):
            ret.append({k: metrics[k][i] for k in metrics.keys()})
        return ret

    ###################
    def run(self, cmds: List[str]) -> Optional[RunData]:
        """
        Launch a list of commands in parallel.

        Args:
            cmds (list): tasks (command lines) to run in parallel

        Returns:
            Optional[RunData]: run data with metrics or None if failed.
        """
        pdata: RunData = RunData(self._mpl)
        timeout: int = int(self._timeout) if self._timeout else 60 * 60 * 24
        popens = []
        files = []

        for i in range(len(cmds)):
            files.append(tempfile.NamedTemporaryFile(suffix=str(i)))
            if self._verbose:
                print("Running:", cmds[i])
            popens.append(
                subprocess.Popen(
                    cmds[i],
                    stdout=files[-1],
                    stdin=self._input_fd,
                    text=True,
                    shell=True,
                )
            )

        t0: float = time.perf_counter()
        while (time.perf_counter() - t0) < timeout and len(popens) != 0:
            for i in range(len(popens)):
                self._wait_for_run(popens[i], files[i], timeout)
                metrics = self._get_metrics(files[i], self._mopts)
                for m in metrics:
                    pdata.add_run(m)
                popens.pop(i)
                files.pop(i)
                break

        return pdata if len(popens) == 0 else None

        print("Warning: task timeout exceeded!")
        return None

    ###################
    def run_commands(self, copies: int, nested: str = "") -> List[str]:
        """
        Compute a list of commands that would launch a task with a given number of copies.

        Args:
            copies (int): How many instances of the task to run
            nested: (str) Nested commands to call instead of function, if defined
        Returns:
            list: Each sublists is a sequence of strings to issue at the command
            line to run a single copy of the task.

        Needs to be implemented by each subclass separately
        """
        return []

    ###################
    def sys_spec_commands(self) -> Dict[str, str]:
        """Compute a mapping from sys specs to commands to run to obtain system specifications."""
        return self._sys_spec
