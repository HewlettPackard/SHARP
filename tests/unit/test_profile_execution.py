"""
Unit tests for profile tab execution helpers.

© Copyright 2025 Hewlett Packard Enterprise Development LP
"""

import pytest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import Mock, patch, MagicMock

from src.gui.utils.profile.execution import (
    determine_task_name_for_profiling,
    build_orchestrator_options,
    ProfilingExecutor,
    load_profiling_data
)


class TestDetermineTaskName:
    """Test task name determination."""

    @patch('src.gui.utils.profile.execution.parse_markdown_runtime_options')
    def test_adds_prof_suffix(self, mock_parse):
        """Task name gets -prof suffix."""
        mock_parse.return_value = {'task': 'mytask'}

        result = determine_task_name_for_profiling('/path/to/mytask.md')
        assert result == 'mytask-prof'

    @patch('src.gui.utils.profile.execution.parse_markdown_runtime_options')
    def test_preserves_existing_prof_suffix(self, mock_parse):
        """Task name with -prof suffix is unchanged."""
        mock_parse.return_value = {'task': 'mytask-prof'}

        result = determine_task_name_for_profiling('/path/to/mytask.md')
        assert result == 'mytask-prof'

    @patch('src.gui.utils.profile.execution.parse_markdown_runtime_options')
    def test_uses_stem_if_no_task_in_options(self, mock_parse):
        """Falls back to filename stem if task not in options."""
        mock_parse.return_value = {}

        result = determine_task_name_for_profiling('/path/to/mytask.md')
        assert result == 'mytask-prof'


class TestBuildOrchestratorOptions:
    """Test options building for orchestrator."""

    @patch('src.gui.utils.profile.execution.load_backend_configs')
    @patch('src.gui.utils.profile.execution.parse_markdown_runtime_options')
    @patch('src.gui.utils.profile.execution.extract_runtime_options_from_markdown')
    def test_prepends_backends_to_original(
        self,
        mock_extract,
        mock_parse,
        mock_load_backends
    ):
        """Profiling backends are prepended to original backends."""
        mock_extract.return_value = {
            'backend_names': ['local'],
            'task': 'original'
        }

        result = build_orchestrator_options(
            '/path/to/task.md',
            ['perf', 'bintime'],
            'task-prof'
        )

        assert result['backend_names'] == ['perf', 'bintime', 'local']
        assert result['backends'] == ['perf', 'bintime', 'local']
        assert result['task'] == 'task-prof'

    @patch('src.gui.utils.profile.execution.load_backend_configs')
    @patch('src.gui.utils.profile.execution.parse_markdown_runtime_options')
    @patch('src.gui.utils.profile.execution.extract_runtime_options_from_markdown')
    def test_derives_backends_from_backend_options(
        self,
        mock_extract,
        mock_parse,
        mock_load_backends
    ):
        """Can derive backend list from backend_options keys."""
        mock_extract.return_value = {
            'backend_options': {
                'local': {},
                'ssh': {}
            },
            'task': 'original'
        }

        result = build_orchestrator_options(
            '/path/to/task.md',
            ['perf'],
            'task-prof'
        )

        # Should extract keys from backend_options
        assert 'perf' in result['backend_names']

    @patch('src.gui.utils.profile.execution.load_backend_configs')
    @patch('src.gui.utils.profile.execution.parse_markdown_runtime_options')
    @patch('src.gui.utils.profile.execution.extract_runtime_options_from_markdown')
    def test_calls_load_backend_configs(
        self,
        mock_extract,
        mock_parse,
        mock_load_backends
    ):
        """Calls load_backend_configs to merge metrics."""
        mock_extract.return_value = {
            'backend_names': ['local'],
            'task': 'original'
        }

        result = build_orchestrator_options(
            '/path/to/task.md',
            ['perf'],
            'task-prof'
        )

        # Should call load_backend_configs with list of Paths and options dict
        mock_load_backends.assert_called_once()
        args = mock_load_backends.call_args[0]
        # First arg is list of config file paths (mitigations.yaml + backend paths)
        assert isinstance(args[0], list)
        assert any('mitigations.yaml' in str(p) for p in args[0])
        assert any('perf.yaml' in str(p) for p in args[0])

    @patch('src.gui.utils.profile.execution.parse_markdown_runtime_options')
    @patch('src.gui.utils.profile.execution.extract_runtime_options_from_markdown')
    def test_raises_if_no_runtime_options(self, mock_extract, mock_parse):
        """Raises ValueError if runtime options cannot be extracted."""
        mock_extract.return_value = None
        mock_parse.return_value = None

        with pytest.raises(ValueError, match="Could not extract runtime options"):
            build_orchestrator_options('/path/to/task.md', ['perf'], 'task-prof')


