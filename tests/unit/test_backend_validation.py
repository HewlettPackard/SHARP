#!/usr/bin/env python3
"""
Unit tests for backend chain validation.

Tests the composability constraint validation logic:
- Valid chains (single backend, composable chains, non-composable leftmost)
- Invalid chains (non-composable in wrong position)
- Error message clarity

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
from src.core.config.backend_loader import validate_backend_chain, BackendChainError
from src.core.execution.orchestrator import ExecutionOrchestrator


class TestValidateBackendChain:
    """Test validate_backend_chain() function."""

    def test_empty_chain(self):
        """Empty backend list is valid."""
        is_valid, error = validate_backend_chain([], {})
        assert is_valid
        assert error == ""

    def test_single_composable_backend(self):
        """Single composable backend is valid."""
        backends = ["local"]
        configs = {"local": {"composable": True}}
        is_valid, error = validate_backend_chain(backends, configs)
        assert is_valid
        assert error == ""

    def test_single_non_composable_backend(self):
        """Single non-composable backend is valid (position 1)."""
        backends = ["mpip"]
        configs = {"mpip": {"composable": False}}
        is_valid, error = validate_backend_chain(backends, configs)
        assert is_valid
        assert error == ""

    def test_composable_chain(self):
        """Chain of composable backends is valid."""
        backends = ["local", "perf"]
        configs = {
            "local": {"composable": True},
            "perf": {"composable": True}
        }
        is_valid, error = validate_backend_chain(backends, configs)
        assert is_valid
        assert error == ""

    def test_composable_chain_multiple(self):
        """Multiple composable backends can be chained."""
        backends = ["local", "perf", "strace"]
        configs = {
            "local": {"composable": True},
            "perf": {"composable": True},
            "strace": {"composable": True}
        }
        is_valid, error = validate_backend_chain(backends, configs)
        assert is_valid
        assert error == ""

    def test_non_composable_leftmost(self):
        """Non-composable backend at position 1 (leftmost) is valid."""
        backends = ["mpip", "perf"]
        configs = {
            "mpip": {"composable": False},
            "perf": {"composable": True}
        }
        is_valid, error = validate_backend_chain(backends, configs)
        assert is_valid
        assert error == ""

    def test_non_composable_not_leftmost(self):
        """Non-composable backend not at position 1 is invalid."""
        backends = ["perf", "mpip"]
        configs = {
            "perf": {"composable": True},
            "mpip": {"composable": False}
        }
        is_valid, error = validate_backend_chain(backends, configs)
        assert not is_valid
        assert "Non-composable backends can only be in position 1 (leftmost)" in error
        assert "position 2 (mpip)" in error

    def test_non_composable_in_middle(self):
        """Non-composable backend in middle position is invalid."""
        backends = ["perf", "mpip", "local"]
        configs = {
            "perf": {"composable": True},
            "mpip": {"composable": False},
            "local": {"composable": True}
        }
        is_valid, error = validate_backend_chain(backends, configs)
        assert not is_valid
        assert "position 2 (mpip)" in error

    def test_multiple_non_composable(self):
        """Multiple non-composable backends are invalid."""
        backends = ["docker", "mpip"]
        configs = {
            "docker": {"composable": False},
            "mpip": {"composable": False}
        }
        is_valid, error = validate_backend_chain(backends, configs)
        assert not is_valid
        assert "position 2 (mpip)" in error

    def test_unknown_backend(self):
        """Unknown backends are skipped during validation."""
        backends = ["unknown", "local"]
        configs = {
            "local": {"composable": True}
        }
        # Should not fail - unknown backend will be caught elsewhere
        is_valid, error = validate_backend_chain(backends, configs)
        assert is_valid
        assert error == ""

    def test_nested_backend_options(self):
        """Handle nested backend_options structure."""
        backends = ["perf"]
        configs = {
            "perf": {
                "backend_options": {
                    "perf": {"composable": True}
                }
            }
        }
        is_valid, error = validate_backend_chain(backends, configs)
        assert is_valid
        assert error == ""

    def test_default_composable(self):
        """Missing composable field defaults to True."""
        backends = ["local", "perf"]
        configs = {
            "local": {},  # No composable field
            "perf": {}    # No composable field
        }
        is_valid, error = validate_backend_chain(backends, configs)
        assert is_valid
        assert error == ""


class TestOrchestratorValidation:
    """Test validation integration in ExecutionOrchestrator."""

    def test_orchestrator_valid_chain(self):
        """Orchestrator accepts valid backend chain."""
        options = {
            "entry_point": "./test",
            "args": [],
            "task": "test",
            "backend_names": ["local", "perf"],
            "backend_options": {
                "local": {"composable": True, "command_template": "$CMD $ARGS", "version": "1.0"},
                "perf": {"composable": True, "command_template": "perf stat -- $CMD $ARGS", "version": "1.0"}
            },
            "metrics": {},
            "repeats": "COUNT",
            "repeater_options": {"count": 1}
        }
        # Should not raise
        orchestrator = ExecutionOrchestrator(options, "test")
        assert orchestrator.backend_names == ["local", "perf"]

    def test_orchestrator_invalid_chain(self):
        """Orchestrator rejects invalid backend chain."""
        options = {
            "entry_point": "./test",
            "args": [],
            "task": "test",
            "backend_names": ["perf", "mpip"],
            "backend_options": {
                "perf": {"composable": True, "command_template": "perf stat -- $CMD $ARGS", "version": "1.0"},
                "mpip": {"composable": False, "command_template": "mpirun -np $MPL $CMD $ARGS", "version": "1.0"}
            },
            "metrics": {},
            "repeats": "COUNT",
            "repeater_options": {"count": 1}
        }
        with pytest.raises(BackendChainError) as exc_info:
            ExecutionOrchestrator(options, "test")
        assert "Non-composable backends can only be in position 1" in str(exc_info.value)
        assert "position 2 (mpip)" in str(exc_info.value)

    def test_orchestrator_non_composable_leftmost(self):
        """Orchestrator accepts non-composable backend at position 1."""
        options = {
            "entry_point": "./test",
            "args": [],
            "task": "test",
            "backend_names": ["mpip"],
            "backend_options": {
                "mpip": {"composable": False, "command_template": "mpirun -np $MPL $CMD $ARGS", "version": "1.0"}
            },
            "metrics": {},
            "repeats": "COUNT",
            "repeater_options": {"count": 1}
        }
        # Should not raise
        orchestrator = ExecutionOrchestrator(options, "test")
        assert orchestrator.backend_names == ["mpip"]

    def test_orchestrator_default_local_backend(self):
        """Orchestrator defaults to local backend when none specified."""
        options = {
            "entry_point": "./test",
            "args": [],
            "task": "test",
            "backend_names": [],  # Empty - should default to ["local"]
            "backend_options": {},
            "metrics": {},
            "repeats": "COUNT",
            "repeater_options": {"count": 1}
        }
        # Should not raise - will load local backend config automatically
        orchestrator = ExecutionOrchestrator(options, "test")
        assert orchestrator.backend_names == ["local"]

    def test_orchestrator_multiple_composable(self):
        """Orchestrator accepts multiple composable backends."""
        options = {
            "entry_point": "./test",
            "args": [],
            "task": "test",
            "backend_names": ["local", "perf", "strace"],
            "backend_options": {
                "local": {"composable": True, "command_template": "$CMD $ARGS", "version": "1.0"},
                "perf": {"composable": True, "command_template": "perf stat -- $CMD $ARGS", "version": "1.0"},
                "strace": {"composable": True, "command_template": "strace -c $CMD $ARGS", "version": "1.0"}
            },
            "metrics": {},
            "repeats": "COUNT",
            "repeater_options": {"count": 1}
        }
        # Should not raise
        orchestrator = ExecutionOrchestrator(options, "test")
        assert orchestrator.backend_names == ["local", "perf", "strace"]


class TestErrorMessages:
    """Test quality of error messages."""

    def test_error_message_clarity(self):
        """Error messages are clear and actionable."""
        backends = ["perf", "mpip"]
        configs = {
            "perf": {"composable": True},
            "mpip": {"composable": False}
        }
        is_valid, error = validate_backend_chain(backends, configs)
        assert not is_valid
        # Check message has key components
        assert "Non-composable" in error
        assert "position 1" in error or "leftmost" in error
        assert "mpip" in error
        assert "position 2" in error

    def test_error_message_multiple_violations(self):
        """Error message lists all violations."""
        backends = ["perf", "docker", "mpip"]
        configs = {
            "perf": {"composable": True},
            "docker": {"composable": False},
            "mpip": {"composable": False}
        }
        is_valid, error = validate_backend_chain(backends, configs)
        assert not is_valid
        # Should mention both docker and mpip
        assert "docker" in error
        assert "mpip" in error
