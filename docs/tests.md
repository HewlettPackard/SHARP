# tests Directory Documentation

This directory contains the complete test suite for the SHARP benchmarking framework, organized into unit tests, integration tests, and fixtures.

## Test Organization

```
tests/
├── conftest.py                # Pytest configuration and shared fixtures
├── backends/                  # Mock backend configurations
│   ├── mock_mpi.yaml
│   ├── mock_perf.yaml
│   ├── mock_ssh.yaml
│   ├── yaml_mock_with_sysspec.yaml
│   └── yaml_mock_without_sysspec.yaml
├── fixtures/                  # Shared test fixtures and helpers
│   ├── __init__.py
│   ├── repeater_fixtures.py   # Repeater test helpers and fixtures
│   └── distributions/         # Synthetic distribution generators
│       ├── __init__.py
│       ├── distributions.py   # Distribution classes
│       └── helpers.py         # Distribution helper functions
├── integration/               # Integration tests
│   ├── __init__.py
│   ├── test_cli_full_options.py       # CLI with full option coverage (14 tests)
│   ├── test_composable_backends.py    # Backend composition (15 tests)
│   ├── test_end_to_end_local.py       # End-to-end local execution (4 tests)
│   ├── test_install_completeness.py   # Installation verification (1 test)
│   ├── test_launcher_simple.py        # Basic launcher functionality (8 tests)
│   └── test_options_processing.py     # Config and option processing (23 tests)
└── unit/                      # Unit tests
    ├── __init__.py
    ├── test_cli_launch.py             # CLI launch logic (31 tests)
    ├── test_include_resolver.py       # Include directive resolution (18 tests)
    ├── test_loader.py                 # Configuration loading (23 tests)
    ├── test_orchestrator.py           # Test orchestration (18 tests)
    ├── test_packaging_builder.py      # Package building (11 tests)
    ├── test_repeaters.py              # Repeater strategies (73 tests)
    ├── test_runner.py                 # Test runner logic (14 tests)
    ├── test_schemas.py                # Schema validation (19 tests)
    ├── test_settings.py               # Settings management (9 tests)
    ├── test_sysinfo.py                # System information (4 tests)
    └── test_writer.py                 # Output writing (21 tests)
```

## Running Tests

The test suite uses **pytest** (not unittest). Execute the following commands from the project root:

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/unit/test_repeaters.py

# Run specific test
pytest tests/unit/test_repeaters.py::test_count_repeater_initialization

# Run with coverage
pytest tests/ --cov=src

# Run quietly (show only summary)
pytest tests/ -q

