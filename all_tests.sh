#!/usr/bin/env bash

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
    HWLOC_COMPONENTS=-gl uv run python -m unittest \
        tests.test_launcher_simple \
        tests.test_options_processing \
        tests.test_composable_backends \
        tests.unit.test_settings \
        -v
else
    # Normal mode: run all tests (including unit tests in subdirectories)
    HWLOC_COMPONENTS=-gl uv run python -m unittest discover -s tests -p "test_*.py" -v
fi
