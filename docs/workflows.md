# Workflows

SHARP supports sequential workflows that allow you to chain multiple tasks together, combining file-based task definitions with inline overrides for maximum flexibility and reusability.

## Overview

A workflow is a YAML file that defines a sequence of tasks to be executed one after another. Each task can be:
- **File include**: Load task configuration from a file
- **Inline definition**: Define the task completely inline
- **Hybrid composition**: Include a file and override specific fields

Workflows stop on the first task failure (sequential execution semantics).

## Basic Workflow Structure

```yaml
version: 1.0.0                    # Required: workflow schema version
description: My workflow          # Optional: human-readable description
experiment: workflow_exp          # Optional: runlogs subdirectory name

workflow:                         # Required: list of tasks
  - include: task1.yaml
  - task: sleep
    backends: [local]
    options:
      repeater: COUNT
      repeats: 5
```

## Running a Workflow

```bash
# Run a workflow file
uv run launch -f workflow.yaml

# With verbose output
uv run launch -f workflow.yaml --verbose
```

## Task Definition Patterns

### Pattern 1: Pure File Include

Load all configuration from a file. This is useful for reusing task definitions across multiple workflows.

```yaml
workflow:
  - include: tasks/performance-test.yaml
  - include: tasks/stress-test.yaml
  - include: tasks/cleanup.yaml
```

**File**: `tasks/performance-test.yaml`
```yaml
options:
  task: matmul
  repeater: COUNT
  repeats: 100
include:
  - benchmarks/micro/cpu/benchmark.yaml
  - backends/local.yaml
backends:
  - local
```

### Pattern 2: Pure Inline Definition

Define everything inline without any file includes. This is useful for simple tasks or one-off experiments.

```yaml
workflow:
  - task: sleep
    backends:
      - local
    options:
      repeater: COUNT
      repeats: 5

  - task: matmul
    backends:
      - local
      - perf
    options:
      repeater: RSE
      size: 1024
```

### Pattern 3: Hybrid Composition - Override Task Name

Include a base configuration file but run a different benchmark. This allows you to reuse backend/option configurations while changing the task.

```yaml
workflow:
  # Use standard perf config but test different benchmarks
  - include: configs/standard-perf-test.yaml
    task: sleep

  - include: configs/standard-perf-test.yaml
    task: matmul

  - include: configs/standard-perf-test.yaml
    task: fft
```

### Pattern 4: Hybrid Composition - Override Options

Include a base task file but override specific options. This allows you to parameterize tasks without duplicating configuration.

```yaml
workflow:
  # Run same task with different repeat counts
  - include: tasks/baseline.yaml
    options:
      repeats: 10

  - include: tasks/baseline.yaml
    options:
      repeats: 100

  - include: tasks/baseline.yaml
    options:
      repeats: 1000
```

### Pattern 5: Hybrid Composition - Override Everything

Include a template file that provides defaults, but override task, backends, and options. This is useful for creating task templates that can be customized per-workflow.

```yaml
workflow:
  # Template provides include paths and default options
  # Override task, backends, and specific options
  - include: templates/benchmark-template.yaml
    task: matmul
    backends:
      - local
      - perf
    options:
      repeater: RSE
      size: 2048
      custom_param: value
```

## Composition Semantics

When both `include` and inline fields are specified, the following merge rules apply:

1. **File provides base configuration**: The included file is loaded first
2. **`task` field override**: Inline `task` replaces `options.task` from the file
3. **`backends` field override**: Inline `backends` completely replaces backends from the file
4. **`options` field merge**: Inline `options` are merged with file options, with inline values taking precedence

### Example of Option Merging

**File**: `base-config.yaml`
```yaml
options:
  task: sleep
  repeater: COUNT
  repeats: 5
  timeout: 30
backends:
  - local
```

**Workflow with override**:
```yaml
workflow:
  - include: base-config.yaml
    options:
      repeats: 1000      # Overrides file's repeats: 5
      custom_arg: value  # Added to options
    # Final merged options:
    #   task: sleep           (from file)
    #   repeater: COUNT       (from file)
    #   repeats: 1000         (overridden)
    #   timeout: 30           (from file)
    #   custom_arg: value     (added)
```

## Experiment Name Handling

The `experiment` field in the workflow config specifies the runlogs subdirectory name:

```yaml
version: 1.0.0
experiment: my_workflow_run    # Creates runlogs/my_workflow_run/

workflow:
  - include: task1.yaml
  - include: task2.yaml
```