# Run with detailed output on failures
pytest tests/ -vv --tb=short
```

## Test Performance

**Total test suite execution time: ~3 minutes** (316 tests across 17 test files)

Breakdown by category:
- **Unit tests**: ~15 seconds (241 tests across 11 modules)
  - test_repeaters.py: 73 tests (~9 seconds)
  - test_cli_launch.py: 31 tests
  - test_loader.py: 23 tests
  - test_writer.py: 21 tests
  - test_schemas.py: 19 tests
  - test_orchestrator.py: 18 tests
  - test_include_resolver.py: 18 tests
  - test_runner.py: 14 tests
  - test_packaging_builder.py: 11 tests
  - test_settings.py: 9 tests
  - test_sysinfo.py: 4 tests
- **Integration tests**: ~2.5 minutes (75 tests across 6 modules)
  - test_options_processing.py: 23 tests
  - test_composable_backends.py: 15 tests
  - test_cli_full_options.py: 14 tests
  - test_launcher_simple.py: 8 tests
  - test_end_to_end_local.py: 4 tests
  - test_install_completeness.py: 1 test (generates ~200+ sub-tests dynamically)

Key optimizations:
- `--skip-sys-specs` flag: Skip expensive system specification collection (default for most tests)
- Mock backends: Mock perf, ssh, and mpi backends for composable tests (6x faster)
- Reduced workloads: Integration tests use smaller datasets for speed
- Test log directory: `runlogs/tests` (auto-created per test, auto-cleaned after)
- Pytest fixtures: Shared setup/teardown reduces redundant operations

## Test Modules

### Unit Tests

#### test_repeaters.py (73 tests)
- **Purpose**: Comprehensive testing of all repeater strategies
- **Framework**: Pure pytest with fixtures
- **Speed**: ~9 seconds
- **Coverage**:
  - **8 Repeater Implementations**:
    - CountRepeater (6 tests): Basic count-based repetition
    - RSERepeater (6 tests): Relative Standard Error convergence
    - CIRepeater (6 tests): Confidence Interval convergence
    - HDIRepeater (6 tests): Highest Density Interval convergence
    - BBRepeater (4 tests): Block Bootstrap convergence
    - GaussianMixtureRepeater (8 tests): GMM-based distribution detection
    - KSRepeater (6 tests): Kolmogorov-Smirnov test convergence
    - DecisionRepeater (7 tests): Meta-heuristic decision repeater
  - **Meta Tests** (12 tests):
    - Factory pattern tests (9 tests): Repeater creation via factory
    - Protocol compliance (3 tests): Interface verification
  - **Distribution Tests** (6 tests): Synthetic distribution generators
  - **Boundary Tests** (6 tests): Edge cases with complex distributions

**Test Pattern**: All repeater tests follow pytest style with:
- Fixtures for repeater instances
- Free functions (not classes)
- Parametrized helpers for common assertion patterns
- No `self.assert*` - uses native Python `assert`

**Warning Suppression**: Uses `pytestmark` to suppress expected sklearn ConvergenceWarnings

#### test_cli_launch.py (31 tests)
- **Purpose**: CLI launch command parsing and execution
- **Tests**: Argument parsing, validation, error handling, subprocess management
- **Speed**: ~1 second

#### test_loader.py (23 tests)
- **Purpose**: Configuration file loading and parsing
- **Tests**: YAML loading, schema validation, default values, error handling
- **Speed**: ~1 second

#### test_writer.py (21 tests)
- **Purpose**: Output file writing (CSV, JSON, YAML)
- **Tests**: File formatting, data serialization, error handling
- **Speed**: ~1 second

#### test_schemas.py (19 tests)
- **Purpose**: Configuration schema validation
- **Tests**: Schema enforcement, type checking, required fields
- **Speed**: <1 second

#### test_orchestrator.py (18 tests)
- **Purpose**: Test orchestration and coordination
- **Tests**: Test execution flow, result aggregation, error propagation
- **Speed**: ~1 second

#### test_include_resolver.py (18 tests)
- **Purpose**: Include directive resolution in configs
- **Tests**: File inclusion, path resolution, circular dependency detection
- **Speed**: <1 second

#### test_runner.py (14 tests)
- **Purpose**: Test runner execution logic
- **Tests**: Process management, timeout handling, result collection
- **Speed**: ~1 second

#### test_packaging_builder.py (11 tests)
- **Purpose**: Package/container building
- **Tests**: Docker image building, dependency resolution
- **Speed**: ~1 second

#### test_settings.py (9 tests)
- **Purpose**: Settings management and configuration
- **Tests**: Setting precedence, environment variables, defaults
- **Speed**: <1 second

#### test_sysinfo.py (4 tests)
- **Purpose**: System information collection
- **Tests**: CPU info, memory info, OS detection
- **Speed**: <1 second

### Integration Tests

#### test_options_processing.py (23 tests)
- **Purpose**: Configuration and option processing
- **Tests**: Config file loading, JSON options, command merging, priority handling, reproduction
- **Speed**: ~60 seconds
- **sys_specs**: Mostly disabled; some tests require real sys_specs for metrics verification

#### test_composable_backends.py (15 tests)
- **Purpose**: Backend composition and chaining
- **Tests**: Single backends (local, perf, ssh, mpi), dual combinations, triple combinations
- **Speed**: ~34 seconds (down from 3m33s with mock backends)
- **sys_specs**: Uses minimal sys_spec config with `-j` flag (only fast commands: nproc, uname, hostname)
- **Mock backends**: Uses `mock_perf.yaml`, `mock_ssh.yaml`, `mock_mpi.yaml` for instant execution

#### test_cli_full_options.py (14 tests)
- **Purpose**: CLI with comprehensive option coverage
- **Tests**: All CLI flags, argument combinations, edge cases
- **Speed**: ~20 seconds

#### test_launcher_simple.py (8 tests)
- **Purpose**: Basic launcher functionality
- **Tests**: Command-line parsing, help messages, simple execution, output files
- **Speed**: ~5 seconds
- **sys_specs**: Disabled (uses `--skip-sys-specs` flag)

#### test_end_to_end_local.py (4 tests)
- **Purpose**: End-to-end local execution workflow
- **Tests**: Full benchmark execution locally, result validation
- **Speed**: ~30 seconds

#### test_install_completeness.py (1 test)
- **Purpose**: Integration test verifying installation and dependencies
- **Tests**: Package installation, import validation, dependency resolution
- **Speed**: ~5 seconds

## Test Infrastructure

### Fixtures

#### Repeater Fixtures (`tests/fixtures/repeater_fixtures.py`)

Provides test infrastructure for repeater testing:

**Helper Functions**:
- `make_repeater_options(key, **kwargs)`: Create repeater configuration dict
- `make_repeater(repeater_class, key, **options)`: Instantiate repeater with config
- `collect_decisions(repeater, data, max_iterations)`: Run repeater and collect decisions

**Fixture Class**:
- `RepeaterTester`: Pytest fixture class with common assertion patterns
  - `assert_initialization(repeater)`: Verify clean initialization
  - `assert_increments_count(repeater)`: Verify count increments correctly
  - `assert_continues_before_starting_sample(repeater, starting_sample)`: Verify starting_sample enforcement
  - `assert_does_not_converge_prematurely(repeater, data_gen, iterations)`: Verify no premature convergence
  - `assert_stops_when_threshold_crossed(repeater, data_gen, starting_sample)`: Verify threshold detection

**Pytest Fixture**:
- `repeater_tester()`: Returns `RepeaterTester` instance for injection into tests

**Mock Data**:
- `MockRunData`: Simulates benchmark run data for testing

#### Distribution Fixtures (`tests/fixtures/distributions.py`)

Provides synthetic distribution generators for testing:

**Available Distributions**:
- `generate_normal_data(mean, std_dev, count)`: Gaussian distribution
- `generate_uniform_data(loc, scale, count)`: Uniform distribution
- `generate_lognormal_data(shape, mean, std_dev, count)`: Log-normal (right-skewed)
- `generate_bimodal_data(count)`: Two-mode distribution
- `generate_multimodal_data(modes, count)`: Multi-mode distribution
- `generate_constant_data(value, noise_scale, count)`: Constant with optional noise
- `generate_sine_data(norm_std, count)`: Periodic sine pattern (autocorrelated)
- `generate_logistic_data(count)`: Logistic distribution (heavy tails)
- `generate_high_variance_normal_data(count)`: High-variance normal

### Mock Backends

Located in `tests/backends/`:

- **mock_perf.yaml**: Simulates perf backend with instant execution
- **mock_ssh.yaml**: Simulates ssh backend with instant execution
- **mock_mpi.yaml**: Simulates MPI backend with instant execution
- **yaml_mock_with_sysspec.yaml**: Test mock backend with sys_spec override
- **yaml_mock_without_sysspec.yaml**: Test mock backend without sys_spec override

### Shared Fixtures (conftest.py)

Located in `tests/conftest.py`:

Provides pytest fixtures shared across all tests:
- Temporary directory management
- Common test data setup
- Cleanup utilities
- Shared mock objects

## Writing New Tests

### Pytest Style (Recommended for All New Tests)

When adding new tests, use pytest style with fixtures:

```python
import pytest
from src.module import MyClass

