#!/usr/bin/env python3
"""
Square a random matrix of a given size on the CPU.

This application creates a random matrix of size `N`x`N` and squares it.
Returns (prints) the time taken by the squaring.

The code uses `numpy` and therefore requires a custom-built environment that 
installs it.

The code can use up all available cores if the version of `numpy` supports it. The default python builder for Fission (using Alpine) does not support it. 
But if you create a custom builder/environment as described 
[here](../../docs/setup/fission.md), you can use multithreaded `numpy`.

The parameter `N` is passed either by argv[1] or in the body of the HTTP 
request.  The run time is somwhere between O(N<sup>2</sup>) and O(N<sup>3</sup>).
On a 24-core E5-2680 v3, this yields about 50s for `N`=20000.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""
from flask import request, Flask
import multiprocessing
import numpy as np
import sys
import time
import os
import warnings

# Ignore the pesky overflow warning
warnings.filterwarnings("ignore", category=RuntimeWarning)
_app = Flask(__name__)


##################
# Create a random square matrix and multiply it by itself on CPU.
# for reproducibility, we set a fixed seed for the PRNG.
@_app.route("/", methods=["POST"])
def square_cpu(n: str = "") -> str:
    """
    Square a random matrix of size n x n.

    Args:
        n (str, optional): size of matrix to square (one dimension).

    Returns:
        str: The duration of execution.
    """
    if n == "":
        n = request.get_data(as_text=True)
    N = int(n)

    mat = np.random.default_rng(0).random((N, N))

    start: float = time.perf_counter()
    sq = np.dot(mat, mat)
    t: float = round(time.perf_counter() - start, 5)

    return f"@@@ Time (sec) to square {N}x{N} matrices on {multiprocessing.cpu_count()} cores: {t}"


def main() -> str:
    """Fission entry point."""
    return square_cpu()


#################################
if __name__ == "__main__":
    N: str = ""
    if os.getenv("FAAS_ENV") == "knative":
        ## Knative entry point
        _app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    if len(sys.argv) < 2:
        try:
            N = input("Enter dimension: ")
        except Exception as ex:
            print("Required argument in stdin: dimension of matrix (int)")
            exit(-1)
    else:
        N = sys.argv[1]

    print(square_cpu(N))
