#!/usr/bin/env python3
"""
Square a random matrix of a given size on the GPU.

This application creates a random matrix of size `N`x`N` and squares it.
It's the CUDA version of `matmul`.
The fast matrix-multiply code is adapted from [here](https://numba.readthedocs.io/en/stable/cuda/examples.html#id30).

The parameter `N` is passed either by argv[1] or in the body of the HTTP request.
The run time grows approximately as O(N<sup>3</sup>) and can therefore get too 
long for a function for `N`>10,000 or so.
Returns (prints) the time taken by the squaring.

The code uses `numba` and therefore requires a custom-built environment that 
installs it.  The code requires CUDA support and a custom environment and builder.
See more setup instructions [here](../setup/CUDA.md).

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""
from flask import request, Flask
import numpy as np
import math
import os
import subprocess
import sys
import time

# os.environ["CUDA_VISIBLE_DEVICES"] = "0"
# os.environ["NUMBA_ENABLE_CUDASIM"] = "2"
# os.environ["NUMBA_CUDA_DEBUGINFO"] = "1"

from numba import cuda, float32  # type: ignore

TPB = 16
"""
Controls threads per block and shared memory usage.
The computation will be done on blocks of TPBxTPB elements.
TPB should not be larger than 32 in this example
"""
_app = Flask(__name__)


@cuda.jit(cache=True)  # type: ignore
def device_matmul(A, B, C) -> None: # type: ignore
    """
    Perform matrix multiplication of C = A * B using CUDA shared memory.

    Reference: https://stackoverflow.com/a/64198479/13697228 by @RobertCrovella
    """
    # Define an array in the shared memory
    # The size and type of the arrays must be known at compile time
    sA = cuda.shared.array(shape=(TPB, TPB), dtype=float32)
    sB = cuda.shared.array(shape=(TPB, TPB), dtype=float32)

    x, y = cuda.grid(2)

    tx: int = cuda.threadIdx.x
    ty: int = cuda.threadIdx.y
    bpg: int = cuda.gridDim.x  # blocks per grid

    # Each thread computes one element in the result matrix.
    # The dot product is chunked into dot products of TPB-long vectors.
    tmp = float32(0.0)
    for i in range(bpg):
        # Preload data into shared memory
        sA[ty, tx] = 0
        sB[ty, tx] = 0
        if y < A.shape[0] and (tx + i * TPB) < A.shape[1]:
            sA[ty, tx] = A[y, tx + i * TPB]
        if x < B.shape[1] and (ty + i * TPB) < B.shape[0]:
            sB[ty, tx] = B[ty + i * TPB, x]

        # Wait until all threads finish preloading
        cuda.syncthreads()

        # Computes partial product on the shared memory
        for j in range(TPB):
            tmp += sA[ty, j] * sB[j, tx]

        # Wait until all threads finish computing
        cuda.syncthreads()
    if y < C.shape[0] and x < C.shape[1]:
        C[y, x] = tmp


@_app.route("/", methods=["POST"])
def square_gpu(n: str = "") -> str:
    """
    Wrapper for `device_matmul()`.

    Create a random square matrix and multiply it by itself on GPU.
    for reproducibility, we set a fixed seed for the rng.
    """
    if n == "":
        n = request.get_data(as_text=True)
    try:
        N: int = int(n)
    except Exception as ex:
        print("Required argument in stdin: dimension of matrix (int)")
        exit(-1)

    mat_h = np.random.default_rng(0).random((N, N))
    sq_h = np.zeros([N, N])
    cuda.pinned(mat_h)
    cuda.pinned(sq_h)
    threadsperblock = (TPB, TPB)
    blockspergrid_x = math.ceil(sq_h.shape[0] / threadsperblock[0])
    blockspergrid_y = math.ceil(sq_h.shape[1] / threadsperblock[1])
    blockspergrid = (blockspergrid_x, blockspergrid_y)

    start: float = time.perf_counter()
    mat_d = cuda.to_device(mat_h)
    sq_d = cuda.to_device(sq_h)
    device_matmul[blockspergrid, threadsperblock](mat_d, mat_d, sq_d)
    sq_h = sq_d.copy_to_host()

    t: float = round(time.perf_counter() - start, 5)
    return f"@@@ Time (sec) to square {n}x{n} matrices on gpu: {t}"


def main() -> str:
    """Fission entry point."""
    return square_gpu()


#######################################
if __name__ == "__main__":
    if os.getenv("FAAS_ENV") == "knative":
        ## Knative entry point
        _app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    N: str = ""
    if len(sys.argv) < 2:
        N = input("Enter dimension: ")
    else:
        N = sys.argv[1]

    print(square_gpu(N))