@pytest.fixture
def my_instance():
    """Provide MyClass instance for tests."""
    return MyClass(config={"key": "value"})

def test_my_feature(my_instance):
    """MyClass should do something."""
    result = my_instance.do_something()
    assert result == expected_value
    assert isinstance(result, int)

def test_my_edge_case():
    """MyClass should handle edge case."""
    instance = MyClass(config={})
    with pytest.raises(ValueError):
        instance.invalid_operation()
```

**Best Practices**:
- Use free functions, not test classes (unless grouping related tests)
- Use fixtures for setup/teardown and shared instances
- Use `assert` statements, not `self.assert*`
- Add descriptive docstrings to each test
- Use `pytestmark` for module-level decorators (e.g., warning filters)
- Parametrize tests when testing multiple similar scenarios

Example with parametrization:

```python
import pytest

@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_doubling(input, expected):
    """Function should double the input."""
    assert double(input) == expected
```## Test Utilities

### Running Subset of Tests

```bash
# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run only repeater tests
pytest tests/unit/test_repeaters.py

# Run tests matching pattern
pytest tests/ -k "decision"  # Runs all tests with "decision" in name

# Run failed tests from last run
pytest tests/ --lf

# Run tests in parallel (requires pytest-xdist)
pytest tests/ -n auto
```

### Debugging Tests

```bash
# Show print statements
pytest tests/ -s

