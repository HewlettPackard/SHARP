#!/usr/bin/env bash

# Parse command line options
FAST_MODE=0
if [[ "$1" == "--fast" ]] || [[ "$1" == "-f" ]]; then
    FAST_MODE=1
    export SKIP_SLOW_TESTS=1
fi

# Pytest automatically shows progress with test names (-v) or just dots/counts (default)
# Use --tb=short for concise tracebacks
# The -v flag gives you a real-time progress view of which test is running

if [[ $FAST_MODE -eq 1 ]]; then
    # Fast mode: skip slow tests (install completeness)
    echo "Running tests in fast mode (skipping slow tests)..."
    echo "Progress will be shown test-by-test..."
    HWLOC_COMPONENTS=-gl uv run pytest tests/ \
        --ignore=tests/integration/test_install_completeness.py \
        --ignore=tests/integration/test_cli_full_options.py \
        --tb=short
else
    # Normal mode: run all tests with pytest
    # Remove -v to see compact dot progress instead of test names
    # Or keep -v to see each test name as it runs
    echo "Running full test suite with pytest..."
    echo "Progress shown as: . = passed, F = failed, E = error, s = skipped"
    HWLOC_COMPONENTS=-gl uv run pytest tests/ --tb=short
fi
