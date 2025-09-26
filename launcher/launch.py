#!/usr/bin/env python3
"""
Main interface to function launcher.

Run this from the command line with --help to list the various options and launching modes.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""
from logger import Logger
from repeater import *
from options import process_options
from rundata import RunData
import shlex
import subprocess
import sys
from typing import *
import warnings

from launcher import Launcher
from custom import CustomLauncher
from local import LocalLauncher
from mpi import MPILauncher
from ssh import SSHLauncher

###################
def launcher_factory(backend: str, options: Dict[str, Any]) -> Launcher:
    """Return a fully-constructed Launcher object based on args."""
    # In the absence of pattern matching (Python 3.10+), it's just a big if:
    if backend == "local":
        return LocalLauncher(backend, options)
    elif backend == "mpi":
        return MPILauncher(backend, options)
    elif backend == "ssh":
        return SSHLauncher(backend, options)
    elif backend in options["backend_options"]:
        return CustomLauncher(backend, options)
    else:
        raise RuntimeError(f"Unrecognized backend {backend}")


###################
def log_run(
    pdata: Optional[RunData],
    log: Logger,
    repeater: Repeater,
    options: Dict[str, Any],
    sys_specs: Dict[str, Any],
) -> None:
    """Log all results from a single run (with possibly multiple copies)."""
    # First, Log data shared across all copies:
    log.add_column(
        "repeat",
        str(repeater.get_count()),
        "int",
        "Batch number when a task is repeated",
    )
    log.add_column("concurrency", options["copies"], "int", "No. of concurrent runs")
    assert pdata is not None

    # Log individual run data for all copies:
    outer: List[float] = pdata.get_outer()
    for i in range(len(outer)):
        log.add_row_data("copy", i + 1, "int", "Run number (iteration)")
        log.add_row_data(
            "outer_time",
            round(outer[i], 5),
            "numeric",
            "External measured run time (s); lower is better",
        )
        for metric, properties in options.get("metrics", {}).items():
            log.add_row_data(
                metric,
                pdata.get_metric(metric)[i],
                properties["type"],
                f"{properties['description']} ({properties['units']}); "
                + f"{'lower' if properties['lower_is_better'] else 'higher'} is better",
            )

    # Prepeare log for the next repetition, if any:
    log.save_data(options["mode"], sys_specs)
    log.clear_rows()
    options["mode"] = "a"  # Subsequent writes to log shouldn't overwrite current data


###################
def chain_of_commands(
    launchers: List[Launcher], copies: int, override: str = "") -> List[str]:
    """
    Compute command-line string for first launcher that chains to all others.

    Only the last command actually runs on the last Launcher,
    all others run the commands for the next launcher.
    Only the first launcher runs `copies` times--the rest are set to run once,
    but since the launchers are chained, they all run `copies` times.

    Args:
        launchers: An ordered list of Launcher-class instances.
        copies: How many parallel copies to run the first command for.
        override: a command to override the last one, if nonempty.

    Returns:
        List[str]: A list of one or more parallel commands composed of the entire chain.
    """
    if len(launchers) == 1:
        return [override] if override else launchers[0].run_commands(copies)

    cmd: str = override if override else launchers[-1].run_commands(1)[0]
    for l in reversed(launchers[1:-1]):
        cmd = l.run_commands(1, cmd)[0]

    return launchers[0].run_commands(copies, cmd)


###################
def get_sys_specs(launchers: List[Launcher]) -> Dict[str, str]:
    """
    Run all system spec commands through the Launcher chain.

    Args:
        launchers: Ordered list of all Launchers

    Returns:
        Dictionary mapping every specification name to its value
    """
    ret: Dict[str, str] = {}
    for s, cmd in launchers[-1].sys_spec_commands().items():
        full_cmd: List[str] = shlex.split(chain_of_commands(launchers, 1, cmd)[0])
        try:
            ret[s] = subprocess.run(full_cmd, capture_output=True, text=True) \
            .stdout \
            .encode() \
            .decode('unicode_escape')
        except Exception as error:
            print(f"Error during system specification {s} running {full_cmd}: {error}")
            ret[s] = f"Error during system specification {s}: {error}"


    if not ret:
        warnings.warn("No system specifications to show. Did you forget to include default_config.yaml")

    return ret


###################
def run_task(
    launchers: List[Launcher], options: Dict[str, Any], log: Logger, repeater: Repeater
) -> None:
    """
    Run a single task repeatedly and log run data until no more repeats are needed.

    Args:
        launchers (list): All Launchers (only the first one gets to run)
        options (dictionary): Dictionary of program options
        log (Logger): A Logger instance to record run results
        repeater (Repeater): A Repeater instance to decide when to stop the run
    """
    cmds: List[str] = chain_of_commands(launchers, options["copies"])
    sys_specs = get_sys_specs(launchers)

    # Warmup backend if needed:
    if options["start"] == "warm":
        launchers[0].run(cmds)

    # Main task run loop, till Repeater says to stop:
    while True:
        if options["start"] == "cold":
            for l in launchers:
                l.reset()

        pdata: Optional[RunData] = launchers[0].run(cmds)
        if options["verbose"]:
            print(
                f'Completed run {repeater.get_count() + 1} for experiment {options["experiment"]} and task {options["task"]}'
            )
            sys.stdout.flush()

        if pdata is None:
            raise Exception("Error executing task--aborting!")

        log_run(pdata, log, repeater, options, sys_specs)
        if not repeater(pdata):
            break


#################### Main
if __name__ == "__main__":
    options: Dict[str, Any] = process_options()
    start: str = str(options["start"])
    task: str = str(options["task"])

    repeater: Repeater = repeater_factory(options)
    launchers: List[Launcher] = [
        launcher_factory(b, options) for b in options["backends"]
    ]

    # Prepeare log and save task-wide data
    log = Logger(options["directory"], task, options)
    log.add_column("task", task, "string", "Task name")
    log.add_column("start", start, "string", "Warm, cold, or normal start")

    # Finally, run the task repeatedly and log its performance data:
    run_task(launchers, options, log, repeater)
