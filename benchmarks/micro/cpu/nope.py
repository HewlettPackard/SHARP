#!/usr/bin/env python3
"""
A no-op function.

nope does nothing, which can be useful for measuring invocation overhead.
It takes no arguments, and returns a string representing zero run time.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

from flask import Flask
import os

_app = Flask(__name__)


@_app.route("/", methods=["POST"])
def do_nothing() -> str:
    """Return a constant string with zero run time."""
    return "@@@ Do nothing time: 0"


def main() -> str:
    """Fission entry point."""
    return do_nothing()


#################################
if __name__ == "__main__":
    if os.getenv("FAAS_ENV") == "knative":
        ## Knative entry point
        _app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    print(do_nothing())
