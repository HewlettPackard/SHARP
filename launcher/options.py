"""
Parse options from command line and configuration files into dictionary.

The top-level function process_options reads in configuration from four sources:
    1. A previous experiment's .md file, if passed with the --repro flag.
    2. One or more YAML/JSON files with dictionaries of options.
    3. An optional JSON string with dictionary of options if passed with the -j flag.
    4. One or more command line flags.

The order above is of increasing priority, such that a command-line option overrides
a JSON string from -j, which overrides a config YAML/JSON file, which overrides .md.

© Copyright 2024--2024 Hewlett Packard Enterprise Development LP
"""
import argparse
import json
import os
from typing import *
import warnings
import yaml

mydir, _ = os.path.split(os.path.abspath(__file__))
logtop, _ = os.path.split(mydir)
logdir: str = os.path.join(logtop, "runlogs")

opt_defaults: Dict[str, Any] = {
    "mpl": 1,
    "repeats": "1",
    "experiment": "misc",
    "directory": logdir,
    "timeout": 3600,
    "copies": 1,
}


###################
def parse_cmdline() -> argparse.Namespace:
    """Parse all command-line arguments using argparse."""
    p = argparse.ArgumentParser(
        description="Run a function on a given backend. Command-line overrides values taken from `default_config.json`. See `docs/launcher.md` for full documentation."
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
    p.add_argument("--repro", help="Load options from previous markdown file", nargs=1)
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
    )
    p.add_argument(
        "-r",
        "--repeats",
        help="How many times to repeat experiment, or adaptive stopping rule: use 'SE' for relative-standard-error threshold, 'CI' for relative-confidence-interval, 'HDI' for highest-density interval, 'BB' for block bootrapping when autocorrelations are suspected), 'GMM' for Gaussian mixture, 'DC' for automatic detection of distribution",
    )
    p.add_argument("-e", "--experiment", help="name of experiment for this function")
    p.add_argument("--description", help="optional description string for experiment")
    p.add_argument(
        "-t",
        "--task",
        help="name of task/logfile for this run, None defaults to function name",
    )
    p.add_argument("-d", "--directory", help="Top-level directory for logs")
    p.add_argument(
        "-i", "--input", help="filename with inputs to function, None defaults to stdin"
    )
    p.add_argument(
        "--timeout", help="Timeout in seconds to wait for function)", type=int
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
    with open(filename, "r") as f:
        if filename.endswith(".yaml"):
            return yaml.load(f, Loader=yaml.FullLoader)
        elif filename.endswith(".json"):
            return json.load(f)
        else:
            raise Exception(f"Unrecognized input file format {filename}")

    return {}


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
def process_previous_options(filename: str) -> Dict[str, Any]:
    """Reproduce option dictionary from a previous run's .md file."""
    copy: bool = False
    jstr: str = ""

    # First, the relevant portion of the .md file to another string:
    with open(filename, "r") as f:
        for line in f:
            if line.strip() == "## Runtime options":
                copy = True
            elif line.strip() == "## Field description":
                break
            elif copy:
                jstr += line

    return json.loads(jstr)


###################
def process_json_options(
    cfg: Dict[str, Any], args: argparse.Namespace
) -> Dict[str, Any]:
    """Merge options with JSON options read in from files or cmd-line string."""
    cfiles: List[List[str]] = \
        args.config if args.config else [[mydir + "/default_config.yaml"]]

    for fn in cfiles:
        merge(cfg, load_config(fn[0]))

    if args.json:
        merge(cfg, json.loads(args.json))

    return cfg


###################
def process_cmdline_options(
    cfg: Dict[str, Any], args: argparse.Namespace
) -> Dict[str, Any]:
    """Process options from command-line flags."""
    # Start with function name and its arguments, override previous values
    if args.func:
        cfg["function"] = args.func[0]
        cfg["arguments"] = " ".join(args.func[1:])

    # Process options that have default values if they're not already defined:
    for k in opt_defaults:
        if k in args and getattr(args, k):
            cfg[k] = getattr(args, k)
        elif k not in cfg:
            cfg[k] = cfg.get(k, opt_defaults[k])

    if args.backend:
        cfg["backends"] = [b[0] for b in args.backend]
    else:
        cfg["backends"] = cfg.get("backends", ["local"])

    if args.append:
        cfg["mode"] = "a"
    else:
        cfg["mode"] = cfg.get("mode", "w")

    if args.task:
        cfg["task"] = args.task
    else:
        cfg["task"] = cfg.get("task", cfg.get("function", None))

    if args.cold:
        cfg["start"] = "cold"
    elif args.warm:
        cfg["start"] = "warm"
    else:
        cfg["start"] = cfg.get("start", "normal")

    # Process optional arguments:
    cfg["verbose"] = args.verbose
    if args.description:
        cfg["description"] = args.description
    if args.input:
        cfg["datafile"] = args.input

    return cfg


###################
def process_options() -> Dict[str, Any]:
    """
    Create a dictionary of runtime options based on args.

    Handles option sources in a particular priority order, with each subsequent
    source potentially overriding previous options:
    - Previous .md file with --repro flag
    - Config file(s) with -f flag
    - JSON string with -j flag
    - Remaining-command line flags.
    """
    args: argparse.Namespace = parse_cmdline()
    cfg: Dict[str, Any] = {}

    if args.repro:
        cfg = process_previous_options(args.repro[0])
    cfg = process_json_options(cfg, args)
    cfg = process_cmdline_options(cfg, args)

    # Sanity checks for options:
    if "function" not in cfg or not cfg["function"]:
        raise RuntimeError("Missing required argument: function or program to run")

    if cfg["arguments"] != "" and "datafile" in cfg:
        warnings.warn(
            f"Warning: command-line arguments to function may conflict with input data file"
        )

    if args.verbose:
        print("Configuration:", cfg)
    return cfg
