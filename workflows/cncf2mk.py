#!/usr/bin/env python3
"""
Convert CNCF workflow to Makefile.

This script reads in a single workflow file in JSON format, conforming to a
subset of CNCF Serverless Workflow Format v. 0.8, and creates a Makefile out 
of the workflow, representing the state transitions as calls to `launch.py`.
Simply call it with a single filename argument.

The specification for the CNCF format can be found [here](https://github.com/serverlessworkflow/specification/blob/main/specification.md)
The accepted subset of the workflow standard includes:
- States of the types: Operation, Sleep, Parallel
- `parallel` actionMode for actions
- Action timeouts, which are passed along to `launcher.py`
- A susbset of functions, designed to be run by launcher.py or the shell
- functionRef arguments, which are passed to launcher

It doesn't include:
- Foreach, Inject, Event, Callback, and Switch states
- Parsing of jq expression, and in particular, variables
- Events
- Filters

The standard is also extended/interpreted in these ways:
- WF metadata, which is passed as options to launcher (icluding "verbose")
- function metadata, which includes the launcher backend (or 'local' for shell)
- 'fnargs' dictionary in function arguments, which are passed to the invoked function

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import isodate  # type: ignore
import json
import os
import sys
from typing import *
from warnings import warn
import yaml

LAUNCHER_CMD = "$(launcher)"

####################################################################
# Code to interpret a workflow file


#########################
def load_workflow(filename: str) -> Dict[str, Any]:
    """
    Read a workflow from a file and return it as a Python object.

    The current implementation literally just slurps in the JSON data as-is
    and returns it with no verification or processing.
    If we ever need more powerful parsing, we could import the SDK from
    [here](https://github.com/serverlessworkflow/sdk-python, but for the time
    being, we can keep the dependencies to a minimum.

    Returns:
      Dict[str, Any]: workflow data as a nested dictionary.
    """
    wf: Dict[str, Any]
    with open(filename, "r") as f:
        if filename.endswith(".yaml"):
            wf = yaml.load(f, Loader=yaml.FullLoader)
        elif filename.endswith(".json"):
            wf = json.load(f)
        else:
            raise Exception(f"Unrecognized input file format {filename}")

    return wf


#########################
def parse_wf_functions(fns) -> Dict[str, str]:
    """
    Parse functions.

    For each function definition in the workflow file, create a template
    for a Makefile recipe for that function (no targets or dependencies)

    Returns:
      Dict[str, Any]: a mapping from function name to Makefile recipe.
    """
    ret = {}
    for fn in fns:
        assert fn.get("type") == "custom", "All functions must have 'custom' type"
        assert "backend" in fn.get(
            "metadata", {}
        ), "All functions must have 'backend' metadata value"
        backend = fn["metadata"]["backend"]
        assert backend in [
            "verbatim",
            "fission",
            "ssh",
            "local",
            "mpi",
        ], f"Unrecognized backend ${backend}"

        recipe = ""
        if backend != "verbatim":
            recipe += f"{LAUNCHER_CMD} "
            recipe += "-e $(id) "
            recipe += f"-p {backend} "

        recipe += f"{fn['operation']}"

        ret[fn["name"]] = recipe

    return ret


#########################
def parse_wf(wf):
    """Break up a workflow to a tuple of variables, states, functions, and metadata."""
    # First, check that none of the required info fields are missing:
    req = {"id", "start", "states", "functions"}
    missing = req.difference(wf.keys())
    assert len(missing) == 0, f"Missing fields in workflow: {missing}"

    states = wf["states"]
    functions = parse_wf_functions(wf["functions"])
    metadata = wf["metadata"] if "metadata" in wf else {}

    # Collect variables:
    variables = {
        k: v
        for k, v in wf.items()
        if k != "states" and k != "functions" and isinstance(v, str)
    }
    variables["end"] = " ".join([s["name"] for s in states if s.get("end")])
    if variables["end"] == "":
        warn("Workflow has no end states!")

    return variables, states, functions, metadata


####################################################################
# Code to actually generate the Makefile


def parse_wf_variables(targets) -> str:
    """
    Copy over variables from workflow to Makefile, returned as a string.

    Convert states to targets if they're in the target list.
    """
    ret: str = ""
    for k, v in variables.items():
        if v in targets:
            v = targets[v]
        ret += f"{k} := {v}\n"

    return ret


#########################
def create_mf_variables(variables, states, metadata):
    """Generate new variables specific to the Makefile."""
    if "basedir" in metadata:
        basedir = metadata["basedir"]
    else:
        me = os.path.abspath(__file__)
        basedir, _ = os.path.split(me)
        basedir, _ = os.path.split(basedir)

    outdir = os.path.join("$(basedir)", "runlogs", variables["id"])
    launcher = os.path.join("$(basedir)", "launchers", "launch.py")
    if "description" in variables:
        launcher += f' --description "$(description)"'
    if metadata.get("verbose") == "True" or metadata.get("verbose") == "yes":
        launcher += " -v"

    return f"""
basedir := {basedir}
outdir := {outdir}
launcher := {launcher}
"""


#########################
def create_std_mf_rules(variables, states, targets) -> str:
    """
    Create standard rules for "clean", "all", etc.

    Args:
        variables (dictionary): All Makefile variables and values.
        states (list): dictionaries with wf state data.
        targets (dictionary): A mapping from state/branch names to targets.

    Returns:
        str: a multline string excerpt of a Makefile.
    """
    snames: List[str] = [s["name"] for s in states]
    assert len(snames) > 0, "Need at least one named state in workflow"

    csvs: List[str] = [k for k in targets.values() if k.endswith(".csv")]
    phonies: List[str] = [k for k in targets.values() if k not in csvs]

    report: str = variables["id"] + ".pdf"

    ret: str = f"csv_files := {' '.join(csvs)}\n"
    ret += f"""

.PHONY: clean {' '.join(phonies)}

all:
\tmkdir -p $(outdir)
\tcd $(outdir); make -f $(abspath $(lastword $(MAKEFILE_LIST))) {report}

{report}: $(end)
\t@echo compiling final report in `pwd`...

clean:
\trm -rf {report} $(csv_files)
"""

    return ret


#########################
def is_launched(actions, fns) -> bool:
    """
    Return whether a particular state/branch calls any launcher function.

    Args:
        actions (list): All actions of current state or branch
        fns (dictionary): Mapping from function names to Makefile recipes

    Returns:
        bool: whether a launcher function is called
    """
    found: int = 0
    for action in actions:
        fname: str = action["functionRef"]["refName"]
        if LAUNCHER_CMD in fns[fname]:
            found += 1

    assert found <= 1, f"State has more than one launcher function!"

    return found == 1


#########################
def compute_targets(states: List[Any], fns: List[Any]) -> Dict[str, Any]:
    """
    Compute all of the Makefile targets.

    Simple workflow states correspond 1:1 to targets if they run a single
    launcher function that produces a CSV file.
    Parallel states that invoke more than one function or states that don't
    call the launcher to produce a regular CSV file are "phony" targets in the
    Makefile sense: They can be executed, but can't be checked for recency.

    Args:
      states (list): dictionaries with wf state data
      fns (list): dictionaries with wf function data

    Returns:
        Dict[str, Any]: a mapping from states or actions to Makefile targets
    """
    targets: Dict[str, Any] = {}
    for s in states:
        stype = s["type"]
        targets[s["name"]] = s["name"]

        if stype == "operation":
            launched = is_launched(s["actions"], fns)
            targets[s["name"]] += ".csv" if launched else ""

        elif stype == "parallel":
            for b in s["branches"]:
                launched = is_launched(b["actions"], fns)
                targets[b["name"]] = b["name"] + ".csv" if launched else ""

    return targets


#########################
def compute_dependencies(states, targets, start) -> Dict[str, Any]:
    """
    Compute all the stage dependencies for every stage.

    Simply iterates states and converts forward dependencies,
    as expressed with "transition" tags, to a reverse mapping.
    Uses targets instead of state names when recording dependencies.
    The only special case is a parallel state, where the dependencies are not
    the state itself but rather its branches.

    Args:
        states (list): dictionaries with wf state data
        targets (dictionary): A mapping from state/branch names to targets
        start (string): Name of starting state

    Returns:
        Dict[str, Any]: a mapping from targets to target dependencies
    """
    deps: Dict[str, Any] = {}
    for state in states:
        fwd: str = state.get("transition")
        if fwd is None:
            assert state.get("end"), "A state with no transition must be an end state"
            continue

        dep: List[str] = []
        if state["type"] != "parallel":
            dep = [targets[state["name"]]]
        else:
            dep = [targets[b["name"]] for b in state["branches"]]
            for b in state["branches"]:
                deps[targets[b["name"]]] = [targets[state["name"]]]

        # Append dependencies to transition target (or create empty list if new)
        dest: str = targets[fwd]
        if dest not in deps:
            deps[dest] = []
        deps[dest] += dep

    # Ensure starting state has no dependencies
    first: str = targets[start]
    assert first not in deps, "Initial state may not have dependencies"
    deps[first] = []

    return deps


#########################
def create_recipe(action, fns, timeout=None) -> str:
    """
    Create a single Makefile recipe from an action.

    Args:
        fns (dictionary): collection of all functions
        timeout (optional string): timeout value (in ISO 8601 duration)
    """
    fn: str = fns[action["functionRef"]["refName"]]
    cmd: List[str] = fn.split()
    args: Dict[str, Any] = action["functionRef"].get("arguments", {})

    if timeout is not None:
        to: int = int(isodate.parse_duration(timeout).total_seconds())
        cmd.insert(1, f"--timeout {to}")

    for arg, val in args.items():
        if arg == "fnargs":
            cmd.append(val)
        else:
            cmd.insert(1, f"{arg} {val}")

    return "\t" + " ".join(cmd)


#########################
def operation_rule(state, fns, targets, deps) -> str:
    """
    Create the complete rule for a given state of type 'operation'.

    Args:
        state (dictionary): Data for a single state
        fns (list): dictionaries with fn function data
        targets (dictionary): mapping from states/branches to target names
        deps (dictionary): mapping from targets to lists of targets (dependencies)
    """
    parallel: bool = state.get("actionMode") == "parallel"
    to: int = state.get("timeouts", {}).get("actionExecTimeout")
    target: str = targets[state["name"]]
    rule: str = f"\n{target}: {' '.join(deps[target])}\n"

    for action in state["actions"]:
        rule += create_recipe(action, fns, to)
        rule += " &\n" if parallel else "\n"

    if parallel:
        rule += "\twait\n"

    return rule


#########################
def parallel_rule(state, fns, targets, deps) -> str:
    """
    Create the complete rule(s) for a given state of type 'parallel'.

    Args:
        state (dictionary): Data for a single state
        fns (list): dictionaries with fn function data
        targets (dictionary): mapping from states/branches to target names
        deps (dictionary): mapping from targets to lists of targets (dependencies)
    """
    to: int = state.get("timeouts", {}).get("branchExecTimeout")
    target: str = targets[state["name"]]
    rules: str = f"\n{target}: {' '.join(deps[target])}\n"

    if state.get("completionType", "allOf") != "allOf":
        warn(
            f"Completion type {state['completionType']} not supported for state {target}, treated as 'allOf'"
        )

    for b in state["branches"]:
        target = targets[b["name"]]
        rules += f"\n{target}: {' '.join(deps[target])}\n"
        for action in b["actions"]:
            rules += create_recipe(action, fns, to) + "\n"

    return rules


#########################
def sleep_rule(state, fns, targets, deps) -> str:
    """
    Create the complete rule for a given state of type 'sleep'.

    Args:
        state (dictionary): Data for a single state
        fns (list): dictionaries with fn function data
        targets (dictionary): mapping from states/branches to target names
        deps (dictionary): mapping from targets to lists of targets (dependencies)
    """
    duration: int = int(isodate.parse_duration(state.get("duration")).total_seconds())
    target: str = targets[state["name"]]
    rule: str = f"\n{target}: {' '.join(deps[target])}\n"
    rule += f"\tsleep {duration}\n"
    return rule


#########################
def create_mf_rules(states, fns, targets, deps) -> str:
    """
    Create all Makefile rules for actual states.

    For every state, creates a Makefile rule with the state's name as target,
    states that transition into it as dependencies, and recipes for all the
    actions it needs to take. 'Parallel' states create more than one rule.

    Args:
        states (list): dictionaries with wf state data
        fns (list): dictionaries with fn function data
        targets (dictionary): mapping from states/branches to target names
        deps (dictionary): mapping from targets to lists of targets (dependencies)
    """
    rules: str = ""

    for state in states:
        handler = state["type"] + "_rule"
        assert handler in globals(), f"Unsupported state type '{state['type']}'"
        rules += globals()[handler](state, fns, targets, deps)

    return rules


#########################
def create_mf(variables, states, fns, metadata) -> str:
    """
    Create Makefile from workflow data.

    Args:
        variables (dictionary): Mapping from Makefile variables to values
        states (list): dictionaries with wf state data
        functions (list): dictionaries with fn function data
        metadada (dictionary): workflow- metadata field

    Returns:
        Complete Makefile in one string.
    """
    targets = compute_targets(states, fns)
    deps = compute_dependencies(states, targets, variables["start"])

    mf: str = parse_wf_variables(targets)
    mf += create_mf_variables(variables, states, metadata)
    mf += create_std_mf_rules(variables, states, targets)
    mf += create_mf_rules(states, fns, targets, deps)

    return mf


####################################################################
# Main: load file, translate, output Makefile

if __name__ == "__main__":
    assert len(sys.argv) == 2, "Error: expecting input filename"

    fn: str = sys.argv[1]
    wf = load_workflow(fn)

    variables, states, functions, metadata = parse_wf(wf)
    mf: str = create_mf(variables, states, functions, metadata)

    with open(fn.rsplit(".", 1)[0] + ".mk", "w") as f:
        f.write(mf)
