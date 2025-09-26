#!/usr/bin/env python3
"""
Run benchmarks from the Rodinia suite for HPC on OpenMP.

This application can be used to run the benchmarks in Rodinia on the CPU using OpenMP.
It takes the benchmark name and its corresponding parameters as inputs.
More details about the benchmarks can be found [here](https://www.cs.virginia.edu/~skadron/Papers/rodinia_iiswc09.pdf).

Below is the list of all the available benchmarks with their default parameters (space separated):

    * backprop: 65536
    * bfs: 4 /app/rodinia/data/bfs/graph1MW_6.txt
    * heartwall: /app/rodinia/data/heartwall/test.avi 20 4
    * hotspot: 1024 1024 2 4 /app/rodinia/data/hotspot/temp_1024 /app/rodinia/data/hotspot/power_1024 output.out
    * kmeans: -n 4 -i /app/rodinia/data/kmeans/kdd_cup
    * lavaMD: -cores 4 -boxes1d 10
    * leukocyte: 5 4 /app/rodinia/data/leukocyte/testfile.avi
    * lud: -s 8000
    * needle: 2048 10 2
    * nn: /app/rodinia/data/nn/filelist.txt 5 30 90
    * particle_filter: -x 128 -y 128 -z 10 -np 10000
    * pathfinder: 100000 100 > pathfinder_out
    * sc: 10 20 256 65536 65536 1000 none output.txt 4
    * srad_v1: 100 0.5 502 458 4
    * srad_v2: 2048 2048 0 127 0 127 2 0.5 2

## Warning: The following functions do not work as intented and need to be updated:

    1. nn: The binary returns error while trying to read an input file.

## Note: For executing the binaries locally, you need to compile the 
[Rodinia benchmarks](https://github.com/yuhc/gpu-rodinia) on your system in the
folder `/usr/local/rodinia/`. It assumes that the binaries are combiled using 
the Makefile and are present in `/usr/local/rodinia/bin/linux/omp/`.
The launcher can be used for local execution as shown below:

    `./launcher/launch.py -b local rodinia-omp 'backprop 65536'`

The input parameters can be passed either by argv, stdin, or in the body of 
the HTTP request.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

from flask import request, Flask
from typing import *
import os
import sys
import time
import subprocess

_app = Flask(__name__)
_binpath: str = ""

rodinia_path: str = "/app/rodinia_3.1/"
"""Top-level path for Rodinia applications."""
commands: Dict[str, List[str]] = {}
"""Commands dictionary with function names as keys and their respective arguments as values."""


def _update_paths(rodinia_path: str) -> None:
    global _binpath
    global commands
    _binpath = rodinia_path + "bin/linux/omp/"
    data_path = rodinia_path + "data/"
    commands = {
        "backprop": ["65536"],
        "bfs": ["4", data_path + "bfs/graph1MW_6.txt"],
        "heartwall": [data_path + "heartwall/test.avi", "20", "4"],
        "hotspot": [
            "1024",
            "1024",
            "2",
            "4",
            data_path + "hotspot/temp_1024",
            data_path + "hotspot/power_1024",
            "output.out",
        ],
        "kmeans": ["-n", "4", "-i", data_path + "kmeans/kdd_cup"],
        "lavaMD": ["-cores", "4", "-boxes1d", "10"],
        "leukocyte": ["5", "4", data_path + "leukocyte/testfile.avi"],
        "lud": ["-s", "8000"],
        "needle": ["2048", "10", "2"],
        "nn": [data_path + "nn/filelist.txt", "5", "30", "90"],
        "particle_filter": ["-x", "128", "-y", "128", "-z", "10", "-np", "10000"],
        "pathfinder": ["100000", "100", ">", "pathfinder_out"],
        "sc": ["10", "20", "256", "65536", "65536", "1000", "none", "output.txt", "4"],
        "srad_v1": ["100", "0.5", "502", "458", "4"],
        "srad_v2": ["2048", "2048", "0", "127", "0", "127", "2", "0.5", "2"],
    }


@_app.route("/", methods=["POST"])
def exec_func(args: str = "") -> str:
    """Run the selected Rodinia benchmark with the given arguments."""
    if args == "":
        args = request.get_data(as_text=True)

    if args == "":
        return "No binary provided for execution"
    # Update path for binaries and command parameters
    _update_paths(rodinia_path)
    # Extract the binary name and form its command based on absolute path
    arg_lst: List[str] = args.split(" ")
    binary_name: str = arg_lst[0]
    if binary_name not in commands.keys():
        return "Not a valid binary"

    binary: str = _binpath + binary_name
    start: float = time.perf_counter()
    execution_command: List[str] = [binary]

    # Choose arguments to be provided
    if len(arg_lst) == 1:
        execution_command.extend(commands[binary_name])
    else:
        execution_command.extend(arg_lst[1:])

    # Execute the binary
    popen = subprocess.Popen(
        execution_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    popen.wait()
    output = popen.stdout.read().decode()  # type: ignore

    t: float = round(time.perf_counter() - start, 5)

    return f"{output}\n@@@ Time to execute function {binary_name}: {t}\n"


def main() -> str:
    """Fission entry point."""
    return exec_func()


#################################
if __name__ == "__main__":
    if os.getenv("FAAS_ENV") == "knative":
        ## Knative entry point
        _app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

    if os.getenv("FAAS_ENV") != "docker":
        rodinia_path = "/usr/local/rodinia/"

    args: str = ""

    if len(sys.argv) < 2:
        try:
            args = input(
                "Enter the function with parameters (optional) to be executed: "
            )
        except Exception as ex:
            print("Arguments: function name in string\n")
            exit(-1)
    else:
        args = " ".join(sys.argv[1:])
    print(exec_func(args))