class TestProfilingExecutor:
    """Test profiling executor class."""

    @patch('src.gui.utils.profile.execution.extract_repeater_max_from_md')
    def test_initialization(self, mock_extract_iterations):
        """Executor initializes with correct attributes."""
        mock_extract_iterations.return_value = 50

        executor = ProfilingExecutor(
            '/path/to/exp1/task.md',
            ['perf', 'bintime'],
            'task-prof'
        )

        assert executor.md_path == '/path/to/exp1/task.md'
        assert executor.backends == ['perf', 'bintime']
        assert executor.task_name == 'task-prof'
        assert executor.experiment_name == 'exp1'
        assert executor.total_iterations == 50

    def test_set_callbacks(self):
        """Callbacks can be set."""
        executor = ProfilingExecutor('/path/to/task.md', ['perf'], 'task-prof')

        on_progress = Mock()
        on_complete = Mock()
        on_error = Mock()

        executor.set_callbacks(
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error
        )

        assert executor.on_progress == on_progress
        assert executor.on_complete == on_complete
        assert executor.on_error == on_error

    @patch('src.gui.utils.profile.execution.ExecutionOrchestrator')
    @patch('src.gui.utils.profile.execution.build_orchestrator_options')
    def test_execute_success(self, mock_build_options, mock_orchestrator_class):
        """Execute completes successfully."""
        # Setup mocks
        mock_build_options.return_value = {'some': 'options'}
        mock_result = Mock()
        mock_result.success = True
        mock_result.error_message = None
        mock_result.output_paths = {'csv': '/path/to/output.csv'}
        mock_orchestrator = Mock()
        mock_orchestrator.run.return_value = mock_result
        mock_orchestrator_class.return_value = mock_orchestrator

        # Setup executor with callbacks
        executor = ProfilingExecutor('/path/to/task.md', ['perf'], 'task-prof')
        on_complete = Mock()
        executor.set_callbacks(on_complete=on_complete)

        # Execute
        executor.execute()

        # Verify complete callback was called with success
        on_complete.assert_called_once()
        args = on_complete.call_args[0]
        assert args[0] is True  # success
        assert 'output_paths' in args[1]  # result_dict

    @patch('src.gui.utils.profile.execution.build_orchestrator_options')
    def test_execute_error(self, mock_build_options):
        """Execute handles errors."""
        # Setup mock to raise exception
        mock_build_options.side_effect = ValueError("Test error")

        # Setup executor with error callback
        executor = ProfilingExecutor('/path/to/task.md', ['perf'], 'task-prof')
        on_error = Mock()
        executor.set_callbacks(on_error=on_error)

        # Execute
        executor.execute()

        # Verify error callback was called
        on_error.assert_called_once()
        error = on_error.call_args[0][0]
        assert isinstance(error, ValueError)


class TestLoadProfilingData:
    """Test profiling data loading."""

    @patch('src.gui.utils.profile.execution.load_csv')
    def test_successful_load(self, mock_load_csv):
        """Successfully loads CSV data."""
        mock_data = Mock()
        mock_load_csv.return_value = mock_data

        data, error = load_profiling_data('/path/to/prof.csv')

        assert data == mock_data
        assert error is None

    @patch('src.gui.utils.profile.execution.load_csv')
    def test_load_error(self, mock_load_csv):
        """Handles load errors gracefully."""
        mock_load_csv.side_effect = FileNotFoundError("File not found")

        data, error = load_profiling_data('/path/to/missing.csv')

        assert data is None
        assert "Error loading profiling results" in error
        assert "File not found" in error


class TestMitigationConfigLoading:
    """Tests for mitigation backend configuration loading.

    Regression tests for bug where mitigations (e.g., huge_pages) wouldn't
    actually run because mitigations.yaml wasn't being loaded.
    """

    def test_mitigations_yaml_exists(self):
        """Mitigations YAML file exists at expected location."""
        from src.gui.utils.profile.execution import MITIGATIONS_YAML
        assert MITIGATIONS_YAML.exists(), f"mitigations.yaml not found at {MITIGATIONS_YAML}"

    def test_mitigations_yaml_contains_backend_options(self):
        """Mitigations YAML contains backend_options section with mitigation definitions."""
        from src.gui.utils.profile.execution import MITIGATIONS_YAML
        import yaml

        with open(MITIGATIONS_YAML) as f:
            config = yaml.safe_load(f)

        assert "backend_options" in config, "mitigations.yaml missing backend_options section"
        backend_options = config["backend_options"]

        # Verify some known mitigations exist
        assert "huge_pages" in backend_options, "huge_pages missing from backend_options"
        assert "run" in backend_options["huge_pages"], "huge_pages missing 'run' command"

    @patch('src.gui.utils.profile.execution.load_backend_configs')
    @patch('src.gui.utils.profile.execution.parse_markdown_runtime_options')
    @patch('src.gui.utils.profile.execution.extract_runtime_options_from_markdown')
    def test_build_options_includes_mitigations_yaml(
        self,
        mock_extract,
        mock_parse,
        mock_load_backends
    ):
        """build_orchestrator_options includes mitigations.yaml in config files.

        Regression test: Previously only backends/*.yaml were loaded, so
        mitigations defined in mitigations.yaml (like huge_pages) had no
        'run' command and wouldn't execute.
        """
        from src.gui.utils.profile.execution import MITIGATIONS_YAML

        mock_extract.return_value = {
            'backend_names': ['local'],
            'task': 'original'
        }

        # Call with a mitigation backend name
        build_orchestrator_options('/path/to/task.md', ['huge_pages'], 'task-huge_pages')

        # Verify mitigations.yaml is in the config files passed to load_backend_configs
        mock_load_backends.assert_called_once()
        config_files = mock_load_backends.call_args[0][0]
        assert MITIGATIONS_YAML in config_files, \
            f"mitigations.yaml not in config_files: {config_files}"

    def test_mitigation_backend_loaded_from_mitigations_yaml(self):
        """Mitigation backends are properly loaded from mitigations.yaml.

        Integration test: Verify that when loading a mitigation backend,
        its 'run' command is actually available from mitigations.yaml.
        """
        from src.gui.utils.profile.execution import MITIGATIONS_YAML
        from src.core.config.backend_loader import load_backend_configs

        config: Dict[str, Any] = {}
        load_backend_configs([MITIGATIONS_YAML], config)

        assert "backend_options" in config
        assert "huge_pages" in config["backend_options"]
        assert "run" in config["backend_options"]["huge_pages"], \
            "huge_pages 'run' command not loaded from mitigations.yaml"
