#!/usr/bin/env python3
"""
Run Llama2 inference for HPC.

This application can be used to run the Llama2 LLM with ollama as an inference service.
It takes the query prompt as input.

The program uses llama2 as the default model.
To use any different model use the example below:
    `execution_command: List[str] = ["ollama", "run", "gemma", prompt]`

More details about ollama and LLMs can be found [here](https://github.com/ollama/ollama).

## Running Ollama locally
To run the LLM model locally, you need to install
[Ollama](https://github.com/ollama/ollama) on your system and run its service.
It assumes that the Llama2 model is pulled after running the service. 
The launcher can be used for local execution as shown below:

    `./launcher/launch.py -v -b local ollama 'Who are you'`

The input parameters can be passed either by argv, stdin, or in the body of 
the HTTP request.

© Copyright 2023--2024 Hewlett Packard Enterprise Development LP
"""

from flask import request, Flask
from typing import *
import os
import sys
import time
import subprocess

_app = Flask(__name__)

@_app.route("/", methods=["POST"])
def exec_func(args: str = "") -> str:
    """Run the model with the given arguments."""
    if args == "":
        args = request.get_data(as_text=True)

    if args == "":
        return "Please ask something first!"
    # Extract the binary name and form its command based on absolute path
    arg_lst: List[str] = args.split(" ")
    prompt: str = arg_lst[0]
    prompt = args
    start: float = time.perf_counter()
    execution_command: List[str] = ["ollama", "run", "llama2", prompt, "--verbose"]

    # Execute the binary
    popen = subprocess.Popen(
        execution_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    popen.wait()
    output = popen.stdout.read().decode()  # type: ignore

    t: float = round(time.perf_counter() - start, 5)

    return f"{output}\n@@@ Time in inference: {t}\n"

def main() -> str:
    """Fission entry point."""
    return exec_func()

#################################
if __name__ == "__main__":
    if os.getenv("FAAS_ENV") == "knative":
        ## Knative entry point
        subprocess.Popen(["/usr/bin/ollama", "serve"])
        _app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

    args: str = ""

    if len(sys.argv) < 2:
        try:
            args = input(
                "Enter the prompt: "
            )
        except Exception as ex:
            print("Arguments: function name in string\n")
            exit(-1)
    else:
        args = " ".join(sys.argv[1:])
    print(exec_func(args))
