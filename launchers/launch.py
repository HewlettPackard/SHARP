#!/usr/bin/env python3
"""
Main interface to function launcher.

Run this from the command line with --help to list the various options and launching modes.

© Copyright 2022--2024 Hewlett Packard Enterprise Development LP
"""
import argparse
import json
from logger import Logger
import os
from repeater import *
from rundata import RunData
import shlex
import subprocess
import sys
from typing import *
import warnings
import yaml

from launcher import Launcher
from custom import CustomLauncher
from local import LocalLauncher
from mpi import MPILauncher
from ssh import SSHLauncher

mydir, _ = os.path.split(os.path.abspath(__file__))
logdir, _ = os.path.split(mydir)
logdir = os.path.join(logdir, "runlogs")


###################
def parse_cmdline() -> argparse.Namespace:
    """Parse all command-line arguments using argparse."""
    p = argparse.ArgumentParser(
        description="Run a function on a given backend. Command-line overrides values taken from `default_config.json`. See `docs/launcher.md` for full documentation.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    p.add_argument(
        "func",
        help="name of function to run (+ optional arguments)",
        nargs=argparse.REMAINDER,
    )
    p.add_argument(
        "-f",
        "--config",
        action="append",
        nargs=1,
        help="JSON or YAML filename with configuration. Multiple files are read in order.",
    )
    p.add_argument(
        "-j",
        "--json",
        help="JSON string with configuration (merges with config files without replacing)",
    )
    p.add_argument(
        "-b",
        "--backend",
        help="Execution environment to run in",
        action="append",
        nargs=1,
    )
    p.add_argument(
        "--mpl",
        help="multiprogramming level: number of concurrent copies to run",
        type=int,
        default=1,
    )
    p.add_argument(
        "-r",
        "--repeats",
        help="How many times to repeat experiment, or adaptive stopping rule: use 'SE' for relative-standard-error threshold, 'CI' for relative-confidence-interval, 'HDI' for highest-density interval, 'BB' for block bootrapping when autocorrelations are suspected), 'GMM' for Gaussian mixture, 'DC' for automatic detection of distribution",
    )
    p.add_argument(
        "-e",
        "--experiment",
        help="name of experiment for this function",
        default="misc",
    )
    p.add_argument("--description", help="optional description string for experiment")
    p.add_argument(
        "-t",
        "--task",
        help="name of task/logfile for this run, None defaults to function name",
    )
    p.add_argument(
        "-d", "--directory", help="Top-level directory for logs in)", default=logdir
    )
    p.add_argument(
        "-i", "--input", help="filename with inputs to function, None defaults to stdin"
    )
    p.add_argument(
        "--timeout",
        help="Timeout in seconds to wait for function)",
        type=int,
        default=3600,
    )
    p.add_argument(
        "-a",
        "--append",
        help="Append run data to previous runs, don't overwrite",
        action="store_true",
    )
    p.add_argument(
        "-v",
        "--verbose",
        help="print to stdout the output from each function run",
        action="store_true",
    )

    g1 = p.add_mutually_exclusive_group()
    g1.add_argument(
        "-c", "--cold", help="Attempt to start function cold", action="store_true"
    )
    g1.add_argument(
        "-w",
        "--warm",
        help="Warm up caches and backend before experiment",
        action="store_true",
    )

    return p.parse_args()


###################
def load_config(filename: str) -> Dict[str, Any]:
    """Load parameters from a JSON or YAML file into options dictionary."""
    config: Dict[str, Any] = {}
    with open(filename, "r") as f:
        if filename.endswith(".yaml"):
            config = yaml.load(f, Loader=yaml.FullLoader)
        elif filename.endswith(".json"):
            config = json.load(f)
        else:
            raise Exception(f"Unrecognized input file format {filename}")

    return config


###################
def merge(a: Dict[Any, Any], b: Dict[Any, Any], path: List[str] = []) -> Dict[str, Any]:
    """
    Recursively merge two dictionaries (e.g., configurations).

    Any sub-dictionary values are also merged, key by key.
    Adapted from https://stackoverflow.com/questions/7204805
    """
    for key in b:
        if key in a and isinstance(a[key], dict) and isinstance(b[key], dict):
            merge(a[key], b[key], path + [str(key)])
        else:
            a[key] = b[key]
    return a


###################
def process_options(args: argparse.Namespace) -> Dict[str, Any]:
    """Create a dictionary of runtime options based on args."""
    cfg: Dict[str, Any] = {}
    if not args.config:
        cfg = load_config(mydir + "/default_config.yaml")
    else:
        for fnlist in args.config:
            merge(cfg, load_config(fnlist[0]))

    if args.json:
        merge(cfg, json.loads(args.json))

    if not args.func:
        raise RuntimeError("Missing required argument: function or program to run")

    cfg["function"] = args.func[0]
    cfg["arguments"] = " ".join(args.func[1:])
    cfg["verbose"] = args.verbose
    cfg["start"] = "cold" if args.cold else "warm" if args.warm else "normal"
    cfg["task"] = args.task if args.task else cfg["function"]
    cfg["mode"] = "a" if args.append else "w"
    cfg["backends"] = [b[0] for b in args.backend] if args.backend else ["local"]
    if args.repeats:
        cfg["repeats"] = args.repeats
    if args.timeout:
        cfg["timeout"] = args.timeout
    if args.experiment:
        cfg["experiment"] = args.experiment
    if args.mpl:
        cfg["copies"] = args.mpl
    if args.description:
        cfg["description"] = args.description
    if args.input:
        cfg["datafile"] = args.input

    # Helpful (?) warnings:
    if cfg["arguments"] != "" and "datafile" in cfg:
        warnings.warn(
            f"Warning: command-line arguments to function may conflict with input data file"
        )

    if args.verbose:
        print("Configuration:", cfg)

    return cfg


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
    """Log all results from a single run."""
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
        full_cmd: str = shlex.split(chain_of_commands(launchers, 1, cmd)[0])
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

        if not repeater(pdata):
            break

    sys_specs = get_sys_specs(launchers)
    log_run(pdata, log, repeater, options, sys_specs)


#################### Main
if __name__ == "__main__":
    args: argparse.Namespace = parse_cmdline()
    options: Dict[str, Any] = process_options(args)
    start: str = str(options["start"])
    task: str = str(options["task"])

    repeater: Repeater = repeater_factory(options)
    launchers: List[Launcher] = [
        launcher_factory(b, options) for b in options["backends"]
    ]

    # Prepeare log and save task-wide data
    log = Logger(args.directory, task, options)
    log.add_column("task", task, "string", "Task name")
    log.add_column("start", start, "string", "Warm, cold, or normal start")

    # Finally, run the task repeatedly and log its performance data:
    run_task(launchers, options, log, repeater)
