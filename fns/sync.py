#!/usr/bin/env python3
# Simple MPI peer-to-peer function that sends a number of messages up and
# down a ring.

from mpi4py import MPI
import sys
import time


def sync_updown(comm, rank, size):
    up = (rank + 1) % size
    down = (rank - 1 + size) % size

    from_up = comm.sendrecv(rank, dest=up)
    from_down = comm.sendrecv(rank, dest=down)


#    print("Rank", rank, "received", from_up, "from", up)
#    print("Rank", rank, "received", from_down, "from", down)


def sync(n=""):
    msgs = int(n)
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    comm.barrier()

    start = time.perf_counter()
    for i in range(msgs):
        sync_updown(comm, rank, size)
    t = round(time.perf_counter() - start, 5)
    return "Elapsed time (sec) to synchronize " + n + "times in sec: " + str(t)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        try:
            print("Please enter number of messages to synchronize:")
            n = sys.stdin.read()
        except Exception as ex:
            print("Required argument in stdin: no. of messages to synchronize")
            exit(-1)
    else:
        n = sys.argv[1]

    print(sync(n))
