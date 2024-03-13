#!/usr/bin/env python3
"""
A simple CPU-stressor function.

This application creates an array in RAM and incmrements all the values in it
sequentially. It runs on the CPU and tests the performance of the memory 
bandwidth on a single thread.
The array size is drawn randomly from a gaussian distribution with a given 
mean and scale.
Returns (prints) the time taken by the process.

The code uses `numpy` and therefore requires a custom-built environment that installs it.

It takes two integer optional parameters in order.
The first parameter is the mean size of the array. If you want the array to be 
a constant size, just pass it as an only parameter.
If the second parameter is given, it is used as the scale of the Gaussian 
distribution (again, you can pass 0 for a constant size).
More details on the distribution can be found 
[here](https://numpy.org/doc/stable/reference/random/generated/numpy.random.normal.html).

The parameters are passed either by argv, stdin, or in the body of the HTTP request.

© Copyright 2022--2024 Hewlett Packard Enterprise Development LP
"""

from flask import request, Flask
from typing import *
import numpy as np
import sys
import time
import os

_app = Flask(__name__)


@_app.route("/", methods=["POST"])
def inc_cpu(mean: int = 0, scale: int = 0) -> str:
    """
    Increment an array in RAM.

    Args:
        mean (int, optional): Mean size of input array.
        scale (int, optional): Scale argument for Gaussian array size.

    Returns:
        str: The duration of execution.
    """
    if mean == 0:
        params: List[str] = request.get_data(as_text=True).split()
        mean = int(params[0])
        scale = int(params[1]) if len(params) > 1 else 0

    n: int = int(np.random.default_rng().normal(mean, scale))
    xs = np.ones(n, dtype=np.float64)

    start: float = time.perf_counter()
    for i in range(n):
        xs[i] += 1
    t: float = round(time.perf_counter() - start, 5)
    return f"@@@ Time in sec to increment an array of size {n}: {t}"


def main() -> str:
    """Fission entry point."""
    return inc_cpu()


#################################
if __name__ == "__main__":
    if os.getenv("FAAS_ENV") == "knative":
        ## Knative entry point
        _app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

    mean: int = 0
    scale: int = 0
    if len(sys.argv) < 2:
        try:
            mean = int(input("Enter mean array size: "))
            sc: str = input(
                "Enter standard deviation of array size (0 or nothing for constant size: "
            )
            scale = 0 if sc == "" else int(sc)
        except Exception as ex:
            print("Arguments: mean array size and (optional) size stddev\n")
            exit(-1)
    else:
        mean = int(sys.argv[1])
        scale = 0 if len(sys.argv) < 3 else int(sys.argv[2])

    print(inc_cpu(mean, scale))
