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
    # Fast mode: unit tests only
    echo "Running unit tests only (fast mode)..."
    echo "Progress will be shown test-by-test with skip reasons..."
    HWLOC_COMPONENTS=-gl uv run pytest tests/unit/ --tb=short -rs
else
    # Normal mode: run all tests with pytest
    # -v = verbose (show each test name and skip reasons as they run)
    # -rs = show summary of skipped tests at end
    # --tb=short = concise tracebacks for failures
    echo "Running full test suite with pytest..."
    echo "Tests shown with skip reasons where applicable..."
    HWLOC_COMPONENTS=-gl uv run pytest tests/ -v --tb=short -rs
fi
