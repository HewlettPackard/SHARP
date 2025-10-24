#!/usr/bin/env bash

# Check if venv is activated
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "ERROR: Virtual environment is not activated!"
    echo "Please activate the venv first:"
    echo "  source venv-sharp/bin/activate"
    exit 1
fi

# Parse command line options
FAST_MODE=0
if [[ "$1" == "--fast" ]] || [[ "$1" == "-f" ]]; then
    FAST_MODE=1
    export SKIP_SLOW_TESTS=1
fi

if [[ $FAST_MODE -eq 1 ]]; then
    # Fast mode: skip slow tests (install completeness and mpi_and_perf)
    # The SKIP_SLOW_TESTS env var is checked in test files to skip slow tests
    echo "Running tests in fast mode (skipping slow tests)..."
    HWLOC_COMPONENTS=-gl python3 -m unittest \
        tests.test_launcher_simple \
        tests.test_options_processing \
        tests.test_composable_backends \
        -v
else
    # Normal mode: run all tests
    HWLOC_COMPONENTS=-gl python3 -m unittest discover -s tests -v
fi
