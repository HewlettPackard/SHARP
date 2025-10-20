# tests Directory Documentation

This directory contains test implementations and mock launchers used for testing the launcher framework.

## Running Tests

The test suite can be run using Python's unittest framework. Execute the following commands from the project root:

```bash
# Run individual test modules
python3 -m unittest tests.test_launcher_simple        # Basic launcher functionality
python3 -m unittest tests.test_options_processing     # Option parsing and processing
python3 -m unittest tests.test_composable_backends    # Backend composition and chaining
python3 -m unittest tests.test_install_completeness   # Integration tests for all backends

# Run all tests
python3 -m unittest discover tests

# Run with verbose output
python3 -m unittest discover tests -v
```

## Test Performance

**Total test suite execution time: ~2 minutes** (57 tests)

Key optimizations:
- `--skip-sys-specs` flag: Skip expensive system specification collection (default for most tests)
- Mock backends: Mock perf, ssh, and mpi backends for composable tests (6x faster)
- Reduced workloads: Integration tests use smaller datasets for speed
- Test log directory: `runlogs/tests` (auto-created per test, auto-cleaned after)

## Test Modules

### 1. test_launcher_simple.py
- **Purpose**: Basic launcher functionality
- **Tests**: Command-line parsing, help messages, simple execution, output files
- **Speed**: ~15 seconds (8 tests)
- **sys_specs**: Disabled (uses `--skip-sys-specs` flag)

### 2. test_options_processing.py
- **Purpose**: Configuration and option processing
- **Tests**: Config file loading, JSON options, command merging, priority handling, reproduction
- **Speed**: ~60 seconds (22 tests)
- **sys_specs**: Mostly disabled; 4 tests require real sys_specs for metrics verification:
  - `test_sys_spec_override`
  - `test_time_backend` (uses bintime backend)
  - `test_repro_task_override`
  - `test_repro_with_backend_override`

### 3. test_composable_backends.py
- **Purpose**: Backend composition and chaining
- **Tests**: Single backends (local, perf, ssh, mpi), dual combinations, triple combinations
- **Speed**: ~34 seconds (15 tests, down from 3m33s with mock backends)
- **sys_specs**: Uses minimal sys_spec config with `-j` flag (only fast commands: nproc, uname, hostname)
- **Mock backends**: Uses `mock_perf.yaml`, `mock_ssh.yaml`, `mock_mpi.yaml` for instant execution

### 4. test_install_completeness.py
- **Purpose**: Integration tests verifying all backend/function combinations work
- **Tests**: Real docker, knative, fission, mpi, ssh backends with representative functions
- **Speed**: ~30 seconds (12 tests, down from 5 minutes)
- **sys_specs**: Disabled (uses `--skip-sys-specs` flag)
- **Workload reductions**: cuda-inc (10000→100), mpi-pingpong (1000→10), ollama removed

## Test Infrastructure

### Mock Backends

Located in `tests/backends/`:

- **mock_perf.yaml**: Simulates perf backend with instant execution
- **mock_ssh.yaml**: Simulates ssh backend with instant execution
- **mock_mpi.yaml**: Simulates MPI backend with instant execution
- **yaml_mock_with_sysspec.yaml**: Test mock backend with sys_spec override
- **yaml_mock_without_sysspec.yaml**: Test mock backend without sys_spec override

### CommandTestCase Base Class

Located in `tests/command_test_case.py`:

- Provides common test infrastructure for all test classes
- Features:
  - `_skip_sys_specs`: Boolean flag to skip sys_spec collection (default False)
  - `run_launcher()`: Runs launcher with automatic `--skip-sys-specs` flag prepending
  - Test log directory: `runlogs/tests` (created per test, cleaned up automatically)
  - Helper methods: `assert_command_success()`, `assert_command_failure()`, CSV utilities
- Usage: Inherit from `CommandTestCase` and set `self._skip_sys_specs = True` in `setUp()` for faster tests

## Writing New Tests

When adding new functionality, please add corresponding tests:

1. Create a new test file in the `tests` directory
2. Inherit from `unittest.TestCase`
3. Add test methods prefixed with `test_`
4. Add the test file to the test suite

Example:
```python
import unittest
from launcher import Launcher

class NewFeatureTests(unittest.TestCase):
    def setUp(self):
        # Setup code
        pass
        
    def test_new_feature(self):
        # Test code
        self.assertTrue(True)
```