# Drop into debugger on failure
pytest tests/ --pdb

# Show locals in traceback
pytest tests/ -l

# Detailed failure info
pytest tests/ -vv --tb=long
```

## Test Coverage

To measure test coverage:

```bash
# Install coverage tools
pip install pytest-cov

# Run with coverage report
pytest tests/ --cov=src --cov-report=html

# View coverage in browser
open htmlcov/index.html
```

## Test Framework

SHARP uses **pytest** as its primary testing framework. All tests are compatible with pytest, though some legacy integration tests may still use `unittest.TestCase` classes (which pytest runs seamlessly).

### Why Pytest?

- **Simpler syntax**: Uses plain `assert` instead of `self.assertEqual()`, etc.
- **Better fixtures**: Dependency injection via function parameters
- **Parametrization**: Easy test generation with `@pytest.mark.parametrize`
- **Better output**: Clearer failure messages and introspection
- **Plugin ecosystem**: Rich ecosystem of plugins for coverage, parallel execution, etc.

### Migration Status

✅ **Fully migrated to pytest**:
- `tests/unit/test_repeaters.py` (73 tests) - Pure pytest with fixtures
- `tests/fixtures/repeater_fixtures.py` - Pytest fixture class pattern

� **Pytest-compatible** (can be migrated later):
- All integration tests - Use `unittest.TestCase` but run via pytest
- All other unit tests - Use `unittest.TestCase` but run via pytest

The current approach allows gradual migration while maintaining full compatibility.

## Testing Philosophy

**Version**: 1.0 (Established December 2025)

### Core Principles

#### 1. Tests Should Catch Real Bugs

Every test should answer: **"What bug would this catch if it regressed?"**

- Tests verify actual behavior, not implementation details
- Tests check real error conditions, edge cases, and integration points
- Tests do NOT exist purely to achieve coverage metrics
- Tests exercise code paths that could actually fail in production

#### 2. Prefer Real Execution Over Mocking

**Default**: Use real execution with temporary directories, actual files, and real processes.

**When to mock**:
- Testing GUI orchestration that coordinates other components
- The mocked functionality has comprehensive tests elsewhere
- Testing callback behavior or error propagation
- Real execution would be prohibitively slow or require external resources

**Current status**: Only 1 mock-heavy file (test_profile_execution.py) out of 45 test files, and those mocks are justified.

#### 3. Coverage Percentage is Secondary

**Philosophy**: 50% coverage with meaningful tests > 95% coverage with trivial tests

- SHARP has 44% overall coverage with 793 meaningful tests
- 20 files have 100% coverage (core utilities, config system)
- Lower coverage in GUI modules is acceptable (tested through UI interaction)
- Lower coverage in CLI entry points is acceptable (tested through integration tests)

**Use coverage to**:
- Identify completely untested code
- Find missing error paths in critical code
- Discover dead code that can be removed

**Do NOT use coverage to**:
- Set arbitrary percentage targets
- Write trivial tests just to hit coverage goals
- Measure test suite quality

#### 4. Test Patterns

**Use pytest fixtures**:
```python
@pytest.fixture
def orchestrator_config(tmp_path):
    """Provide complete orchestrator configuration."""
    return {'benchmark_spec': {'entry_point': '/bin/sleep', 'args': ['0.1']}}