Task files can also specify their own experiment names, which take precedence over the workflow-level experiment name. The `-e` command-line flag overrides both.

**Priority**: CLI `-e` flag > Task file `options.experiment` > Workflow `experiment` field

## Real-World Examples

### Example 1: Parameterized Performance Testing

Test multiple configurations of the same benchmark:

```yaml
version: 1.0.0
description: Matrix multiplication scaling study
experiment: matmul_scaling

workflow:
  # Small matrix
  - include: configs/matmul-base.yaml
    options:
      size: 512
      repeats: 100

  # Medium matrix
  - include: configs/matmul-base.yaml
    options:
      size: 1024
      repeats: 50

  # Large matrix
  - include: configs/matmul-base.yaml
    options:
      size: 2048
      repeats: 10
```

### Example 2: Multi-Stage Benchmarking

Run different benchmarks with different backends:

```yaml
version: 1.0.0
description: Comprehensive system benchmark
experiment: full_system_test

workflow:
  # CPU benchmark with local backend
  - task: matmul
    backends: [local]
    options:
      repeater: COUNT
      repeats: 100

  # CPU benchmark with perf monitoring
  - task: matmul
    backends: [local, perf]
    options:
      repeater: COUNT
      repeats: 100

  # I/O benchmark
  - include: benchmarks/io-test.yaml

  # Memory bandwidth test
  - include: benchmarks/stream.yaml
    options:
      array_size: 1000000
```

### Example 3: Template-Based Workflow

Use a template with different specializations:

```yaml
version: 1.0.0
description: Templated benchmark suite
experiment: template_test

workflow:
  # Quick smoke test
  - include: templates/quick-test.yaml
    task: sleep

  # Full performance test with overrides
  - include: templates/perf-test.yaml
    task: matmul
    options:
      repeats: 1000
      size: 2048

  # Stress test
  - include: templates/stress-test.yaml
    task: fft
    backends: [local, perf, temps]
```

## Advanced Usage

### Relative Paths

Task file paths in `include` are resolved relative to the workflow file's directory:

```yaml
# workflow.yaml in project root
workflow:
  - include: tasks/task1.yaml           # Looks for project-root/tasks/task1.yaml
  - include: ../shared/common.yaml      # Can use relative paths
  - include: /abs/path/to/task.yaml     # Absolute paths also work
```

### Verbose Output

Use `--verbose` to see detailed execution information:

```bash
uv run launch -f workflow.yaml --verbose
```

Output includes:
- Which tasks are being executed
- Whether tasks use file includes, inline definitions, or hybrid composition
- Task identifiers for debugging
- Execution progress

### Error Handling

Workflows stop on the first task failure:

```yaml
workflow:
  - include: task1.yaml   # Succeeds
  - include: task2.yaml   # Fails
  - include: task3.yaml   # Not executed
```

The workflow returns exit code 1 and prints information about which task failed.

## Best Practices

1. **Use file includes for reusable configurations**: Define common task configurations in files and include them in multiple workflows

2. **Use inline definitions for simple tasks**: For one-off or very simple tasks, inline definitions reduce file clutter

3. **Use hybrid composition for parameterization**: When you need to test the same task with different parameters, use file includes with option overrides

4. **Organize task files by purpose**: Keep task definitions in a `tasks/` directory, templates in `templates/`, and common configs in `configs/`

5. **Document complex workflows**: Use the `description` field to explain what the workflow does

6. **Use meaningful experiment names**: The `experiment` field determines the runlogs directory name - make it descriptive

## Schema Reference

### WorkflowConfig

Top-level workflow configuration.

```yaml
version: string           # Required: "1.0.0"
description: string       # Optional: workflow description
experiment: string        # Optional: runlogs subdirectory name
workflow: [WorkflowTask]  # Required: list of tasks
```

### WorkflowTask

Individual task in a workflow. Must specify at least `include` or `task`.

```yaml
include: string           # Optional: path to task config file
task: string              # Optional: benchmark/task name
backends: [string]        # Optional: list of backend names
options: {key: value}     # Optional: task options dict
```

**Composition Rules**:
- If only `include`: Load all config from file
- If only `task`: Pure inline definition
- If both: File provides base, inline fields override/merge

## See Also

- [Task Launching](launch.md) - Individual task execution
- [Backends](backends.md) - Available execution backends
- [Benchmarks](../benchmarks/README.md) - Available benchmarks
