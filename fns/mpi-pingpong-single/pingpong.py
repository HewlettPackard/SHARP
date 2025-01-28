#!/usr/bin/env python3
"""
Simple MPI peer-to-peer function that sends a number of messages up and down a ring.

This function runs an MPI application in a single function instance.
The MPI application is a Python program using the `mpi4py` library.
It performs a synchronization in a ring using `N` ranks, all in the same 
function/container. `N` is a parameter passed to the function.

The function uses a binary environment with Python3 and OpenMPI installed.
It then executes `mpirun` in a script.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

from flask import request, Flask
from mpi4py import MPI
from typing import *
import sys
import time
import socket
import os

_app = Flask(__name__)


def _sync_updown(comm: Any, rank: int, size: int) -> None:
    """Exchange a message with one neighbor up and down the ring."""
    up: int = (rank + 1) % size
    down: int = (rank - 1 + size) % size

    _ = comm.sendrecv(rank, dest=up)
    _ = comm.sendrecv(rank, dest=down)
    # print("Rank", rank, "received", from_up, "from", up)
    # print("Rank", rank, "received", from_down, "from", down)


@_app.route("/", methods=["POST"]) # type: ignore
def pingpong(n: str = "") -> str:
    """
    Iteratively exchange messages up and down the ring of MPI processes.

    Sets up the MPI COMM WORLD and starts exchanging messages in a loop.

    Args:
        n (str, optional): The number of synchronization steps (loops) to run.

    Returns:
        str: The duration of execution.
    """
    if n == "":
        n = request.get_data(as_text=True)
    try:
        msgs: int = int(n)
    except ValueError as ve:
        print(f"Given number of messages is not a number: {n}")

    comm = MPI.COMM_WORLD
    rank: int = comm.Get_rank()
    size: int = comm.Get_size()

    print(f"Rank {rank} executes on host {socket.getfqdn()}")

    comm.barrier()

    start: float = time.perf_counter()
    for _ in range(msgs):
        _sync_updown(comm, rank, size)

    t: float = round(time.perf_counter() - start, 5)
    return f"@@@ Time (sec) to synchronize {n} times in sec: {t}"


def main() -> str:
    """Fission entry point."""
    return pingpong()


#################################
if __name__ == "__main__":
    if os.getenv("FAAS_ENV") == "knative":
        ## Knative entry point
        _app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

    n: str = ""
    if len(sys.argv) < 2:
        try:
            print("Please enter number of messages to synchronize:")
            n = sys.stdin.read()
        except Exception:
            print("Required argument in stdin: no. of messages to synchronize")
            exit(-1)
    else:
        n = sys.argv[1]

    print(pingpong(n))
