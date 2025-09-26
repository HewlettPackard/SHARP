# Benchmark metrics

In addition to the default `outer_time` metric that is measured for all benchmarks and functions, the user can add arbitrary metrics to their benchmarks.
These metrics are logged into the CSV files in `runlogs`, described in the corresponding .md file, and can be imported into the resulting .pdf report.

To add metrics to your run, you need to add a configuration subsection called `metrics` (configuration can be modified via the `-f` or `-j` flags to `launcher.py` and visualized with `-v`, as described [here](./launcher.md)).
The `metrics` section includes one or more metric sections (dictionaries), each including the following variables:

 * `description` (string): a text explaining what is being measured.
 * `extract` (string): a shell command line that can be used to extract a single value for this metric from the standard output of the benchmark. That output will be piped to this command line.
 * `lower_is_better` (Boolean): denotes whether a lower metric value means better performance.
 * `type` (string): the type of the metric value (numeric, boolean, etc.).
 * `units` (string): the units of measurement for the metric.


The following JSON file is an example with three metrics (can be done in YAML format as well):

```json
{
  "metrics": {
    "cache_misses": {
      "description": "Total cache misses",
      "extract": "grep \"  cache-misses\" | awk '{ print $1; }'",
      "lower_is_better": true,
      "type": "numeric",
      "units": "count"
    },
    "pareto_16_16_time": {
      "description": "Predicted 16-16 configuration time",
      "extract": "grep \"Pareto config:  16 cores-16\" | awk '{ print $11; }'",
      "lower_is_better": true,
      "type": "numeric",
      "units": "s"
    },
    "pareto_16_16_cost": {
      "description": "Predicted 16-16 configuration cost",
      "extract": "grep \"Pareto config:  16 cores-16\" | awk '{ print $13; }'",
      "lower_is_better": true,
      "type": "numeric",
      "units": "USD"
    }
  }
}
```

## 'auto' metrics


SHARP also lets you define a backend with a single metric named 'auto'.
This metric can actually expand to numerous metrics when parsing the
application's output using the 'extract' command.
Each line in that output is assumed to have two columns, the first with the 
metric's name and the second with the metric's value.
It is assumed that there is only one 'auto' metric in all the backend files 
included in a single experiment. It's also assumed that all the metrics that
have a value in one run (copy/rank) will have the same metrics for all the other runs.

To see an example in action, examine the backend file `backends/strace.yaml`.
Run it with the command:
```sh
./launcher/launch.py -f launcher/default_config.yaml -f backends/strace.yaml -b strace /bin/ls
```
Then, examine the content of the files `runlogs/misc/ls.*`.

