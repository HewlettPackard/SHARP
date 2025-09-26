# tests Directory Documentation

This directory contains test implementations and mock launchers used for testing the launcher framework with different system specification configurations.

## Running Tests

The test suite can be run using Python's unittest framework. Execute the following commands from the project root:

```bash
# Run individual test files
python3 -m unittest tests/simple_launcher_tests.py        # Tests basic launcher functionality
python3 -m unittest tests/options_processing_tests.py     # Tests option parsing and processing
python3 -m unittest tests/composable_backends_tests.py    # Tests backend composition

# Run all tests
python3 -m unittest discover tests
```

## Test Suites

### 1. Simple Launcher Tests
- Tests basic launcher functionality
- Verifies command generation
- Tests system specification handling
- Located in `simple_launcher_tests.py`

### 2. Options Processing Tests
- Tests configuration file loading
- Tests command-line argument parsing
- Tests option merging and priority
- Located in `options_processing_tests.py`

### 3. Composable Backends Tests
- Tests backend composition
- Tests nested command generation
- Tests backend chaining
- Located in `composable_backends_tests.py`

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
