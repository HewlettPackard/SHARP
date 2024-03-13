# Benchmark: performance prediction


This benchmark is a wrapper around AUB's performance-prediction benchmarking suite.
It collects all of the input performance metrics during fingerprinting (from Linux's `perf` tools), as well as the output predictions for run time and cost for all all the given configurations.
the resulting PDF report simply visualizes the distributions of all these variables.

The "function" script (`fns/perfpred/perfpred.sh`) takes as arguments the data for the specific benchmark within the suite to run.

## Metrics

The metrics you wish to collect from the run may vary by the version of the AUB predictor or the configurations you care about.
There is a supplementary script called `gen_metrics.py` automates the process of generating a long `metrics.json` file with all the possible metrics from the predictor.
Take a look at the script, modify as needed, and then run it to produce the metrics you need before running SHARP.

**Note**

The actual code from AUB is not a part of SHARP and is not included, so trying to run this benchmark will fail unless you obtain this code independently.
The benchmark tries to run the script `fns/perfpred/perfpred.sh` to run this code, which is currently incomplete.
If you obtain the AUB suite, or you simply want to hook up this benchmark to your own code, all you need to change is this script and the appropriate files in the `examples/perfpred` directory, especially the [metrics](../metrics.md) file.
