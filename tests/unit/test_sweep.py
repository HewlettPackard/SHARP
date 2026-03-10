"""
Unit tests for parameter sweep expansion.

Tests CartesianSweepStrategy functionality including:
- Dict-based sweep specification
- Cartesian product expansion
- Args, env, and options section handling
- Error handling for invalid sweep data

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
from pydantic import ValidationError
from src.core.config.schema import ExperimentConfig, SweepConfig
from src.core.execution.parameter_space import CartesianSweepStrategy


@pytest.fixture
def temp_sweep_dir(tmp_path):
    """Create temporary directory for sweep files."""
    sweep_dir = tmp_path / "sweeps"
    sweep_dir.mkdir()
    return sweep_dir


@pytest.fixture
def base_config():
    """Create a basic experiment config for testing."""
    return ExperimentConfig(
        version="4.0",
        environment={},
        include=[],
        options={"directory": "runlogs"}
    )


def create_strategy(sweep_dict: dict, base_config: ExperimentConfig) -> CartesianSweepStrategy:
    """Helper to create CartesianSweepStrategy with validation."""
    sweep_config = SweepConfig(**sweep_dict)
    return CartesianSweepStrategy(base_config, sweep_config)


def test_empty_sweep(temp_sweep_dir, base_config):
    """Test sweep with no parameters raises error."""
    sweep_dict = {}

    with pytest.raises(ValidationError, match="Sweep must specify at least one of"):
        create_strategy(sweep_dict, base_config)


def test_args_single_value(temp_sweep_dir, base_config):
    """Test args section with single value list."""
    sweep_dict = {
        "args": [["--size", "100"]]
    }

    strategy = create_strategy(sweep_dict, base_config)
    configs = strategy.generate_configurations()

    assert len(configs) == 1
    launch_id, config, params = configs[0]
    assert config.options["args"] == ["--size", "100"]


def test_args_multiple_values(temp_sweep_dir, base_config):
    """Test args section with multiple value lists."""
    sweep_dict = {
        "args": [
            ["--size", "100"],
            ["--size", "200"],
            ["--size", "300"]
        ]
    }

    strategy = create_strategy(sweep_dict, base_config)
    configs = strategy.generate_configurations()

    assert len(configs) == 3
    assert configs[0][1].options["args"] == ["--size", "100"]
    assert configs[1][1].options["args"] == ["--size", "200"]
    assert configs[2][1].options["args"] == ["--size", "300"]


def test_env_single_values(temp_sweep_dir, base_config):
    """Test env section with scalar values only."""
    sweep_dict = {
        "env": {
            "OMP_NUM_THREADS": "4",
            "MKL_NUM_THREADS": "4"
        }
    }

    strategy = create_strategy(sweep_dict, base_config)
    configs = strategy.generate_configurations()

    assert len(configs) == 1
    _, config, _ = configs[0]
    assert config.environment["OMP_NUM_THREADS"] == "4"
    assert config.environment["MKL_NUM_THREADS"] == "4"


def test_env_array_expansion(temp_sweep_dir, base_config):
    """Test env section with array values creates Cartesian product."""
    sweep_dict = {
        "env": {
            "OMP_NUM_THREADS": ["1", "2", "4"],
            "MKL_NUM_THREADS": ["1", "4"]
        }
    }

    strategy = create_strategy(sweep_dict, base_config)
    configs = strategy.generate_configurations()

    # 3 OMP values * 2 MKL values = 6 combinations
    assert len(configs) == 6

    # Check that all combinations are present
    omp_values = [c[1].environment["OMP_NUM_THREADS"] for c in configs]
    mkl_values = [c[1].environment["MKL_NUM_THREADS"] for c in configs]

    assert omp_values.count("1") == 2  # "1" appears with both MKL values
    assert omp_values.count("2") == 2
    assert omp_values.count("4") == 2
    assert mkl_values.count("1") == 3  # "1" appears with all OMP values
    assert mkl_values.count("4") == 3


def test_options_single_values(temp_sweep_dir, base_config):
    """Test options section with scalar values only."""
    sweep_dict = {
        "options": {
            "mpl": 1,
            "start": "warm"
        }
    }

    strategy = create_strategy(sweep_dict, base_config)
    configs = strategy.generate_configurations()

    assert len(configs) == 1
    _, config, _ = configs[0]
    assert config.options["mpl"] == 1
    assert config.options["start"] == "warm"


def test_options_array_expansion(temp_sweep_dir, base_config):
    """Test options section with array values creates Cartesian product."""
    sweep_dict = {
        "options": {
            "mpl": [1, 2, 4],
            "start": ["warm", "cold"]
        }
    }

    strategy = create_strategy(sweep_dict, base_config)
    configs = strategy.generate_configurations()

    # 3 mpl values * 2 start values = 6 combinations
    assert len(configs) == 6

    mpl_values = [c[1].options["mpl"] for c in configs]
    start_values = [c[1].options["start"] for c in configs]

    assert mpl_values.count(1) == 2
    assert mpl_values.count(2) == 2
    assert mpl_values.count(4) == 2
    assert start_values.count("warm") == 3
    assert start_values.count("cold") == 3


def test_mixed_sections(temp_sweep_dir, base_config):
    """Test sweep with all three sections combined."""
    sweep_dict = {
        "args": [
            ["--size", "100"],
            ["--size", "200"]
        ],
        "env": {
            "OMP_NUM_THREADS": ["2", "4"]
        },
        "options": {
            "mpl": [1, 2]
        }
    }

    strategy = create_strategy(sweep_dict, base_config)
    configs = strategy.generate_configurations()

    # 2 args * 2 env * 2 options = 8 combinations
    assert len(configs) == 8


def test_mixed_scalar_and_array(temp_sweep_dir, base_config):
    """Test mixing scalar and array values in same section."""
    sweep_dict = {
        "env": {
            "FIXED_VAR": "constant",  # Scalar - same for all
            "SWEPT_VAR": ["a", "b", "c"]  # Array - expanded
        }
    }

    strategy = create_strategy(sweep_dict, base_config)
    configs = strategy.generate_configurations()

    assert len(configs) == 3
    for _, config, _ in configs:
        assert config.environment["FIXED_VAR"] == "constant"

    swept_values = [c[1].environment["SWEPT_VAR"] for c in configs]
    assert set(swept_values) == {"a", "b", "c"}


def test_launch_id_sequential(temp_sweep_dir, base_config):
    """Test that launch IDs are sequential and properly formatted with unique hash."""
    sweep_dict = {
        "options": {"mpl": [1, 2, 3, 4, 5]}
    }

    strategy = create_strategy(sweep_dict, base_config)
    configs = strategy.generate_configurations()

    launch_ids = [c[0] for c in configs]
    # Check format: sweep_NNNN_HASH where HASH is 6 hex chars
    import re
    pattern = re.compile(r"^sweep_\d{4}_[0-9a-f]{6}$")
    for lid in launch_ids:
        assert pattern.match(lid), f"Invalid launch_id format: {lid}"

    # Check sequential numbering (all have same hash)
    numbers = [lid.split("_")[1] for lid in launch_ids]
    assert numbers == ["0001", "0002", "0003", "0004", "0005"]

    # Check all have same hash (from same sweep)
    hashes = [lid.split("_")[2] for lid in launch_ids]
    assert len(set(hashes)) == 1, "All launch_ids in one sweep should have same hash"


def test_get_invariants_single_values(temp_sweep_dir, base_config):
    """Test get_invariants with single values."""
    sweep_dict = {
        "env": {"VAR": "value"},
        "options": {"opt": 123}
    }

    strategy = create_strategy(sweep_dict, base_config)
    invariants = strategy.get_parameter_ranges()

    assert "env.VAR" in invariants
    assert invariants["env.VAR"] == ["value"]
    assert "opt" in invariants
    assert invariants["opt"] == [123]


def test_get_invariants_array_values(temp_sweep_dir, base_config):
    """Test get_invariants with array values."""
    sweep_dict = {
        "env": {"THREADS": ["1", "2", "4"]},
        "options": {"mpl": [1, 2]}
    }

    strategy = create_strategy(sweep_dict, base_config)
    invariants = strategy.get_parameter_ranges()

    assert invariants["env.THREADS"] == ["1", "2", "4"]
    assert invariants["mpl"] == [1, 2]





def test_embedded_dict_format(base_config):
    """Test that embedded sweep dict (not file) is supported."""
    sweep_data = {
        "args": [["--size", "100"], ["--size", "200"]],
        "env": {"OMP_NUM_THREADS": ["1", "2"]},
        "options": {"mpl": 1}
    }

    # Pass dict directly instead of file path
    strategy = create_strategy(sweep_data, base_config)
    configs = strategy.generate_configurations()

    # 2 args × 2 env × 1 options = 4 configs
    assert len(configs) == 4


def test_conflict_warnings(base_config, temp_sweep_dir):
    """Test that conflicts between config and sweep generate warnings."""
    import warnings

    # Set base config values that will be overridden
    base_config.environment["OMP_NUM_THREADS"] = "16"
    base_config.options["start"] = "cold"

    sweep_dict = {
        "env": {"OMP_NUM_THREADS": "4"},
        "options": {"start": "warm"}
    }

    strategy = create_strategy(sweep_dict, base_config)

    # Capture warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        configs = strategy.generate_configurations()

        # Should have 2 warnings (one for env, one for options)
        assert len(w) == 2
        assert "OMP_NUM_THREADS" in str(w[0].message)
        assert "start" in str(w[1].message)


def test_error_not_dict(base_config):
    """Test error handling when sweep data is not a dict."""
    with pytest.raises(ValidationError, match="Sweep must specify at least one of"):
        create_strategy({}, base_config)


def test_error_args_not_list(temp_sweep_dir, base_config):
    """Test error handling when args is not a list."""
    sweep_dict = {"args": "not a list"}

    with pytest.raises(ValidationError, match="Input should be a valid list"):
        create_strategy(sweep_dict, base_config)


def test_error_env_not_dict(temp_sweep_dir, base_config):
    """Test error handling when env is not a dict."""
    sweep_dict = {"env": ["not", "a", "dict"]}

    with pytest.raises(ValidationError, match="Input should be a valid dictionary"):
        create_strategy(sweep_dict, base_config)


def test_error_options_not_dict(temp_sweep_dir, base_config):
    """Test error handling when options is not a dict."""
    sweep_dict = {"options": "not a dict"}

    with pytest.raises(ValidationError, match="Input should be a valid dictionary"):
        create_strategy(sweep_dict, base_config)


def test_preserve_base_config_values(temp_sweep_dir, base_config):
    """Test that base config values are preserved when not overridden."""
    # Set some values in base config
    base_config.environment["PRESERVED_VAR"] = "original"
    base_config.options["preserved_opt"] = "original"

    sweep_dict = {
        "env": {"NEW_VAR": "new"},
        "options": {"new_opt": "new"}
    }

    strategy = create_strategy(sweep_dict, base_config)
    configs = strategy.generate_configurations()

    _, config, _ = configs[0]
    # Original values should still be present
    assert config.environment["PRESERVED_VAR"] == "original"
    assert config.options["preserved_opt"] == "original"
    # New values should be added
    assert config.environment["NEW_VAR"] == "new"
    assert config.options["new_opt"] == "new"


def test_large_cartesian_product(temp_sweep_dir, base_config):
    """Test large Cartesian product expansion."""
    sweep_dict = {
        "env": {
            "VAR1": ["a", "b", "c"],
            "VAR2": ["1", "2"],
            "VAR3": ["x", "y", "z", "w"]
        }
    }

    strategy = create_strategy(sweep_dict, base_config)
    configs = strategy.generate_configurations()

    # 3 * 2 * 4 = 24 combinations
    assert len(configs) == 24

    # Verify all combinations are unique
    env_tuples = [
        (c[1].environment["VAR1"], c[1].environment["VAR2"], c[1].environment["VAR3"])
        for c in configs
    ]
    assert len(set(env_tuples)) == 24
