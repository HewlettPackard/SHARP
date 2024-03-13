#!/usr/bin/env python3
"""
Bounce-back the request body.

This application reads in the entire body of the request and returns it as a 
string, together with the time it took to read the request.
This "kernel" time measures only the overhead of reading the request data 
through flask.
The complete two-way overhead of sending the request and reading it back can 
be measured as the roundtrip time from launching the function to completion.

© Copyright 2022--2024 Hewlett Packard Enterprise Development LP
"""

from flask import request, Flask
import sys
import time
import os

_app = Flask(__name__)


@_app.route("/", methods=["POST"])
def bounce(data: str = "") -> str:
    """Return the input data + the time it took to do so."""
    start: float = time.perf_counter()
    if data == "":
        data = request.get_data(as_text=True)

    total_bytes: int = len(data)
    t: float = round(time.perf_counter() - start, 5)
    return (
        data
        + f"\n@@@ Time (sec) to read request of {total_bytes} bytes in sec: {t}"
    )


def main() -> str:
    """Fission entry point."""
    return bounce()


#################################
if __name__ == "__main__":
    if os.getenv("FAAS_ENV") == "knative":
        ## Knative entry point
        _app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    data: str = ""

    if len(sys.argv) < 2:
        try:
            data = input("Please enter the text to bounce:")
        except Exception as ex:
            print("Required argument in stdin: data to bounce back")
            exit(-1)
    else:
        data = " ".join(sys.argv[1:])

    print(bounce(data))
