"""
Unit tests for workflow execution module.

Tests the minimal sequential workflow support (Phase 4).

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import yaml

from src.cli import workflow
from src.core.config.schema import WorkflowConfig


class TestLoadWorkflow:
    """Test workflow loading and validation."""

    def test_load_valid_workflow_with_includes(self, tmp_path):
        """Load valid workflow YAML file with file includes."""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
description: Test workflow
workflow:
  - include: task1.yaml
  - include: task2.yaml
  - include: task3.yaml
""")

        config = workflow.load_workflow(str(workflow_file))
        assert isinstance(config, WorkflowConfig)
        assert config.version == "1.0.0"
        assert config.description == "Test workflow"
        assert len(config.workflow) == 3
        assert config.workflow[0].include == "task1.yaml"
        assert config.workflow[0].task is None

    def test_load_valid_workflow_with_inline_tasks(self, tmp_path):
        """Load valid workflow YAML file with inline task definitions."""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
description: Test workflow with inline tasks
workflow:
  - task: sleep
    backends: [local]
    options:
      repeater: COUNT
      repeats: 5
  - task: matmul
    backends: [local, perf]
    options:
      repeater: RSE
""")

        config = workflow.load_workflow(str(workflow_file))
        assert isinstance(config, WorkflowConfig)
        assert config.version == "1.0.0"
        assert len(config.workflow) == 2
        assert config.workflow[0].task == "sleep"
        assert config.workflow[0].backends == ["local"]
        assert config.workflow[0].options["repeater"] == "COUNT"
        assert config.workflow[1].task == "matmul"
        assert config.workflow[1].backends == ["local", "perf"]

    def test_load_workflow_from_dict(self):
        """Load workflow from dictionary (no file needed)."""
        workflow_dict = {
            'version': '1.0.0',
            'description': 'Dict workflow',
            'workflow': [
                {'include': 'task1.yaml'},
                {'task': 'sleep', 'backends': ['local'], 'options': {'repeats': 5}}
            ]
        }

        config = workflow.load_workflow_from_dict(workflow_dict)
        assert config.version == '1.0.0'
        assert config.description == 'Dict workflow'
        assert len(config.workflow) == 2
        assert config.workflow[0].include == 'task1.yaml'
        assert config.workflow[1].task == 'sleep'

    def test_load_minimal_workflow(self, tmp_path):
        """Load minimal workflow (no description)."""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
workflow:
  - include: task1.yaml
""")

        config = workflow.load_workflow(str(workflow_file))
        assert config.version == "1.0.0"
        assert config.description is None
        assert len(config.workflow) == 1
        assert config.workflow[0].include == "task1.yaml"

    def test_load_nonexistent_file(self):
        """Error when workflow file doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Workflow file not found"):
            workflow.load_workflow("nonexistent.yaml")

    def test_load_empty_file(self, tmp_path):
        """Error when workflow file is empty."""
        workflow_file = tmp_path / "empty.yaml"
        workflow_file.write_text("")

        with pytest.raises(ValueError, match="Empty workflow configuration"):
            workflow.load_workflow(str(workflow_file))

    def test_load_invalid_schema(self, tmp_path):
        """Error when workflow YAML is invalid."""
        workflow_file = tmp_path / "invalid.yaml"
        workflow_file.write_text("""
version: 1.0.0
# Missing required 'workflow' field
""")

        with pytest.raises(ValueError, match="Invalid workflow configuration"):
            workflow.load_workflow(str(workflow_file))

    def test_load_invalid_workflow_type(self, tmp_path):
        """Error when workflow field is not a list."""
        workflow_file = tmp_path / "invalid.yaml"
        workflow_file.write_text("""
version: 1.0.0
workflow: "not a list"
""")

        with pytest.raises(ValueError, match="Invalid workflow configuration"):
            workflow.load_workflow(str(workflow_file))

    def test_load_workflow_with_experiment_field(self, tmp_path):
        """Load workflow with experiment field for runlogs directory."""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
experiment: my_experiment
workflow:
  - include: task1.yaml
  - include: task2.yaml
""")

        config = workflow.load_workflow(str(workflow_file))
        assert config.experiment == "my_experiment"
        assert len(config.workflow) == 2


