#!/usr/bin/env python3
"""
A simple I/O-bound benchmark "application".

This application reads in one or more input files with buffer cache disabled,
and for each one creates an output file with a ".out" appended to its filename.
Each output is a copy of the input using reverse byte order.

The program tries to disable the Linux buffer cache before reading to ensure actual disk I/O is performed and measured.
This application can serve as a simple I/O micro-benchmark.
Several example input files of different sizes can be used in the format `zeros-*m`.
The code recreates these files (if not already present), without the need for 
any external package or initialization.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

from flask import request, Flask
from typing import *
import os
import sys
import time
import subprocess

_app = Flask(__name__)


@_app.route("/", methods=["POST"])
def swap_bytes(fns: str = "") -> str:
    """
    Reverse the bytes in a list of files.

    For every file in the input list of filenames, try to locate the file in
    the current directory. If the file isn't there, it will create it and fill
    it with zeros (the number of bytes is the suffix of the filename).

    Then, for every input file, it will open an output file with a ".out" suffix
    and copy over all the input bytes in the file in reverse order.

    Args:
        fns (str): a space-separated list of filenames.

    Returns:
        str: a string with the time in seconds it took to reverse all files
    """
    if fns == "":
        fns = request.get_data(as_text=True)

    total_bytes: int = 0
    available_files: List[str] = os.listdir()

    for in_fn in fns.split():
        if in_fn not in available_files:
            execution_command = ["head", "-c", in_fn.split("-")[1], "/dev/zero"]
            popen = subprocess.Popen(
                execution_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            output, _ = popen.communicate()
            with open(in_fn, "wb") as file:
                file.write(output)

    start: float = time.perf_counter()

    for in_fn in fns.split():
        print(in_fn)
        fout = open(in_fn + ".out", "wb")
        fsize: int = os.path.getsize(in_fn)
        total_bytes += fsize

        with open(in_fn, "rb") as f:
            os.posix_fadvise(f.fileno(), 0, fsize, os.POSIX_FADV_DONTNEED)
            data: bytes = f.read()

        fout.write(data[::-1])
        fout.close()

    t: float = round(time.perf_counter() - start, 5)
    return f"@@@ Time (sec) to swap {total_bytes} bytes in sec: {t}"


def main() -> str:
    """Fission entry point."""
    return swap_bytes()


##################################
if __name__ == "__main__":
    if os.getenv("FAAS_ENV") == "knative":
        ## Knative entry point
        _app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

    fns: str = ""
    if len(sys.argv) < 2:
        try:
            fns = input("Please enter one or more filenames to swap in one line:")
        except Exception as ex:
            print("Required argument in stdin: list of filenames to swap")
            exit(-1)
    else:
        fns = " ".join(sys.argv[1:])

    print(swap_bytes(fns))
