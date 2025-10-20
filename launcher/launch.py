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

###################
def launcher_factory(backend: str, options: Dict[str, Any]) -> Launcher:
    """Return a fully-constructed Launcher object based on args."""
    bopts = options.get("backend_options", {})
    # Use default local backend if nothing is provided
    if backend is None:
        backend = "local"

    # All backends are now YAML-based - use standard Launcher
    return Launcher(backend, options)


###################
def log_run(
    pdata: Optional[RunData],
    log: Logger,
    repeater: Repeater,
    options: Dict[str, Any],
) -> None:
    """Log all results from a single run (with possibly multiple copies)."""
    # First, Log data shared across all copies:
    log.add_column(
        "repeat",
        str(repeater.get_count()),
        "int",
        "Batch number (iteration) when a task is repeated",
    )
    log.add_column("concurrency", options["copies"], "int", "No. of concurrent runs")
    assert pdata is not None

    # Log individual run data for all copies:
    outer: List[float] = pdata.get_outer()
    for i in range(len(outer)):
        log.add_row_data("rank", i, "int", "Concurrent run number")
        log.add_row_data(
            "outer_time",
            round(outer[i], 5),
            "numeric",
            "External measured run time (s); lower is better",
        )

        for metric in pdata.user_metrics():
            mopts = options.get("metrics", {})
            properties = mopts.get(metric, mopts.get("auto", {}))
            assert properties, f"Couldn't find properties for metric {metric}!"

            log.add_row_data(
                metric,
                pdata.get_metric(metric)[i],
                properties["type"],
                f"{properties['description']} ({properties['units']}); "
                + f"{'lower' if properties['lower_is_better'] else 'higher'} is better",
            )

    # Prepeare log for the next repetition, if any:
    log.save_csv(options["mode"])
    log.clear_rows()
    options["mode"] = "a"  # Subsequent writes to log shouldn't overwrite current data


###################
def chain_of_commands(
    launchers: List[Launcher], copies: int, override: str = "") -> List[str]:
    """
    Compute command-line string for first launcher that chains to all others.

    Only the last command actually runs on the last Launcher,
    all others run the commands for the next launcher.

    If any launcher in the chain handles concurrency internally (like MPI),
    the outer launcher should only create one command, letting the inner
    launcher handle the parallelism.

    Args:
        launchers: An ordered list of Launcher-class instances.
        copies: How many parallel copies to run the first command for.
        override: a command to override the last one, if nonempty.

    Returns:
        List[str]: A list of one or more parallel commands composed of the entire chain.
    """
    if len(launchers) == 1:
        return [override] if override else launchers[0].run_commands(copies)

    # Check if any launcher in the chain handles concurrency internally
    has_internal_concurrency = any(l.handles_concurrency_internally() for l in launchers)

    # Build the command chain from the end
    # The last launcher gets the full copies count if it handles concurrency internally
    last_launcher_copies = copies if launchers[-1].handles_concurrency_internally() else 1
    cmd: str = override if override else launchers[-1].run_commands(last_launcher_copies)[0]

    # Middle launchers get full copies if they handle concurrency internally, otherwise 1 copy
    for l in reversed(launchers[1:-1]):
        middle_copies = copies if l.handles_concurrency_internally() else 1
        cmd = l.run_commands(middle_copies, cmd)[0]

    # The first launcher gets the copy count if it handles concurrency internally,
    # otherwise gets 1 copy if any other launcher handles concurrency internally
    if launchers[0].handles_concurrency_internally():
        outer_copies = copies
    else:
        outer_copies = 1 if has_internal_concurrency else copies

    return launchers[0].run_commands(outer_copies, cmd)


###################
def get_sys_specs(launchers: List[Launcher]) -> Dict[str, Any]:
    """
    Run all system spec commands through the Launcher chain.

    Args:
        launchers: Ordered list of all Launchers

    Returns:
        Dictionary mapping every specification name to its value
        (two-level nested structure for grouped specs)
    """
    ret: Dict[str, Dict[str, str]] = {}
    sys_spec_commands = launchers[-1].sys_spec_commands()

    # If sys_spec_commands is empty, skip system specification collection
    # This can happen if --skip-sys-specs flag was used or sys_spec.yaml is missing
    if not sys_spec_commands:
        return {}

    for group, commands in sys_spec_commands.items():
        ret[group] = {}
        for key, command in commands.items():
            full_cmd: str = chain_of_commands(launchers, 1, command)[0].replace('\n', ';')
            try:
                result = subprocess.run(full_cmd, capture_output=True, text=True, shell=True) \
                    .stdout \
                    .encode() \
                    .decode('unicode_escape') \
                    .strip()
                ret[group][key] = result
            except Exception as error:
                print(f"Error during system specification {group}.{key} running {full_cmd}: {error}")
                ret[group][key] = f"Error: {error}"

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
    mode: str = options["mode"] # save it, it gets modified in log_run

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

        log_run(pdata, log, repeater, options)
        if not repeater(pdata):
            break

    log.save_md(mode, get_sys_specs(launchers))


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