def test_orchestrator_executes(orchestrator_config):
    """Test full orchestrator execution."""
    orchestrator = ExecutionOrchestrator(orchestrator_config)
    result = orchestrator.run()
    assert result.success
```

**Test real file I/O**:
```python
def test_save_markdown_with_system_specs(tmp_path):
    """Markdown output includes system specifications."""
    writer = RunLogger(str(tmp_path / "exp"), "task")
    writer.save_md()

    md_path = tmp_path / "exp" / "task.md"
    with open(md_path) as f:
        content = f.read()

    assert "## Initial system configuration" in content
```

**Use synthetic data for statistical tests**:
```python
from tests.fixtures.distributions import distributions

def test_rse_repeater_converges_on_normal():
    """RSE repeater converges when relative error drops below threshold."""
    repeater = RSERepeater({'threshold_value': 0.05})

    for sample in distributions.normal(mean=100, std=5, size=100):
        rundata = MockRunData({'time': sample})
        if repeater(rundata):
            break

    assert repeater.converged
```

### What NOT to Test

❌ **Implementation details**: Don't test private methods or internal state
❌ **Framework behavior**: Don't test that pytest fixtures work
❌ **Library functionality**: Don't test that Pydantic validates (test your schemas)
❌ **Tautologies**: Don't write tests that can't fail

### Test Documentation

Every test should have:
1. **Descriptive name**: `test_sweep_generates_all_combinations`
2. **Docstring**: Explains what behavior is being validated
3. **Clear assertions**: What would break if this fails?

### Test Maintenance

**When a bug is found**:
1. Write a failing test that reproduces the bug
2. Fix the bug
3. Verify the test now passes
4. Document the regression in test docstring

**When refactoring**:
1. Run tests before refactoring (establish baseline)
2. Refactor incrementally (small changes)
3. Run tests after each change (immediate feedback)
4. Update tests only if behavior changes

### Test Review Checklist

Before merging new tests:
- [ ] Test has descriptive name and docstring
- [ ] Test uses real execution (or justifies mocking)
- [ ] Test would catch an actual bug if code regressed
- [ ] Test runs in reasonable time (<1s unit, <10s integration)
- [ ] Test cleans up resources (tmp_path handles this)
- [ ] Test is deterministic (no random failures)
- [ ] Test error messages are clear
- [ ] Test follows existing patterns

### Quality Metrics

**Phase 6.1 Audit Results** (December 2025):
- ✅ 793 passing tests across 45 files
- ✅ 44% meaningful coverage (not artificially inflated)
- ✅ Minimal mock usage (1 mock-heavy file, justified)
- ✅ Strong integration test coverage (14 files)
- ✅ Real execution dominates (80%+ of tests)
- ✅ Zero trivial tests identified

**References**:
- Test Quality Audit: `/test_quality_audit_findings.md`
- Coverage Report: `htmlcov/index.html`
