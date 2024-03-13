#!/usr/bin/env python3
"""
A function to idly wait.

This function suspends execution for a given amount of seconds (given as
command-line argument, in stdin, or in the request body).
It is useful for creating a cool-down period between other functions, possibly 
flushing the framework's caches.

Caution: most frameworks time out for long functions (the default for Fission 
is 60s).
If you plan to sleep for longer periods, you must adjust the timeout period.

© Copyright 2022--2024 Hewlett Packard Enterprise Development LP
"""

from flask import request, Flask
import sys
import time
import os

_app = Flask(__name__)


@_app.route("/", methods=["POST"])
def sleep_sec(seconds: str = "") -> str:
    """Sleep for `seconds` seconds and return how long it took."""
    if seconds == "":
        seconds = request.get_data(as_text=True)

    start: float = time.perf_counter()
    time.sleep(float(seconds))
    t: float = round(time.perf_counter() - start, 5)
    return f"@@@ Time in sec to sleep {seconds} seconds: {t}"


def main() -> str:
    """Fission entry point."""
    return sleep_sec()


#################################
if __name__ == "__main__":
    if os.getenv("FAAS_ENV") == "knative":
        ## Knative entry point
        _app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    seconds: str = ""
    if len(sys.argv) < 2:
        seconds = input("Enter seconds to sleep: ")
    else:
        seconds = sys.argv[1]

    print(sleep_sec(seconds))
