"""
Base class for all launchers. Provides the basic Launcher API.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
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
        self._topdir, _ = os.path.split(os.path.abspath(__file__))
        self._fndir, _ = os.path.split(os.path.abspath(self._topdir))
        self._fndir = os.path.join(self._fndir, "fns")
        self._input_fd = self.__get_input_fd(options)
        self._venv_path = os.path.join(self._topdir, "../venv-sharp/bin")

        self._task = options["task"]
        self._func = options["function"]
        self._args = options["arguments"]
        self._mpl = options["copies"]
        self._verbose = options["verbose"]
        self._timeout = options.get("timeout", None)
        self._mopts = options.get("metrics", {})
        self._sys_spec: Dict[str, str] = options.get("sys_spec_commands", {})
        self._fn_path = options.get("fn_path", "")

    ###################
    def reset(self) -> None:
        """Reset all caches and stale data for function so that next launch is cold."""
        pass

    ###################
    def _find_exec(self, func: str) -> str:
        """
        Search an executable for a given function name `func`.

        The search order is:
        1. If fn_path is specified in backend options, return path with python file.
        2. If func is an absolute path and exists, return it directly
        3. Look for `func`[.ext] in the fns/<func> directory
        4. If none found, return the original func path
        """
        # Check if custom function path is specified
        if hasattr(self, '_fn_path') and self._fn_path:
            return os.path.join(self._fn_path, f"{func}.py")

        # If func is an absolute path and exists, return it directly
        if os.path.isabs(func) and os.path.isfile(func):
            return func

        # Search in fns directory using basename of func for directory name
        func_name = os.path.basename(func)
        fdir: str = os.path.join(self._fndir, func_name)
        for fn in glob.glob(os.path.join(fdir, f"{func_name}.*")):
            if os.path.isfile(fn) and os.access(fn, os.X_OK):
                return fn

        # Return original func path if no match found
        return func

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
    def parse_auto_metrics(self, output: str) -> Dict[str, List[str]]:
        """Extract all the metric names and lists of values from output."""
        metrics: Dict[str, List[str]] = {}
        for line in output.splitlines():
            cols = line.split()
            name = cols[0]
            if name in metrics:
                metrics[name].append(cols[1])
            else:
                metrics[name] = [cols[1]]

        return(metrics)


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
                (one dictionary per run and ranks). if timeout exceeded
                or subprocess failed or extraction failed, None is returned.
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
            else:       # Normal case (no errors):
                if name != "auto":
                    metrics[name] = result.stdout.split()
                else:
                    mets = self.parse_auto_metrics(result.stdout)
                    metrics.update(mets)

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
                    stderr=subprocess.STDOUT
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