class TestRunWorkflow:
    """Test workflow execution."""

    @patch('src.cli.launch.main')
    def test_run_simple_workflow_with_includes(self, mock_launch_main, tmp_path):
        """Run simple 3-task workflow with file includes successfully."""
        # Create workflow file
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
description: Simple test workflow
workflow:
  - include: task1.yaml
  - include: task2.yaml
  - include: task3.yaml
""")

        # Create task files
        for i in [1, 2, 3]:
            task_file = tmp_path / f"task{i}.yaml"
            task_file.write_text(f"""
options:
  experiment: exp{i}
  repeater: COUNT
  repeats: 2
""")

        # Mock launch.main to return success
        mock_launch_main.return_value = 0

        # Run workflow
        result = workflow.run_workflow(str(workflow_file), verbose=False)

        # Verify success
        assert result == 0
        assert mock_launch_main.call_count == 3

    @patch('src.cli.launch.main')
    def test_run_simple_workflow_with_inline_tasks(self, mock_launch_main, tmp_path):
        """Run simple 2-task workflow with inline definitions successfully."""
        # Create workflow file
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
description: Inline task workflow
workflow:
  - task: sleep
    backends: [local]
    options:
      repeater: COUNT
      repeats: 2
  - task: nope
    backends: [local]
    options:
      repeater: COUNT
      repeats: 1
""")

        # Mock launch.main to return success
        mock_launch_main.return_value = 0

        # Run workflow
        result = workflow.run_workflow(str(workflow_file), verbose=False)

        # Verify success
        assert result == 0
        assert mock_launch_main.call_count == 2

        # Verify that inline tasks were passed correctly
        # First call should have 'sleep' as positional arg
        first_call_args = mock_launch_main.call_args_list[0][0][0]
        assert 'sleep' in first_call_args
        assert '-b' in first_call_args
        assert 'local' in first_call_args

    @patch('src.cli.launch.main')
    def test_run_workflow_stops_on_failure(self, mock_launch_main, tmp_path):
        """Workflow stops on first failure."""
        # Create workflow file
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
workflow:
  - include: task1.yaml
  - include: task2.yaml
  - include: task3.yaml
""")

        # Create task files
        for i in [1, 2, 3]:
            task_file = tmp_path / f"task{i}.yaml"
            task_file.write_text(f"""
options:
  experiment: exp{i}
""")

        # Mock launch.main: task1 succeeds, task2 fails
        mock_launch_main.side_effect = [0, 1, 0]

        # Run workflow
        result = workflow.run_workflow(str(workflow_file), verbose=False)

        # Verify failure and early stop
        assert result == 1
        assert mock_launch_main.call_count == 2  # Should stop after task2 fails

    @patch('src.cli.launch.main')
    def test_run_workflow_missing_experiment_file(self, mock_launch_main, tmp_path):
        """Workflow handles missing experiment file gracefully."""
        # Create workflow file
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
workflow:
  - include: task1.yaml
  - include: nonexistent.yaml
  - include: task3.yaml
""")

        # Create only exp1 and exp3
        (tmp_path / "task1.yaml").write_text("options:\n  experiment: exp1\n")
        (tmp_path / "task3.yaml").write_text("options:\n  experiment: exp3\n")

        mock_launch_main.return_value = 0

        # Run workflow
        result = workflow.run_workflow(str(workflow_file), verbose=False)

        # Verify failure (file not found)
        assert result == 1
        # exp1 runs, nonexistent.yaml fails, exp3 not attempted
        assert mock_launch_main.call_count == 1

    @patch('src.cli.launch.main')
    def test_run_workflow_verbose(self, mock_launch_main, tmp_path, capsys):
        """Workflow prints progress in verbose mode."""
        # Create workflow file
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
description: Verbose test workflow
workflow:
  - include: task1.yaml
  - include: task2.yaml
