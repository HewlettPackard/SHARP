#!/bin/bash
#
# Comprehensive backend testing for microbenchmarks
#
# Tests all microbenchmarks across all supported backends:
# - 10 benchmarks: sleep, nope, inc, matmul, bounce, swapbytes, sympy-expand,
#                  gsl-integrate, mpi-pingpong-single, cuda-inc, cuda-matmul
# - 6 backends: local, docker, ssh, mpi, knative, fission
# - Total: 60 combinations (some may be skipped based on backend availability)
#
# © Copyright 2025--2025 Hewlett Packard Enterprise Development LP

set -e

# Get project root (two levels up from benchmarks/micro)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Configuration
EXPERIMENT_NAME="backend_matrix_test"
LOG_DIR="${PROJECT_ROOT}/runlogs/${EXPERIMENT_NAME}"
RESULTS_FILE="${LOG_DIR}/test_results.txt"
VERBOSE=${VERBOSE:-0}

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create log directory
mkdir -p "$LOG_DIR"
echo "Backend Testing Matrix - $(date)" > "$RESULTS_FILE"
echo "========================================" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"

# Benchmark definitions (name:args:backends)
# backends: L=local, D=docker, S=ssh, M=mpi, K=knative, F=fission
BENCHMARKS=(
    "sleep:1.0:L,D,S,M,K,F"
    "nope::L,D,S,M,K,F"
    "inc:1000 0:L,D,S,M,K,F"
    "matmul:100:L,D,S,M,K,F"
    "bounce:hello_world:L,D,K,F"  # Can run CLI mode with text arg or server mode for serverless
    "swapbytes:zeros-1m:L,D,K,F"  # Can run CLI mode with filename arg or server mode for serverless
    "sympy-expand:10:L,D"  # Only test with local and docker
    "gsl-integrate:100:L,D"  # Only test with local and docker
    "mpi-pingpong-single:10:M,D"  # MPI-specific, docker can wrap MPI - 10 sync rounds
    "cuda-inc:10000 0:L"  # GPU benchmark (Docker build failed - pip missing in CUDA image)
    "cuda-matmul:512:L"  # GPU benchmark (Docker build failed - pip missing in CUDA image)
)

# Backend availability checks
check_backend() {
    local backend=$1
    case $backend in
        local)
            return 0  # Always available
            ;;
        docker)
            command -v docker &>/dev/null
            ;;
        ssh)
            # Test SSH to localhost
            command -v ssh &>/dev/null && ssh -o BatchMode=yes -o ConnectTimeout=2 localhost true &>/dev/null
            ;;
        mpi)
            command -v mpirun &>/dev/null
            ;;
        knative)
            # Requires kubectl and knative service
            command -v kubectl &>/dev/null && kubectl get ksvc &>/dev/null 2>&1
            ;;
        fission)
            # Requires fission CLI and fission deployment
            command -v fission &>/dev/null && fission fn list &>/dev/null 2>&1
            ;;
        *)
            return 1
            ;;
    esac
}

# Backend name mapping
backend_name() {
    case $1 in
        L) echo "local" ;;
        D) echo "docker" ;;
        S) echo "ssh" ;;
        M) echo "mpi" ;;
        K) echo "knative" ;;
        F) echo "fission" ;;
        *) echo "unknown" ;;
    esac
}

# Test counters
total_tests=0
passed_tests=0
failed_tests=0
skipped_tests=0

# Run a single test
run_test() {
    local benchmark=$1
    local args=$2
    local backend=$3

    total_tests=$((total_tests + 1))

    local backend_full=$(backend_name "$backend")
    local test_name="${benchmark}@${backend_full}"

    echo -n "Testing ${test_name}... "

    # Check backend availability
    if ! check_backend "$backend_full"; then
        echo -e "${YELLOW}SKIP${NC} (backend not available)"
        echo "SKIP: $test_name (backend not available)" >> "$RESULTS_FILE"
        skipped_tests=$((skipped_tests + 1))
        return 0
    fi

    # Build command with unique experiment name per backend
    local exp_name="${EXPERIMENT_NAME}_${backend_full}"
    local cmd="uv run launch -e $exp_name -b $backend_full $benchmark"
    if [ -n "$args" ]; then
        cmd="$cmd $args"
    fi

    # Run test with timeout
    local output_file="${LOG_DIR}/${test_name}.log"
    local timeout_seconds=60  # 60 second timeout per test

    if [ "$VERBOSE" -eq 1 ]; then
        echo ""
        echo "Running: $cmd (timeout: ${timeout_seconds}s)"
    fi

    if timeout "$timeout_seconds" $cmd &> "$output_file"; then
        echo -e "${GREEN}PASS${NC}"
        echo "PASS: $test_name" >> "$RESULTS_FILE"
        passed_tests=$((passed_tests + 1))
    else
        local exit_code=$?
        if [ $exit_code -eq 124 ]; then
            echo -e "${RED}TIMEOUT${NC}"
            echo "TIMEOUT: $test_name (>${timeout_seconds}s)" >> "$RESULTS_FILE"
            echo "  Command: $cmd" >> "$RESULTS_FILE"
            echo "  Log: $output_file" >> "$RESULTS_FILE"
        else
            echo -e "${RED}FAIL${NC}"
            echo "FAIL: $test_name" >> "$RESULTS_FILE"
            echo "  Command: $cmd" >> "$RESULTS_FILE"
            echo "  Log: $output_file" >> "$RESULTS_FILE"
        fi
        failed_tests=$((failed_tests + 1))
    fi
}

# Setup: Create zeros-1m file for swapbytes tests
ZEROS_FILE="${PROJECT_ROOT}/benchmarks/micro/io/zeros-1m"
if [ ! -f "$ZEROS_FILE" ]; then
    echo "Creating zeros-1m file for swapbytes tests..."
    dd if=/dev/zero of="$ZEROS_FILE" bs=1M count=1 &>/dev/null
fi

# Main test loop
echo "Starting backend matrix testing..."
echo "Results will be saved to: $RESULTS_FILE"
echo ""

for bench_spec in "${BENCHMARKS[@]}"; do
    IFS=':' read -r benchmark args backends_str <<< "$bench_spec"

    echo "=== Testing benchmark: $benchmark ==="

    # Convert backends string to array
    IFS=',' read -ra backends <<< "$backends_str"

    for backend in "${backends[@]}"; do
        run_test "$benchmark" "$args" "$backend"
    done

    echo ""
done

# Summary
echo ""
echo "========================================" | tee -a "$RESULTS_FILE"
echo "Test Summary" | tee -a "$RESULTS_FILE"
echo "========================================" | tee -a "$RESULTS_FILE"
echo "Total:   $total_tests" | tee -a "$RESULTS_FILE"
echo -e "${GREEN}Passed:  $passed_tests${NC}" | tee -a "$RESULTS_FILE"
echo -e "${RED}Failed:  $failed_tests${NC}" | tee -a "$RESULTS_FILE"
echo -e "${YELLOW}Skipped: $skipped_tests${NC}" | tee -a "$RESULTS_FILE"
echo "" | tee -a "$RESULTS_FILE"

# Cleanup: Remove zeros-1m file and its output
if [ -f "$ZEROS_FILE" ]; then
    rm -f "$ZEROS_FILE" "${ZEROS_FILE}.out"
fi

if [ $failed_tests -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}" | tee -a "$RESULTS_FILE"
    exit 0
else
    echo -e "${RED}Some tests failed. See logs in $LOG_DIR${NC}" | tee -a "$RESULTS_FILE"
    exit 1
fi
