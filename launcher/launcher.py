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
import platform


class Launcher:
    """Flexible launcher based on command-line options."""

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
        self._backend = backend

        self._task = options["task"]
        self._func = options["function"]
        self._args = options["arguments"]
        self._mpl = options["copies"]
        self._verbose = options["verbose"]
        self._timeout = options.get("timeout", None)
        self._mopts = options.get("metrics", {})
        # Skip sys_specs if requested (useful for fast testing)
        if options.get("skip_sys_specs", False):
            self._sys_spec = {}
        else:
            self._sys_spec: Dict[str, Dict[str, str]] = options.get("sys_spec_commands", {})
        self._fn_path = options.get("fn_path", "")

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

        # Parse hosts for SSH-like backends
        self.__hosts = self.__parse_hosts(bopts[backend])

        # Parse MPI-specific options
        self.__mpiflags = bopts[backend].get("mpiflags", "")
        self.__tmp_path = bopts[backend].get("tmp_path", "/tmp/")

        # Create unique temporary directory for MPI if tmp_path is specified
        if "tmp_path" in bopts[backend]:
            # Create a unique temporary directory within the specified base path
            base_tmp = bopts[backend]["tmp_path"].rstrip("/")
            self.__unique_tmp_dir = tempfile.mkdtemp(prefix="mpi-stats-", dir=base_tmp if os.path.exists(base_tmp) else None)
            self.__unique_tmp_dir += "/"  # Ensure trailing slash for consistency

    ###################
    def __parse_hosts(self, backend_opts: Dict[str, Any]) -> List[str]:
        """Parse hosts from backend options, supporting hosts string or hostfile."""
        if "hosts" in backend_opts and backend_opts["hosts"]:
            return str(backend_opts["hosts"]).split(",")
        elif "hostfile" in backend_opts and backend_opts["hostfile"]:
            try:
                with open(backend_opts["hostfile"], "r") as f:
                    return [line.strip() for line in f if line.strip()]
            except FileNotFoundError:
                warnings.warn(f"Hostfile {backend_opts['hostfile']} not found, using localhost")
                return [platform.node()]
        else:
            # Default to localhost if no hosts specified
            return [platform.node()]

    ###################
    def reset(self) -> None:
        """Perform any reset activities to ensure cold start."""
        if self.__reset_cmd:
            cmd = self.__expand_macros(self.__reset_cmd)
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode != 0 and self._backend == "local":
                    # Special handling for local backend cache flushing
                    print("Flushing all filesystem caches...")
                    print("Can't reset caches. Consider adding this line to /etc/sudoers:")
                    print(f"{os.getlogin()}\tALL=NOPASSWD:\t/sbin/sysctl vm.drop_caches=3")
                    print("Stderr:", result.stderr)
                    raise PermissionError("Failed to flush filesystem caches")
            except Exception as e:
                if self._backend == "local":
                    # Re-raise with helpful message for local backend
                    raise
                else:
                    # For other backends, just warn but continue
                    warnings.warn(f"Reset command failed for backend {self._backend}: {e}")

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
    def __expand_macros(self, src: str, copy_index: int = 0) -> str:
        """
        Replace special-meaning macros in a string with values from the Launcher.

        Currently supported macros are:
            $TASK: The name of the task
            $FN: The name of the function
            $ARGS: A string of space-separated arguments to the command/function
            $HOST: Current host for round-robin selection (based on copy_index)
            $HOST0, $HOST1, etc.: Specific host by index
            $MPIFLAGS: MPI flags from backend options
            $TMP_PATH: Temporary path for MPI outputs (unique per execution)
        In addition, $CMD and $MPL are substitited at `commands` for the actual
        command to run (possibly nested) and actual concurrency.
        """
        result = (
            src.replace("$TASK", self._task)
            .replace("$FN", self._func)
            .replace("$ARGS", self._args)
            .replace("$MPIFLAGS", self.__mpiflags)
        )

        # Use unique temporary directory if available, otherwise fall back to configured tmp_path
        tmp_path = getattr(self, '_Launcher__unique_tmp_dir', self.__tmp_path)
        result = result.replace("$TMP_PATH", tmp_path)

        # Handle host macros
        if "$HOST" in result:
            # Round-robin host selection
            host = self.__hosts[copy_index % len(self.__hosts)] if self.__hosts else "localhost"
            result = result.replace("$HOST", host)

        # Handle specific host indices ($HOST0, $HOST1, etc.)
        for i, host in enumerate(self.__hosts):
            result = result.replace(f"$HOST{i}", host)

        return result

    ###################
    def __build_base_command(self, copies: int, nested: str = "") -> str:
        """
        Build the base command with CMD, MPL, and ARGS substitutions.

        This method handles the core command construction logic that's common
        to both MPI and non-MPI backends.

        Args:
            copies (int): Number of copies for MPL substitution
            nested (str): Nested commands to call instead of function, if defined

        Returns:
            str: Command with basic substitutions applied (before macro expansion)
        """
        if nested:
            cmd = self.__run_cmd.replace("$CMD", nested)
            # Always substitute $MPL for MPI backends, even when used as outer backends
            if self.__is_mpi_backend():
                cmd = cmd.replace("$MPL", str(copies))
            # Remove $ARGS from all the outer backends
            cmd = cmd.replace(" $ARGS", "").replace("$ARGS ", "").replace("$ARGS", "")
        else:
            cmd = self.__run_cmd
            cmd = cmd.replace("$CMD", self._find_exec(self._func))
            cmd = cmd.replace("$MPL", str(copies))
            if "$ARGS" not in self.__run_cmd:
                cmd += " " + self._args
        return cmd

    def __is_mpi_backend(self) -> bool:
        """
        Check if this is an MPI-style backend that handles concurrency internally.

        MPI backends use mpirun/mpiexec and handle all processes internally,
        so only one command should be created regardless of copy count.

        Returns:
            bool: True if backend is MPI-style (handles concurrency internally)
        """
        # More reliable detection: look for mpirun/mpiexec AND $MPL usage
        cmd_lower = self.__run_cmd.lower()
        has_mpi_command = any(mpi_cmd in cmd_lower for mpi_cmd in ['mpirun', 'mpiexec', 'srun'])
        has_mpl_macro = "$MPL" in self.__run_cmd
        return has_mpi_command and has_mpl_macro

    def __build_mpi_command(self, copies: int, nested: str = "") -> str:
        """
        Build a single MPI command that handles all processes internally.

        For MPI backends, we return a single command where mpirun manages
        multiple processes. This matches the behavior of the original mpi.py
        backend where --mpl translates to -np for mpirun.

        Args:
            copies (int): Number of MPI processes to run (becomes -np value)
            nested (str): Nested commands to call instead of function, if defined

        Returns:
            str: Single MPI command with macro expansion applied
        """
        cmd = self.__build_base_command(copies, nested)
        return self.__expand_macros(cmd, copy_index=0)

    def __build_parallel_commands(self, copies: int, nested: str = "") -> List[str]:
        """
        Build multiple commands for parallel execution (one per copy).

        For non-MPI backends (like SSH), we create one command per copy.
        Each command runs independently and may target different hosts
        (round-robin distribution for SSH).

        Args:
            copies (int): Number of command copies to create
            nested (str): Nested commands to call instead of function, if defined

        Returns:
            List[str]: List of commands, one per copy, with per-copy macro expansion
        """
        cmds = []
        for i in range(copies):
            cmd = self.__build_base_command(copies, nested)
            cmd = self.__expand_macros(cmd, copy_index=i)
            cmds.append(cmd)
        return cmds

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
        For MPI backends: returns single command that handles all processes internally.
        For SSH-like backends: distributes copies across hosts in round-robin fashion.
        """
        if self.__is_mpi_backend():
            # MPI backends return a single command that handles all processes internally
            return [self.__build_mpi_command(copies, nested)]
        else:
            # Non-MPI backends create one command per copy
            return self.__build_parallel_commands(copies, nested)

    ###################
    def handles_concurrency_internally(self) -> bool:
        """
        Check if this launcher handles concurrency internally (like MPI).

        Returns:
            bool: True if this launcher manages multiple processes internally
        """
        return self.__is_mpi_backend()

    ###################
    def sys_spec_commands(self) -> Dict[str, Dict[str, str]]:
        """Compute a mapping from sys specs to commands to run to obtain system specifications.

        Returns two-level nested dictionary: {group: {key: command}}
        """
        ret: Dict[str, Dict[str, str]] = {}

        for group, commands in self._sys_spec.items():
            ret[group] = {}
            for key, command in commands.items():
                cmd: str = self.__spec_run_cmd.replace("$SPEC_COMMAND", command)
                # Use first host for system specifications
                cmd = self.__expand_macros(cmd, copy_index=0)
                ret[group][key] = cmd

        return ret
