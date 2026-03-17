# Benchmark development guidelines

If you're just writing a short one-off testing function, you can ignore this guide.

Otherwise, if you want SHARP to execute your benchmark as part of an experiment, the benchmark should conform to a few standardized guidelines:

* Each benchmark should have a `benchmark.yaml` entry that declares its `entry_point`, default `args`, and any custom [metrics](./metrics.md) it emits.
* The local entry point should be directly executable, whether it is a script, binary, or wrapper program.
* When running locally, an application should accept its inputs from command-line arguments or stdin when appropriate.
* If you deploy the benchmark to a FaaS platform such as Fission or Knative, make the deployed function or service accept the same logical input and expose the same metrics that the benchmark definition expects.
* The program should output all performance metrics it wants to collect to standard output, in a form that can be extracted by the metric rules.
* If the benchmark needs packaging or build steps, express them in the benchmark's `build:` section instead of relying on repo-specific `prep-*` Makefile targets.

For local testing and packaging consistency, it is usually simplest to keep the executable entry point next to the benchmark definition and give it a stable, descriptive name.

Please make sure that your code conforms to the documentation standards outlined in [PEP 257](https://peps.python.org/pep-0257/), which you can verify by running the program [pep257](https://peps.python.org/pep-0257/).
Please make sure that your code includes type annotations according to [PEP 484](https://peps.python.org/pep-0484/) and produces no errors or warnings under [mypy](https://mypy-lang.org/).
