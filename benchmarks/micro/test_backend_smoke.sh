#!/bin/bash
#
# Quick smoke test for backend matrix
# Tests a subset of benchmarks to verify basic functionality
#
# © Copyright 2025--2025 Hewlett Packard Enterprise Development LP

set -e

# Get project root (two levels up from benchmarks/micro)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Test configuration
EXPERIMENT_NAME="backend_smoke_test"
LOG_DIR="${PROJECT_ROOT}/runlogs/${EXPERIMENT_NAME}"
mkdir -p "$LOG_DIR"

echo "Backend Smoke Test - $(date)"
echo "====================================="
echo ""

# Color output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Test counters
passed=0
failed=0

# Run test helper
test_run() {
    local bench=$1
    local backend=$2
    local args=$3

    echo -n "Testing $bench @ $backend... "

    # Use unique experiment name per backend to avoid overwriting results
    local exp_name="${EXPERIMENT_NAME}_${backend}"
    if uv run launch -e "$exp_name" -b "$backend" $bench $args &> "$LOG_DIR/${bench}_${backend}.log"; then
        echo -e "${GREEN}PASS${NC}"
        passed=$((passed + 1))
    else
        echo -e "${RED}FAIL${NC} (see $LOG_DIR/${bench}_${backend}.log)"
        failed=$((failed + 1))
    fi
}

# Quick smoke tests
echo "=== Local Backend ==="
test_run "sleep" "local" "0.1"
test_run "nope" "local" ""
test_run "matmul" "local" "50"

echo ""
echo "=== Docker Backend ==="
test_run "sleep" "docker" "0.1"
test_run "matmul" "docker" "50"
test_run "sympy-expand" "docker" "5"

echo ""
echo "====================================="
echo "Results: $passed passed, $failed failed"
echo "====================================="

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}All smoke tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
