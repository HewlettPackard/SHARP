# Function (application) development guidelines

If you're just writing a short one-off testing function, you can ignore this guide.

Otherwise, if you want the launchers to be able to execute your function as part of a workflow, your function needs to conform to a few standardized guidelines that the launchers expect:

* Each application needs to be executable with a main file/function (including scripts), for local evaluation.
* When running locally, an application should take its inputs from stdin or from command-line arguments (support both).
* When running as a function, an application should take its inputs from the request body.
* The function should output all the performance metrics it wants to collect and report to standard output, in a way that can be extracted using a [metrics](./metrics.md) specification.
* Each application directory should include a Makefile. As a minimum, the Makefile should include these targets:
    * `all`: Compile the application (if necessary, no-op if it's a finished script).
    * `prep-*`: Build and install a package for a given FaaS framework. For example, `prep-fission` on a Python function would zip up a package and set it up for execution with Fission.

For local testing and framework consistency, each function should also have a python file with the same name (+.py) as the Fission function (and as it happens, the directory name). If your python program happens to have a different filename, just add a symbolic link to it with the right name.

Please make sure that your code conforms to the documentation standards outlined in [PEP 257](https://peps.python.org/pep-0257/), which you can verify by running the program [pep257](https://peps.python.org/pep-0257/).
You can then automatically extract documentation for your code under `docs/fns` by running `make` in that directory.
Please also make sure that your code includes type annotations according to [PEP 484](https://peps.python.org/pep-0484/) and produces no errors or warnings under [mypy](https://mypy-lang.org/).
