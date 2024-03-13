# Conversion from CNCF workflows to Makefiles with `cncf2mk.py`

## Features

This script reads in a workflow file in JSON or YAML format, conforming to a subset of CNCF Serverless Workflow Format v. 0.8, and creates a Makefile out of the workflow, representing the state transitions as calls to `launch.py`.
The specification can be found [here](https://github.com/serverlessworkflow/specification/blob/main/specification.md).

The accepted subset of the workflow standard includes:

 * States of the types: Operation, Sleep, Parallel
 * `parallel` actionMode for actions
 * Action timeouts, which are passed along to `launcher.py`
 * A susbset of functions, designed to be run by `launcher.py` or the shell
 * functionRef arguments, which are passed to launcher

It doesn't include:

* Foreach, Inject, Event, Callback, and Switch states
* Parsing of jq expressions, and in particular, variables
* Events
* Filters

The standard is also extended/interpreted in these ways:

 * Workflow metadata, which is passed as options to launcher (icluding "verbose")
 * Function metadata, which includes the launcher backend (or 'local' for shell)
 * 'fnargs' dictionary in function arguments, which are passed to the invoked function

Here's a fairly complete example of the current capabilities of the script:

```yaml
---
id: demo
name: Example workflow
description: A demonstration of a simple workflow with dependencies
version: '1.0'
specVersion: '0.8'
start: CreateInputFiles
annotations:
- I/O
- CPU
- GPU
metadata:
  verbose: "no"
states:

- name: CreateInputFiles
  type: operation
  actionMode: parallel
  actions:
  - functionRef:
      refName: createZeros-10m
  - functionRef:
      refName: createZeros-100m
  transition: swapbytes-1

- name: swapbytes-1
  type: operation
  actions:
  - functionRef:
      refName: swapbytes
      arguments:
        "--mpl": 10
        fnargs: "/tmp/zeros-10m"
  timeouts:
    actionExecTimeout: PT10S
  transition: inc-both

- name: inc-both
  type: parallel
  completionType: allOf
  branches:
  - name: inc
    actions:
    - functionRef:
        refName: inc
        arguments:
          "--mpl": 15
          fnargs: '100000'
  - name: cuda-inc
    actions:
    - functionRef:
        refName: cuda-inc
        arguments:
          "--mpl": 5
          fnargs: '100000'
  timeouts:
    branchExecTimeout: PT30S
  transition: sleepy

- name: sleepy
  type: sleep
  duration: PT10S
  transition: swapbytes-2

- name: swapbytes-2
  type: operation
  actions:
  - functionRef:
      refName: swapbytes
      arguments:
        "--mpl": 10
        fnargs: "/tmp/zeros-100m"
  timeouts:
    actionExecTimeout: PT20S
  end: true

functions:
- name: createZeros-10m
  operation: head -c 10m /dev/zero > /tmp/zeros-10m
  type: custom
  metadata:
    backend: verbatim

- name: createZeros-100m
  operation: head -c 100m /dev/zero > /tmp/zeros-100m
  type: custom
  metadata:
    backend: verbatim

- name: swapbytes
  operation: swapbytes
  type: custom
  metadata:
    backend: local

- name: inc
  operation: inc
  type: custom
  metadata:
    backend: fission

- name: cuda-inc
  operation: cuda-inc
  type: custom
  metadata:
    backend: fission
```

---

When converted to Makefile with the script (using `./cncf2mk.py wf`, where `wf` is a workflow file in JSON or YAML format), this workflows looks something like this:


```make
id := demo
name := Example workflow
description := A demonstration of a simple workflow with dependencies
version := 1.0
specVersion := 0.8
start := CreateInputFiles
end := swapbytes-2.csv

basedir := /home/frachten/sharp
outdir := $(basedir)/runlogs/demo
launcher := $(basedir)/launchers/launch.py --description "$(description)"
csv_files := swapbytes-1.csv inc.csv cuda-inc.csv swapbytes-2.csv


.PHONY: clean CreateInputFiles inc-both sleepy

all:
	mkdir -p $(outdir)
	cd $(outdir); make -f $(abspath $(lastword $(MAKEFILE_LIST))) demo.pdf

demo.pdf: $(end)
	@echo compiling final report in `pwd`...

clean:
	rm -rf demo.pdf $(csv_files)

CreateInputFiles:
	head -c 10m /dev/zero > /tmp/zeros-10m &
	head -c 100m /dev/zero > /tmp/zeros-100m &
	wait

swapbytes-1.csv: CreateInputFiles
	$(launcher) --mpl 10 --timeout 10 -e $(id) -b local swapbytes /tmp/zeros-10m

inc-both: swapbytes-1.csv

inc.csv: inc-both
	$(launcher) --mpl 15 --timeout 30 -e $(id) -b fission inc 100000

cuda-inc.csv: inc-both
	$(launcher) --mpl 5 --timeout 30 -e $(id) -b fission cuda-inc 100000

sleepy: inc.csv cuda-inc.csv
	sleep 10

swapbytes-2.csv: sleepy
	$(launcher) --mpl 10 --timeout 20 -e $(id) -b local swapbytes /tmp/zeros-100m
```

## Writing your own workflow

The best place to start is with the existing example and library. If you need to do something you can't find in the examples, it's probably not supported yet. But just in case, you can check the standard, write the state/action you need, and see if the Makefile produced does what you expect. If not, you can edit the Makefile manually or roll out your own from scratch.

### Naming rules

 * States, branches, and functions must all have unique names.
 * The name of the state or branch becomes the name of the output file (+.csv), so you can't have two states or two branches with the same name or the files will overwrite each other.
 * The same function can be reused in multiple states and branches, as long as the state/branch names (and consequent output filenames) are different.
 * For the same reason, do not try to call multiple functions that produce an output file from the same set of actions (it's OK to have multiple `verbatim` functions). If you need to call more than one launcher function, break it into multiple states or branches.

### Validation

To validate that your workflow files conform to the CNCF serverless workflow standard, you can install and run the validator from the python SDK [here](https://github.com/serverlessworkflow/sdk-python).
Alternatively, you can run the validator in a container.
First, build the validator image using: `docker build --network=host -t wfvalidator:latest .` (in the `workflows` subdirectory).
Then, use it to validate a workflow file: `docker run -v $(pwd)/example-workflow.json:/sdk-python/input.json -t wfvalidator python3 /sdk-python/validator.py /sdk-python/input.json` (in this example, the workflow file you are validating is called `./example-workflow.json`, but it can also be a YAML file).