""")

        # Create task files
        for i in [1, 2]:
            task_file = tmp_path / f"task{i}.yaml"
            task_file.write_text(f"options:\n  experiment: exp{i}\n")

        mock_launch_main.return_value = 0

        # Run workflow with verbose
        result = workflow.run_workflow(str(workflow_file), verbose=True)

        # Verify success
        assert result == 0

        # Check output
        captured = capsys.readouterr()
        assert "Executing workflow: Verbose test workflow" in captured.out
        assert "[1/2] Running: task1.yaml" in captured.out
        assert "[2/2] Running: task2.yaml" in captured.out
        assert "✓ Completed: task1.yaml" in captured.out
        assert "✓ Workflow completed successfully: 2 tasks" in captured.out

    @patch('src.cli.launch.main')
    def test_run_workflow_with_absolute_paths(self, mock_launch_main, tmp_path):
        """Workflow handles absolute experiment paths."""
        # Create workflow file
        workflow_file = tmp_path / "workflow.yaml"
        exp1_path = tmp_path / "task1.yaml"
        exp1_path.write_text("options:\n  experiment: exp1\n")

        workflow_file.write_text(f"""
version: 1.0.0
workflow:
  - include: {str(exp1_path)}
""")

        mock_launch_main.return_value = 0

        # Run workflow
        result = workflow.run_workflow(str(workflow_file), verbose=False)

        # Verify success
        assert result == 0
        assert mock_launch_main.call_count == 1

    @patch('src.cli.launch.main')
    def test_run_workflow_with_relative_paths(self, mock_launch_main, tmp_path):
        """Workflow resolves relative experiment paths correctly."""
        # Create subdirectory structure
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        # Create workflow file in root
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
workflow:
  - include: tasks/task1.yaml
  - include: tasks/task2.yaml
""")

        # Create task files in subdirectory
        (tasks_dir / "task1.yaml").write_text("options:\n  experiment: exp1\n")
        (tasks_dir / "task2.yaml").write_text("options:\n  experiment: exp2\n")

        mock_launch_main.return_value = 0

        # Run workflow
        result = workflow.run_workflow(str(workflow_file), verbose=False)

        # Verify success
        assert result == 0
        assert mock_launch_main.call_count == 2

    def test_run_workflow_invalid_file(self):
        """Workflow returns error for invalid workflow file."""
        result = workflow.run_workflow("nonexistent.yaml", verbose=False)
        assert result == 1

    @patch('src.cli.launch.main')
    def test_run_workflow_invalid_experiment_yaml(self, mock_launch_main, tmp_path, capsys):
        """Workflow handles invalid experiment YAML gracefully."""
        # Create workflow file
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
workflow:
  - include: invalid.yaml
""")

        # Create invalid experiment file (truly invalid YAML - tabs and colons without structure)
        (tmp_path / "invalid.yaml").write_text("this: is:\n\t\tinvalid yaml: : :")

        # Run workflow
        result = workflow.run_workflow(str(workflow_file), verbose=False)

        # Verify failure
        assert result == 1
        assert mock_launch_main.call_count == 0  # Should not try to run

        # Check error message
        captured = capsys.readouterr()
        assert "Error loading task" in captured.err


class TestWorkflowMain:
    """Test workflow CLI entry point."""

    @patch('src.cli.workflow.run_workflow')
    def test_main_basic(self, mock_run_workflow, tmp_path):
        """Test basic CLI invocation."""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
workflow:
  - task1.yaml
""")

        mock_run_workflow.return_value = 0

        result = workflow.main([str(workflow_file)])

        assert result == 0
        mock_run_workflow.assert_called_once_with(str(workflow_file), False)

    @patch('src.cli.workflow.run_workflow')
    def test_main_verbose(self, mock_run_workflow, tmp_path):
        """Test CLI with verbose flag."""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
workflow:
  - task1.yaml
""")

        mock_run_workflow.return_value = 0

        result = workflow.main([str(workflow_file), '--verbose'])

        assert result == 0
        mock_run_workflow.assert_called_once_with(str(workflow_file), True)

    @patch('src.cli.workflow.run_workflow')
    def test_main_verbose_short_flag(self, mock_run_workflow, tmp_path):
        """Test CLI with -v flag."""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
version: 1.0.0
workflow:
  - task1.yaml
""")

        mock_run_workflow.return_value = 0

        result = workflow.main([str(workflow_file), '-v'])

        assert result == 0
        mock_run_workflow.assert_called_once_with(str(workflow_file), True)
